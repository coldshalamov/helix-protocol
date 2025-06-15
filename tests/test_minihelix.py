import hashlib

from helix import minihelix as mh
from helix import nested_miner


def test_G_deterministic():
    seed = b"abc"
    N = 4
    expected = hashlib.sha256(seed + len(seed).to_bytes(1, "big")).digest()[:N]
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


def test_find_nested_seed_simple(monkeypatch):
    N = 8
    base_seed = b"abc"
    inter1 = mh.G(base_seed, N)
    inter2 = mh.G(inter1, N)
    block = mh.G(inter2, N)

    def fake_randint(a, b):
        return len(base_seed)

    def fake_urandom(n):
        assert n == len(base_seed)
        return base_seed

    monkeypatch.setattr(nested_miner.random, "randint", fake_randint)
    monkeypatch.setattr(nested_miner.os, "urandom", fake_urandom)

    result = nested_miner.find_nested_seed(block, max_depth=3, attempts=1)
    assert result is not None, "find_nested_seed did not return a result"
    encoded, depth = result
    print("Returned chain", encoded, "depth", depth)
    assert depth == 3, f"expected depth 3, got {depth}"
    expected = (
        nested_miner.encode_header(3, len(base_seed))
        + base_seed
        + inter1
        + inter2
    )
    assert encoded == expected, "incorrect seed encoding"
    assert nested_miner.verify_nested_seed(encoded, block), "seed chain failed verification"
    print("Nested seed search SUCCESS")

