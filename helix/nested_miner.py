from __future__ import annotations

from .minihelix import G


def encode_header(depth: int, seed_len: int) -> bytes:
    """Return a single byte encoding ``depth`` and ``seed_len``.

    The high nibble stores ``depth`` and the low nibble stores ``seed_len``.
    Both values must be in the range 1-15.
    """

    if depth < 1 or depth > 15:
        raise ValueError("depth must be between 1 and 15")
    if seed_len < 1 or seed_len > 15:
        raise ValueError("seed_len must be between 1 and 15")
    return bytes([(depth << 4) | seed_len])


def decode_header(header: int | bytes) -> tuple[int, int]:
    """Decode ``header`` produced by :func:`encode_header`."""

    if isinstance(header, (bytes, bytearray)):
        if len(header) != 1:
            raise ValueError("header must be a single byte")
        header = header[0]
    depth = (header >> 4) & 0xF
    seed_len = header & 0xF
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

    Returns an encoded seed chain and its depth on success.  The encoding
    begins with :func:`encode_header` followed by the outer seed and any
    intermediate seeds.
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
                header = encode_header(depth, len(seed))
                encoded = header + b"".join(chain)
                return encoded, depth
            if depth < max_depth:
                chain.append(current)
        nonce += 1
    return None


def _verify_chain(chain: list[bytes], target_block: bytes) -> bool:
    if not chain:
        return False

    N = len(target_block)
    first = chain[0]
    if len(first) > N or len(first) == 0:
        return False

    current = first
    for next_seed in chain[1:]:
        current = G(current, N)
        if current != next_seed:
            return False

    current = G(current, N)
    return current == target_block


def verify_nested_seed(seed_chain: list[bytes] | bytes, target_block: bytes) -> bool:
    """Return ``True`` if ``seed_chain`` regenerates ``target_block``."""

    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain:
            return False
        depth, seed_len = decode_header(seed_chain[0])
        N = len(target_block)
        needed = 1 + seed_len + N * (depth - 1)
        if len(seed_chain) != needed:
            return False
        offset = 1
        chain: list[bytes] = []
        chain.append(seed_chain[offset : offset + seed_len])
        offset += seed_len
        for _ in range(1, depth):
            chain.append(seed_chain[offset : offset + N])
            offset += N
        return _verify_chain(chain, target_block)

    return _verify_chain(seed_chain, target_block)


def hybrid_mine(target_block: bytes, max_depth: int = 10) -> tuple[bytes, int] | None:
    """Search for a seed producing ``target_block`` and return the outer seed and depth."""

    result = find_nested_seed(target_block, max_depth=max_depth)
    if result is None:
        return None

    encoded, depth = result
    _, seed_len = decode_header(encoded[0])
    seed = encoded[1 : 1 + seed_len]
    return seed, depth
