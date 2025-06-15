"""Minimal Helix node implementation built on :mod:`helix.gossip`."""

import hashlib
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import event_manager, minihelix, nested_miner, signature_utils
from .config import GENESIS_HASH
from .ledger import load_balances, save_balances, apply_mining_results
from .gossip import GossipNode, LocalGossipNetwork
from .network import SocketGossipNetwork


class GossipMessageType:
    NEW_EVENT = "NEW_EVENT"
    NEW_STATEMENT = NEW_EVENT  # backward compatibility
    MINED_MICROBLOCK = "MINED_MICROBLOCK"
    FINALIZED = "FINALIZED"


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


class HelixNode(GossipNode):
    def __init__(
        self,
        *,
        events_dir: str,
        balances_file: str,
        node_id: str = "NODE",
        network: LocalGossipNetwork | SocketGossipNetwork | None = None,
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        genesis_file: str | None = None,
        max_nested_depth: int = 4,
        public_key: str | None = None,
        private_key: str | None = None,
    ) -> None:
        if network is None:
            network = LocalGossipNetwork()
        super().__init__(node_id, network)

        self.events_dir = Path(events_dir)
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.balances_file = str(balances_file)
        self.microblock_size = microblock_size
        self.max_nested_depth = max_nested_depth
        self.public_key = public_key
        self.private_key = private_key

        if genesis_file is None:
            genesis_file = Path(__file__).resolve().parent / "genesis.json"
        data = Path(genesis_file).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != GENESIS_HASH:
            raise ValueError("Genesis file hash mismatch")
        self.genesis = json.loads(data.decode("utf-8"))

        self.events: Dict[str, Dict[str, Any]] = {}
        self.balances: Dict[str, float] = load_balances(self.balances_file)

        self.load_state()

    def load_state(self) -> None:
        for path in self.events_dir.glob("*.json"):
            try:
                event = event_manager.load_event(str(path))
                self.import_event(event)
            except Exception:
                continue

    def save_state(self) -> None:
        for event in self.events.values():
            event_manager.save_event(event, str(self.events_dir))
        save_balances(self.balances, self.balances_file)

    def _send(self, message: Dict[str, Any]) -> None:
        self.send_message(message)

    def create_event(self, statement: str, *, private_key: str | None = None) -> Dict[str, Any]:
        if private_key is None:
            private_key = self.private_key
        event = event_manager.create_event(
            statement,
            microblock_size=self.microblock_size,
            parent_id=GENESIS_HASH,
            private_key=private_key,
        )
        if private_key and event.get("originator_pub"):
            fee = event["header"]["block_count"]
            event["header"]["gas_fee"] = fee
            origin = event["originator_pub"]
            self.balances[origin] = self.balances.get(origin, 0.0) - float(fee)
        return event

    def import_event(self, event: Dict[str, Any]) -> None:
        if not verify_statement_id(event):
            raise ValueError("statement_id mismatch")
        event_manager.validate_parent(event)
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event

    def submit_event(self, statement: str, *, private_key: str | None = None) -> Dict[str, Any]:
        event = self.create_event(statement, private_key=private_key)
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event
        event_manager.save_event(event, str(self.events_dir))
        self._send({"type": GossipMessageType.NEW_EVENT, "event": event})
        return event

    def mine_event(self, event: Dict[str, Any]) -> None:
        evt_id = event["header"]["statement_id"]
        for idx, block in enumerate(event["microblocks"]):
            if event["mined_status"][idx]:
                continue
            simulate_mining(idx)
            seed = find_seed(block)
            chain: Optional[List[bytes]] = None
            if seed and verify_seed(seed, block):
                chain = [seed]
            else:
                result = nested_miner.find_nested_seed(block, max_depth=self.max_nested_depth)
                if result:
                    chain, _ = result
                    if not nested_miner.verify_nested_seed(chain, block):
                        chain = None
            if chain is None:
                continue

            depth = len(chain)
            event_manager.accept_mined_seed(event, idx, chain, miner=self.node_id)

            message = {
                "type": GossipMessageType.MINED_MICROBLOCK,
                "event_id": evt_id,
                "index": idx,
                "seed": chain[0].hex(),
                "depth": depth,
            }
            if self.public_key and self.private_key:
                payload = f"{evt_id}:{idx}:{chain[0].hex()}:{depth}".encode("utf-8")
                message["signature"] = signature_utils.sign_data(payload, self.private_key)
                message["pubkey"] = self.public_key
            self._send(message)

        if event.get("is_closed"):
            self.finalize_event(event)

        event_manager.save_event(event, str(self.events_dir))

    def finalize_event(self, event: Dict[str, Any]) -> None:
        if not event.get("is_closed"):
            return
        for bet in event.get("bets", {}).get("YES", []):
            pub = bet.get("pubkey")
            amt = float(bet.get("amount", 0))
            if pub:
                self.balances[pub] = self.balances.get(pub, 0.0) + amt
        apply_mining_results(event, self.balances)
        save_balances(self.balances, self.balances_file)
        event_manager.save_event(event, str(self.events_dir))
        self._send({"type": GossipMessageType.FINALIZED, "event_id": event["header"]["statement_id"]})

    def _handle_message(self, message: Dict[str, Any]) -> None:
        msg_type = message.get("type")
        if msg_type in {GossipMessageType.NEW_EVENT, GossipMessageType.NEW_STATEMENT}:
            event = message.get("event")
            if event:
                try:
                    self.import_event(event)
                except Exception:
                    pass
        elif msg_type == GossipMessageType.MINED_MICROBLOCK:
            evt_id = message.get("event_id")
            idx = message.get("index")
            seed_hex = message.get("seed")
            depth = int(message.get("depth", 1))
            pub = message.get("pubkey")
            sig = message.get("signature")
            if evt_id not in self.events:
                return
            event = self.events[evt_id]
            if idx is None or idx >= len(event["microblocks"]):
                return
            seed = bytes.fromhex(seed_hex)
            if pub and sig:
                payload = f"{evt_id}:{idx}:{seed.hex()}:{depth}".encode("utf-8")
                if not signature_utils.verify_signature(payload, sig, pub):
                    return
            chain = [seed]
            current = seed
            for _ in range(1, depth):
                current = minihelix.G(current, len(event["microblocks"][idx]))
                chain.append(current)
            try:
                event_manager.accept_mined_seed(event, idx, chain)
            except Exception:
                return
            if event.get("is_closed"):
                self.finalize_event(event)
        elif msg_type == GossipMessageType.FINALIZED:
            evt_id = message.get("event_id")
            if evt_id in self.events:
                self.events[evt_id]["is_closed"] = True
                self.finalize_event(self.events[evt_id])

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=0.1)
            except queue.Empty:
                continue
            self._handle_message(msg)

    def run(self) -> None:
        threading.Thread(target=self._message_loop, daemon=True).start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


__all__ = [
    "LocalGossipNetwork",
    "GossipNode",
    "GossipMessageType",
    "HelixNode",
    "simulate_mining",
    "find_seed",
    "verify_seed",
    "verify_statement_id",
]
