from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed


def find_nested_seed(
    target_block: bytes,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_steps: int = 1000,
) -> bytes | None:
    """Search for a seed chain that regenerates ``target_block``.

    Returns an encoded chain: the seed followed by any intermediate steps,
    ending when the target block is matched. No header or depth encoding is used.
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
        current = seed
        chain = [current]
        for _ in range(max_steps):
            current = G(current, N)
            if current == target_block:
                return b"".join(chain)
            chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(
    seed_chain: list[bytes] | bytes,
    target_block: bytes,
    *,
    max_steps: int = 1000,
) -> bool:
    """Return True if applying G repeatedly to ``seed_chain[0]`` yields ``target_block``.

    Accepts either a list of steps or a flat concatenated byte sequence.
    """

    N = len(target_block)

    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain or len(seed_chain) % N != 0:
            return False
        steps = [seed_chain[i : i + N] for i in range(0, len(seed_chain), N)]
    else:
        steps = list(seed_chain)

    if not steps or len(steps[0]) == 0 or len(steps[0]) > N:
        return False

    current = steps[0]
    for i, step in enumerate(steps[1:], start=1):
        if i > max_steps:
            return False
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
    max_steps: int = 1000,
) -> bytes | None:
    """Try nested mining first; fallback to flat mining if needed.

    Returns a seed (not a chain) if mining is successful.
    """
    result = find_nested_seed(
        target_block,
        start_nonce=start_nonce,
        attempts=attempts,
        max_steps=max_steps,
    )
    if result is not None:
        return result

    seed = mine_seed(target_block, max_attempts=attempts)
    return seed


__all__ = [
    "find_nested_seed",
    "verify_nested_seed",
    "hybrid_mine",
]
