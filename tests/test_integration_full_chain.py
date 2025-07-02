import pytest

from helix import minihelix
from chain_validator import resolve_seed_collision


def test_integration_full_chain():
    micro_size = 2

    # Mine a sample microblock using minihelix.G
    original_seed = b"a"
    target_block = minihelix.G(original_seed, micro_size)

    mined = minihelix.mine_seed(target_block)
    assert mined == original_seed

    # Validate regeneration matches the original block
    assert minihelix.verify_seed(mined, target_block)

    # Submit a longer seed and then replace it with the shorter one
    long_info = {"seed": original_seed + b"x", "delta_seconds": 1.0, "pubkey": "A"}
    short_info = {"seed": original_seed, "delta_seconds": 2.0, "pubkey": "B"}
    chosen = resolve_seed_collision(long_info, short_info)
    assert chosen["seed"] == original_seed

    # Construct a chain of microblocks
    seeds = [original_seed, b"b"]
    blocks = [minihelix.G(s, micro_size) for s in seeds]
    statement_bytes = b"".join(blocks)

    # Final statement reconstruction and integrity checks
    assert sum(len(b) for b in blocks) == len(statement_bytes)
    assert len(blocks) == 2
    for seed, block in zip(seeds, blocks):
        assert minihelix.verify_seed(seed, block)
    rebuilt = b"".join(minihelix.G(s, micro_size) for s in seeds)
    assert rebuilt == statement_bytes
