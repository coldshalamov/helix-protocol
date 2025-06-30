import pytest

from helix.vote_header import encode_vote_header, decode_vote_header


def test_examples():
    hdr = encode_vote_header(12.34, 56.78)
    assert hdr == bytes([2, 2, 0x04, 0xD2, 0x16, 0x2E])
    yes, no = decode_vote_header(hdr)
    assert yes == pytest.approx(12.34)
    assert no == pytest.approx(56.78)

    hdr = encode_vote_header(0.01, 0.01)
    assert hdr == bytes([1, 1, 0x01, 0x01])
    assert decode_vote_header(hdr) == pytest.approx((0.01, 0.01))

    max_yes = 42949672.95
    hdr = encode_vote_header(max_yes, 0)
    assert hdr == bytes([4, 1, 0xFF, 0xFF, 0xFF, 0xFF, 0x00])
    yes, no = decode_vote_header(hdr)
    assert yes == pytest.approx(max_yes)
    assert no == pytest.approx(0)


def test_all_bit_lengths():
    for yes_bits in range(1, 33):
        yes_val = (1 << yes_bits) - 1
        yes_amt = yes_val / 100
        yes_len = max(1, (yes_bits + 7) // 8)
        for no_bits in range(1, 33):
            no_val = (1 << no_bits) - 1
            no_amt = no_val / 100
            no_len = max(1, (no_bits + 7) // 8)
            hdr = encode_vote_header(yes_amt, no_amt)
            assert hdr[0] == yes_len
            assert hdr[1] == no_len
            assert len(hdr) == 2 + yes_len + no_len
            y, n = decode_vote_header(hdr)
            assert y == pytest.approx(yes_amt)
            assert n == pytest.approx(no_amt)
