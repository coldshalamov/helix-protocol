```python
"""Minimal Helix node implementation built on :mod:`helix.gossip`."""

import hashlib
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

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
import blockchain


class GossipMessageType:
    NEW_EVENT = "NEW_EVENT"
    NEW_STATEMENT = NEW_EVENT
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
        chain_file: str | None = None,
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
        if chain_file is None:
            chain_file = str(Path(balances_file).parent / "blockchain.jsonl")
        self.chain_file = str(chain_file)
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
        self.merkle_trees: Dict[str, list[list[bytes]]] = {}
        self.balances: Dict[str, float] = load_balances(self.balances_file)
        self.registry = statement_registry.StatementRegistry()

        self.load_state()
        self.registry.rebuild_from_events(str(self.events_dir))

        self.chain: list[dict] = blockchain.load_chain(self.chain_file)
        for block in self.chain:
            evt_id = block.get("event_id")
            if not evt_id:
                continue
            event = self.events.get(evt_id)
            if event is None:
                evt_path = self.events_dir / f"{evt_id}.json"
                if not evt_path.exists():
                    continue
                try:
                    event = event_manager.load_event(str(evt_path))
                    self.import_event(event)
                except Exception:
                    continue
            apply_mining_results(event, self.balances)

        # Resolved logic: set chain tip and print restored state
        self.chain_tip = self.chain[-1]["block_id"] if self.chain else GENESIS_HASH
        total = get_total_supply(str(self.events_dir))
        if blockchain.validate_chain(self.chain):
            print(f"Restored tip {self.chain_tip} | Total HLX {total:.4f}")
        else:
            print("Blockchain validation mismatch")

    def _store_merkle_tree(self, event: Dict[str, Any]) -> None:
        evt_id = event["header"]["statement_id"]
        tree = merkle.build_merkle_tree(event["microblocks"])
        self.merkle_trees[evt_id] = tree

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

    def recover_from_chain(self) -> None:
        self.balances = {}
        self.chain = blockchain.load_chain(self.chain_file)
        for block in self.chain:
            evt_id = block.get("event_id") or (block.get("event_ids") or [None])[0]
            if not evt_id:
                continue
            event = self.events.get(evt_id)
            if event is None:
                path = self.events_dir / f"{evt_id}.json"
                if not path.exists():
                    continue
                try:
                    event = event_manager.load_event(str(path))
                    self.import_event(event)
                except Exception:
                    continue
            apply_mining_results(event, self.balances)
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
        self._store_merkle_tree(event)
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
        self._store_merkle_tree(event)

    def submit_event(self, statement: str, *, private_key: str | None = None) -> Dict[str, Any]:
        event = self.create_event(statement, private_key=private_key)
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event
        event_manager.save_event(event, str(self.events_dir))
        self._send({"type": GossipMessageType.NEW_EVENT, "event": event})
        return event

    def submit_seed(
        self,
        event_id: str,
        index: int,
        seed_chain: list[bytes],
        merkle_proof: merkle.MerkleProof,
    ) -> None:
        seed = seed_chain[0]
        message = {
            "type": GossipMessageType.MINED_MICROBLOCK,
            "event_id": event_id,
            "index": index,
            "seed": seed.hex(),
            "merkle_proof": {
                "siblings": [s.hex() for s in merkle_proof.siblings],
                "index": merkle_proof.index,
            },
        }
        if self.public_key and self.private_key:
            payload = f"{event_id}:{index}:{seed.hex()}".encode("utf-8")
            message["signature"] = signature_utils.sign_data(payload, self.private_key)
            message["pubkey"] = self.public_key
        self._send(message)

    def mine_event(self, event: Dict[str, Any]) -> None:
        evt_id = event["header"]["statement_id"]
        for idx, block in enumerate(event["microblocks"]):
            if event["mined_status"][idx]:
                continue
            simulate_mining(idx)
            seed = find_seed(block)
            seed_chain: Optional[list[bytes]] = None
            if seed and verify_seed(seed, block):
                seed_chain = [seed]
            else:
                result = nested_miner.find_nested_seed(block, max_depth=self.max_nested_depth)
                if result:
                    if isinstance(result, tuple):
                        encoded, _ = result
                    else:
                        encoded = bytes(result)
                    chain = nested_miner._decode_chain(encoded, len(block))
                    if nested_miner.verify_nested_seed(chain, block):
                        seed_chain = chain
            if seed_chain is None:
                continue

            depth = len(seed_chain)
            header_byte = (depth << 4) | len(seed_chain[0])
            encoded = bytes([header_byte]) + b"".join(seed_chain)

            event_manager.accept_mined_seed(event, idx, encoded, miner=self.node_id)

            proof = merkle.build_merkle_proof(event["microblocks"], idx)
            self.submit_seed(evt_id, idx, seed_chain, proof)

        if all(event["mined_status"]) and not event.get("finalized"):
            event_manager.finalize_event(event, node_id=self.node_id, chain_file=self.chain_file)
            self.finalize_event(event, append_chain=False)

        event_manager.save_event(event, str(self.events_dir))

    def finalize_event(self, event: Dict[str, Any], *, append_chain: bool = False) -> None:
        if not event.get("is_closed") or event.get("finalized"):
            return
        for bet in event.get("bets", {}).get("YES", []):
            pub = bet.get("pubkey")
            amt = float(bet.get("amount", 0))
            if pub:
                self.balances[pub] = self.balances.get(pub, 0.0) + amt
        apply_mining_results(event, self.balances)
        rewards = event.get("rewards", [])
        refunds = event.get("refunds", [])
        update_total_supply(sum(rewards) + sum(refunds))
        save_balances(self.balances, self.balances_file)
        event_manager.save_event(event, str(self.events_dir))
        if append_chain:
            block = {
                "parent_id": blockchain.get_chain_tip(self.chain_file),
                "event_id": event["header"]["statement_id"],
                "timestamp": time.time(),
                "miner": self.node_id,
            }
            blockchain.append_block(block, self.chain_file)
            self.chain.append(block)
        event["finalized"] = True
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
            merkle_info = message.get("merkle_proof")
            pub = message.get("pubkey")
            sig = message.get("signature")

            if evt_id not in self.events:
                return
            event = self.events[evt_id]
            if idx is None or idx >= len(event["microblocks"]):
                return
            seed = bytes.fromhex(seed_hex)
            if pub and sig:
                payload = f"{evt_id}:{idx}:{seed.hex()}".encode("utf-8")
                if not signature_utils.verify_signature(payload, sig, pub):
                    return
            block = event["microblocks"][idx]
            N = len(block)
            chain = [seed]
            current = seed
            found = False
            for _ in range(1, self.max_nested_depth + 1):
                current = minihelix.G(current, N)
                if current == block:
                    found = True
                    break
                chain.append(current)
            if not found:
                return

            depth = len(chain)
            header_byte = (depth << 4) | len(chain[0])
            encoded = bytes([header_byte]) + b"".join(chain)

            if not merkle_info:
                return
            siblings = [bytes.fromhex(s) for s in merkle_info.get("siblings", [])]
            index = merkle_info.get("index")
            proof = merkle.MerkleProof(siblings=siblings, index=index)

            root = merkle.merkle_root(self.merkle_trees.get(evt_id) or merkle.build_merkle_tree(event["microblocks"]))
            if not merkle.verify_merkle_proof(block, proof.siblings, root, proof.index):
                return

            try:
                event_manager.accept_mined_seed(event, idx, encoded)
            except Exception:
                return
            if event.get("is_closed"):
                self.finalize_event(event, append_chain=True)
        elif msg_type == GossipMessageType.FINALIZED:
            evt_id = message.get("event_id")
            if evt_id in self.events:
                self.events[evt_id]["is_closed"] = True
                self.finalize_event(self.events[evt_id], append_chain=True)

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
    "recover_from_chain",
]

if __name__ == "__main__":  # pragma: no cover - CLI runtime
    import argparse

    parser = argparse.ArgumentParser(prog="helix-node")
    parser.add_argument("--events-dir", default="data/events", help="Event storage directory")
    parser.add_argument("--balances-file", default="data/balances.json", help="Wallet balances file")
    parser.add_argument("--chain-file", help="Blockchain JSONL file")
    parser.add_argument("--recover", action="store_true", help="Rebuild state from chain before starting")
    args = parser.parse_args()

    node = HelixNode(
        events_dir=args.events_dir,
        balances_file=args.balances_file,
        chain_file=args.chain_file,
    )
    if args.recover:
        node.recover_from_chain()
    node.run()
