from __future__ import annotations

"""Deterministic exhaustive MiniHelix miner.

This module implements an exhaustive search strategy for nested MiniHelix
seeds.  The miner starts from every possible 1- and 2-byte seed and
recursively explores all child seeds as dictated by the output of
:func:`minihelix.G`.
"""

from pathlib import Path
from typing import Iterable, List, Optional

from . import minihelix
from .minihelix import G


def _generate_initial_seeds() -> Iterable[bytes]:
    """Yield all 1- and 2-byte seeds in lexicographic order."""
    for length in (1, 2):
        max_value = 256 ** length
        for i in range(max_value):
            yield i.to_bytes(length, "big")


class ExhaustiveMiner:
    """Stateful exhaustive miner supporting checkpointing."""

    def __init__(
        self,
        target_block: bytes,
        max_depth: int = 500,
        *,
        checkpoint_path: str | None = None,
    ) -> None:
        self.target = target_block
        self.block_size = len(target_block)
        self.max_depth = max_depth
        self.initial_seeds = list(_generate_initial_seeds())
        self.attempts = 0
        self.checkpoint_path = checkpoint_path

    def _load_start_index(self) -> int:
        if not self.checkpoint_path:
            return 0
        path = Path(self.checkpoint_path)
        if path.exists():
            try:
                return int(path.read_text())
            except Exception:
                return 0
        return 0

    def _save_start_index(self, index: int) -> None:
        if not self.checkpoint_path:
            return
        Path(self.checkpoint_path).write_text(str(index))

    def _dfs(self, seed: bytes, depth: int, chain: List[bytes]) -> Optional[List[bytes]]:
        """Depth-first search returning the seed chain or ``None``."""
        self.attempts += 1
        output = G(seed, self.block_size)
        chain.append(seed)
        if output == self.target:
            result = list(chain)
            print(f"Attempts for microblock: {self.attempts}")
            return result
        if depth >= self.max_depth:
            chain.pop()
            return None
        next_len = output[0]
        if next_len == 0 or next_len > self.block_size:
            chain.pop()
            return None
        count = 256 ** next_len
        for i in range(count):
            next_seed = i.to_bytes(next_len, "big")
            result = self._dfs(next_seed, depth + 1, chain)
            if result is not None:
                return result
        chain.pop()
        return None

    def mine(self, start_index: int = 0) -> Optional[List[bytes]]:
        """Search for a compression seed chain starting from ``start_index``."""
        if start_index == 0:
            start_index = self._load_start_index()

        found_index = None
        result = None
        for idx in range(start_index, len(self.initial_seeds)):
            seed = self.initial_seeds[idx]
            result = self._dfs(seed, 1, [])
            if result is not None:
                found_index = idx
                break

        if found_index is not None:
            self._save_start_index(found_index + 1)
        else:
            self._save_start_index(len(self.initial_seeds))

        return result


def exhaustive_mine(
    target_block: bytes,
    *,
    max_depth: int = 500,
    start_index: int = 0,
    checkpoint_path: str | None = None,
) -> Optional[List[bytes]]:
    """Convenience function returning the first valid seed chain."""
    miner = ExhaustiveMiner(
        target_block,
        max_depth=max_depth,
        checkpoint_path=checkpoint_path,
    )
    return miner.mine(start_index=start_index)


__all__ = ["exhaustive_mine", "ExhaustiveMiner"]
