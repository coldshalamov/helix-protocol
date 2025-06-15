```python
from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

from .minihelix import G, mine_seed


def _encode_chain(chain: list[bytes]) -> bytes:
    depth = len(chain)
    seed_len = len(chain[0])
    return bytes([depth, seed_len]) + b"".join(chain)


def _decode_chain(encoded: bytes, block_size: int) -> list[bytes]:
    """Decode ``encoded`` chain produced by :func:`find_nested_seed`."""
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
    *,
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_steps: int = 1000,
    max_depth: int | None = None,
) -> bytes | tuple[bytes, int] | None:
    """Search for a seed chain that regenerates ``target_block``.

    If ``max_depth`` is provided, the returned value is ``(encoded, depth)`` where
    ``encoded`` is an encoded seed chain. Otherwise the flat byte chain is
    returned for backward compatibility.
    """

    def _seed_from_nonce(nonce: int, max_len: int) -> bytes | None:
        for length in range(1, max_len + 1):
            count = 256 ** length
            if nonce < count:
                return nonce.to_bytes(length, "big")
            nonce -= count
        return None

    return_bytes_only = False
    if max_depth is None:
        max_depth = max_steps
    else:
        return_bytes_only = True
        max_depth = min(max_steps, max_depth)

    N = len(target_block)
    nonce = start_nonce
    for _ in range(attempts):
        seed = _seed_from_nonce(nonce, N)
        if seed is None:
            return None
        current = seed
        chain = [current]
        for _ in range(max_depth):
            current = G(current, N)
            if current == target_block:
                if return_bytes_only:
                    return b"".join(chain)
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
    """Return True if applying G repeatedly to seed_chain regenerates target_block."""

    N = len(target_block)

    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain or len(seed_chain) % N != 0:
            return False
        steps = [seed_chain[i : i + N] for i in range(0, len(seed_chain), N)]
    else:
        steps = list(seed_chain)

    if not steps or len(steps[0]) == 0 or len(steps[0]) > N:
        return False

    if len(steps) > max_steps:
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
    start_nonce: int = 0,
    attempts: int = 10_000,
    max_steps: int = 1000,
    max_depth: int = 4,
) -> tuple[bytes, int] | bytes | None:
    """Try nested mining first; fallback to flat mining if needed."""
    result = find_nested_seed(
        target_block,
        start_nonce=start_nonce,
        attempts=attempts,
        max_steps=max_steps,
        max_depth=max_depth,
    )
    if result is not None:
        encoded, depth = result
        chain = _decode_chain(encoded, len(target_block))
        return chain[0], depth

    seed = mine_seed(target_block, max_attempts=attempts)
    if seed is None:
        return None
    return seed


__all__ = [
    "decode_header",
    "_decode_chain",
    "find_nested_seed",
    "verify_nested_seed",
    "hybrid_mine",
]
```
