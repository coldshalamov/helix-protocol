from __future__ import annotations

"""Utilities for mining nested MiniHelix seeds."""

import json
import os
import threading
import queue
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict

from . import minihelix
from .minihelix import G, mine_seed

# Maximum supported depth when validating nested seed chains.  This
# mirrors the limit enforced by :mod:`helix.exhaustive_miner` and
# prevents extremely deep (and expensive) chains from being accepted.
MAX_DEPTH = 500


class NestedSeed(bytes):
    """Representation of a mined seed or seed chain."""

    def __new__(
        cls,
        chain_bytes: bytes,
        depth: int,
        encoded: bytes,
        chain: list[bytes],
        *,
        fallback_only: bool = False,
    ):
        obj = bytes.__new__(cls, chain_bytes)
        obj.depth = depth
        obj.encoded = encoded
        obj.chain = chain
        obj.fallback_only = fallback_only
        return obj

    def __iter__(self):
        yield self.chain
        yield self.depth


def _encode_chain(chain: list[bytes]) -> bytes:
    depth = len(chain)
    seed_len = len(chain[0])
    return bytes([depth, seed_len]) + b"".join(chain)


def encode_chain(chain: list[bytes]) -> bytes:
    """Encode ``chain`` into the on-chain byte representation."""
    return _encode_chain(chain)


def _decode_chain(
    encoded: bytes, block_size: int, *, validate_output: bool = True
) -> list[bytes]:
    """Decode ``encoded`` seed chain into a list of seeds or microblocks."""
    if not encoded:
        return []

    depth = encoded[0]
    seed_len = encoded[1]
    seed = encoded[2 : 2 + seed_len]
    rest = encoded[2 + seed_len :]

    chain = [seed]
    current = seed
    for i in range(depth - 1):
        start = i * block_size
        segment = rest[start : start + block_size]
        if validate_output:
            expected = G(current, block_size)
            if segment != expected:
                raise ValueError("invalid nested seed chain")
        chain.append(segment)
        current = segment

    return chain


def decode_chain(
    encoded: bytes, block_size: int, *, validate_output: bool = True
) -> list[bytes]:
    """Public wrapper around :func:`_decode_chain`."""

    return _decode_chain(encoded, block_size, validate_output=validate_output)


def _seed_is_valid(seed: bytes, block_size: int) -> bool:
    """Return True if ``seed`` length does not exceed ``block_size``."""
    return 0 < len(seed) <= block_size


def find_nested_seed(target_block: bytes) -> NestedSeed | None:
    """Return the shortest seed regenerating ``target_block``.

    The search exhaustively enumerates flat seeds up to the block length.
    For each seed the direct ``minihelix.unpack_seed`` result is checked
    against ``target_block``.  If that fails, the header derived from the
    seed is used to extract a single nested seed which is also verified.
    Equal-length seeds are accepted but flagged as ``fallback_only``.
    """

    N = len(target_block)
    best: NestedSeed | None = None
    best_len = N + 1

    for flat_len in range(1, N + 1):
        max_value = 256 ** flat_len
        for i in range(max_value):
            seed = i.to_bytes(flat_len, "big")

            # Try flat seed directly
            out = minihelix.unpack_seed(seed, N)
            if out == target_block:
                if flat_len < best_len or best is None:
                    enc = bytes([1, flat_len]) + seed
                    best = NestedSeed(seed, 1, enc, [seed], fallback_only=flat_len == N)
                    best_len = flat_len

            # Derive and test nested seed
            g_out = minihelix.G(seed, N + minihelix.HEADER_SIZE)
            hdr_flat, nested_len = minihelix.decode_header(g_out[: minihelix.HEADER_SIZE])
            if hdr_flat != flat_len or nested_len == 0 or nested_len > N:
                continue
            nested_seed = g_out[minihelix.HEADER_SIZE : minihelix.HEADER_SIZE + nested_len]
            nested_out = minihelix.unpack_seed(nested_seed, N)
            if nested_out == target_block:
                if nested_len < best_len or best is None:
                    enc = bytes([2, flat_len]) + seed + nested_seed
                    best = NestedSeed(seed + nested_seed, 2, enc, [seed, nested_seed], fallback_only=nested_len == N)
                    best_len = nested_len

    return best


def verify_nested_seed(
    seed_chain: list[bytes] | bytes,
    target_block: bytes,
    *,
    max_steps: int = 1000,
    max_depth: int = MAX_DEPTH,
) -> bool:
    """Return ``True`` if ``seed_chain`` regenerates ``target_block``.

    The chain may be provided either as a list of seeds/microblocks or as
    the encoded bytes returned by :func:`find_nested_seed`.  Validation is
    bounded by ``max_depth`` and ``max_steps`` to mirror the main mining
    logic.
    """
    N = len(target_block)

    if isinstance(seed_chain, (bytes, bytearray)):
        if not seed_chain:
            return False
        depth = seed_chain[0]
        seed_len = seed_chain[1]
        expected_len = 2 + seed_len + (depth - 1) * N
        if len(seed_chain) != expected_len:
            return False
        if depth == 0 or depth > max_depth or depth - 1 > max_steps:
            return False

        offset = 2
        seed = seed_chain[offset : offset + seed_len]
        if not _seed_is_valid(seed, N):
            return False
        offset += seed_len
        current = seed
        for step_num in range(1, depth):
            if step_num > max_steps:
                return False
            current = G(current, N)
            next_block = seed_chain[offset : offset + N]
            if len(next_block) != N or current != next_block:
                return False
            offset += N
        current = G(current, N)
        return current == target_block

    # List version
    if not seed_chain:
        return False
    if len(seed_chain) > max_depth or len(seed_chain) - 1 > max_steps:
        return False
    seed = seed_chain[0]
    if not _seed_is_valid(seed, N):
        return False
    for block in seed_chain[1:]:
        if len(block) != N:
            return False

    current = seed
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
    result = find_nested_seed(target_block)
    if result is not None:
        return result.chain[0], result.depth

    seed = mine_seed(target_block, max_attempts=attempts)
    if seed is not None:
        return seed, 1

    return None


def unpack_seed_chain(
    seed_chain: list[bytes] | bytes,
    *,
    block_size: int | None = None,
    validate_output: bool = True,
) -> bytes:
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
            block_size = (
                len(rest) // (depth - 1)
                if depth > 1
                else minihelix.DEFAULT_MICROBLOCK_SIZE
            )
        chain: list[bytes] = [seed]
        current = seed
        for i in range(depth - 1):
            start = i * block_size
            segment = rest[start : start + block_size]
            if validate_output:
                expected = G(current, block_size)
                if segment != expected:
                    raise ValueError("invalid nested seed chain")
            chain.append(segment)
            current = segment
    else:
        chain = list(seed_chain)
        if block_size is None:
            block_size = (
                len(chain[1]) if len(chain) > 1 else minihelix.DEFAULT_MICROBLOCK_SIZE
            )
        if validate_output and len(chain) > 1:
            current = chain[0]
            for segment in chain[1:]:
                if G(current, block_size) != segment:
                    raise ValueError("invalid nested seed chain")
                current = segment

    current = chain[0]
    for _ in range(len(chain)):
        current = G(current, block_size)
    return current


def _load_event(event: str | Dict[str, Any], events_dir: str) -> tuple[Dict[str, Any], Path | None]:
    """Return event dict from ``event`` or load from ``events_dir``."""

    if isinstance(event, str):
        path = Path(events_dir) / f"{event}.json"
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data, path
    return event, None


def _save_event(event: Dict[str, Any], path: Path | None) -> None:
    if path is None:
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(event, fh, indent=2)


def parallel_mine_event(
    event: Dict[str, Any] | str,
    *,
    events_dir: str = "events",
    max_depth: int = 4,
    workers: int | None = None,
) -> int:
    """Mine all unmined microblocks in ``event`` concurrently."""

    evt, path = _load_event(event, events_dir)

    blocks = [b if isinstance(b, (bytes, bytearray)) else bytes.fromhex(b) for b in evt.get("microblocks", [])]
    seeds = evt.setdefault("seeds", [None] * len(blocks))
    depths = evt.setdefault("seed_depths", [0] * len(blocks))
    status = evt.setdefault("mined_status", [False] * len(blocks))

    pending: queue.Queue[int] = queue.Queue()
    for idx, seed in enumerate(seeds):
        if seed is None:
            pending.put(idx)

    lock = threading.Lock()
    mined = 0

    def worker(tid: int) -> None:
        nonlocal mined
        while True:
            try:
                idx = pending.get_nowait()
            except queue.Empty:
                break

            block = blocks[idx]
            current_best = seeds[idx]
            best_len = len(current_best) if isinstance(current_best, (bytes, bytearray)) else float("inf") if current_best is None else len(bytes(current_best))

            result = hybrid_mine(block, max_depth=max_depth)
            if result is None:
                continue
            seed, depth = result
            chain = [seed]
            current = seed
            for _ in range(1, depth):
                current = G(current, len(block))
                chain.append(current)
            encoded = bytes([depth, len(seed)]) + b"".join(chain)
            with lock:
                prev = seeds[idx]
                prev_len = best_len if prev is not None else float("inf")
                if prev is None or len(encoded) < prev_len:
                    seeds[idx] = encoded
                    depths[idx] = depth
                    status[idx] = True
                    mined += 1
                    print(f"Thread {tid} mined microblock {idx}")

    worker_count = workers or max(1, min(os.cpu_count() or 1, len(blocks)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(worker, i) for i in range(worker_count)]
        for fut in futures:
            fut.result()

    _save_event(evt, path)
    return mined

