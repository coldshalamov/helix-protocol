import hashlib
import os
import random

from .minihelix import DEFAULT_MICROBLOCK_SIZE


def truncate_hash(data: bytes, length: int) -> bytes:
    """Return the first `length` bytes of SHA256(data)."""
    return hashlib.sha256(data).digest()[:length]


def generate_microblock(seed: bytes, block_size: int = DEFAULT_MICROBLOCK_SIZE) -> bytes:
    """Return microblock for ``seed`` using the MiniHelix hash stream."""

    output = b""
    i = 0
    while len(output) < block_size:
        output += hashlib.sha256(seed + bytes([i])).digest()
        i += 1
    return output[:block_size]


def find_seed(target: bytes, max_seed_len: int = 32, *, attempts: int = 1_000_000) -> bytes | None:
    """Search for a seed that generates `target` when truncated to len(target)."""
    target_len = len(target)
    for _ in range(attempts):
        seed_len = random.randint(1, max_seed_len)
        seed = os.urandom(seed_len)
        candidate = generate_microblock(seed)[:target_len]
        if candidate == target:
            return seed
    return None


__all__ = [
    "truncate_hash",
    "generate_microblock",
    "find_seed",
]
