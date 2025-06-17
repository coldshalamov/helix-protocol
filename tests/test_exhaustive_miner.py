from helix import exhaustive_miner, minihelix


def test_exhaustive_mine_single_seed(capsys):
    N = 4
    seed = bytes.fromhex("9c")
    block = minihelix.G(seed, N)
    miner = exhaustive_miner.ExhaustiveMiner(block, max_depth=1)
    result = miner.mine()
    out = capsys.readouterr().out
    assert result == [seed]
    assert "Attempts for microblock" in out
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
    assert "Attempts for microblock" in out
    assert miner.attempts > 0


def test_exhaustive_mine_failure(capsys):
    N = 2
    seed = b"xyz"
    target = minihelix.G(seed, N)
    miner = exhaustive_miner.ExhaustiveMiner(target, max_depth=1)
    result = miner.mine()
    out = capsys.readouterr().out
    assert result is None
    assert "Attempts for microblock" in out
    assert miner.attempts > 0
