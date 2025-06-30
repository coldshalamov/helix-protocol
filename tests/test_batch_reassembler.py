import pytest

from helix import batch_reassembler, minihelix


def test_reassemble_statement_roundtrip():
    microblock_size = 4
    seeds = [b"a", b"b"]
    blocks = [minihelix.unpack_seed(s, microblock_size) for s in seeds]
    statement = b"".join(blocks).rstrip(b"\x00").decode("utf-8", errors="replace")

    batch = bytearray()
    batch.append(microblock_size)
    batch.append(len(seeds))
    for s in seeds:
        header = minihelix.encode_header(len(s), 0)
        batch += header
        batch += s

    out = batch_reassembler.reassemble_statement(bytes(batch))
    assert out == statement
