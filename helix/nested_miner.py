"""Nested MiniHelix mining utilities."""

from __future__ import annotations

import os
import random

from .minihelix import G

def encode_header(depth: int, seed_len: int) -> bytes:
    """Return a single-byte header encoding ``depth`` and ``seed_len``."""
    if not 1 <= depth <= 15:
        raise ValueError("depth must be 1-15")
    if not 1 <= seed_len <= 16:
        raise ValueError("seed_len must be 1-16")
    return bytes([(depth << 4) | (seed_len - 1)])

def decode_header(b: int) -> tuple[int, int]:
    """Decode ``b`` into ``(depth, seed_len)``."""
    depth = (b >> 4) & 0x0F
    seed_len = (b & 0x0F) + 1
    if depth == 0 or seed_len < 1 or seed_len > 16:
        raise ValueError("invalid header")
    return depth, seed_len

def find_nested_seed(
    target_block: bytes, max_depth: int = 3, *, attempts: int = 1_000_000
) -> tuple[bytes, int] | None:
    """Search for a seed that produces ``target_block`` through nested ``G``.

    Returns a tuple of ``(seed_chain, depth)`` where ``seed_chain`` contains
    the intermediate seeds leading to ``target_block``.  ``depth`` is the
    number of ``G`` applications required.
    """

    N = len(target_block)
