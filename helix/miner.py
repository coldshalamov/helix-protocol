import hashlib
import os
import random


def truncate_hash(data: bytes, length: int) -> bytes:
    """Return the first `length` bytes of SHA256(data)."""
    return hashlib.sha256(data).digest()[:length]


def generate_microblock(seed: bytes) -> bytes:
    """Return microblock for a given seed using G(s) = Truncate_N(H(s || len(s)))."""
    length = len(seed)
    input_data = seed + length.to_bytes(4, "big")
    return hashlib.sha256(input_data).digest()


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
