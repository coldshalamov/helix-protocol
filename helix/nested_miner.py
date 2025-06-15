from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed


def encode_header(depth: int, seed_len: int) -> bytes:
    """Return a one byte header encoding ``depth`` and ``seed_len``.

    The high nibble stores ``depth`` and the low nibble stores ``seed_len``.
    Both must be in the range 1..15.
    """
    if not (1 <= depth <= 15):
        raise ValueError("depth must be 1..15")
    if not (1 <= seed_len <= 15):
        raise ValueError("seed_len must be 1..15")
    return bytes([(depth << 4) | seed_len])


def decode_header(value: int | bytes) -> tuple[int, int]:
    """Decode a header produced by :func:`encode_header`.

    ``value`` may be the raw integer or a one-byte ``bytes`` object.
    Returns (depth, seed_len).
    """
    if isinstance(value, (bytes, bytearray)):
        if len(value) != 1:
            raise ValueError("header must be a single byte")
        value = value[0]
    depth = (value >> 4) & 0x0F
    seed_len = value & 0x0F
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
                header = encode_header(depth, len(seed))
                return header + seed + b"".join(intermediates), depth
            if depth < max_depth:
                intermediates.append(current)
        nonce += 1
    return None


def verify_nested_seed(seed_chain: list[bytes] | bytes, target_block: bytes) -> bool:
    """Return ``True`` if ``seed_chain`` regenerates ``target_block``.

    ``seed_chain`` may be a list of seed steps or a raw byte sequence
    containing each step concatenated together.  No header or depth
    encoding is assumed.
    """

    N = len(target_block)

    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain or len(seed_chain) % N != 0:
            return False
        steps = [seed_chain[i : i + N] for i in range(0, len(seed_chain), N)]
    else:
        if not seed_chain:
            return False
        steps = list(seed_chain)
        if len(steps[0]) == 0 or len(steps[0]) > N:
            return False
        for step in steps[1:]:
            if len(step) != N:
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
        seed_len = decode_header(encoded[0])[1]
        return encoded[1 : 1 + seed_len], depth

    seed = mine_seed(target_block, max_attempts=attempts)
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
