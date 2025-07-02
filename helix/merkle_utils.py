import hashlib
from typing import Iterable, List


def build_merkle_tree(leaves: Iterable[bytes]) -> List[List[str]]:
    """Return a simple hex-digest Merkle tree from ``leaves``."""
    level = [hashlib.sha256(x).hexdigest() for x in leaves]
    tree = [level]
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        next_level = []
        for i in range(0, len(level), 2):
            data = (level[i] + level[i + 1]).encode("utf-8")
            next_level.append(hashlib.sha256(data).hexdigest())
        tree.append(next_level)
        level = next_level
    return tree

__all__ = ["build_merkle_tree"]
