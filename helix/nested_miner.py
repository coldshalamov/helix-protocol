from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed


def _decode_chain(encoded: bytes, target_size: int) -> list[bytes]:
    """Convert encoded seed sequence into list of seeds for replay verification."""
    depth = encoded[0]
    seed_len = encoded[1]
    offset = 2
    first = encoded[offset : offset + seed_len]
    offset += seed_len
    chain = [first]
    for _ in range(1, depth):
        chain.append(encoded[offset : offset + target_size])
        offset += target_size
    return chain


def find_nested_seed(
    target_block: bytes,
    max_depth: int = 10,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_steps: int | None = None,
) -> tuple[bytes, int] | None:
    """Deterministically search for a nested seed chain yielding ``target_block``.

    Seeds are enumerated in increasing length starting at one byte. ``start_nonce``
    selects the offset into this enumeration and ``attempts`` controls how many
    seeds are tested. The outermost seed length is always strictly less than the
    target size while intermediate seeds may be any length.

    Returns a tuple: (encoded seed bytes, depth).
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
        intermediates: list[bytes] = []
        current = seed
        for depth in range(1, max_depth + 1):
            current = G(current, N)
            if current == target_block:
                if max_steps is not None:
                    return b"".join([seed] + intermediates)
                header = bytes([depth, len(seed)])
                return header + seed + b"".join(intermediates), depth
            if depth < max_depth:
                intermediates.append(current)
        nonce += 1
    return None


def verify_nested_seed(
    seed_chain: list[bytes] | bytes,
    target_block: bytes,
    *,
    max_steps: int = 1000,
) -> bool:
    """Return True if ``seed_chain`` regenerates ``target_block``.

    Accepts either a list of seed steps or a flat byte-encoded chain.
    ``max_steps`` limits the number of intermediate applications of ``G``.
    """
    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain:
            return False
        depth = seed_chain[0]
        seed_len = seed_chain[1]
        N = len(target_block)
        expected_len = 2 + seed_len + (depth - 1) * N
        if len(seed_chain) != expected_len:
            return False

        offset = 2
        seed = seed_chain[offset : offset + seed_len]
        if len(seed) == 0 or len(seed) > N:
            return False
        offset += seed_len
        current = seed
        if depth - 1 >= max_steps:
            return False
        for step_num in range(1, depth):
            if step_num > max_steps:
                return False
            current = G(current, N)
            if current != seed_chain[offset : offset + N]:
                return False
            offset += N

        current = G(current, N)
        return current == target_block
    else:
        # List of bytes version
        if not seed_chain:
            return False
        N = len(target_block)
        current = seed_chain[0]
        if len(current) == 0 or len(current) > N:
            return False
        if len(seed_chain) - 1 >= max_steps:
            return False
        for step_num, step in enumerate(seed_chain[1:], start=1):
            if step_num > max_steps:
                return False
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
) -> tuple[bytes, int] | None:
    """Attempt nested mining first, then fall back to flat direct mining.

    Returns (outermost seed, depth).
    """
    result = find_nested_seed(
        target_block,
        max_depth=max_depth,
        start_nonce=start_nonce,
        attempts=attempts,
    )
    if result is not None:
        encoded, depth = result
        seed_len = encoded[1]
        return encoded[2 : 2 + seed_len], depth

    seed = mine_seed(target_block, max_attempts=attempts)
    if seed is not None:
        return seed, 1
    return None


__all__ = [
    "find_nested_seed",
    "verify_nested_seed",
    "hybrid_mine",
]
