from helix import minihelix, nested_miner


def test_hybrid_mine_simple():
    seed = b"\x01"
    # Create a target that is two applications of G on the seed
    target = minihelix.G(minihelix.G(seed, N=1), N=1)
    result = nested_miner.hybrid_mine(target, max_depth=2)
    assert result == (seed, 2)
