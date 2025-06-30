"""Vote header utilities."""

__all__ = ["encode_vote_header"]


def _encode_amount(value: float) -> bytes:
    """Return a 2-byte big-endian integer for ``value`` HLX."""
    raw = int(round(float(value) * 100))
    if raw <= 0:
        raw = 1
    if raw > 0xFFFF:
        raise ValueError("vote amount out of range")
    return raw.to_bytes(2, "big")


def encode_vote_header(yes_votes: float, no_votes: float) -> bytes:
    """Return 4-byte header encoding YES and NO vote totals.

    Values are stored using a fixed-point format with 2 decimal places.
    """
    return _encode_amount(yes_votes) + _encode_amount(no_votes)
