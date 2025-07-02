import hashlib
from typing import List, Tuple


def _hash(data: bytes) -> bytes:
    """Return SHA256 digest of ``data``."""
    return hashlib.sha256(data).digest()


def build_merkle_tree(microblocks: List[bytes]) -> Tuple[bytes, List[List[bytes]]]:
    """Return the root and full tree from binary-digest Merkle structure."""
    if not microblocks:
        return b"", []

    level: List[bytes] = [_hash(b) for b in microblocks]
    tree: List[List[bytes]] = [level]

    while len(level) > 1:
        next_level: List[bytes] = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(_hash(left + right))
        tree.append(next_level)
        level = next_level

    root = level[0]
    return root, tree


def generate_merkle_proof(index: int, tree: List[List[bytes]]) -> List[bytes]:
    """Return the Merkle proof for the leaf at ``index`` using ``tree``."""
    proof: List[bytes] = []
    for level in tree[:-1]:
        sibling_idx = index ^ 1
        if sibling_idx < len(level):
            proof.append(level[sibling_idx])
        index //= 2
    return proof


def verify_merkle_proof(leaf: bytes, proof: List[bytes], root: bytes, index: int) -> bool:
    """Return ``True`` if ``proof`` authenticates ``leaf`` against ``root``."""
    computed = _hash(leaf)
    for sibling in proof:
        if index % 2 == 0:
            computed = _hash(computed + sibling)
        else:
            computed = _hash(sibling + computed)
        index //= 2
    return computed == root


__all__ = [
    "build_merkle_tree",
    "generate_merkle_proof",
    "verify_merkle_proof",
]
