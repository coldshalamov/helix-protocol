"""Compact vote header utilities.

The header encodes YES and NO vote totals using unsigned 16-bit integers in
hundredths of a HLX token.  This compact fixed-width format allows binary
transmission and deterministic replay of finalized events.
"""

from __future__ import annotations
from typing import Tuple

VOTE_SCALE = 100
MAX_VALUE = 0xFFFF


def _encode_amount(value: float) -> bytes:
    """Return a 2-byte big-endian integer for ``value`` HLX."""

    raw = int(round(float(value) * VOTE_SCALE))
    if raw < 0 or raw > MAX_VALUE:
        raise ValueError("vote amount out of range")
    return raw.to_bytes(2, "big")


def encode_vote_header(yes_votes: float, no_votes: float) -> bytes:
    """Return a 4-byte header encoding YES and NO vote totals."""

    return _encode_amount(yes_votes) + _encode_amount(no_votes)


def decode_vote_header(header_bytes: bytes) -> Tuple[float, float]:
    """Reverse :func:`encode_vote_header` and return vote totals in HLX."""

    if len(header_bytes) != 4:
        raise ValueError("vote header must be exactly 4 bytes")

    yes_raw = int.from_bytes(header_bytes[:2], "big")
    no_raw = int.from_bytes(header_bytes[2:], "big")
    return yes_raw / VOTE_SCALE, no_raw / VOTE_SCALE


__all__ = ["encode_vote_header", "decode_vote_header"]
