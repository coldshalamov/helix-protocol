from helix import exhaustive_miner, minihelix


def test_exhaustive_mine_single_seed(capsys):
    N = 4
    seed = bytes.fromhex("9c")
    block = minihelix.G(seed, N)
    miner = exhaustive_miner.ExhaustiveMiner(block, max_depth=1)
    result = miner.mine()
    out = capsys.readouterr().out
    assert result == [seed]
    assert miner.attempts > 0


def test_exhaustive_mine_nested_seed(capsys):
    N = 4
    base_seed = bytes.fromhex("cf")
    second_seed = bytes.fromhex("0033")
    target = minihelix.G(second_seed, N)
    start_index = int.from_bytes(base_seed, "big")
    miner = exhaustive_miner.ExhaustiveMiner(target, max_depth=2)
    result = miner.mine(start_index=start_index)
    out = capsys.readouterr().out
    assert result == [base_seed, second_seed]
    assert miner.attempts > 0


def test_exhaustive_mine_failure(capsys):
    N = 2
    seed = b"xyz"
    target = minihelix.G(seed, N)
    miner = exhaustive_miner.ExhaustiveMiner(target, max_depth=1)
    result = miner.mine()
    out = capsys.readouterr().out
    assert result is None
    assert miner.attempts > 0


def test_exhaustive_mine_checkpoint(tmp_path):
    N = 1
    seed_a = b"\x01"
    block_a = minihelix.G(seed_a, N)
    checkpoint = tmp_path / "cp.txt"

    result_a = exhaustive_miner.exhaustive_mine(
        block_a, max_depth=1, checkpoint_path=str(checkpoint)
    )
    assert result_a == [seed_a]
    assert checkpoint.read_text() == "2"

    seed_b = b"\x02"
    block_b = minihelix.G(seed_b, N)
    result_b = exhaustive_miner.exhaustive_mine(
        block_b, max_depth=1, checkpoint_path=str(checkpoint)
    )
    assert result_b == [seed_b]
    assert checkpoint.read_text() == "3"


def test_exhaustive_mine_depth_limit():
    """Return None when the required chain exceeds max_depth."""
    N = 4
    base_seed = bytes.fromhex("c0")
    second_seed = bytes.fromhex("00000000")
    target = minihelix.G(second_seed, N)
    result = exhaustive_miner.exhaustive_mine(target, max_depth=1)
    assert result is None


def test_exhaustive_mine_start_index_out_of_range():
    """Return None when start_index skips all seeds."""
    N = 4
    seed = b"\x01"
    target = minihelix.G(seed, N)
    start = len(list(exhaustive_miner._generate_initial_seeds()))
    result = exhaustive_miner.exhaustive_mine(target, max_depth=1, start_index=start)
    assert result is None
