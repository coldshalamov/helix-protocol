# helix_cli.py - Fully merged CLI interface for the Helix protocol

import argparse
import json
import os
import time
import hashlib
import socket
from pathlib import Path

from . import (
    event_manager,
    minihelix,
    miner,
    nested_miner,
    signature_utils,
    betting_interface,
    helix_node,
)
from .ledger import load_balances, get_total_supply, compression_stats
from .gossip import GossipNode, LocalGossipNetwork
from .blockchain import load_chain
from .config import GENESIS_HASH

# ----------------------------- Commands -----------------------------

def cmd_mine_benchmark(args: argparse.Namespace) -> None:
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
    print(f"Compression ratio: {ratio:.2f}x")
    print(f"Seed length: {len(seed)} depth={depth}")


def cmd_view_peers(args: argparse.Namespace) -> None:
    path = Path(args.peers_file)
    if not path.exists():
        raise SystemExit(f"Peers file not found: {path}")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            peers = json.load(fh)
    except Exception as exc:
        raise SystemExit(f"Failed to read peers file: {exc}")

    if not isinstance(peers, list):
        raise SystemExit("Invalid peers file format")

    for peer in peers:
        if not isinstance(peer, dict):
            continue
        node_id = peer.get("node_id", "")
        host = peer.get("host")
        port = peer.get("port")
        last_seen = float(peer.get("last_seen", 0.0))
        reachable = False
        if host and isinstance(port, int):
            try:
                with socket.create_connection((host, int(port)), timeout=1):
                    pass
                reachable = True
            except Exception:
                reachable = False
        print(f"{node_id} last_seen={last_seen} reachable={reachable}")


def cmd_token_stats(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    total_hlx = get_total_supply(str(events_dir))
    mined_events = 0
    total_reward = 0.0

    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            event = event_manager.load_event(str(path))
            rewards = event.get("rewards", [])
            refunds = event.get("refunds", [])
            reward = sum(rewards) - sum(refunds)
            if event.get("is_closed"):
                mined_events += 1
                total_reward += reward

    avg_reward = total_reward / mined_events if mined_events else 0.0

    print(f"Total HLX Supply: {total_hlx:.4f}")
    print(f"Total Mined Events: {mined_events}")
    print(f"Average Reward/Event: {avg_reward:.4f}")

# ----------------------------- Parser -----------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helix",
        description="Command line interface for the Helix protocol",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # Benchmark mining
    p_bench = sub.add_parser("mine-benchmark", help="Benchmark nested mining")
    p_bench.add_argument("--depth", type=int, default=4, help="Max nesting depth")
    p_bench.set_defaults(func=cmd_mine_benchmark)

    # View peers
    p_peers = sub.add_parser("view-peers", help="Display peer reachability")
    p_peers.add_argument("--peers-file", default="peers.json", help="Peers file path")
    p_peers.set_defaults(func=cmd_view_peers)

    # Token stats
    p_stats = sub.add_parser("token-stats", help="Display total HLX stats")
    p_stats.add_argument("--data-dir", default="data", help="Data directory")
    p_stats.set_defaults(func=cmd_token_stats)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


__all__ = [
    "main",
    "build_parser",
    "cmd_token_stats",
    "cmd_mine_benchmark",
    "cmd_view_peers",
]
