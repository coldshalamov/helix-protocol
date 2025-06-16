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
]  # HelixNode and recover_from_chain will be defined in separate file to resolve conflicts cleanly


class HelixNode:
    def __init__(self, node_id: str, data_dir: Path, gossip_network: Optional[Any] = None):
        self.node_id = node_id
        self.data_dir = data_dir
        self.gossip = gossip_network or LocalGossipNetwork()
        self.gossip.register(self)
        self.wallet = load_balances(data_dir)
        self.total_supply = get_total_supply(data_dir)
        self.registry = statement_registry.load_registry(data_dir)
        self.mempool = queue.Queue()
        self.running = False

    def start(self):
        self.running = True
        print(f"[HelixNode] Node {self.node_id} started. Listening for gossip...")

    def stop(self):
        self.running = False
        print(f"[HelixNode] Node {self.node_id} stopped.")

    def receive_message(self, message: Dict[str, Any]):
        print(f"[HelixNode] Received message: {message.get('type', 'UNKNOWN')}")

