"""MiniHelix generative proof-of-work utilities."""

from __future__ import annotations

import hashlib


DEFAULT_MICROBLOCK_SIZE = 8


def G(seed: bytes, N: int = DEFAULT_MICROBLOCK_SIZE) -> bytes:
    """Return ``N`` bytes generated from ``seed`` using the MiniHelix function."""
    if not seed:
        raise ValueError("seed must not be empty")
    if len(seed) > 255:
        raise ValueError("seed must be 255 bytes or fewer")
    data = seed + len(seed).to_bytes(1, "big")
    return hashlib.sha256(data).digest()[:N]


def mine_seed(target_block: bytes, max_attempts: int | None = None) -> bytes | None:
    """Brute-force search for a seed that regenerates ``target_block``."""
    N = len(target_block)
    attempt = 0
    for length in range(1, N + 1):
        max_value = 256 ** length
        for i in range(max_value):
            if max_attempts is not None and attempt >= max_attempts:
                return None
            seed = i.to_bytes(length, "big")
            if G(seed, N) == target_block:
                return seed
            attempt += 1
    return None


def verify_seed(seed: bytes, target_block: bytes) -> bool:
    """Return ``True`` if ``seed`` regenerates ``target_block``."""
    if len(seed) > len(target_block) or not seed:
        return False
    return G(seed, len(target_block)) == target_block


def main() -> None:
    """Simple demonstration of MiniHelix mining and verification."""
    microblock = b"science!"
    print(f"Target microblock: {microblock!r}")
    seed = mine_seed(microblock, max_attempts=1_000_000)
    if seed is None:
        print("No seed found within the attempt limit.")
        return
    print(f"Found seed: {seed.hex()}")
    print("Verification:", verify_seed(seed, microblock))


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()
