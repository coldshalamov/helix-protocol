"""Minimal Helix node implementation built on :mod:`helix.gossip`."""

import hashlib
import json
import queue
import threading
import time
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    """Lightweight node combining event handling and gossip."""

    def __init__(
        self,
        *,
        events_dir: str,
        balances_file: str,
        network: LocalGossipNetwork,
        node_id: str = "NODE",
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        chain_file: str = "blockchain.jsonl",
        genesis_file: str | None = None,
        max_nested_depth: int = 4,
        public_key: str | None = None,
        private_key: str | None = None,
    ) -> None:
        super().__init__(node_id, network)
        self.events_dir = events_dir
        self.balances_file = balances_file
        self.chain_file = chain_file
        self.microblock_size = microblock_size
        self.max_nested_depth = max_nested_depth
        self.public_key = public_key
        self.private_key = private_key
        self.events: Dict[str, Dict[str, Any]] = {}
        self.balances = load_balances(balances_file)

        self.genesis: Dict[str, Any] | None = None
        if genesis_file is not None and Path(genesis_file).exists():
            with open(genesis_file, "r", encoding="utf-8") as fh:
                self.genesis = json.load(fh)

        self._load_events()

    # --------------------------------------------------------------
    # Persistence helpers

    def _event_path(self, event_id: str) -> Path:
        return Path(self.events_dir) / f"{event_id}.json"

    def _load_events(self) -> None:
        path = Path(self.events_dir)
        if not path.exists():
            return
        for file in path.glob("*.json"):
            try:
                event = event_manager.load_event(str(file))
            except Exception:
                continue
            evt_id = event.get("header", {}).get("statement_id")
            if evt_id:
                self.events[evt_id] = event

    def save_state(self) -> None:
        Path(self.events_dir).mkdir(parents=True, exist_ok=True)
        for event in self.events.values():
            event_manager.save_event(event, self.events_dir)
        save_balances(self.balances, self.balances_file)

    # --------------------------------------------------------------
    # Event lifecycle

    def create_event(self, statement: str, private_key: str | None = None) -> Dict[str, Any]:
        event = event_manager.create_event(
            statement,
            microblock_size=self.microblock_size,
            private_key=private_key,
        )
        fee = event["header"].get("block_count", 0)
        event["header"]["gas_fee"] = fee
        if private_key is not None:
            key_bytes = base64.b64decode(private_key)
            pub = base64.b64encode(signing.SigningKey(key_bytes).verify_key.encode()).decode("ascii")
            self.balances[pub] = self.balances.get(pub, 0.0) - fee
        return event

    def import_event(self, event: Dict[str, Any]) -> None:
        event_manager.validate_parent(event)
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event

    def mine_event(self, event: Dict[str, Any]) -> None:
        evt_id = event["header"]["statement_id"]
        for idx, block in enumerate(event.get("microblocks", [])):
            if event["seeds"][idx] is not None:
                continue
            simulate_mining(idx)
            seed = find_seed(block)
            depth = 1
            if seed is None or not verify_seed(seed, block):
                result = nested_miner.hybrid_mine(block, max_depth=self.max_nested_depth)
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
            event_manager.accept_mined_seed(event, idx, encoded, miner=self.public_key)
            self._broadcast_seed(evt_id, idx, seed)
        self.save_state()
        if event.get("is_closed"):
            self.finalize_event(event)

    # --------------------------------------------------------------
    def finalize_event(self, event: Dict[str, Any]) -> None:
        event_manager.finalize_event(event, node_id=self.public_key or self.node_id, chain_file=self.chain_file)
        apply_mining_results(event, self.balances)
        self.save_state()
        self.send_message({"type": GossipMessageType.FINALIZED, "event": event})

    # --------------------------------------------------------------
    # Gossip handling

    def _broadcast_seed(self, evt_id: str, index: int, seed: bytes) -> None:
        msg = {
            "type": GossipMessageType.MINED_MICROBLOCK,
            "event_id": evt_id,
            "index": index,
            "seed": seed.hex(),
        }
        if self.private_key and self.public_key:
            payload = f"{evt_id}:{index}:{seed.hex()}".encode("utf-8")
            sig = signature_utils.sign_data(payload, self.private_key)
            msg["pubkey"] = self.public_key
            msg["signature"] = sig
        self.send_message(msg)

    def _handle_message(self, message: Dict[str, Any]) -> None:
        mtype = message.get("type")
        if mtype == GossipMessageType.NEW_STATEMENT:
            event = message.get("event")
            if event:
                self.import_event(event)
                self.save_state()
        elif mtype == GossipMessageType.MINED_MICROBLOCK:
            evt_id = message.get("event_id")
            index = message.get("index")
            seed_hex = message.get("seed")
            pub = message.get("pubkey")
            sig = message.get("signature")
            if evt_id in self.events and isinstance(index, int) and seed_hex:
                event = self.events[evt_id]
                block = event["microblocks"][index]
                payload = f"{evt_id}:{index}:{seed_hex}".encode("utf-8")
                if pub and sig and not signature_utils.verify_signature(payload, sig, pub):
                    return
                seed = bytes.fromhex(seed_hex)
                chain = [seed]
                current = seed
                while True:
                    current = minihelix.G(current, len(block))
                    if current == block:
                        break
                    chain.append(current)
                event_manager.accept_mined_seed(event, index, chain, miner=pub)
                if event.get("is_closed"):
                    self.finalize_event(event)
                self.save_state()
        elif mtype == GossipMessageType.FINALIZED:
            event = message.get("event")
            if event:
                evt_id = event["header"]["statement_id"]
                self.events[evt_id] = event
                apply_mining_results(event, self.balances)
                self.save_state()

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=0.1)
            except queue.Empty:
                continue
            self._handle_message(msg)


def recover_from_chain(chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return chain


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
