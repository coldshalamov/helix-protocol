# helix_cli.py - Fully merged CLI interface for the Helix protocol

import argparse
import json
import os
import time
import hashlib
import socket
import base64
import threading
from pathlib import Path
import importlib

from . import (
    event_manager,
    minihelix,
    miner,
    nested_miner,
    signature_utils,
    betting_interface,
    helix_node,
)
from .ledger import load_balances, save_balances, get_total_supply, compression_stats
from .gossip import GossipNode, LocalGossipNetwork
from .blockchain import load_chain, get_chain_tip


def cmd_view_chain(args: argparse.Namespace) -> None:
    """Print a brief summary of the local chain."""
    base = Path(args.data_dir)
    chain_path = base / "chain.json"
    blocks = load_chain(str(chain_path))
    if not blocks:
        print("No chain data found")
        return

    events_dir = base / "events"
    for idx, block in enumerate(blocks):
        # determine event identifier
        evt_ids = (
            block.get("event_ids")
            or block.get("events")
            or block.get("event_id")
            or []
        )
        if isinstance(evt_ids, list):
            evt_id = evt_ids[0] if evt_ids else ""
        else:
            evt_id = evt_ids

        ts = block.get("timestamp", 0)

        micro_count = 0
        if evt_id:
            evt_path = events_dir / f"{evt_id}.json"
            if evt_path.exists():
                try:
                    evt = event_manager.load_event(str(evt_path))
                    micro_count = len(evt.get("microblocks", []))
                except Exception:
                    micro_count = 0

        print(f"{idx} {evt_id} {ts} {micro_count}")

    print(f"Total blocks: {len(blocks)}")


def doctor(args: argparse.Namespace) -> None:
    """Check whether required files and dependencies exist."""
    paths = [
        "data/events",
        "data/balances.json",
        "data/blockchain.jsonl",
        "wallet.json",
        "requirements.txt",
    ]
    missing = False
    for p in paths:
        if not Path(p).exists():
            print(f"Missing: {p}")
            missing = True
    try:
        importlib.import_module("nacl")
    except Exception:
        print("Missing: nacl")
        missing = True
    if not missing:
        print("System check passed.")

from .config import GENESIS_HASH

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

def cmd_export_wallet(args: argparse.Namespace) -> None:
    pub, priv = signature_utils.load_keys(args.wallet)
    balances = load_balances(str(args.balances))
    data = {
        "public_key": pub,
        "private_key": priv,
        "balance": balances.get(pub, 0),
    }
    encoded = base64.b64encode(json.dumps(data).encode("utf-8")).decode("ascii")
    print(encoded)

def cmd_import_wallet(args: argparse.Namespace) -> None:
    raw = base64.b64decode(args.data)
    info = json.loads(raw.decode("utf-8"))
    pub = info["public_key"]
    priv = info["private_key"]
    balance = info.get("balance", 0)
    signature_utils.save_keys(args.wallet, pub, priv)
    balances = load_balances(str(args.balances))
    balances[pub] = balance
    save_balances(balances, str(args.balances))

def cmd_show_balance(args: argparse.Namespace) -> None:
    pub, _ = signature_utils.load_keys(args.wallet)
    balances = load_balances(str(args.balances))
    print(balances.get(pub, 0))


<<<<<<< codex/expand-helix_cli.py-with-subcommands
def cmd_submit(args: argparse.Namespace) -> None:
    """Create a new statement event and save it."""

    pub, priv = signature_utils.load_keys("wallet.json")
    event = event_manager.create_event(
        args.statement,
        microblock_size=args.microblock_size,
        private_key=priv,
    )
    event_manager.save_event(event, "data/events")
    print(event["header"]["statement_id"])


def cmd_mine(args: argparse.Namespace) -> None:
    """Mine all microblocks for the specified event."""

    evt_path = Path("data/events") / f"{args.statement_id}.json"
    if not evt_path.exists():
        raise SystemExit("Event not found")
    event = event_manager.load_event(str(evt_path))
    for idx, block in enumerate(event.get("microblocks", [])):
        if event.get("seeds", [None])[idx] is not None:
            continue
        seed = minihelix.mine_seed(block)
        if seed is None:
            continue
        event["seeds"][idx] = [seed.hex()]
        event_manager.mark_mined(event, idx)
    event_manager.save_event(event, "data/events")


def cmd_finalize(args: argparse.Namespace) -> None:
    """Finalize an event and append it to the chain."""

    path = Path("data/events") / f"{args.statement_id}.json"
    if not path.exists():
        raise SystemExit("Event not found")
    event = event_manager.load_event(str(path))
    node = helix_node.HelixNode(
        events_dir="data/events",
        balances_file="data/balances.json",
        chain_file="data/blockchain.jsonl",
        network=LocalGossipNetwork(),
        node_id="FINALIZER",
    )
    node.finalize_event(event)
    print("Event finalized")


def cmd_view_tip(args: argparse.Namespace) -> None:
    """Display the current blockchain tip."""

    tip = get_chain_tip("data/blockchain.jsonl")
    print(tip)


def cmd_balance(args: argparse.Namespace) -> None:
    """Print wallet HLX balance."""

    pub, _ = signature_utils.load_keys("wallet.json")
    balances = load_balances("data/balances.json")
    print(balances.get(pub, 0))


def cmd_sync(args: argparse.Namespace) -> None:
    """Run a live node that syncs and mines blocks."""

    node = helix_node.HelixNode(
        events_dir="data/events",
        balances_file="data/balances.json",
        chain_file="data/blockchain.jsonl",
        network=LocalGossipNetwork(),
        node_id="SYNC",
    )
    threading.Thread(target=node._message_loop, daemon=True).start()
    if hasattr(node, "start_sync_loop"):
        node.start_sync_loop()


def cmd_doctor(args: argparse.Namespace) -> None:
    """Verify local Helix setup."""

    required = [
        Path("data/events"),
        Path("data/balances.json"),
        Path("data/blockchain.jsonl"),
        Path("wallet.json"),
        Path("requirements.txt"),
    ]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        for m in missing:
            print(f"Missing: {m}")
    else:
        print("System check passed.")
=======
def place_bet(args: argparse.Namespace) -> None:
    """Place a signed YES/NO bet on a statement."""
    wallet_path = Path("wallet.json")
    if not wallet_path.exists():
        raise SystemExit("wallet.json not found")

    with open(wallet_path, "r", encoding="utf-8") as fh:
        wallet = json.load(fh)

    choice = args.choice.upper()
    if choice not in {"YES", "NO"}:
        raise SystemExit("choice must be YES or NO")

    signing_key = signature_utils.load_private_key(wallet["private"])

    bet = {
        "event_id": args.statement_id,
        "public_key": wallet["public"],
        "choice": choice,
        "amount": int(args.amount),
    }
    payload = json.dumps(bet, sort_keys=True).encode("utf-8")
    signature = signing_key.sign(payload).signature.hex()
    bet["signature"] = signature

    try:
        betting_interface.record_bet(bet)
        print("Bet submitted")
    except Exception as exc:
        print(f"Bet submission failed: {exc}")
>>>>>>> main


def cmd_verify_statement(args: argparse.Namespace) -> None:
    """Verify mined event integrity."""

    path = Path(args.path)
    if not path.exists():
        raise SystemExit("Event file not found")

    event = event_manager.load_event(str(path))
    ok = event_manager.verify_statement(event)

    statement = event_manager.reassemble_microblocks(event.get("microblocks", []))
    digest = hashlib.sha256(statement.encode("utf-8")).hexdigest()
    expected = event.get("header", {}).get("statement_id")

    if ok and digest == expected:
        print("Verification succeeded")
    else:
        print("Verification failed")

def cmd_token_stats(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"

    minted = 0.0
    burned = 0.0

    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            event = event_manager.load_event(str(path))
            rewards = event.get("rewards", [])
            refunds = event.get("refunds", [])
            minted += sum(rewards) - sum(refunds)
            burned += float(event.get("header", {}).get("gas_fee", 0))

    supply = minted - burned

    print(f"Total HLX Supply: {supply:.4f}")
    print(f"Burned from Gas: {burned:.4f}")
    print(f"HLX Minted via Compression: {minted:.4f}")
    print("Token Velocity: N/A")

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helix",
        description="Command line interface for the Helix protocol",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="Check system health")
    doctor_parser.set_defaults(func=doctor)

    p_bench = sub.add_parser("mine-benchmark", help="Benchmark nested mining")
    p_bench.add_argument("--depth", type=int, default=4, help="Max nesting depth")
    p_bench.set_defaults(func=cmd_mine_benchmark)

    p_peers = sub.add_parser("view-peers", help="Display peer reachability")
    p_peers.add_argument("--peers-file", default="peers.json", help="Peers file path")
    p_peers.set_defaults(func=cmd_view_peers)

    p_export = sub.add_parser("export-wallet", help="Export wallet keys and balance")
    p_export.add_argument("--wallet", required=True, help="Wallet file")
    p_export.add_argument("--balances", required=True, help="Balances file")
    p_export.set_defaults(func=cmd_export_wallet)

    p_import = sub.add_parser("import-wallet", help="Import wallet keys and balance")
    p_import.add_argument("data", help="Base64 wallet backup")
    p_import.add_argument("--wallet", required=True, help="Wallet file")
    p_import.add_argument("--balances", required=True, help="Balances file")
    p_import.set_defaults(func=cmd_import_wallet)

    p_verify = sub.add_parser("verify-statement", help="Verify a finalized statement")
    p_verify.add_argument("path", help="Path to event JSON file")
    p_verify.set_defaults(func=cmd_verify_statement)

    p_stats = sub.add_parser("token-stats", help="Display token supply stats")
    p_stats.add_argument("--data-dir", default="data", help="Data directory")
    p_stats.set_defaults(func=cmd_token_stats)

    p_balance = sub.add_parser("show-balance", help="Show wallet HLX balance")
    p_balance.add_argument("--wallet", required=True, help="Wallet file")
    p_balance.add_argument("--balances", required=True, help="Balances file")
    p_balance.set_defaults(func=cmd_show_balance)

    bet_parser = sub.add_parser("bet", help="Place a YES or NO bet")
    bet_parser.add_argument("statement_id", help="Statement ID")
    bet_parser.add_argument("choice", help="YES or NO")
    bet_parser.add_argument("amount", type=int, help="Amount in HLX")
    bet_parser.set_defaults(func=place_bet)

    p_chain = sub.add_parser("view-chain", help="Display blockchain summary")
    p_chain.add_argument("--data-dir", default="data", help="Data directory")
    p_chain.set_defaults(func=cmd_view_chain)

    p_submit = sub.add_parser("submit", help="Create and save a new statement")
    p_submit.add_argument("statement", help="Statement text")
    p_submit.add_argument("--microblock-size", type=int, default=3, help="Microblock size")
    p_submit.set_defaults(func=cmd_submit)

    p_mine = sub.add_parser("mine", help="Mine microblocks for an event")
    p_mine.add_argument("statement_id", help="Statement identifier")
    p_mine.set_defaults(func=cmd_mine)

    p_final = sub.add_parser("finalize", help="Finalize an event")
    p_final.add_argument("statement_id", help="Statement identifier")
    p_final.set_defaults(func=cmd_finalize)

    p_tip = sub.add_parser("view", help="Show blockchain tip")
    p_tip.set_defaults(func=cmd_view_tip)

    p_bal = sub.add_parser("balance", help="Show wallet balance")
    p_bal.set_defaults(func=cmd_balance)

    sub.add_parser("sync", help="Run a syncing node").set_defaults(func=cmd_sync)

    sub.add_parser("doctor", help="Verify setup").set_defaults(func=cmd_doctor)

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
    "cmd_export_wallet",
    "cmd_import_wallet",
    "cmd_verify_statement",
    "cmd_show_balance",
    "place_bet",
    "cmd_view_chain",
<<<<<<< codex/expand-helix_cli.py-with-subcommands
    "cmd_submit",
    "cmd_mine",
    "cmd_finalize",
    "cmd_view_tip",
    "cmd_balance",
    "cmd_sync",
    "cmd_doctor",
=======
    "doctor",
>>>>>>> main
]
