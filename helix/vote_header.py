"""Binary encoder for finalized event vote counts."""

from __future__ import annotations
from typing import Tuple

VOTE_SCALE = 100


def _encode_value(value: int) -> tuple[int, int, int]:
    """Return ``(prefix, bits, bit_length)`` for ``value``."""
    bit_len = max(value.bit_length(), 1)
    if bit_len > 32:
        raise ValueError("value too large to encode")
    prefix = bit_len - 1
    return prefix, value, bit_len


def encode_vote_header(yes_votes: float, no_votes: float, *, bonus: bool = False) -> bytes:
    """Encode YES/NO votes and optional delta bonus flag into a binary header.

    ``bonus`` indicates whether the previous verifier received their delta
    bonus.  Votes are provided as HLX token amounts and are stored in ``0.01``
    HLX units.  The returned bytes contain the bonus flag followed by two
    length-prefixed integers as described in the module documentation.
    """
    yes_int = int(round(yes_votes * VOTE_SCALE))
    no_int = int(round(no_votes * VOTE_SCALE))

    yes_prefix, yes_bits, yes_len = _encode_value(yes_int)
    no_prefix, no_bits, no_len = _encode_value(no_int)

    total_bits = 1 + 5 + yes_len + 5 + no_len

    value = 0
    # Bonus flag
    value = (value << 1) | int(bool(bonus))
    # YES prefix
    value = (value << 5) | yes_prefix
    # YES value
    value = (value << yes_len) | yes_bits
    # NO prefix
    value = (value << 5) | no_prefix
    # NO value
    value = (value << no_len) | no_bits

    byte_len = (total_bits + 7) // 8
    padding = byte_len * 8 - total_bits
    value <<= padding
    return value.to_bytes(byte_len, "big")


def decode_vote_header(data: bytes) -> Tuple[float, float, bool]:
    """Decode vote header produced by :func:`encode_vote_header`.

    Returns a tuple ``(yes_votes, no_votes, bonus_flag)`` where ``bonus_flag``
    indicates whether the delta bonus was granted to the previous verifier.
    """
    total_bits = len(data) * 8
    value = int.from_bytes(data, "big")

    index = 0

    def take(n: int) -> int:
        nonlocal index
        shift = total_bits - index - n
        part = (value >> shift) & ((1 << n) - 1)
        index += n
        return part

    bonus = bool(take(1))

    yes_prefix = take(5)
    yes_len = yes_prefix + 1
    yes_val = take(yes_len)

    no_prefix = take(5)
    no_len = no_prefix + 1
    no_val = take(no_len)

    return yes_val / VOTE_SCALE, no_val / VOTE_SCALE, bonus


__all__ = ["encode_vote_header", "decode_vote_header"]
