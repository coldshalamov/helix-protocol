def accept_mined_seed(event: Dict[str, Any], index: int, seed_chain: List[bytes], *, miner: Optional[str] = None) -> float:
    """Accept ``seed_chain`` for microblock ``index`` of ``event``.

    ``seed_chain`` contains the starting seed followed by any intermediate
    values.  Its length represents the depth of the nested mining.  The chain
    is verified with :func:`verify_nested_seed` before it is applied.
    """
    seed = seed_chain[0]
    depth = len(seed_chain)

    block = event["microblocks"][index]
    assert nested_miner.verify_nested_seed(seed_chain, block), "invalid seed chain"

    penalty = nesting_penalty(depth)
    reward = reward_for_depth(depth)
    refund = 0.0

    microblock_size = event.get("header", {}).get("microblock_size", DEFAULT_MICROBLOCK_SIZE)
    if len(seed) > microblock_size:
        raise ValueError("seed length exceeds microblock size")

    if event["seeds"][index] is None:
        event["seeds"][index] = seed
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        if "miners" in event:
            event["miners"][index] = miner
        if "refund_miners" in event:
            event["refund_miners"][index] = None
        mark_mined(event, index)
        return 0.0

    old_seed = event["seeds"][index]
    old_depth = event["seed_depths"][index]

    replace = False
    if len(seed) < len(old_seed):
        replace = True
    elif len(seed) == len(old_seed) and depth < old_depth:
        replace = True

    if replace:
        refund = event["rewards"][index] - reward
        event["seeds"][index] = seed
        event["seed_depths"][index] = depth
        event["penalties"][index] = penalty
        event["rewards"][index] = reward
        if "miners" in event:
            old_miner = event["miners"][index]
            event["miners"][index] = miner
        else:
            old_miner = None
        if "refund_miners" in event:
            event["refund_miners"][index] = old_miner
        event["refunds"][index] += refund
        print(
            f"Replaced seed at index {index}: length {len(old_seed)} depth {old_depth} -> length {len(seed)} depth {depth}"
        )

    return refund
