import json
import os
from typing import Iterable, Set, List, Dict, Any

try:
    import blockchain as _bc
except Exception:  # pragma: no cover - optional blockchain module
    _bc = None

from . import event_manager


class StatementRegistry:
    """Registry of statement hashes to prevent exact duplicates."""

    def __init__(self, hashes: Iterable[str] | None = None) -> None:
        """Create a new registry."""

        self._hashes: Set[str] = set(hashes or [])

    def _hash_statement(self, statement: str) -> str:
        return event_manager.sha256(statement.encode("utf-8"))

    def check_and_add(self, statement: str) -> None:
        """Add ``statement`` if not already present else raise ``ValueError``."""
        h = self._hash_statement(statement)
        if h in self._hashes:
            print(f"Duplicate statement detected: {h}")
            raise ValueError("Duplicate statement")
        self._hashes.add(h)

    def has_id(self, statement_id: str) -> bool:
        """Return ``True`` if ``statement_id`` is known."""
        return statement_id in self._hashes

    def has(self, statement: str) -> bool:
        return self._hash_statement(statement) in self._hashes

    def load(self, path: str) -> None:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
                if isinstance(data, list):
                    self._hashes = set(str(x) for x in data)

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(sorted(self._hashes), fh, indent=2)

    def rebuild_from_events(self, events_dir: str) -> None:
        if not os.path.isdir(events_dir):
            return
        for fname in os.listdir(events_dir):
            if not fname.endswith(".json"):
                continue
            try:
                event = event_manager.load_event(os.path.join(events_dir, fname))
            except Exception:
                continue
            if event.get("is_closed"):
                h = event["header"]["statement_id"]
                self._hashes.add(h)

    def cleanup_events(self, events_dir: str, *, chain_file: str = "blockchain.jsonl") -> List[str]:
        """Delete orphan or invalid events in ``events_dir``.

        Files that cannot be loaded or whose ``statement_id`` is not present in
        the blockchain referenced by ``chain_file`` are removed.  The list of
        deleted file paths is returned.
        """
        removed: List[str] = []

        referenced: Set[str] | None = None
        if _bc is not None and hasattr(_bc, "load_chain") and os.path.exists(chain_file):
            try:
                chain = _bc.load_chain(chain_file)
            except Exception:  # pragma: no cover - corrupt chain
                chain = []
            referenced = set()
            for block in chain:
                ids = (
                    block.get("event_ids")
                    or block.get("events")
                    or block.get("event_id")
                )
                if isinstance(ids, list):
                    for eid in ids:
                        if eid:
                            referenced.add(str(eid))
                elif ids:
                    referenced.add(str(ids))

        if not os.path.isdir(events_dir):
            return removed

        for fname in os.listdir(events_dir):
            if not fname.endswith(".json"):
                continue
            path = os.path.join(events_dir, fname)
            evt_id: str | None = None
            try:
                event = event_manager.load_event(path)
                evt_id = event.get("header", {}).get("statement_id")
            except Exception:
                pass

            if evt_id is None or (referenced is not None and evt_id not in referenced):
                try:
                    os.remove(path)
                    removed.append(path)
                except FileNotFoundError:  # pragma: no cover - race condition
                    pass

        return removed


__all__ = ["StatementRegistry", "finalize_statement"]


def finalize_statement(event: Dict[str, Any], *, delta_bonus: bool = False) -> str:
    """Mark ``event`` as finalized and record the delta bonus flag."""

    statement_id = event.get("header", {}).get("statement_id")
    event["finalized"] = True
    event["delta_bonus"] = bool(delta_bonus)
    return statement_id

