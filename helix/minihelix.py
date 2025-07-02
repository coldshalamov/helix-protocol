import hashlib
import os
import random
from typing import Tuple

DEFAULT_MICROBLOCK_SIZE = 4
HEADER_SIZE = 2


def G(seed: bytes, N: int) -> bytes:
    """Return the first ``N`` bytes of the MiniHelix hash stream for ``seed``."""
    output = b""
    current = hashlib.sha256(seed).digest()
    output += current
    while len(output) < N:
        current = hashlib.sha256(current).digest()
        output += current
    return output[:N]


def mine_seed(target: bytes, *, max_attempts: int = 1_000_000, max_seed_len: int = 32) -> bytes | None:
    """Search for a seed that regenerates ``target``."""
    length = len(target)
    for _ in range(max_attempts):
        seed_len = random.randint(1, max_seed_len)
        seed = os.urandom(seed_len)
        if G(seed, length) == target:
            return seed
    return None


def verify_seed(seed: bytes, target: bytes) -> bool:
    """Return ``True`` if ``seed`` regenerates ``target``."""
    return G(seed, len(target)) == target


def decode_header(hdr: bytes) -> Tuple[int, int]:
    """Decode a two-byte header into (flat_length, nested_length)."""
    if len(hdr) < HEADER_SIZE:
        raise ValueError("header too short")
    return hdr[0], hdr[1]


def unpack_seed(seed: bytes, block_size: int) -> bytes:
    """Return the microblock produced by ``seed``."""
    return G(seed, block_size)


__all__ = [
    "DEFAULT_MICROBLOCK_SIZE",
    "HEADER_SIZE",
    "G",
    "mine_seed",
    "verify_seed",
    "decode_header",
    "unpack_seed",
]
