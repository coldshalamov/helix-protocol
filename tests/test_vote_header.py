import pytest

from helix.vote_header import encode_vote_header, decode_vote_header


def round_float(value: float) -> float:
    return round(value, 2)


def test_encode_decode_basic():
    yes = 12.34
    no = 56.78
    encoded = encode_vote_header(yes, no)
    decoded_yes, decoded_no = decode_vote_header(encoded)
    assert round_float(decoded_yes) == yes
    assert round_float(decoded_no) == no


def test_zero_votes():
    encoded = encode_vote_header(0.0, 0.0)
    decoded_yes, decoded_no = decode_vote_header(encoded)
    assert decoded_yes == 0.0
    assert decoded_no == 0.0
