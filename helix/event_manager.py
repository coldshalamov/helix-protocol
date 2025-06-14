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

from __future__ import annotations

import hashlib
import re
import string
import math
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - type checking only
    from .statement_registry import StatementRegistry

from .signature_utils import load_keys, sign_data
from .config import GENESIS_HASH

DEFAULT_MICROBLOCK_SIZE = 8  # bytes
FINAL_BLOCK_PADDING_BYTE = b"\x00"

# Base reward for mining a microblock.  Actual payout is scaled by
# the nesting depth of the provided seed.
BASE_REWARD = 1.0


def nesting_penalty(depth: int) -> int:
    """Return the penalty associated with ``depth`` levels of nesting."""

    if depth < 1:
        raise ValueError("depth must be >= 1")
    return depth - 1


def reward_for_depth(depth: int) -> float:
    """Return mining reward scaled by ``depth``."""

    return BASE_REWARD / depth


def normalize_statement(statement: str) -> str:
    """Return ``statement`` lowercased with collapsed whitespace and without
    trailing punctuation."""

    s = statement.strip()
    s = re.sub(r"\s+", " ", s)
    s = s.rstrip(string.punctuation)
    return s.lower()


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
    statement: str,
    microblock_size: int = DEFAULT_MICROBLOCK_SIZE,
    *,
    parent_id: str = GENESIS_HASH,
    keyfile: str | None = None,
    registry: "StatementRegistry" | None = None,
    normalize: bool = False,
) -> Dict[str, Any]:
    """Create an event dictionary for ``statement`` and optionally sign it.

    If ``normalize`` is ``True`` the statement ID is calculated using a
    normalized version of the statement so that near-duplicates share the same
    identifier.
    """

    microblocks, block_count, total_len = split_into_microblocks(
        statement, microblock_size
    )
    hash_input = normalize_statement(statement) if normalize else statement
    statement_id = sha256(hash_input.encode("utf-8"))
    if registry is not None:
        registry.check_and_add(statement)

    header = {
        "statement_id": statement_id,
        "original_length": total_len,
        "microblock_size": microblock_size,
        "block_count": block_count,
        "parent_id": parent_id,
    }

    if keyfile is not None:
        pub, priv = load_keys(keyfile)
        signature = sign_data(repr(header).encode("utf-8"), priv)
        header["originator_sig"] = signature
        header["originator_pub"] = pub

    event = {
        "header": header,
        "statement": statement,
        "microblocks": microblocks,
        "mined_status": [False] * block_count,
        "seeds": [None] * block_count,
        "seed_depths": [0] * block_count,
        "penalties": [0] * block_count,
        "rewards": [0.0] * block_count,
        "refunds": [0.0] * block_count,
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


def accept_mined_seed(event: Dict[str, Any], index: int, seed: bytes, depth: int) -> float:
    """Accept ``seed`` for microblock ``index`` with nesting ``depth``.

    Returns the reward refund amount if an existing seed was replaced.
    """

    penalty = nesting_penalty(depth)
    reward = reward_for_depth(depth)
    refund = 0.0

    if event["seeds"][index] is None:
        event["seeds"][index] = seed
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        mark_mined(event, index)
        return 0.0

    old_seed = event["seeds"][index]
    old_depth = event["seed_depths"][index]
    if len(old_seed) == len(seed) and depth < old_depth:
        refund = event["rewards"][index] - reward
        event["seeds"][index] = seed
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        event["refunds"][index] += refund

    return refund


def save_event(event: Dict[str, Any], directory: str) -> str:
    """Persist ``event`` to ``directory`` as JSON and return file path."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    filename = path / f"{event['header']['statement_id']}.json"
    data = event.copy()
    data["microblocks"] = [b.hex() for b in event["microblocks"]]
    if "seeds" in data:
        data["seeds"] = [s.hex() if isinstance(s, bytes) else None for s in data["seeds"]]
    # numeric fields are stored directly
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return str(filename)


def validate_parent(event: Dict[str, Any], *, ancestors: set[str] | None = None) -> None:
    """Raise ``ValueError`` if ``event`` has an unknown ``parent_id``."""

    if ancestors is None:
        ancestors = {GENESIS_HASH}
    parent_id = event.get("header", {}).get("parent_id")
    if parent_id not in ancestors:
        raise ValueError("invalid parent_id")


def load_event(path: str) -> Dict[str, Any]:
    """Load an event from ``path`` and return the event dict."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["microblocks"] = [bytes.fromhex(b) for b in data.get("microblocks", [])]
    if "seeds" in data:
        data["seeds"] = [bytes.fromhex(s) if isinstance(s, str) and s else None for s in data["seeds"]]
    # Ensure optional numeric fields exist
    block_count = len(data.get("microblocks", []))
    data.setdefault("seed_depths", [0] * block_count)
    data.setdefault("penalties", [0] * block_count)
    data.setdefault("rewards", [0.0] * block_count)
    data.setdefault("refunds", [0.0] * block_count)
    validate_parent(data)
    return data


__all__ = [
    "DEFAULT_MICROBLOCK_SIZE",
    "FINAL_BLOCK_PADDING_BYTE",
    "split_into_microblocks",
    "reassemble_microblocks",
    "normalize_statement",
    "create_event",
    "mark_mined",
    "nesting_penalty",
    "reward_for_depth",
    "accept_mined_seed",
    "save_event",
    "load_event",
    "validate_parent",
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
