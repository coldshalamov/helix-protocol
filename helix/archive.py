import json
import gzip
import os
from pathlib import Path
from typing import List

from . import event_manager


def _event_to_dict(event: dict) -> dict:
    data = event.copy()
    if "seeds" in data:
        data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in data["seeds"]]
    return data


def _create_bundle(events: List[dict]) -> bytes:
    """Return gzipped JSON bytes for a list of finalized events."""
    serialized = [_event_to_dict(e) for e in events]
    events_json = json.dumps(serialized).encode("utf-8")
    compressed = gzip.compress(events_json)
    size_saved = len(events_json) - len(compressed)
    ratio = len(events_json) / len(compressed) if len(compressed) else 0

    bundle = {
        "metadata": {
            "total_events": len(events),
            "size_saved": size_saved,
            "compression_ratio": ratio,
        },
        "events": serialized,
    }
    bundle_json = json.dumps(bundle).encode("utf-8")
    return gzip.compress(bundle_json)


def archive_finalized_events(events_dir: str, archive_dir: str, bundle_size: int = 100) -> List[str]:
    """Bundle finalized events from ``events_dir`` and store them compressed.

    Returns a list of created bundle file paths.
    """
    finalized = []
    if os.path.isdir(events_dir):
        for fname in sorted(os.listdir(events_dir)):
            if not fname.endswith(".json"):
                continue
            try:
                event = event_manager.load_event(os.path.join(events_dir, fname))
            except Exception:
                continue
            if event.get("is_closed"):
                finalized.append(event)

    Path(archive_dir).mkdir(parents=True, exist_ok=True)
    paths = []
    for start in range(0, len(finalized), bundle_size):
        chunk = finalized[start:start + bundle_size]
        data = _create_bundle(chunk)
        file_path = Path(archive_dir) / f"bundle_{start // bundle_size}.json.gz"
        with open(file_path, "wb") as fh:
            fh.write(data)
        paths.append(str(file_path))
    return paths


__all__ = ["archive_finalized_events"]
