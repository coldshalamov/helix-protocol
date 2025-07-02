"""Pure Python fallback for the MiniHelix hash functions."""

import hashlib
import os
import random
from typing import Optional, Tuple

try:  # pragma: no cover - optional native extension
    from .minihelix import DEFAULT_MICROBLOCK_SIZE, HEADER_SIZE, G
    from .minihelix import mine_seed, verify_seed, decode_header, unpack_seed
except Exception:  # pragma: no cover - use slow Python implementations
    DEFAULT_MICROBLOCK_SIZE = 8
    HEADER_SIZE = 2

    def G(seed: bytes, N: int = DEFAULT_MICROBLOCK_SIZE) -> bytes:
        """Return ``N`` bytes of MiniHelix output for ``seed``."""
        output = b""
        current = hashlib.sha256(seed).digest()
        output += current
        while len(output) < N:
            current = hashlib.sha256(current).digest()
            output += current
        return output[:N]

    def mine_seed(target: bytes, *, max_attempts: int = 1_000_000, max_seed_len: int = 32) -> Optional[bytes]:
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


def mine_seed(target_block: bytes, max_attempts: int | None = 1_000_000) -> bytes | None:
    """Compatibility wrapper calling :func:`find_seed`."""
    return find_seed(target_block, max_seed_len=DEFAULT_MICROBLOCK_SIZE, attempts=max_attempts or 0)


__all__ = [
    "DEFAULT_MICROBLOCK_SIZE",
    "HEADER_SIZE",
    "G",
    "mine_seed",
    "verify_seed",
    "truncate_hash",
    "generate_microblock",
    "find_seed",
    "decode_header",
    "unpack_seed",
]
