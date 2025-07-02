import hashlib
import pytest

from helix import minihelix as mh
from helix import exhaustive_miner


def test_G_deterministic():
    seed = b"abc"
    N = 4
    expected = hashlib.sha256(seed + b"\x00").digest()[:N]
    assert mh.G(seed, N) == expected


def test_mine_and_verify_seed():
    seed = b"\x01"
    block = mh.G(seed, N=1)
    found = mh.mine_seed(block)
    assert found == seed
    assert mh.verify_seed(found, block)


def test_verify_seed_false():
    seed = b"\x02"
    block = mh.G(seed, N=1)
    assert not mh.verify_seed(b"\x03", block)


def test_find_nested_seed_simple():
    N = 4
    base_seed = b"a"
    inter1 = mh.G(base_seed, N)
    inter2 = mh.G(inter1, N)
    block = mh.G(inter2, N)

    start_index = int.from_bytes(base_seed, "big")

    chain = exhaustive_miner.exhaustive_mine(
        block, max_depth=3, start_index=start_index
    )
    assert chain is not None, "exhaustive_mine did not return a result"
    assert chain == [base_seed, inter1, inter2], "incorrect seed chain"

    # Verification of the full seed chain via G() composition
    out = base_seed
    for _ in range(3):
        out = mh.G(out, N)
    assert out == block, "seed chain failed verification"
    print("Nested seed search SUCCESS")
