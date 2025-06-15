from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed

def decode_header(header: int) -> tuple[int, int]:
    """Decode ``header`` byte into ``(depth, seed_len)``."""
    depth = header >> 4
    seed_len = header & 0x0F
    return depth, seed_len


def _decode_chain(encoded: bytes, block_size: int) -> list[bytes]:
    """Decode ``encoded`` chain produced by :func:`find_nested_seed`."""
    if not encoded:
        return []
    depth = encoded[0]
    seed_len = encoded[1]
    seed = encoded[2 : 2 + seed_len]
    rest = encoded[2 + seed_len :]
    chain = [seed]
    for i in range(depth - 1):
        start = i * block_size
        chain.append(rest[start : start + block_size])
    return chain

def find_nested_seed(
    target_block: bytes,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_depth: int = 1000,
    **kwargs,
) -> tuple[bytes, int] | bytes | None:
    """Search for a seed chain that regenerates ``target_block``.

    Returns ``(encoded_chain, depth)`` where ``encoded_chain`` is the compact
    byte representation excluding the final ``G``.
    """

    def _seed_from_nonce(nonce: int, max_len: int) -> bytes | None:
        for length in range(1, max_len + 1):
            count = 256 ** length
            if nonce < count:
                return nonce.to_bytes(length, "big")
            nonce -= count
        return None

    return_bytes_only = False
    if "max_steps" in kwargs:
        max_depth = kwargs["max_steps"]
        return_bytes_only = True

    N = len(target_block)
    nonce = start_nonce
    for _ in range(attempts):
        seed = _seed_from_nonce(nonce, N)
        if seed is None:
            return None
        current = seed
        chain = [current]
        for depth in range(1, max_depth + 1):
            current = G(current, N)
            if current == target_block:
                encoded = bytes([depth, len(seed)]) + b"".join(chain)
                if return_bytes_only:
                    return b"".join(chain)
                return encoded, depth
            chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(
    seed_chain: list[bytes] | bytes,
    target_block: bytes,
    *,
    max_steps: int = 1000,
) -> bool:
    """Return True if applying G repeatedly to seed_chain regenerates target_block."""

    N = len(target_block)

    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain or len(seed_chain) % N != 0:
            return False
        steps = [seed_chain[i : i + N] for i in range(0, len(seed_chain), N)]
    else:
        steps = list(seed_chain)

    if not steps or len(steps[0]) == 0 or len(steps[0]) > N:
        return False

    if len(steps) > max_steps:
        return False

    current = steps[0]
    for step in steps[1:]:
        current = G(current, N)
        if current != step:
            return False

    current = G(current, N)
    return current == target_block


def hybrid_mine(
    target_block: bytes,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_depth: int = 1000,
) -> tuple[bytes, int] | None:
    """Try nested mining first; fallback to flat mining if needed."""
    result = find_nested_seed(
        target_block,
        start_nonce=start_nonce,
        attempts=attempts,
        max_depth=max_depth,
    )
    if result is not None:
        encoded, depth = result
        chain = _decode_chain(encoded, len(target_block))
        return chain[0], depth

    seed = mine_seed(target_block, max_attempts=attempts)
    if seed is None:
        return None
    return seed, 1


__all__ = [
    "decode_header",
    "_decode_chain",
    "find_nested_seed",
    "verify_nested_seed",
    "hybrid_mine",
]
