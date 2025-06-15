from __future__ import annotations

from .minihelix import G
from . import minihelix


def encode_header(depth: int, seed_len: int) -> bytes:
    """Encode ``depth`` and ``seed_len`` into a single header byte."""
    if not (1 <= depth <= 15):
        raise ValueError("depth must be 1-15")
    if not (1 <= seed_len <= 15):
        raise ValueError("seed_len must be 1-15")
    return bytes([(depth << 4) | seed_len])


def decode_header(header: int) -> tuple[int, int]:
    """Decode ``header`` into ``(depth, seed_len)``."""
    depth = (header >> 4) & 0x0F
    seed_len = header & 0x0F
    return depth, seed_len


def find_nested_seed(
    target_block: bytes,
    max_depth: int = 10,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
) -> tuple[list[bytes], int] | None:
    """Deterministically search for a nested seed chain yielding ``target_block``.

    Seeds are enumerated in increasing length starting at one byte. ``start_nonce``
    selects the offset into this enumeration and ``attempts`` controls how many
    seeds are tested. The outermost seed length is always strictly less than the
    target size while intermediate seeds may be any length.
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
        for depth in range(1, max_depth + 1):
            current = G(current, N)
            if current == target_block:
                encoded = encode_header(depth, len(seed)) + b"".join(chain)
                return encoded, depth
            if depth < max_depth:
                chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(encoded: bytes, target_block: bytes) -> bool:
    """Return ``True`` if ``encoded`` regenerates ``target_block``."""

    if not encoded:
        return False

    depth, seed_len = decode_header(encoded[0])
    N = len(target_block)

    if seed_len == 0 or seed_len > len(encoded) - 1:
        return False

    pointer = 1
    seed = encoded[pointer : pointer + seed_len]
    pointer += seed_len

    if len(seed) > N:
        return False

    current = seed
    for _ in range(1, depth):
        current = G(current, N)
        if pointer + N > len(encoded):
            return False
        next_seed = encoded[pointer : pointer + N]
        if next_seed != current:
            return False
        pointer += N

    current = G(current, N)
    if current != target_block:
        return False

    return pointer == len(encoded)


def hybrid_mine(target_block: bytes, max_depth: int = 10, *, attempts: int = 1_000_000):
    """Attempt nested search before standard mining for ``target_block``."""
    result = find_nested_seed(target_block, max_depth=max_depth, attempts=attempts)
    if result is not None:
        encoded, depth = result
        _, seed_len = decode_header(encoded[0])
        seed = encoded[1 : 1 + seed_len]
        return seed, depth

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
