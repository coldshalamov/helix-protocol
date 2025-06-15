import hashlib
from typing import List

def build_merkle_tree(leaves: List[bytes]) -> List[List[bytes]]:
    """Return a full Merkle tree built from ``leaves`` using SHA-256."""
    if not leaves:
        raise ValueError("at least one leaf required")
    level = [hashlib.sha256(l).digest() for l in leaves]
    tree = [level]
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(hashlib.sha256(left + right).digest())
        tree.append(next_level)
        level = next_level
    return tree

def merkle_root(tree: List[List[bytes]]) -> bytes:
    """Return the root hash of ``tree``."""
    return tree[-1][0]

def merkle_proof(tree: List[List[bytes]], index: int) -> List[bytes]:
    """Return the Merkle proof for ``index`` from ``tree``."""
    proof = []
    for level in tree[:-1]:
        sibling_index = index ^ 1
        if sibling_index < len(level):
            proof.append(level[sibling_index])
        else:
            proof.append(level[index])
        index //= 2
    return proof

def verify_merkle_proof(leaf: bytes, proof: List[bytes], root: bytes, index: int) -> bool:
    """Validate ``leaf`` belongs to Merkle tree with ``root`` using ``proof``."""
    h = hashlib.sha256(leaf).digest()
    for sibling in proof:
        if index % 2 == 0:
            h = hashlib.sha256(h + sibling).digest()
        else:
            h = hashlib.sha256(sibling + h).digest()
        index //= 2
    return h == root
