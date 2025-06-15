
from helix import nested_miner
from helix import minihelix


def test_verify_nested_seed():
    N = 8
    base_seed = b"seed"
    inter = minihelix.G(base_seed, N)
    chain = nested_miner.encode_header(2, len(base_seed)) + base_seed + inter
    target = minihelix.G(inter, N)
    assert nested_miner.verify_nested_seed(chain, target)


def test_find_nested_seed_deterministic(monkeypatch):
    N = 8
    base_seed = b"abc"
    intermediate = minihelix.G(base_seed, N)
    target = minihelix.G(intermediate, N)

    def fake_randint(a, b):
        return len(base_seed)

    def fake_urandom(n):
        assert n == len(base_seed)
        return base_seed

    monkeypatch.setattr(nested_miner.random, "randint", fake_randint)
    monkeypatch.setattr(nested_miner.os, "urandom", fake_urandom)

    result = nested_miner.find_nested_seed(target, max_depth=2, attempts=1)
    assert result is not None
    encoded, depth = result
    assert depth == 2
    expected = nested_miner.encode_header(2, len(base_seed)) + base_seed + intermediate
    assert encoded == expected
