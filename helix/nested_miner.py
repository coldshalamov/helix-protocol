from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from . import minihelix, exhaustive_miner
from .minihelix import G, mine_seed


class NestedSeed(bytes):
    """Representation of a mined nested seed chain."""

    def __new__(cls, chain_bytes: bytes, depth: int, encoded: bytes, chain: list[bytes]):
        obj = bytes.__new__(cls, chain_bytes)
        obj.depth = depth
        obj.encoded = encoded
        obj.chain = chain
        return obj

    def __iter__(self):
        yield self.chain
        yield self.depth


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


def _seed_is_valid(seed: bytes, block_size: int) -> bool:
    """Return True if ``seed`` length does not exceed ``block_size``."""
    return 0 < len(seed) <= block_size


def find_nested_seed(
    target_block: bytes,
    max_depth: int = 10,
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_steps: int = 1000,
) -> NestedSeed | None:
    """Recursively search for a nested seed chain yielding ``target_block``.

    This performs a depth-first exploration of candidate seeds.  At each
    level a finite range of seeds is enumerated.  If applying :func:`G`
    to a seed produces the ``target_block`` the search stops.  Otherwise
    the function recurses with the intermediate output as the new target.
    The search depth is limited by ``max_depth`` and ``max_steps``.
    """

    def _seed_from_nonce(nonce: int, max_len: int) -> bytes | None:
        """Return the seed corresponding to ``nonce``."""
        for length in range(1, max_len + 1):
            count = 256 ** length
            if nonce < count:
                return nonce.to_bytes(length, "big")
            nonce -= count
        return None

    N = len(target_block)
    max_depth = min(max_depth, max_steps)

    g_cache: dict[bytes, bytes] = {}

    def dfs(target: bytes, depth: int, nonce: int) -> list[bytes] | None:
        """Return a seed chain generating ``target`` or ``None``."""

        for attempt in range(attempts):
            seed = _seed_from_nonce(nonce + attempt, N)
            if seed is None:
                break
            if not _seed_is_valid(seed, N):
                continue

            nxt = g_cache.get(seed)
            if nxt is None:
                nxt = G(seed, N)
                g_cache[seed] = nxt

            if nxt != target:
                continue

            if depth < max_depth:
                sub = dfs(seed, depth + 1, 0)
                if sub is not None:
                    print(f"match depth={depth + len(sub)} size={len(seed)}")
                    return sub + [seed]

            print(f"match depth={depth} size={len(seed)}")
            return [seed]
        
        return None

    chain = dfs(target_block, 1, start_nonce)
    if chain is None:
        return None

    encoded = _encode_chain(chain)
    chain_bytes = b"".join(chain)
    return NestedSeed(chain_bytes, len(chain), encoded, chain)


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
    for step_num, step in enumerate(seed_chain[1:], start=1):
        if step_num > max_steps:
            return False
        current = G(current, N)
        if current != step:
            return False
    current = G(current, N)
    return current == target_block


def hybrid_mine(
    target_block: bytes,
    *,
    max_depth: int = 10,
    attempts: int | None = None,
    max_steps: int = 1000,
) -> tuple[bytes, int] | None:
    """Attempt direct and nested mining for ``target_block``.

    The function first tries :func:`find_nested_seed`. If successful,
    returns the base seed and depth. If not, falls back to :func:`mine_seed`.

    Returns a ``(seed, depth)`` tuple.
    """
    chain = exhaustive_miner.exhaustive_mine(target_block, max_depth=max_depth)
    if chain is not None:
        return chain[0], len(chain)

    seed = mine_seed(target_block, max_attempts=attempts)
    if seed is not None:
        return seed, 1

    return None

def unpack_seed_chain(seed_chain: list[bytes] | bytes, *, block_size: int | None = None) -> bytes:
    """Return the microblock generated from ``seed_chain``.

    The chain may be provided either as a list of seeds or the encoded
    byte form returned by :func:`find_nested_seed`. When ``block_size`` is
    not provided, it is inferred from the chain if possible. The returned
    bytes are produced by applying :func:`minihelix.G` ``depth`` times to the
    base seed.
    """
    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain:
            return b""
        depth = seed_chain[0]
        seed_len = seed_chain[1]
        seed = seed_chain[2 : 2 + seed_len]
        rest = seed_chain[2 + seed_len :]
        if block_size is None:
            block_size = len(rest) // (depth - 1) if depth > 1 else minihelix.DEFAULT_MICROBLOCK_SIZE
        chain: list[bytes] = [seed]
        for i in range(depth - 1):
            start = i * block_size
            chain.append(rest[start : start + block_size])
    else:
        chain = list(seed_chain)
        if block_size is None:
            block_size = len(chain[1]) if len(chain) > 1 else minihelix.DEFAULT_MICROBLOCK_SIZE

    current = chain[0]
    for _ in range(len(chain)):
        current = G(current, block_size)
    return current

