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


__all__ = [
    "LocalGossipNetwork",
    "GossipNode",
    "GossipMessageType",
    "simulate_mining",
    "find_seed",
    "verify_seed",
    "verify_statement_id",
    "mine_microblocks",
    "initialize_genesis_block",
    "HelixNode",
]  # HelixNode and recover_from_chain will be defined in separate file to resolve conflicts cleanly


class HelixNode(GossipNode):
    """Minimal networked node used in the tests."""

    def __init__(
        self,
        *,
        events_dir: str,
        balances_file: str,
        chain_file: str | None = None,
        network: Optional[LocalGossipNetwork] = None,
        node_id: str = "NODE",
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        public_key: str | None = None,
        private_key: str | None = None,
        genesis_file: str = "genesis.json",
        max_nested_depth: int = 4,
    ) -> None:
        network = network or LocalGossipNetwork()
        super().__init__(node_id, network)
        self.events_dir = Path(events_dir)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.balances_file = Path(balances_file)
        self.chain_file = Path(chain_file or "blockchain.jsonl")
        self.microblock_size = microblock_size
        self.public_key = public_key
        self.private_key = private_key
        self.max_nested_depth = max_nested_depth

        self.events: Dict[str, Dict[str, Any]] = {}
        self.balances: Dict[str, float] = load_balances(str(self.balances_file))

        gf = Path(genesis_file)
        if gf.exists():
            data = gf.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != GENESIS_HASH:
                raise ValueError("genesis file hash mismatch")
            self.genesis = json.loads(data.decode("utf-8"))
        else:
            self.genesis = None

        self.load_state()

    # ------------------------------------------------------------------
    # Persistence helpers

    def load_state(self) -> None:
        self.events = {}
        if self.events_dir.exists():
            for path in self.events_dir.glob("*.json"):
                try:
                    event = event_manager.load_event(str(path))
                except Exception:
                    continue
                evt_id = event["header"]["statement_id"]
                self.events[evt_id] = event

    def save_state(self) -> None:
        for event in self.events.values():
            event_manager.save_event(event, str(self.events_dir))
        save_balances(self.balances, str(self.balances_file))

    def import_event(self, event: Dict[str, Any]) -> None:
        try:
            event_manager.validate_parent(event)
        except Exception:
            raise
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event

    # ------------------------------------------------------------------
    # Event operations

    def create_event(self, statement: str, private_key: str | None = None) -> Dict[str, Any]:
        priv = private_key or self.private_key
        parent = bc.get_chain_tip(str(self.chain_file))
        event = event_manager.create_event(statement, self.microblock_size, parent_id=parent, private_key=priv)
        fee = event["header"]["block_count"]
        event["header"]["gas_fee"] = fee
        originator = event.get("originator_pub")
        if originator:
            self.balances[originator] = self.balances.get(originator, 0.0) - fee
        return event

    def mine_event(self, event: Dict[str, Any]) -> None:
        evt_id = event["header"]["statement_id"]
        for idx, block in enumerate(event.get("microblocks", [])):
            if event["seeds"][idx] is not None:
                continue
            simulate_mining(idx)
            seed = find_seed(block)
            if seed is None or not verify_seed(seed, block):
                continue
            event_manager.accept_mined_seed(event, idx, [seed], miner=self.node_id)
            if self.private_key and self.public_key:
                payload = f"{evt_id}:{idx}:{seed.hex()}".encode("utf-8")
                sig = signature_utils.sign_data(payload, self.private_key)
                msg = {
                    "type": GossipMessageType.MINED_MICROBLOCK,
                    "event_id": evt_id,
                    "index": idx,
                    "seed": seed.hex(),
                    "pubkey": self.public_key,
                    "signature": sig,
                }
            else:
                msg = {
                    "type": GossipMessageType.MINED_MICROBLOCK,
                    "event_id": evt_id,
                    "index": idx,
                    "seed": seed.hex(),
                }
            self.send_message(msg)
        self.save_state()

    def finalize_event(self, event: Dict[str, Any]) -> Dict[str, float]:
        payouts = event_manager.finalize_event(
            event,
            node_id=self.node_id,
            chain_file=str(self.chain_file),
            balances_file=str(self.balances_file),
        )
        self.balances = load_balances(str(self.balances_file))
        self.save_state()
        self.send_message({"type": GossipMessageType.FINALIZED, "event": event})
        return payouts

    # ------------------------------------------------------------------
    # Gossip handling

    def _handle_message(self, message: Dict[str, Any]) -> None:
        mtype = message.get("type")
        if mtype == GossipMessageType.NEW_STATEMENT:
            event = message.get("event")
            if event and verify_statement_id(event):
                evt_id = event["header"]["statement_id"]
                self.events[evt_id] = event
                self.save_state()
                self.forward_message(message)
        elif mtype == GossipMessageType.MINED_MICROBLOCK:
            evt_id = message.get("event_id")
            idx = message.get("index")
            seed_hex = message.get("seed")
            pub = message.get("pubkey")
            sig = message.get("signature")
            if evt_id in self.events and idx is not None and seed_hex:
                if pub and sig:
                    payload = f"{evt_id}:{idx}:{seed_hex}".encode("utf-8")
                    if not signature_utils.verify_signature(payload, sig, pub):
                        return
                try:
                    seed = bytes.fromhex(seed_hex)
                except ValueError:
                    return
                event = self.events[evt_id]
                event_manager.accept_mined_seed(event, idx, [seed], miner=pub)
                self.save_state()
                self.forward_message(message)
        elif mtype == GossipMessageType.FINALIZED:
            event = message.get("event")
            if event:
                evt_id = event["header"]["statement_id"]
                self.events[evt_id] = event
                update_total_supply(event.get("miner_reward", 0.0))
                apply_mining_results(event, self.balances)
                for acct, amt in event.get("payouts", {}).items():
                    self.balances[acct] = self.balances.get(acct, 0.0) + amt
                self.save_state()
                self.forward_message(message)
        elif mtype == GossipMessageType.FINALIZED_BLOCK:
            block = message.get("block")
            if block and self.apply_block(block):
                self.forward_message(message)

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=0.05)
            except queue.Empty:
                continue
            self._handle_message(msg)

