from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Iterable


@dataclass
class MerkleProof:
    """Proof of membership for a leaf in a Merkle tree."""
    siblings: List[bytes]
    index: int


def _hash(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def build_merkle_tree(leaves: List[bytes]) -> List[List[bytes]]:
    """Return a full Merkle tree built from ``leaves`` using SHA-256."""
    if not leaves:
        raise ValueError("at least one leaf required")
    level = [_hash(leaf) for leaf in leaves]
    tree = [level]
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(_hash(left + right))
        tree.append(next_level)
        level = next_level
    return tree


def merkle_root(tree: List[List[bytes]]) -> bytes:
    """Return the root hash of a Merkle tree."""
    return tree[-1][0]


def merkle_root_from_leaves(leaves: Iterable[bytes]) -> bytes:
    """Convenience method to compute root hash directly from leaves."""
    return merkle_root(build_merkle_tree(list(leaves)))


def merkle_proof(tree: List[List[bytes]], index: int) -> List[bytes]:
    """Return the Merkle proof for ``index`` from a full tree."""
    proof = []
    for level in tree[:-1]:
        sibling_index = index ^ 1
        if sibling_index < len(level):
            proof.append(level[sibling_index])
        else:
            proof.append(level[index])
        index //= 2
    return proof


def build_merkle_proof(leaves: List[bytes], index: int) -> MerkleProof:
    """Build a MerkleProof object for a specific leaf index."""
    if index < 0 or index >= len(leaves):
        raise IndexError("leaf index out of range")
    tree = build_merkle_tree(leaves)
    siblings = merkle_proof(tree, index)
    return MerkleProof(siblings=siblings, index=index)


def verify_merkle_proof(leaf: bytes, proof: MerkleProof | List[bytes], root: bytes, index: int | None = None) -> bool:
    """Validate that ``leaf`` is part of the Merkle tree rooted at ``root``.

    Accepts either a structured ``MerkleProof`` or a raw sibling list with ``index``.
    """
    h = _hash(leaf)
    if isinstance(proof, MerkleProof):
        siblings = proof.siblings
        idx = proof.index
    else:
        if index is None:
            raise ValueError("index must be provided for raw proof list")
        siblings = proof
        idx = index

    for sibling in siblings:
        if idx % 2 == 0:
            h = _hash(h + sibling)
        else:
            h = _hash(sibling + h)
        idx //= 2
    return h == root
