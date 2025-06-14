import pytest

pytest.importorskip("nacl")

from helix import event_manager as em


def test_reward_depth_one():
    assert em.calculate_reward(1.0, 1) == 1.0


def test_reward_depth_two():
    assert em.calculate_reward(2.0, 2) == 1.0


def test_reward_rounding():
    assert em.calculate_reward(1.0, 3) == 0.3333


def test_reward_invalid_depth():
    with pytest.raises(ValueError):
        em.calculate_reward(1.0, 0)
