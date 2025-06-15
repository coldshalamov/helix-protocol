from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed


def find_nested_seed(
    target_block: bytes,
    max_depth: int = 10,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
) -> list[bytes] | None:
    """Deterministically search for a nested seed chain yielding ``target_block``.

    Seeds are enumerated in increasing length starting at one byte. ``start_nonce``
    selects the offset into this enumeration and ``attempts`` controls how many
    seeds are tested.  The outermost seed length is always strictly less than the
    target size while intermediate seeds may be any length.

    Returns a list containing the seed chain.  The final block is produced by
    applying :func:`G` once more to the last item in the returned list.
    """

    def _seed_from_nonce(nonce: int, max_len: int) -> bytes | None:
        for length in range(1, max_len + 1):
            count = 256 ** length
            if nonce < count:
                return nonce.to_bytes(length, "big")
            nonce -= count
        return None

    N = len(target_block)
    nonce = start_nonce
    for _ in range(attempts):
        seed = _seed_from_nonce(nonce, N)
        if seed is None:
            return None
        chain = [seed]
        current = seed
        for level in range(1, max_depth + 1):
            current = G(current, N)
            if current == target_block:
                return chain
            if level < max_depth:
                chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(seed_chain: list[bytes] | bytes, target_block: bytes) -> bool:
    """Return ``True`` if replaying ``G`` over ``seed_chain`` yields ``target_block``."""

    if isinstance(seed_chain, (bytes, bytearray)):
        chain = [bytes(seed_chain)]
    else:
        chain = list(seed_chain)

    if not chain:
        return False

    N = len(target_block)
    current = chain[0]
    if len(current) == 0 or len(current) > N:
        return False
    for step in chain[1:]:
        current = G(current, N)
        if current != step:
            return False
    current = G(current, N)
    return current == target_block


def hybrid_mine(
    target_block: bytes,
    *,
    max_depth: int = 10,
    start_nonce: int = 0,
    attempts: int = 10_000,
) -> list[bytes] | None:
    """Attempt nested mining first, then fall back to flat direct mining.

    Returns the seed chain if successful.
    """
    chain = find_nested_seed(
        target_block,
        max_depth=max_depth,
        start_nonce=start_nonce,
        attempts=attempts,
    )
    if chain is not None:
        return chain

    seed = mine_seed(target_block, max_attempts=attempts)
    if seed is not None:
        return [seed]
    return None


__all__ = [
    "find_nested_seed",
    "verify_nested_seed",
    "hybrid_mine",
]
