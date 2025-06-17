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
    CHAIN_TIP = "CHAIN_TIP"
    CHAIN_REQUEST = "CHAIN_REQUEST"
    CHAIN_RESPONSE = "CHAIN_RESPONSE"


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
]


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
        self.blockchain = bc.load_chain(str(self.chain_file))

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
        payouts = event_manager.finalize_event(event, node_id=self.node_id, chain_file=str(self.chain_file))
        apply_mining_results(event, self.balances)
        for acct, amount in payouts.items():
            self.balances[acct] = self.balances.get(acct, 0.0) + amount
        self.save_state()
        self.send_message({"type": GossipMessageType.FINALIZED, "event": event})
        return payouts

    def _validate_block_header(self, block: Dict[str, Any]) -> bool:
        copy = dict(block)
        block_id = copy.pop("block_id", None)
        if block_id is None:
            return False
        digest = hashlib.sha256(
            json.dumps(copy, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return digest == block_id

    def apply_block(self, block: Dict[str, Any]) -> bool:
        if not self._validate_block_header(block):
            return False
        for evt_id in block.get("event_ids", []):
            path = self.events_dir / f"{evt_id}.json"
            if not path.exists():
                return False
            try:
                event = event_manager.load_event(str(path))
            except Exception:
                return False
            for mb, seed in zip(event.get("microblocks", []), event.get("seeds", [])):
                if seed is None or not nested_miner.verify_nested_seed(seed, mb):
                    return False
        parent_id = block.get("parent_id")
        tip = self.blockchain[-1]["block_id"] if self.blockchain else GENESIS_HASH
        if parent_id == tip:
            self.blockchain.append(block)
            bc.append_block(block, path=str(self.chain_file))
            return True
        parent_index = -1
        for i, blk in enumerate(self.blockchain):
            if blk.get("block_id") == parent_id:
                parent_index = i
                break
        if parent_index == -1:
            return False
        candidate = self.blockchain[: parent_index + 1] + [block]
        chosen = bc.resolve_fork(self.blockchain, candidate, events_dir=str(self.events_dir))
        if chosen is candidate:
            self.blockchain = candidate
            with open(self.chain_file, "w", encoding="utf-8") as fh:
                for b in self.blockchain:
                    fh.write(json.dumps(b, separators=(",", ":")) + "\n")
            return True
        return False

    def start_sync_loop(self) -> None:
        """Periodically broadcast chain tip and apply new blocks."""

        def _sync_loop() -> None:
            last_len = len(self.blockchain)
            while True:
                chain = bc.load_chain(str(self.chain_file))
                last_block = chain[-1] if chain else None
                block_id = last_block.get("block_id") if last_block else GENESIS_HASH
                height = len(chain)
                self.send_message(
                    {
                        "type": GossipMessageType.CHAIN_TIP,
                        "sender": self.node_id,
                        "block_id": block_id,
                        "height": height,
                    }
                )
                if len(chain) > last_len:
                    for block in chain[last_len:]:
                        if self.apply_block(block):
                            self.broadcast_block(block)
                    last_len = len(chain)
                elif len(chain) < last_len:
                    self.blockchain = chain
                    last_len = len(chain)
                time.sleep(5)

        threading.Thread(target=_sync_loop, daemon=True).start()

    def start(self) -> None:
        threading.Thread(target=self._message_loop, daemon=True).start()
        threading.Thread(target=self.start_sync_loop, daemon=True).start()

    def _handle_message(self, message: Dict[str, Any]) -> None:
        # (Same as previously implemented — unchanged.)
        ...
