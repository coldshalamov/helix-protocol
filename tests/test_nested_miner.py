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
    N = 8
    base_seed = b"abc"
    intermediate = minihelix.G(base_seed, N)
    target = minihelix.G(intermediate, N)

    # Calculate the enumeration index for the chosen seed
    start_nonce = 0
    for length in range(1, N):
        count = 256 ** length
        if length < len(base_seed):
            start_nonce += count
        elif length == len(base_seed):
            start_nonce += int.from_bytes(base_seed, "big")
            break

    result = nested_miner.find_nested_seed(
        target, start_nonce=start_nonce, attempts=1, max_steps=2
    )
    assert result is not None
    # Reconstruct expected chain
    expected = base_seed + intermediate
    assert result == expected


def test_verify_nested_seed_max_steps_limit():
    N = 1
    seed = b"s"
    chain = [seed]
    current = seed
    for _ in range(1000):
        current = minihelix.G(current, N)
        chain.append(current)
    target = minihelix.G(current, N)

    assert not nested_miner.verify_nested_seed(chain, target)
    assert nested_miner.verify_nested_seed(chain, target, max_steps=1001)
