import pytest

from helix.vote_header import encode_vote_header, decode_vote_header


@pytest.mark.parametrize(
    "yes,no",
    [
        (0.0, 0.0),
        (1.23, 4.56),
        (123.45, 6.78),
        (655.35, 0.01),
    ],
)
def test_roundtrip(yes: float, no: float) -> None:
    header = encode_vote_header(yes, no)
    decoded_yes, decoded_no = decode_vote_header(header)
    assert round(decoded_yes, 2) == round(yes, 2)
    assert round(decoded_no, 2) == round(no, 2)
    assert encode_vote_header(decoded_yes, decoded_no) == header
