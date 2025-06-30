"""Binary encoder for finalized event vote counts with tests."""

from __future__ import annotations
from typing import Tuple
import pytest

VOTE_SCALE = 100


def _encode_value(value: int) -> tuple[int, int, int]:
    """Return ``(prefix, bits, bit_length)`` for ``value``."""
    bit_len = max(value.bit_length(), 1)
    if bit_len > 32:
        raise ValueError("value too large to encode")
    prefix = bit_len - 1
    return prefix, value, bit_len


def encode_vote_header(yes_votes: float, no_votes: float) -> bytes:
    """Encode YES and NO votes into a compact binary header.

    Votes are provided as HLX token amounts and are stored in 0.01 HLX units.
    The returned bytes contain two length-prefixed integers as described in the
    module documentation.
    """
    yes_int = int(round(yes_votes * VOTE_SCALE))
    no_int = int(round(no_votes * VOTE_SCALE))

    yes_prefix, yes_bits, yes_len = _encode_value(yes_int)
    no_prefix, no_bits, no_len = _encode_value(no_int)

    total_bits = 5 + yes_len + 5 + no_len

    value = 0
    value = (value << 5) | yes_prefix
    value = (value << yes_len) | yes_bits
    value = (value << 5) | no_prefix
    value = (value << no_len) | no_bits

    byte_len = (total_bits + 7) // 8
    padding = byte_len * 8 - total_bits
    value <<= padding
    return value.to_bytes(byte_len, "big")


def decode_vote_header(data: bytes) -> Tuple[float, float]:
    """Decode vote header produced by :func:`encode_vote_header`."""
    total_bits = len(data) * 8
    value = int.from_bytes(data, "big")

    index = 0

    def take(n: int) -> int:
        nonlocal index
        shift = total_bits - index - n
        part = (value >> shift) & ((1 << n) - 1)
        index += n
        return part

    yes_prefix = take(5)
    yes_len = yes_prefix + 1
    yes_val = take(yes_len)

    no_prefix = take(5)
    no_len = no_prefix + 1
    no_val = take(no_len)

    return yes_val / VOTE_SCALE, no_val / VOTE_SCALE


# ✅ Unit test

def test_vote_header_roundtrip():
    for yes, no in [
        (0.01, 0.01),
        (1.23, 4.56),
        (123.45, 678.9),
        (0.0, 100.0),
        (42949672.95, 0.0),
    ]:
        encoded = encode_vote_header(yes, no)
        decoded_yes, decoded_no = decode_vote_header(encoded)
        assert round(decoded_yes, 2) == round(yes, 2)
        assert round(decoded_no, 2) == round(no, 2)


__all__ = ["encode_vote_header", "decode_vote_header"]
