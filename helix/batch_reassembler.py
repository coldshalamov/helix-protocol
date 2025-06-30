from __future__ import annotations

"""Utilities for decoding finalized Helix batch segments."""

from typing import List

from . import minihelix


def reassemble_statement(batch_bytes: bytes) -> str:
    """Return the original statement from ``batch_bytes``.

    ``batch_bytes`` is expected to contain a small header followed by all
    compressed seeds in order.  The first byte stores the microblock size
    and the second byte the number of blocks.  Each seed is then encoded as
    ``[seed_header][seed_bytes]`` where ``seed_header`` uses the MiniHelix
    header format (see :func:`minihelix.decode_header`).  The seeds are
    unpacked using :func:`minihelix.unpack_seed` and the resulting
    microblocks concatenated and decoded as UTF-8.
    """
    if not batch_bytes:
        return ""

    if len(batch_bytes) < 2:
        raise ValueError("batch header too short")

    microblock_size = batch_bytes[0]
    block_count = batch_bytes[1]
    offset = 2

    blocks: List[bytes] = []
    for _ in range(block_count):
        if offset + minihelix.HEADER_SIZE > len(batch_bytes):
            raise ValueError("truncated seed header")
        hdr = batch_bytes[offset : offset + minihelix.HEADER_SIZE]
        flat_len, _ = minihelix.decode_header(hdr)
        offset += minihelix.HEADER_SIZE
        if offset + flat_len > len(batch_bytes):
            raise ValueError("truncated seed data")
        seed = batch_bytes[offset : offset + flat_len]
        offset += flat_len
        blocks.append(minihelix.unpack_seed(seed, microblock_size))

    payload = b"".join(blocks).rstrip(b"\x00")
    return payload.decode("utf-8", errors="replace")
