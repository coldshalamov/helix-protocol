from __future__ import annotations

from . import minihelix
from .minihelix import G


def find_nested_seed(
    target_block: bytes,
    max_depth: int = 10,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
) -> tuple[bytes, int] | None:
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
        chain: list[bytes] = [seed]
        current = seed
        for depth in range(1, max_depth + 1):
            current = G(current, N)
            if current == target_block:
                header = encode_header(depth, len(seed))
                return header + b"".join(chain), depth
            if depth < max_depth:
                chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(seed_chain: list[bytes] | bytes, target_block: bytes) -> bool:
    """Return ``True`` if ``seed_chain`` regenerates ``target_block``.

    ``seed_chain`` may be either the raw byte encoding produced by
    :func:`find_nested_seed` or a list of individual seeds.
    """

    if isinstance(seed_chain, bytes):
        if not seed_chain:
            return False
        depth, seed_len = decode_header(seed_chain[0])
        offset = 1
        first = seed_chain[offset : offset + seed_len]
        if len(first) != seed_len:
            return False
        offset += seed_len
        seeds = [first]
        for _ in range(1, depth):
            next_seed = seed_chain[offset : offset + len(target_block)]
            if len(next_seed) != len(target_block):
                return False
            seeds.append(next_seed)
            offset += len(target_block)
        if offset != len(seed_chain):
            return False
    else:
        seeds = list(seed_chain)

    if not seeds:
        return False

    N = len(target_block)
    first = seeds[0]
    if len(first) == 0 or len(first) > N:
        return False

    current = first
    for nxt in seeds[1:]:
        current = G(current, N)
        if current != nxt:
            return False

    current = G(current, N)
    return current == target_block


def encode_header(depth: int, seed_length: int) -> bytes:
    """Encode ``depth`` and ``seed_length`` into a single byte."""
    if depth < 1 or depth > 15:
        raise ValueError("depth must be between 1 and 15")
    if seed_length < 0 or seed_length > 15:
        raise ValueError("seed_length must be between 0 and 15")
    return bytes([(depth << 4) | (seed_length & 0x0F)])


def decode_header(value: int | bytes) -> tuple[int, int]:
    """Decode a header byte produced by :func:`encode_header`."""
    if isinstance(value, bytes):
        if len(value) != 1:
            raise ValueError("header must be a single byte")
        value = value[0]
    depth = (value >> 4) & 0x0F
    seed_length = value & 0x0F
    return depth, seed_length


def hybrid_mine(target_block: bytes, max_depth: int = 10, *, attempts: int = 1_000_000) -> tuple[bytes, int] | None:
    """Search for a nested seed and return the base seed and depth."""
    result = find_nested_seed(target_block, max_depth=max_depth, attempts=attempts)
    if result is None:
        return None
    encoded, depth = result
    d, seed_len = decode_header(encoded[0])
    seed = encoded[1:1 + seed_len]
    return seed, depth
__all__ = [
    "find_nested_seed",
    "verify_nested_seed",
    "encode_header",
    "decode_header",
    "hybrid_mine",
]
