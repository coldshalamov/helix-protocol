"""Minimal Helix node implementation built on :mod:`helix.gossip`."""

import hashlib
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import base64
from nacl import signing

from . import (
    event_manager,
    minihelix,
    nested_miner,
    signature_utils,
    merkle,
)
from .config import GENESIS_HASH
from .ledger import (
    load_balances,
    save_balances,
    apply_mining_results,
    update_total_supply,
    get_total_supply,
)
from . import statement_registry
from .gossip import GossipNode, LocalGossipNetwork
from .network import SocketGossipNetwork
import blockchain as bc
import helix.blockchain as blockchain


class GossipMessageType:
    NEW_EVENT = "NEW_EVENT"
    NEW_STATEMENT = NEW_EVENT
    MINED_MICROBLOCK = "MINED_MICROBLOCK"
    FINALIZED = "FINALIZED"
    FINALIZED_BLOCK = "FINALIZED_BLOCK"


def simulate_mining(index: int) -> None:
    return None


def find_seed(target: bytes, attempts: int = 1_000_000) -> Optional[bytes]:
    return minihelix.mine_seed(target, max_attempts=attempts)


def verify_seed(seed: bytes, target: bytes) -> bool:
    return minihelix.verify_seed(seed, target)


def verify_statement_id(event: Dict[str, Any]) -> bool:
    statement = event.get("statement")
    stmt_id = event.get("header", {}).get("statement_id")
    if not isinstance(statement, str) or not stmt_id:
        return False
    digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    return digest == stmt_id


def mine_microblocks(event: Dict[str, Any], *, max_depth: int = 4) -> tuple[int, float]:
    """Mine all unmined microblocks for ``event``.

    Parameters
    ----------
    event:
        Event dictionary to update in-place.
    max_depth:
        Maximum nested depth for :func:`nested_miner.hybrid_mine`.

    Returns
    -------
    tuple[int, float]
        ``(mined_count, elapsed_seconds)``
    """
    start = time.perf_counter()
    mined = 0
    for idx, block in enumerate(event.get("microblocks", [])):
        if event.get("seeds", [None])[idx] is not None:
            continue
        result = nested_miner.hybrid_mine(block, max_depth=max_depth)
        if result is None:
            continue
        seed, depth = result
        chain = [seed]
        current = seed
        for _ in range(1, depth):
            current = minihelix.G(current, len(block))
            chain.append(current)
        header = (depth << 4) | len(seed)
        encoded = bytes([header]) + b"".join(chain)
        event_manager.accept_mined_seed(event, idx, encoded)
        mined += 1

    elapsed = time.perf_counter() - start
    return mined, elapsed


def initialize_genesis_block(
    *,
    chain_file: str = "chain.json",
    balances_file: str = "balances.json",
) -> None:
    """Create the genesis block and initial balances if missing.

    This function writes ``balances_file`` and ``chain_file`` when the chain does
    not yet exist. Block ``0`` is created with ``type`` set to ``"GENESIS"`` and
    ``previous_hash`` of 64 zeroes. ``1000`` HLX are minted to the address
    ``"HELIX_FOUNDATION"``.
    """
    chain_path = Path(chain_file)
    if chain_path.exists():
        return

    balances_path = Path(balances_file)
    balances: Dict[str, float] = {}
    if balances_path.exists():
        try:
            with open(balances_path, "r", encoding="utf-8") as fh:
                balances = json.load(fh)
        except Exception:
            balances = {}

    balances["HELIX_FOUNDATION"] = balances.get("HELIX_FOUNDATION", 0.0) + 1000.0

    with open(balances_path, "w", encoding="utf-8") as fh:
        json.dump(balances, fh, indent=2)

    block = {
        "index": 0,
        "type": "GENESIS",
        "previous_hash": "0" * 64,
        "timestamp": time.time(),
    }

    with open(chain_path, "w", encoding="utf-8") as fh:
        json.dump([block], fh, indent=2)


class HelixNode(GossipNode):
    """Simplified Helix node used for the unit tests."""

    def __init__(
        self,
        *,
        events_dir: str,
        balances_file: str,
        chain_file: str = "blockchain.jsonl",
        genesis_file: str | None = None,
        node_id: str = "NODE",
        network: LocalGossipNetwork | None = None,
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        max_nested_depth: int = 4,
        public_key: str | None = None,
        private_key: str | None = None,
    ) -> None:
        super().__init__(node_id, network or LocalGossipNetwork())

        self.events_dir = Path(events_dir)
        self.balances_file = Path(balances_file)
        self.chain_file = Path(chain_file)
        self.genesis_file = Path(genesis_file) if genesis_file else None

        self.microblock_size = microblock_size
        self.max_nested_depth = max_nested_depth
        self.public_key = public_key
        self.private_key = private_key

        self.events: Dict[str, Dict[str, Any]] = {}
        self.balances: Dict[str, float] = load_balances(str(self.balances_file))

        if self.genesis_file and self.genesis_file.exists():
            with open(self.genesis_file, "r", encoding="utf-8") as fh:
                self.genesis = json.load(fh)
        else:
            self.genesis = None

        self.load_state()

    # ------------------------------------------------------------------
    # Persistence helpers

    def load_state(self) -> None:
        self.events_dir.mkdir(parents=True, exist_ok=True)
        for path in self.events_dir.glob("*.json"):
            try:
                event = event_manager.load_event(str(path))
            except Exception:
                continue
            evt_id = event.get("header", {}).get("statement_id")
            if evt_id:
                self.events[evt_id] = event

    def save_state(self) -> None:
        save_balances(self.balances, str(self.balances_file))
        for event in self.events.values():
            event_manager.save_event(event, str(self.events_dir))

    # ------------------------------------------------------------------
    # Event lifecycle helpers

    def create_event(self, statement: str, private_key: str | None = None) -> Dict[str, Any]:
        parent = blockchain.get_chain_tip(str(self.chain_file))
        event = event_manager.create_event(
            statement,
            self.microblock_size,
            parent_id=parent,
            private_key=private_key,
        )
        fee = event["header"].get("block_count", 0)
        event["header"]["gas_fee"] = fee
        if private_key:
            key_bytes = base64.b64decode(private_key)
            pub = base64.b64encode(signing.SigningKey(key_bytes).verify_key.encode()).decode("ascii")
            self.balances[pub] = self.balances.get(pub, 0.0) - float(fee)
        return event

    def import_event(self, event: Dict[str, Any]) -> None:
        event_manager.validate_parent(event)
        if not verify_statement_id(event):
            raise ValueError("invalid statement hash")
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event

    def mine_event(self, event: Dict[str, Any]) -> None:
        before = list(event.get("seeds", []))
        mine_microblocks(event, max_depth=self.max_nested_depth)
        evt_id = event["header"]["statement_id"]
        for idx, seed_chain in enumerate(event.get("seeds", [])):
            if before[idx] is not None or seed_chain is None:
                continue
            seed = seed_chain[0] if isinstance(seed_chain, list) else seed_chain[2 : 2 + seed_chain[1]]
            msg = {
                "type": GossipMessageType.MINED_MICROBLOCK,
                "event_id": evt_id,
                "index": idx,
                "seed": seed.hex(),
            }
            if self.public_key and self.private_key:
                payload = f"{evt_id}:{idx}:{seed.hex()}".encode("utf-8")
                msg["pubkey"] = self.public_key
                msg["signature"] = signature_utils.sign_data(payload, self.private_key)
            self.send_message(msg)

        if event.get("is_closed"):
            self.finalize_event(event)

    def finalize_event(self, event: Dict[str, Any]) -> None:
        payouts = event_manager.finalize_event(
            event,
            node_id=self.node_id,
            chain_file=str(self.chain_file),
        )
        apply_mining_results(event, self.balances)
        for addr, amt in payouts.items():
            self.balances[addr] = self.balances.get(addr, 0.0) + float(amt)
        self.save_state()
        block = blockchain.load_chain(str(self.chain_file))[-1]
        self.send_message({"type": GossipMessageType.FINALIZED_BLOCK, "block": block})

    # ------------------------------------------------------------------
    # Networking helpers

    def _handle_message(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type in {GossipMessageType.NEW_EVENT, GossipMessageType.NEW_STATEMENT}:
            event = message.get("event")
            if isinstance(event, dict):
                try:
                    self.import_event(event)
                    self.save_state()
                except Exception:
                    pass
        elif msg_type == GossipMessageType.MINED_MICROBLOCK:
            evt_id = message.get("event_id")
            idx = message.get("index")
            seed_hex = message.get("seed")
            if evt_id in self.events and isinstance(idx, int) and isinstance(seed_hex, str):
                seed = bytes.fromhex(seed_hex)
                pub = message.get("pubkey")
                sig = message.get("signature")
                if pub and sig:
                    payload = f"{evt_id}:{idx}:{seed_hex}".encode("utf-8")
                    if not signature_utils.verify_signature(payload, sig, pub):
                        return
                event = self.events[evt_id]
                event_manager.accept_mined_seed(event, idx, [seed])
        elif msg_type == GossipMessageType.FINALIZED_BLOCK:
            block = message.get("block")
            if block:
                bc.append_block(block, str(self.chain_file))
                evt_ids = block.get("event_ids") or []
                for eid in evt_ids:
                    if eid in self.events:
                        self.events[eid]["finalized"] = True

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=0.1)
            except queue.Empty:
                continue
            self._handle_message(msg)


def recover_from_chain(*, chain_file: str = "blockchain.jsonl") -> List[Dict[str, Any]]:
    """Return chain data from ``chain_file`` if present."""
    return bc.load_chain(chain_file)


__all__ = [
    "LocalGossipNetwork",
    "GossipNode",
    "GossipMessageType",
    "HelixNode",
    "simulate_mining",
    "find_seed",
    "verify_seed",
    "verify_statement_id",
    "mine_microblocks",
    "initialize_genesis_block",
    "recover_from_chain",
]
