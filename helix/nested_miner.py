from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed


def encode_header(depth: int, seed_len: int) -> bytes:
    """Return a one byte header encoding ``depth`` and ``seed_len``.

    The high nibble stores ``depth`` and the low nibble stores ``seed_len``.
    Both values must be in the range ``1..15`` which keeps the encoding
    compact and matches the limits used in the tests.
    """

    if not 1 <= depth <= 15:
        raise ValueError("depth must be 1..15")
    if not 1 <= seed_len <= 15:
        raise ValueError("seed_len must be 1..15")
    return bytes([(depth << 4) | seed_len])


def decode_header(value: int | bytes) -> tuple[int, int]:
    """Decode a header produced by :func:`encode_header`.

    ``value`` may be the raw integer or a ``bytes`` object containing a single
    byte.  The function returns ``(depth, seed_len)``.
    """

    if isinstance(value, bytes):
        if len(value) != 1:
            raise ValueError("header must be exactly one byte")
        value = value[0]
    depth = (value >> 4) & 0x0F
    seed_len = value & 0x0F
    return depth, seed_len


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

    The returned value is a tuple of the encoded seed chain and its depth.  The
    encoding is ``encode_header(depth, len(seed))`` followed by the first seed
    and any intermediate seeds used during the search.
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


def verify_nested_seed(encoded_chain: bytes, target_block: bytes) -> bool:
    """Return True if applying G() iteratively over ``seed_chain`` yields ``target_block``.

    Only ``seed_chain[0]`` is required to be ``<=`` the target block length.
    Inner seeds may be any length.
    """

    if not encoded_chain:
        return False

    N = len(target_block)
    depth, seed_len = decode_header(encoded_chain[0])
    expected_len = 1 + seed_len + (depth - 1) * N
    if len(encoded_chain) != expected_len:
        return False

    offset = 1
    seed = encoded_chain[offset : offset + seed_len]
    if len(seed) == 0 or len(seed) > N:
        return False
    offset += seed_len
    current = seed
    for _ in range(1, depth):
        current = G(current, N)
        if current != encoded_chain[offset : offset + N]:
            return False
        offset += N

    current = G(current, N)
    return current == target_block


def hybrid_mine(
    target_block: bytes,
    *,
    max_depth: int = 10,
    start_nonce: int = 0,
    attempts: int = 10_000,
) -> tuple[bytes, int] | None:
    """Attempt direct mining then fall back to nested search.

    Returns ``(seed, depth)`` where ``depth`` is ``1`` for a direct seed or the
    nested depth discovered by :func:`find_nested_seed`.
    """

    result = find_nested_seed(
        target_block,
        max_depth=max_depth,
        start_nonce=start_nonce,
        attempts=attempts,
    )
    if result is not None:
        encoded, depth = result
        return encoded[1 : 1 + decode_header(encoded[0])[1]], depth

    seed = mine_seed(target_block, max_attempts=attempts)
    if seed is not None:
        return seed, 1
    return None
