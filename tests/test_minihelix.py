import hashlib

from helix import minihelix as mh


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

