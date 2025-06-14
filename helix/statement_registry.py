import json
import os
from typing import Iterable, Set

from . import event_manager


class StatementRegistry:
    """Registry of statement hashes to prevent exact duplicates."""

    def __init__(self, hashes: Iterable[str] | None = None, *, normalize: bool = False) -> None:
        """Create a new registry.

        If ``normalize`` is ``True`` statements are normalized prior to hashing
        so that near-duplicates resolve to the same identifier.
        """

        self._hashes: Set[str] = set(hashes or [])
        self.normalize = normalize

    def _hash_statement(self, statement: str) -> str:
        text = (
            event_manager.normalize_statement(statement)
            if self.normalize
            else statement
        )
        return event_manager.sha256(text.encode("utf-8"))

    def check_and_add(self, statement: str) -> None:
        """Add ``statement`` if not already present else raise ``ValueError``."""
        h = self._hash_statement(statement)
        if h in self._hashes:
            raise ValueError("Duplicate statement")
        self._hashes.add(h)

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


__all__ = ["StatementRegistry"]
