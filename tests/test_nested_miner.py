from helix import nested_miner, exhaustive_miner
from helix import minihelix
import pytest


def test_verify_nested_seed():
    N = 8
    base_seed = b"seed"
    inter = minihelix.G(base_seed, N)
    chain = [base_seed, inter]
    target = minihelix.G(inter, N)
    assert nested_miner.verify_nested_seed(chain, target)


@pytest.mark.skip(reason="Legacy miner deprecated")
def test_find_nested_seed_deterministic():
    N = 1
    base_seed = b"\x01"
    intermediate = minihelix.G(base_seed, N)
    target = minihelix.G(intermediate, N)

    chain = exhaustive_miner.exhaustive_mine(target, max_depth=2)
    assert chain is not None, "exhaustive_mine returned None"

    depth = len(chain)
    assert depth <= 2
    assert nested_miner.verify_nested_seed(chain, target)


def test_verify_nested_seed_max_steps_limit():
    N = 1
    seed = b"s"
    chain = [seed]
    current = seed
    # Build a chain of 7 elements
    for _ in range(6):
        current = minihelix.G(current, N)
        chain.append(current)
    target = minihelix.G(current, N)

    # Should fail at max_steps=5, succeed at max_steps=6
    assert not nested_miner.verify_nested_seed(chain, target, max_steps=5)
    assert nested_miner.verify_nested_seed(chain, target, max_steps=6)


def test_verify_nested_seed_max_depth_limit():
    N = 1
    seed = b"s"
    chain = [seed]
    current = seed
    for _ in range(nested_miner.MAX_DEPTH):
        current = minihelix.G(current, N)
        chain.append(current)
    target = minihelix.G(current, N)

    # Should fail if max_depth is too low
    assert not nested_miner.verify_nested_seed(chain, target, max_steps=len(chain) - 1)
    # Should pass when depth limit is relaxed
    assert nested_miner.verify_nested_seed(
        chain,
        target,
        max_steps=len(chain) - 1,
        max_depth=nested_miner.MAX_DEPTH + 1,
    )
