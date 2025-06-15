import pytest

pytest.importorskip("nacl")

from helix import event_manager as em


def test_compute_reward_saves_bytes():
    assert em.compute_reward(b"a", 3) == 2.0


def test_compute_reward_no_savings():
    assert em.compute_reward(b"abc", 3) == 0.0
