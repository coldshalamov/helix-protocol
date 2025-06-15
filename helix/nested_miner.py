from __future__ import annotations

from . import minihelix
from .minihelix import G


def encode_header(depth: int, seed_len: int) -> bytes:
    """Return a single byte encoding ``depth`` and ``seed_len``.

    The high nibble stores ``depth`` and the low nibble stores ``seed_len``.
    Both must be in the range 1–15.
    """
    if not (1 <= depth <= 15 and 1 <= seed_len <= 15):
        raise ValueError("depth and seed_len must be between 1 and 15")
    return bytes([(depth << 4) | seed_len])


def decode_header(header: int | bytes) -> tuple[int, int]:
    """Decode a single byte into ``(depth, seed_len)``."""
    if isinstance(header, (bytes, bytearray)):
        if len(header) != 1:
            raise ValueError("header must be a single byte")
        header = header[0]
    depth = (header >> 4) & 0x0F
    seed_len = header & 0x0F
    return depth, seed_len


def _decode_chain(encoded: bytes, target_size: int) -> list[bytes]:
    """Convert encoded seed sequence into list of seeds for replay verification."""
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
    """Search for a nested seed chain that regenerates ``target_block``.

    Returns encoded bytes and the depth of the chain if found.
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


def _verify_chain(chain: list[bytes], target_block: bytes) -> bool:
    """Internal verifier for a decoded list of seeds."""
    if not chain:
        return False
    N = len(target_block)
    current = chain[0]
    if len(current) == 0 or len(current) > N:
        return False
    for next_seed in chain[1:]:
        current = G(current, N)
        if current != next_seed:
            return False
    current = G(current, N)
    return current == target_block


def verify_nested_seed(seed_chain: list[bytes] | bytes, target_block: bytes) -> bool:
    """Return True if ``seed_chain`` regenerates ``target_block``."""
    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain:
            return False
        depth, seed_len = decode_header(seed_chain[0])
        N = len(target_block)
        expected_len = 1 + seed_len + N * (depth - 1)
        if len(seed_chain) != expected_len:
            return False
        offset = 1
        seeds = [seed_chain[offset : offset + seed_len]]
        offset += seed_len
        for _ in range(1, depth):
            seeds.append(seed_chain[offset : offset + N])
            offset += N
        return _verify_chain(seeds, target_block)
    return _verify_chain(list(seed_chain), target_block)


def hybrid_mine(target_block: bytes, max_depth: int = 10, *, attempts: int = 1_000_000) -> tuple[bytes, int] | None:
    """Try nested mining first; fall back to flat mining if needed."""
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
