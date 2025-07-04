"""Minimal Helix node implementation built on :mod:`helix.gossip`."""

import hashlib
import json
import queue
import threading
import time
import base64
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
from nacl import signing

from . import (
    event_manager,
    minihelix,
    nested_miner,
    signature_utils,
)
from .config import GENESIS_HASH
from .ledger import (
    load_balances,
    save_balances,
    apply_mining_results,
    get_total_supply,
    apply_delta_bonus,
    apply_delta_penalty,
    delta_claim_valid,
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
    FINALIZED_BLOCK_HEADER = "finalized_block"
    CHAIN_TIP = "CHAIN_TIP"
    CHAIN_REQUEST = "CHAIN_REQUEST"
    CHAIN_RESPONSE = "CHAIN_RESPONSE"


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
    "recover_from_chain",
]


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


def recover_from_chain(
    chain: List[Dict[str, Any]], events_dir: str
) -> tuple[Dict[str, Dict[str, Any]], Dict[str, float]]:
    events: Dict[str, Dict[str, Any]] = {}
    balances: Dict[str, float] = {}
    path = Path(events_dir)
    for block in chain:
        ids = block.get("event_ids") or []
        if isinstance(ids, str):
            ids = [ids]
        for evt_id in ids:
            evt_file = path / f"{evt_id}.json"
            if not evt_file.exists():
                continue
            try:
                event = event_manager.load_event(str(evt_file))
            except Exception:
                continue
            events[evt_id] = event
            apply_mining_results(event, balances)
            for acct, amt in event.get("payouts", {}).items():
                balances[acct] = balances.get(acct, 0.0) + amt
    return events, balances


def _write_chain(chain: List[Dict[str, Any]], path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for block in chain:
            blk = dict(block)
            blk.pop("height", None)
            fh.write(json.dumps(blk) + "\n")


def resolve_fork(
    old_chain: List[Dict[str, Any]], new_chain: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Return the preferred chain between ``old_chain`` and ``new_chain``.

    The preferred chain is determined as follows:

    - Choose ``new_chain`` if it contains more blocks than ``old_chain``.
    - If both have the same number of blocks, pick the one whose last
      ``block_id`` is lexicographically greater.

    Parameters
    ----------
    old_chain:
        The current local chain.
    new_chain:
        Chain received from a peer.

    Returns
    -------
    List[Dict[str, Any]]
        The chain to adopt. No chain re-organization happens here, the caller
        is responsible for adopting the returned chain if desired.
    """

    if len(new_chain) > len(old_chain):
        return new_chain

    if len(new_chain) == len(old_chain) and new_chain and old_chain:
        new_last = new_chain[-1].get("block_id", "")
        old_last = old_chain[-1].get("block_id", "")
        if str(new_last) > str(old_last):
            return new_chain

    return old_chain


class HelixNode(GossipNode):
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
        self.fork_chain: List[Dict[str, Any]] | None = None

        # Delta bonus tracking
        self._pending_bonus: Dict[str, str] = {}
        self._verification_queue: List[tuple[Dict[str, Any], bool, str]] = []
        self._bonus_amount = 1.0

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

    def create_event(
        self,
        statement: str,
        *,
        parent_id: str = GENESIS_HASH,
        private_key: str | None = None,
    ) -> Dict[str, Any]:
        """Create a new statement event using :func:`event_manager.create_event`."""

        priv = self.private_key if private_key is None else private_key
        event = event_manager.create_event(
            statement,
            microblock_size=self.microblock_size,
            parent_id=parent_id,
            private_key=priv,
        )
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event
        return event

    def mine_event(self, event: Dict[str, Any]) -> None:
        """Mine microblocks for ``event`` using :func:`find_seed`."""

        for idx, block in enumerate(event.get("microblocks", [])):
            if event.get("seeds", [None])[idx] is not None:
                continue
            seed = find_seed(block)
            if seed is None:
                continue
            event_manager.accept_mined_seed(event, idx, [seed], miner=self.node_id)

    def import_event(self, event: Dict[str, Any]) -> None:
        """Validate and store ``event`` in the node state."""

        event_manager.validate_parent(event)
        if not verify_statement_id(event):
            raise ValueError("invalid statement_id")
        evt_id = event["header"]["statement_id"]
        self.events[evt_id] = event
        self.save_state()

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

    def get_balance(self, wallet_id: str) -> float:
        """Return the current HLX balance for ``wallet_id``."""

        return float(self.balances.get(wallet_id, 0.0))

    def _track_fork(self, block: Dict[str, Any]) -> None:
        if self.fork_chain is None:
            parent_id = block.get("parent_id")
            idx = next(
                (
                    i
                    for i, b in enumerate(self.blockchain)
                    if b["block_id"] == parent_id
                ),
                None,
            )
            if idx is None:
                return
            self.fork_chain = self.blockchain[: idx + 1]
        if self.fork_chain[-1]["block_id"] == block.get("parent_id"):
            self.fork_chain.append(block)

    def _resolve_forks(self) -> None:
        if not self.fork_chain:
            return
        chosen = resolve_fork(self.blockchain, self.fork_chain)
        if chosen is self.fork_chain:
            self._adopt_chain(chosen)
        self.fork_chain = None

    def _adopt_chain(self, chain: List[Dict[str, Any]]) -> None:
        self.blockchain = chain
        _write_chain(chain, str(self.chain_file))
        self.events, self.balances = recover_from_chain(chain, str(self.events_dir))
        self.save_state()

    def finalize_event(self, event: Dict[str, Any]) -> Dict[str, float]:
        before = bc.load_chain(str(self.chain_file))

        # Enforce pending delta bonus decision if available
        if self._verification_queue:
            prev_block, granted, block_id = self._verification_queue.pop(0)
            miner = self._pending_bonus.pop(block_id, None)
            if miner:
                apply_delta_bonus(
                    miner,
                    self.balances,
                    self._bonus_amount,
                    block_hash=block_id,
                )

                if granted and prev_block:
                    parent_id = prev_block.get("parent_id")
                    parent = next(
                        (b for b in self.blockchain if b.get("block_id") == parent_id),
                        None,
                    )
                    if parent and not delta_claim_valid(prev_block, parent):
                        apply_delta_penalty(
                            miner,
                            self.balances,
                            self._bonus_amount,
                            block_hash=block_id,
                        )

        prev_block = self.blockchain[-1] if self.blockchain else None
        bonus_for_prev = bool(prev_block)
        if prev_block and bonus_for_prev:
            miner_prev = prev_block.get("finalizer") or prev_block.get("miner")
            if miner_prev:
                apply_delta_bonus(
                    miner_prev,
                    self.balances,
                    self._bonus_amount,
                    block_hash=prev_block.get("block_id"),
                )

        payouts = event_manager.finalize_event(
            event,
            node_id=self.node_id,
            chain_file=str(self.chain_file),
            events_dir=str(self.events_dir),
            balances_file=str(self.balances_file),
            delta_bonus=bonus_for_prev,
        )
        chain_after = bc.load_chain(str(self.chain_file))
        if len(chain_after) > len(before):
            block_header = chain_after[-1]
            self.blockchain = chain_after
            evt_id = event["header"]["statement_id"]
            self.send_message(
                {
                    "type": GossipMessageType.FINALIZED_BLOCK_HEADER,
                    "event_id": evt_id,
                    "block_header": block_header,
                }
            )
            if prev_block:
                self._verification_queue.append(
                    (prev_block, bonus_for_prev, block_header["block_id"])
                )
            self._pending_bonus[block_header["block_id"]] = self.node_id
        self.balances = load_balances(str(self.balances_file))
        self.save_state()
        self.send_message({"type": GossipMessageType.FINALIZED, "event": event})
        return payouts

    def start_event_auto_finalizer(self) -> None:
        """Launch a background thread that finalizes and resolves events."""

        def _auto_loop() -> None:
            while True:
                print("Auto-finalizer: checking events")
                for evt_id, event in list(self.events.items()):
                    if not event.get("is_closed"):
                        continue
                    if event.get("payouts"):
                        continue
                    print(f"Auto-finalizer: event {evt_id} completed")
                    try:
                        self.finalize_event(event)
                        print(f"Auto-finalizer: finalized {evt_id}")
                    except Exception as exc:  # pragma: no cover - logging only
                        print(f"Auto-finalizer: failed to finalize {evt_id}: {exc}")
                        continue
                    try:
                        from . import betting_interface

                        print(f"Auto-finalizer: resolving bets for {evt_id}")
                        betting_interface.resolve_bets(evt_id)
                    except Exception as exc:  # pragma: no cover - logging only
                        print(
                            f"Auto-finalizer: bet resolution failed for {evt_id}: {exc}"
                        )
                time.sleep(2.0)

        threading.Thread(target=_auto_loop, daemon=True).start()

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

                mined_status = event.get("mined_status")
                if (
                    event.get("is_closed")
                    and mined_status
                    and all(mined_status)
                    and not event.get("payouts")
                ):
                    node_id = self.public_key or self.node_id
                    payouts = event_manager.finalize_event(event, node_id=node_id)
                    event_manager.save_event(event, str(self.events_dir))
                    print("[\u2713] Event finalized!")
                    print(f"    ID: {evt_id}")
                    reward = event.get("miner_reward", 0.0)
                    print(f"    Total HLX reward: {reward}")
                    print(f"    Finalizer: {node_id}")
                elif event.get("is_closed") and event_manager.verify_statement(event):
                    self.finalize_event(event)
        elif mtype == GossipMessageType.FINALIZED:
            event = message.get("event")
            if event:
                evt_id = event["header"]["statement_id"]
                self.events[evt_id] = event
                apply_mining_results(event, self.balances)
                for acct, amt in event.get("payouts", {}).items():
                    self.balances[acct] = self.balances.get(acct, 0.0) + amt
                self.save_state()
                self.forward_message(message)
        elif mtype == GossipMessageType.FINALIZED_BLOCK:
            block = message.get("block")
            if block and self.apply_block(block):
                self.forward_message(message)
        elif mtype == GossipMessageType.FINALIZED_BLOCK_HEADER:
            evt_id = message.get("event_id")
            block = message.get("block_header")
            if not evt_id or not isinstance(block, dict):
                return
            if evt_id not in self.events:
                # unknown event; propagate request if fetch mechanism exists
                self.forward_message(message)
                return
            if self.apply_block(block):
                self.forward_message(message)

    def _message_loop(self) -> None:
        while True:
            try:
                msg = self.receive(timeout=0.05)
            except queue.Empty:
                continue
            self._handle_message(msg)
