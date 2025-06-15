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
            chain_file = str(Path(balances_file).parent / "chain.json")
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

    # ... all other methods below remain unchanged ...
```
