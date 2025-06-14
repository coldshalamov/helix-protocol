"""Helix Statement Encoder and Local Event Manager.

This module implements the client-side utilities for submitting a statement to
the Helix protocol.  It can encode a raw statement into fixed-length
microblocks, track their mining status and automatically close the event once
all blocks have been validated.  Originators are awarded **1% of the final pot**
when an event closes – this payout is performed by the chain and is outside the
scope of this module.

Padding uses a null byte (``0x00``); when reconstructing the statement these
padding bytes can be safely trimmed.
"""

import hashlib
import math
from typing import Any, Dict, List, Tuple

DEFAULT_MICROBLOCK_SIZE = 8  # bytes
FINAL_BLOCK_PADDING_BYTE = b"\x00"


def sha256(data: bytes) -> str:
    """Return the SHA256 hex digest of ``data``."""

    return hashlib.sha256(data).hexdigest()


def pad_block(data: bytes, size: int) -> bytes:
    """Pad ``data`` with null bytes to ``size`` bytes."""

    if len(data) < size:
        return data + FINAL_BLOCK_PADDING_BYTE * (size - len(data))
    return data


def split_into_microblocks(
    statement: str, microblock_size: int = DEFAULT_MICROBLOCK_SIZE
) -> Tuple[List[bytes], int, int]:
    """Return padded microblocks for ``statement``.

    Returns a tuple of ``(blocks, block_count, total_length)``.
    """

    encoded = statement.encode("utf-8")
    total_len = len(encoded)
    block_count = math.ceil(total_len / microblock_size)
    blocks = [
        pad_block(encoded[i : i + microblock_size], microblock_size)
        for i in range(0, total_len, microblock_size)
    ]
    return blocks, block_count, total_len


def reassemble_microblocks(blocks: List[bytes]) -> str:
    """Reconstruct the original statement from ``blocks``."""

    payload = b"".join(blocks).rstrip(FINAL_BLOCK_PADDING_BYTE)
    return payload.decode("utf-8")


def create_event(
    statement: str, microblock_size: int = DEFAULT_MICROBLOCK_SIZE
) -> Dict[str, Any]:
    """Create an event dictionary for ``statement``."""

    microblocks, block_count, total_len = split_into_microblocks(
        statement, microblock_size
    )
    statement_id = sha256(statement.encode("utf-8"))

    header = {
        "statement_id": statement_id,
        "original_length": total_len,
        "microblock_size": microblock_size,
        "block_count": block_count,
    }

    event = {
        "header": header,
        "statement": statement,
        "microblocks": microblocks,
        "mined_status": [False] * block_count,
        "is_closed": False,
        "bets": {"YES": [], "NO": []},
    }
    return event


def mark_mined(event: Dict[str, Any], index: int) -> None:
    """Mark microblock ``index`` as mined and close the event if complete."""

    if event["is_closed"]:
        return
    event["mined_status"][index] = True
    if all(event["mined_status"]):
        event["is_closed"] = True
        print(f"Event {event['header']['statement_id']} is now closed.")


__all__ = [
    "DEFAULT_MICROBLOCK_SIZE",
    "FINAL_BLOCK_PADDING_BYTE",
    "split_into_microblocks",
    "reassemble_microblocks",
    "create_event",
    "mark_mined",
]


if __name__ == "__main__":
    statement = (
        "The James Webb telescope detected complex organic molecules in interstellar space."
    )
    event = create_event(statement)

    for i in range(len(event["microblocks"])):
        print(f"Mining microblock {i + 1}/{len(event['microblocks'])}...")
        mark_mined(event, i)

    print("Final event state:")
    print(event)
    print("Reassembled statement:")
    print(reassemble_microblocks(event["microblocks"]))
