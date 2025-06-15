import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from . import event_manager
from .config import GENESIS_HASH
from .ledger import load_balances, save_balances
from .gossip import GossipNode, LocalGossipNetwork  # ✅ required import

class HelixNode(GossipNode):
    """Minimal Helix node used for testing and simulation."""

    def __init__(
        self,
        *,
        events_dir: str,
        balances_file: str,
        node_id: str = "NODE",
        network: Optional[LocalGossipNetwork] = None,
        microblock_size: int = event_manager.DEFAULT_MICROBLOCK_SIZE,
        genesis_file: str = "genesis.json",
        max_nested_depth: int = 3,
    ) -> None:
        if network is None:
            network = LocalGossipNetwork()
        super().__init__(node_id, network)
        self.events_dir = events_dir
        self.balances_file = balances_file
        self.microblock_size = microblock_size
        self.genesis_file = genesis_file
        self.max_nested_depth = max_nested_depth
        self.genesis = self._load_genesis(genesis_file)
        self.events: Dict[str, Dict[str, Any]] = {}
        self.balances: Dict[str, int] = {}
        self.load_state()

    def _load_genesis(self, path: str) -> dict:
        data = Path(path).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest != GENESIS_HASH:
            raise ValueError("genesis.json does not match GENESIS_HASH")
        return json.loads(data.decode("utf-8"))

    def load_state(self) -> None:
        Path(self.events_dir).mkdir(parents=True, exist_ok=True)
        for fname in os.listdir(self.events_dir):
            if not fname.endswith(".json"):
                continue
            try:
                event = event_manager.load_event(os.path.join(self.events_dir, fname))
            except Exception:
                continue
            if event.get("header", {}).get("parent_id") != GENESIS_HASH:
                continue
            self.events[event["header"]["statement_id"]] = event
        self.balances = load_balances(self.balances_file)

    def save_state(self) -> None:
        for event in self.events.values():
            event_manager.save_event(event, self.events_dir)
        save_balances(self.balances, self.balances_file)

    def submit_event(self, statement: str, *, private_key: Optional[str] = None) -> dict:
        event = event_manager.create_event(
            statement,
            microblock_size=self.microblock_size,
            parent_id=GENESIS_HASH,
            private_key=private_key,
        )
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event
        self.save_state()
        return event
