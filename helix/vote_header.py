VOTE_SCALE = 100


def encode_vote_header(yes: float, no: float) -> bytes:
    """Encode YES and NO vote amounts into a variable-length header."""
    yes_int = round(yes * VOTE_SCALE)
    no_int = round(no * VOTE_SCALE)
    if not (0 <= yes_int <= 0xFFFFFFFF):
        raise ValueError("YES value out of range")
    if not (0 <= no_int <= 0xFFFFFFFF):
        raise ValueError("NO value out of range")
    yes_len = max(1, (yes_int.bit_length() + 7) // 8)
    no_len = max(1, (no_int.bit_length() + 7) // 8)
    return (
        bytes([yes_len, no_len])
        + yes_int.to_bytes(yes_len, "big")
        + no_int.to_bytes(no_len, "big")
    )


def decode_vote_header(data: bytes) -> tuple[float, float]:
    """Decode YES and NO vote amounts from a header created by ``encode_vote_header``."""
    if len(data) < 2:
        raise ValueError("header too short")
    yes_len = data[0]
    no_len = data[1]
    if yes_len == 0 or no_len == 0:
        raise ValueError("invalid lengths")
    expect_len = 2 + yes_len + no_len
    if len(data) < expect_len:
        raise ValueError("header truncated")
    yes_int = int.from_bytes(data[2 : 2 + yes_len], "big")
    no_int = int.from_bytes(data[2 + yes_len : expect_len], "big")
    return yes_int / VOTE_SCALE, no_int / VOTE_SCALE


__all__ = ["encode_vote_header", "decode_vote_header"]
