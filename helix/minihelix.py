"""Pure Python fallback for the MiniHelix hash functions."""

import hashlib
import os
import random

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

    def mine_seed(target: bytes, *, max_attempts: int | None = None) -> bytes | None:
        """Brute force a seed generating ``target``."""
        attempts = 0
        N = len(target)
        while max_attempts is None or attempts < max_attempts:
            seed = os.urandom(1)
            if G(seed, N) == target:
                return seed
            attempts += 1
        return None

    def verify_seed(seed: bytes, target: bytes) -> bool:
        return G(seed, len(target)) == target

    def decode_header(hdr: bytes) -> tuple[int, int]:
        if len(hdr) != HEADER_SIZE:
            raise ValueError("invalid header")
        return hdr[0], hdr[1]

    def unpack_seed(seed: bytes, block_size: int) -> bytes:
        depth = seed[0]
        length = seed[1]
        payload = seed[2:2 + length]
        current = payload
        for _ in range(depth - 1):
            current = G(current, block_size)
        return current


def truncate_hash(data: bytes, length: int) -> bytes:
    """Return the first `length` bytes of SHA256(data)."""
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
    "G",
    "mine_seed",
    "verify_seed",
    "decode_header",
    "unpack_seed",
]
