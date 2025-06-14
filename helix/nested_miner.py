"""Nested MiniHelix mining utilities."""

from __future__ import annotations

import os
import random


from .minihelix import G


def find_nested_seed(
    target_block: bytes, max_depth: int = 3, *, attempts: int = 1_000_000
) -> tuple[list[bytes], int] | None:
    """Search for a seed that produces ``target_block`` through nested ``G``.

    Returns a tuple of ``(seed_chain, depth)`` where ``seed_chain`` contains
    the intermediate seeds leading to ``target_block``.  ``depth`` is the
    number of ``G`` applications required.
    """

    N = len(target_block)
    for _ in range(attempts):
        length = random.randint(1, N)
        seed = os.urandom(length)
        chain = [seed]
        current = seed
        for depth in range(1, max_depth + 1):
            candidate = G(current, N)
            if candidate == target_block:
                return chain, depth
            if depth < max_depth:
                chain.append(candidate)
                current = candidate
    return None


def verify_nested_seed(seed_chain: list[bytes], target_block: bytes) -> bool:
    """Return ``True`` if applying ``G`` over ``seed_chain`` yields ``target_block``."""

    if not seed_chain:
        return False

    N = len(target_block)
    current = seed_chain[0]
    for next_seed in seed_chain[1:]:
        current = G(current, N)
        if current != next_seed:
            return False
    current = G(current, N)
    return current == target_block


__all__ = ["find_nested_seed", "verify_nested_seed"]
