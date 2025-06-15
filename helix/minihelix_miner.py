from __future__ import annotations

"""Advanced MiniHelix mining utilities with batch-aware validation."""

from typing import Any, Dict, List, Optional

from .minihelix import G
from .event_manager import reassemble_microblocks, sha256


def _seed_is_valid(seed: bytes, microblock_size: int) -> bool:
    """Return True if ``seed`` is short enough to yield compression."""
    return 0 < len(seed) < microblock_size


def mine_seed_with_header(
    target_block: bytes,
    header: Dict[str, Any],
    *,
    max_attempts: Optional[int] = None,
) -> Optional[bytes]:
    """Search for a seed regenerating ``target_block`` respecting ``header``.

    The ``header`` dictionary must contain ``microblock_size``.  Seeds that are
    longer than this size or that obviously cannot compress the block are
    skipped before evaluating :func:`G`.
    """

    microblock_size = header.get("microblock_size", len(target_block))
    N = microblock_size
    attempt = 0
    for length in range(1, microblock_size):
        max_value = 256 ** length
        for i in range(max_value):
            if max_attempts is not None and attempt >= max_attempts:
                return None
            seed = i.to_bytes(length, "big")
            attempt += 1
            if not _seed_is_valid(seed, microblock_size):
                continue
            output = G(seed, N)
            if len(output) != microblock_size:
                continue
            if output == target_block:
                return seed
    return None


def mine_batch(
    blocks: List[bytes],
    header: Dict[str, Any],
    *,
    max_attempts: Optional[int] = None,
) -> List[Optional[bytes]]:
    """Mine all ``blocks`` using :func:`mine_seed_with_header`.

    If all blocks are mined successfully and ``statement_id`` is present in the
    header, the recomposed statement hash is verified at the end.
    """

    seeds: List[Optional[bytes]] = []
    for block in blocks:
        seeds.append(mine_seed_with_header(block, header, max_attempts=max_attempts))

    if None not in seeds and "statement_id" in header:
        microblock_size = header.get("microblock_size", len(blocks[0]) if blocks else 0)
        regenerated = [G(s, microblock_size) for s in seeds]  # type: ignore
        statement = reassemble_microblocks(regenerated)
        if sha256(statement.encode("utf-8")) != header["statement_id"]:
            raise ValueError("statement hash mismatch")

    return seeds
