#!/usr/bin/env python3
"""Example miner for Helix microblocks."""

import argparse
import os

from helix.miner import find_seed


def main() -> None:
    parser = argparse.ArgumentParser(description="Mine a seed for a target microblock.")
    parser.add_argument("target", help="Hex-encoded target microblock")
    parser.add_argument("--max-seed", type=int, default=16, help="Maximum seed length to try")
    parser.add_argument("--attempts", type=int, default=1_000_000, help="Maximum attempts")
    args = parser.parse_args()

    target_bytes = bytes.fromhex(args.target)
    seed = find_seed(target_bytes, max_seed_len=args.max_seed, attempts=args.attempts)

    if seed is not None:
        print(f"Found seed: {seed.hex()}")
    else:
        print("No seed found in given attempts")


if __name__ == "__main__":
    main()
