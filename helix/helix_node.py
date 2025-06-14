"""Simplified Helix node that verifies and mines events."""
from __future__ import annotations

from typing import Any, Dict

from .event_manager import mark_mined
from .signature_utils import verify_signature


def verify_originator_signature(event: Dict[str, Any]) -> bool:
    """Return ``True`` if the event header signature is valid."""
    header = event.get("header", {}).copy()
    sig = header.pop("originator_sig", None)
    pub = header.pop("originator_pub", None)
    if not sig or not pub:
        return False
    return verify_signature(repr(header).encode("utf-8"), sig, pub)


def mine_event(event: Dict[str, Any]) -> None:
    """Verify ``event`` and mark all microblocks as mined."""
    if not verify_originator_signature(event):
        raise ValueError("Invalid originator signature")

    for i in range(len(event["microblocks"])):
        mark_mined(event, i)


__all__ = ["verify_originator_signature", "mine_event"]


if __name__ == "__main__":
    import json
    from .event_manager import create_event

    event = create_event("demo", keyfile=None)
    try:
        mine_event(event)
    except ValueError as exc:
        print(exc)
    print(json.dumps(event, indent=2))
