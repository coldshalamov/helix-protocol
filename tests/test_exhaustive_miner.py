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


def test_exhaustive_mine_depth_limit():
    """Return ``None`` when the required chain exceeds ``max_depth``."""
    N = 4
    base_seed = bytes.fromhex("c0")
    second_seed = bytes.fromhex("00000000")
    target = minihelix.G(second_seed, N)
    assert exhaustive_miner.exhaustive_mine(target, max_depth=1) is None


def test_exhaustive_mine_start_index_out_of_range():
    """Return ``None`` when ``start_index`` skips all seeds."""
    N = 4
    seed = b"01"
    target = minihelix.G(seed, N)
    start = len(list(exhaustive_miner._generate_initial_seeds()))
    assert exhaustive_miner.exhaustive_mine(target, max_depth=1, start_index=start) is None
