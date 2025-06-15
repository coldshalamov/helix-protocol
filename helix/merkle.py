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


def merkle_root(leaves: Iterable[bytes]) -> bytes:
    nodes = [_hash(leaf) for leaf in leaves]
    if not nodes:
        return b""
    while len(nodes) > 1:
        if len(nodes) % 2 == 1:
            nodes.append(nodes[-1])
        nodes = [_hash(nodes[i] + nodes[i + 1]) for i in range(0, len(nodes), 2)]
    return nodes[0]


def build_merkle_proof(leaves: List[bytes], index: int) -> MerkleProof:
    if index < 0 or index >= len(leaves):
        raise IndexError("leaf index out of range")
    siblings: List[bytes] = []
    hashes = [_hash(leaf) for leaf in leaves]
    idx = index
    while len(hashes) > 1:
        if len(hashes) % 2 == 1:
            hashes.append(hashes[-1])
        sibling_index = idx ^ 1
        siblings.append(hashes[sibling_index])
        idx //= 2
        hashes = [
            _hash(hashes[i] + hashes[i + 1]) for i in range(0, len(hashes), 2)
        ]
    return MerkleProof(siblings=siblings, index=index)


def verify_merkle_proof(leaf: bytes, proof: MerkleProof, root: bytes) -> bool:
    computed = _hash(leaf)
    idx = proof.index
    for sibling in proof.siblings:
        if idx % 2 == 0:
            computed = _hash(computed + sibling)
        else:
            computed = _hash(sibling + computed)
        idx //= 2
    return computed == root
