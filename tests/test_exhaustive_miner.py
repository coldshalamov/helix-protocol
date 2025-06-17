from helix import exhaustive_miner, minihelix


def test_exhaustive_mine_single_seed():
    N = 4
    seed = bytes.fromhex("9c")
    block = minihelix.G(seed, N)
    result = exhaustive_miner.exhaustive_mine(block, max_depth=1)
    assert result == [seed]


def test_exhaustive_mine_nested_seed():
    N = 4
    base_seed = bytes.fromhex("cf")
    second_seed = bytes.fromhex("0033")
    target = minihelix.G(second_seed, N)
    start_index = int.from_bytes(base_seed, "big")
    result = exhaustive_miner.exhaustive_mine(target, max_depth=2, start_index=start_index)
    assert result == [base_seed, second_seed]
