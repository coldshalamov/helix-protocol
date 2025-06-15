from __future__ import annotations

from .minihelix import G


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
        for length in range(1, max_len):
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
                return chain, depth
            if depth < max_depth:
                chain.append(current)
        nonce += 1
    return None


def verify_nested_seed(seed_chain: list[bytes], target_block: bytes) -> bool:
    """Return True if applying G() iteratively over ``seed_chain`` yields ``target_block``.

    Only ``seed_chain[0]`` is required to be ``<=`` the target block length.
    Inner seeds may be any length.
    """

    if not seed_chain:
        return False

    N = len(target_block)

    first = seed_chain[0]
    if len(first) > N or len(first) == 0:
        return False

    current = first
    for next_seed in seed_chain[1:]:
        current = G(current, N)
        if current != next_seed:
            return False

    # Final application of G must yield the target block
    current = G(current, N)
    return current == target_block
