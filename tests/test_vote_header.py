import pytest

from helix.vote_header import encode_vote_header


def test_vote_header_encoding():
    header = encode_vote_header(1.23, 4.56)
    assert header == b"\x00\x7b\x01\xc8"
