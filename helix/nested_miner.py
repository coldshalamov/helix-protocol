"""Nested MiniHelix mining utilities."""

from __future__ import annotations

import os
import random


from .minihelix import G


def encode_header(depth: int, seed_len: int) -> bytes:
    """Return a single-byte header encoding ``depth`` and ``seed_len``."""
    if not 1 <= depth <= 15:
        raise ValueError("depth must be 1-15")
    if not 1 <= seed_len <= 16:
        raise ValueError("seed_len must be 1-16")
    return bytes([(depth << 4) | (seed_len - 1)])


def decode_header(b: int) -> tuple[int, int]:
    """Decode ``b`` into ``(depth, seed_len)``."""
    depth = (b >> 4) & 0x0F
    seed_len = (b & 0x0F) + 1
    if depth == 0 or seed_len < 1 or seed_len > 16:
        raise ValueError("invalid header")
    return depth, seed_len


def find_nested_seed(
    target_block: bytes, max_depth: int = 3, *, attempts: int = 1_000_000
) -> tuple[bytes, int] | None:
    """Search for a seed that produces ``target_block`` through nested ``G``.

    Returns a tuple of ``(seed_chain, depth)`` where ``seed_chain`` contains
    the intermediate seeds leading to ``target_block``.  ``depth`` is the
    number of ``G`` applications required.
    """

    N = len(target_block)
    for _ in range(attempts):
        length = random.randint(1, N)
        seed = os.urandom(length)
        chain = [seed]
        current = seed
        for depth in range(1, max_depth + 1):
            candidate = G(current, N)
            if candidate == target_block:
                header = encode_header(depth, len(chain[0]))
                return header + b"".join(chain), depth
            if depth < max_depth:
                chain.append(candidate)
                current = candidate
    return None


def verify_nested_seed(seed_chain: bytes, target_block: bytes) -> bool:
    """Return ``True`` if ``seed_chain`` recreates ``target_block`` using nested ``G``."""

    if not seed_chain:
        return False

    try:
        depth, seed_len = decode_header(seed_chain[0])
    except Exception:
        return False

    if seed_len >= len(target_block):
        return False

    if len(seed_chain) < 1 + seed_len:
        return False

    N = len(target_block)
    pos = 1
    current = seed_chain[pos : pos + seed_len]
    if len(current) != seed_len:
        return False
    pos += seed_len

    for _ in range(1, depth):
        current = G(current, N)
        if pos + N <= len(seed_chain):
            next_seed = seed_chain[pos : pos + N]
            if next_seed != current:
                return False
            pos += N

    if len(seed_chain) not in {1 + seed_len, 1 + seed_len + (depth - 1) * N}:
        return False

    current = G(current, N)
    return current == target_block


def hybrid_mine(target_block: bytes, max_depth: int = 4) -> tuple[bytes, int] | None:
    """Return a seed and depth that regenerate ``target_block`` using nested ``G``.

    The search iterates over seeds in increasing length starting at one byte.
    For each seed ``s`` it computes ``G(s)``, ``G(G(s))`` and so on up to
    ``max_depth`` times.  If any of these intermediate values equals
    ``target_block`` the seed and the matching depth are returned.  The search
    stops after ten million seeds have been tried without success.
    """

    N = len(target_block)
    attempt = 0
    for length in range(1, N + 1):
        max_value = 256 ** length
        for i in range(max_value):
            if attempt >= 10_000_000:
                return None
            seed = i.to_bytes(length, "big")
            current = seed
            for depth in range(1, max_depth + 1):
                current = G(current, N)
                if current == target_block:
                    print(f"Found seed {seed.hex()} at depth {depth}")
                    return seed, depth
            attempt += 1
    return None


def mine_event_with_nested_parallel(
    event: dict,
    max_depth: int = 10,
    max_attempts: int | None = None,
    miner_id: str | None = None,
) -> None:
    """Batch mine all unmined microblocks of ``event`` using nested seeds.

    For each randomly generated seed, this function checks the seed and up to
    ``max_depth`` successive applications of :func:`G` against every unmined
    microblock.  The first depth that matches a block is accepted immediately
    via :func:`event_manager.accept_mined_seed`.  Mining stops when either all
    microblocks have been mined or ``max_attempts`` seeds have been tried.
    """

    from . import event_manager

    microblocks = event["microblocks"]
    status = event["mined_status"]

    targets: list[tuple[int, bytes]] = [
        (i, microblocks[i]) for i in range(len(microblocks)) if not status[i]
    ]
    if not targets:
        print("All microblocks already mined.")
        return

    N = len(targets[0][1])
    attempts = 0
    mined_count = 0
    print(f"Starting mining on {len(targets)} microblocks...")

    try:
        while targets:
            length = random.randint(1, N)
            seed = os.urandom(length)
            chain = [seed]
            current = seed

            for depth in range(1, max_depth + 1):
                current = G(current, N)
                for idx, target in list(targets):
                    if current == target:
                        encoded = encode_header(depth, len(chain[0])) + b"".join(chain[:depth])
                        event_manager.accept_mined_seed(
                            event, idx, encoded, miner=miner_id
                        )
                        print(
                            f"\u2714 Mined block {idx} at depth {depth} (seed len {len(seed)})"
                        )
                        mined_count += 1
                chain.append(current)

                targets = [
                    (i, blk) for i, blk in targets if not event["mined_status"][i]
                ]
                if not targets:
                    break

            attempts += 1
            if max_attempts is not None and attempts >= max_attempts:
                break
    except KeyboardInterrupt:
        print("Mining interrupted by user.")

    print(
        f"Mining complete. Mined {mined_count} microblocks after {attempts} attempts."
    )


__all__ = [
    "find_nested_seed",
    "verify_nested_seed",
    "encode_header",
    "decode_header",
    "hybrid_mine",
    "mine_event_with_nested_parallel",
]
