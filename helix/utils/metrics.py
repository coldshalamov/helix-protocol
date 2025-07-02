def compression_ratio(event: dict) -> float:
    original = event["header"]["microblock_size"] * len(event["seeds"])
    compressed = sum(len(s) for s in event["seeds"] if s)
    return round(1.0 - compressed / original, 4)
