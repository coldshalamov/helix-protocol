from helix import nested_miner
from helix import minihelix


def test_verify_nested_seed():
    N = 8
    base_seed = b"seed"
    inter = minihelix.G(base_seed, N)
    chain = [base_seed, inter]
    target = minihelix.G(inter, N)
    assert nested_miner.verify_nested_seed(chain, target)


def test_find_nested_seed_deterministic():
    N = 1
    base_seed = b"\x01"
    intermediate = minihelix.G(base_seed, N)
    target = minihelix.G(intermediate, N)

    result = nested_miner.find_nested_seed(target, max_depth=2, attempts=200)
    assert result is not None, "find_nested_seed returned None"

    encoded, depth = result
    chain = nested_miner._decode_chain(encoded, N)
    assert depth == len(chain) <= 2
    assert nested_miner.verify_nested_seed(chain, target)


def test_verify_nested_seed_max_steps_limit():
    N = 1
    seed = b"s"
    chain = [seed]
    current = seed
    # create a short chain to exercise the max_steps check without
    # exceeding the global MAX_DEPTH limit
    for _ in range(6):
        current = minihelix.G(current, N)
        chain.append(current)
    target = minihelix.G(current, N)

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

    assert not nested_miner.verify_nested_seed(chain, target, max_steps=len(chain) - 1)
    assert nested_miner.verify_nested_seed(
        chain,
        target,
        max_steps=len(chain) - 1,
        max_depth=nested_miner.MAX_DEPTH + 1,
    )
