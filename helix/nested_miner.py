from __future__ import annotations

from .minihelix import G
from . import minihelix


def encode_header(depth: int, seed_len: int) -> bytes:
    """Pack ``depth`` and ``seed_len`` into a single byte."""
    if not (1 <= depth <= 15 and 1 <= seed_len <= 15):
        raise ValueError("depth and seed_len must be between 1 and 15")
    return bytes([(depth << 4) | seed_len])


def decode_header(b: int | bytes) -> tuple[int, int]:
    """Return ``(depth, seed_len)`` encoded by ``encode_header``."""
    if isinstance(b, (bytes, bytearray)):
        if not b:
            raise ValueError("empty header")
        b = b[0]
    depth = (b >> 4) & 0x0F
    seed_len = b & 0x0F
    return depth, seed_len


def _decode_chain(encoded: bytes, target_size: int) -> list[bytes]:
    depth, seed_len = decode_header(encoded[0])
    offset = 1
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
) -> tuple[bytes, int] | None:
    """Deterministically search for a nested seed chain yielding ``target_block``."""
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
        for depth in range(1, max_depth + 1):
            current = G(current, N)
            if current == target_block:
                encoded = encode_header(depth, len(seed)) + b"".join(chain)
                return encoded, depth
            if depth < max_depth:
                chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(encoded: bytes | list[bytes], target_block: bytes) -> bool:
    """Return ``True`` if ``encoded`` regenerates ``target_block``."""
    if not encoded:
        return False

    N = len(target_block)

    if isinstance(encoded, (bytes, bytearray)):
        try:
            chain = _decode_chain(encoded, N)
        except Exception:
            return False
    else:
        chain = list(encoded)

    first = chain[0]
    if len(first) == 0 or len(first) > N:
        return False

    current = first
    for next_seed in chain[1:]:
        current = G(current, N)
        if next_seed != current:
            return False

    current = G(current, N)
    return current == target_block


def hybrid_mine(target_block: bytes, max_depth: int = 10, *, attempts: int = 1_000_000) -> tuple[bytes, int] | None:
    """Attempt nested mining first, fall back to flat mining if needed."""
    result = find_nested_seed(target_block, max_depth=max_depth, attempts=attempts)
    if result is not None:
        encoded, depth = result
        chain = _decode_chain(encoded, len(target_block))
        return chain[0], depth

    seed = minihelix.mine_seed(target_block, max_attempts=attempts)
    if seed is not None:
        return seed, 1
    return None


__all__ = [
    "encode_header",
    "decode_header",
    "find_nested_seed",
    "verify_nested_seed",
    "hybrid_mine",
]
