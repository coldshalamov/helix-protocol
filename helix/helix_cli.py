import argparse
import json
import os
import time
import hashlib
from pathlib import Path

from . import event_manager
from . import minihelix
from . import miner
from . import nested_miner
from . import signature_utils
from . import betting_interface
from .ledger import load_balances, get_total_supply, compression_stats
from .gossip import GossipNode, LocalGossipNetwork
from .blockchain import load_chain
from . import helix_node
from .config import GENESIS_HASH

# [... everything else remains the same until the conflict block near the end ...]

def cmd_mine_benchmark(args: argparse.Namespace) -> None:
    """Benchmark mining a random microblock."""
    size = event_manager.DEFAULT_MICROBLOCK_SIZE
    block = os.urandom(size)

    calls = 0
    orig_mh_G = minihelix.G
    orig_nm_G = nested_miner.G

    def counting_G(seed: bytes, N: int = size) -> bytes:
        nonlocal calls
        calls += 1
        return orig_mh_G(seed, N)

    minihelix.G = counting_G
    nested_miner.G = counting_G
    start = time.perf_counter()
    try:
        result = nested_miner.hybrid_mine(block, max_depth=args.depth)
    finally:
        minihelix.G = orig_mh_G
        nested_miner.G = orig_nm_G
    elapsed = time.perf_counter() - start

    if result is None:
        print(f"No seed found (G() calls={calls}, time={elapsed:.2f}s)")
        return

    seed, depth = result
    ratio = (len(block) / len(seed)) if len(seed) < len(block) else 1.0
    print(f"Time: {elapsed:.2f}s")
    print(f"G() calls: {calls}")
    if len(seed) < len(block):
        print(f"Compression ratio: {ratio:.2f}x")
    else:
        print("Compression ratio: 1.00x")
    print(f"Seed length: {len(seed)} depth={depth}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Diagnose local node files and print status information."""
    base = Path(args.data_dir)

    # Genesis block check
    genesis = base / "genesis.json"
    if not genesis.exists():
        print("genesis.json not found")
    else:
        digest = hashlib.sha256(genesis.read_bytes()).hexdigest()
        if digest != GENESIS_HASH:
            print("hash mismatch")

    # Microblock counts
    events_dir = base / "events"
    mined = 0
    unmined = 0
    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            ev = event_manager.load_event(str(path))
            statuses = ev.get("mined_status", [False] * len(ev.get("microblocks", [])))
            mined_blocks = sum(1 for m in statuses if m)
            total_blocks = ev.get("header", {}).get(
                "block_count", len(ev.get("microblocks", []))
            )
            mined += mined_blocks
            unmined += total_blocks - mined_blocks
    print(f"Mined microblocks: {mined}")
    print(f"Unmined microblocks: {unmined}")

    # Wallet and balance
    wallet = base / "wallet.txt"
    if wallet.exists():
        try:
            pub, _ = signature_utils.load_keys(str(wallet))
            balances_file = base / "balances.json"
            balances = load_balances(str(balances_file))
            balance = balances.get(pub, 0)
            print(f"Wallet balance: {balance}")
        except Exception:
            print("wallet inaccessible")
    else:
        print("no wallet file")

    # Chain info
    chain_path = base / "blockchain.jsonl"
    if not chain_path.exists():
        alt = base / "chain.json"
        if alt.exists():
            chain_path = alt
    blocks = load_chain(str(chain_path))
    if blocks:
        height = len(blocks) - 1
        ts = blocks[-1].get("timestamp")
        print(f"Latest block: {height} {ts}")
    else:
        print("No chain data found")


# End of file export list
__all__ = [
    "main",
    "build_parser",
    "cmd_init",
    "initialize_genesis_block",
    "cmd_doctor",
    "cmd_token_stats",
    "cmd_mine_benchmark",
    "cmd_submit_and_mine",
]
