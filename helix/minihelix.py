import hashlib
import os
import random
from typing import Optional

DEFAULT_MICROBLOCK_SIZE = 8


def G(seed: bytes, N: int = DEFAULT_MICROBLOCK_SIZE) -> bytes:
    """Return the first ``N`` bytes of the MiniHelix hash stream for ``seed``."""
    output = hashlib.sha256(seed).digest()
    while len(output) < N:
        output += hashlib.sha256(output).digest()
    return output[:N]


def mine_seed(target: bytes, max_attempts: int = 100000) -> Optional[bytes]:
    """Brute-force a seed producing ``target`` using :func:`G`."""
    N = len(target)
    for length in range(1, N + 1):
        max_value = min(256 ** length, max_attempts)
        for i in range(max_value):
            seed = i.to_bytes(length, "big")
            if G(seed, N) == target:
                return seed
        max_attempts -= max_value
        if max_attempts <= 0:
            break
    return None


def verify_seed(seed: bytes, target: bytes) -> bool:
    """Return ``True`` if ``seed`` regenerates ``target``."""
    return G(seed, len(target)) == target


def truncate_hash(data: bytes, length: int) -> bytes:
    """Return the first ``length`` bytes of SHA256 of ``data``."""
    return hashlib.sha256(data).digest()[:length]


def generate_microblock(seed: bytes, block_size: int = DEFAULT_MICROBLOCK_SIZE) -> bytes:
    """Return microblock for ``seed`` using the MiniHelix hash stream."""
    output = b""
    current = hashlib.sha256(seed).digest()
    output += current
    while len(output) < block_size:
        current = hashlib.sha256(current).digest()
        output += current
    return output[:block_size]


def find_seed(target: bytes, max_seed_len: int = 32, *, attempts: int = 1_000_000) -> Optional[bytes]:
    """Randomly search for a seed that generates ``target``."""
    target_len = len(target)
    for _ in range(attempts):
        seed_len = random.randint(1, max_seed_len)
        seed = os.urandom(seed_len)
        candidate = generate_microblock(seed)[:target_len]
        if candidate == target:
            return seed
    return None


__all__ = [
    "DEFAULT_MICROBLOCK_SIZE",
    "G",
    "mine_seed",
    "verify_seed",
    "truncate_hash",
    "generate_microblock",
    "find_seed",
]
