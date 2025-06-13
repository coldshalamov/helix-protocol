"""Helix Statement Encoder and Local Event Manager
Author: Robin Gattis
Description: This script allows statement originators to:
 - Encode a statement into microblocks
 - Store metadata in a shared header
 - Track which blocks are mined
 - Auto-close the event when all microblocks are validated
 - Prepare metadata for on-chain submission

NOTE: This is originator-side logic only. Reward and validation systems are handled by Helix miners.
"""

import hashlib
import math
from typing import List, Tuple, Dict

DEFAULT_MICROBLOCK_SIZE = 8  # bytes
FINAL_BLOCK_PADDING_BYTE = b"\x00"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pad_block(data: bytes, size: int) -> bytes:
    if len(data) < size:
        return data + FINAL_BLOCK_PADDING_BYTE * (size - len(data))
    return data


def split_into_microblocks(statement: str, microblock_size: int = DEFAULT_MICROBLOCK_SIZE) -> Tuple[List[bytes], int, int]:
    encoded = statement.encode("utf-8")
    total_len = len(encoded)
    block_count = math.ceil(total_len / microblock_size)
    blocks = [pad_block(encoded[i : i + microblock_size], microblock_size) for i in range(0, total_len, microblock_size)]
    return blocks, block_count, total_len


def create_event(statement: str, microblock_size: int = DEFAULT_MICROBLOCK_SIZE) -> Dict[str, object]:
    microblocks, block_count, total_len = split_into_microblocks(statement, microblock_size)
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


def mark_mined(event: Dict[str, object], index: int) -> None:
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
