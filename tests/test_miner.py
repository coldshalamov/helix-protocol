import hashlib
import os
import random

from helix import miner


def test_generate_microblock():
    seed = b"abc"
    expected = hashlib.sha256(seed + b"\x00").digest()[:8]
    assert miner.generate_microblock(seed) == expected


def test_find_seed_deterministic(monkeypatch):
    seed = b"deterministic"
    target = miner.generate_microblock(seed)[:4]

    def fake_randint(a, b):
        return len(seed)

    def fake_urandom(n):
        assert n == len(seed)
        return seed

    monkeypatch.setattr(miner.random, "randint", fake_randint)
    monkeypatch.setattr(miner.os, "urandom", fake_urandom)

    result = miner.find_seed(target, attempts=1)
    assert result == seed
