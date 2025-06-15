from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed


def _encode_chain(chain: list[bytes]) -> bytes:
    depth = len(chain)
    seed_len = len(chain[0])
    return bytes([depth, seed_len]) + b"".join(chain)


def _decode_chain(encoded: bytes, block_size: int) -> list[bytes]:
    """Decode encoded seed chain into list of seeds for verification."""
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


def decode_header(header: int) -> tuple[int, int]:
    """Decode ``header`` byte into ``(depth, seed_len)``."""
    depth = header >> 4
    seed_len = header & 0x0F
    return depth, seed_len


def find_nested_seed(
    target_block: bytes,
    max_depth: int = 10,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_steps: int = 1000,
) -> tuple[bytes, int] | None:
    """Deterministically search for a nested seed chain yielding ``target_block``.

    Returns (encoded seed bytes, depth).
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
        for _ in range(max_depth):
            current = G(current, N)
            if current == target_block:
                encoded = _encode_chain(chain)
                return encoded, len(chain)
            chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(
    seed_chain: list[bytes] | bytes,
    target_block: bytes,
    *,
    max_steps: int = 1000,
) -> bool:
    """Return True if ``seed_chain`` regenerates ``target_block``."""
    N = len(target_block)

    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain:
            return False
        depth = seed_chain[0]
        seed_len = seed_chain[1]
        expected_len = 2 + seed_len + (depth - 1) * N
        if len(seed_chain) != expected_len:
            return False

        offset = 2
        seed = seed_chain[offset : offset + seed_len]
        if not (0 < len(seed) <= N):
            return False
        offset += seed_len
        current = seed
        for step_num in range(1, depth):
            if step_num > max_steps:
                return False
            current = G(current, N)
            if current != seed_chain[offset : offset + N]:
                return False
            offset += N
        current = G(current, N)
        return current == target_block

    # List version
    if not seed_chain or not (0 < len(seed_chain[0]) <= N):
        return False
    if len(seed_chain) - 1 >= max_steps:
        return False
    current = seed_chain[0]
    for step_num, step in enumerate(seed_chain[1:]()
