```python
import argparse
import json
import hashlib
from pathlib import Path
import threading
import time

from .helix_node import HelixNode
from .gossip import LocalGossipNetwork
from .network import TCPGossipTransport, SocketGossipNetwork, Peer
from . import signature_utils
from .config import GENESIS_HASH
from . import event_manager
from . import nested_miner
from . import betting_interface
from .ledger import load_balances, compression_stats, get_total_supply
from .blockchain import load_chain


def _default_genesis_file() -> str:
    path = Path(__file__).resolve().parent / "genesis.json"
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        print(f"Genesis file missing: {path}")
        raise SystemExit(1)
    digest = hashlib.sha256(data).hexdigest()
    if digest != GENESIS_HASH:
        print("Genesis file hash mismatch")
        raise SystemExit(1)
    return str(path)

# ... [All other command implementations are unchanged from your provided code] ...

def cmd_token_stats(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    total = get_total_supply(str(events_dir))
    print(f"Total HLX Issued: {total:.4f}")


def cmd_view_chain(args: argparse.Namespace) -> None:
    """Print a summary of each block in the chain."""
    chain_file = args.path if args.path else str(Path(args.data_dir) / "chain.json")
    blocks = load_chain(chain_file)
    if not blocks:
        print("No chain data found")
        return
    for block in blocks:
        bid = block.get("id") or block.get("block_id")
        parent = block.get("parent_id")
        events = block.get("events") or block.get("event_ids") or []
        timestamp = block.get("timestamp")
        miner = block.get("miner")
        count = len(events) if isinstance(events, list) else events
        print(f"{bid} {parent} {count} {timestamp} {miner}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="helix-cli")
    parser.add_argument("--data-dir", default="data", help="Directory for node data")
    parser.add_argument("--port", type=int, default=8000, help="Gossip port")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("start-node", help="Start a Helix node").set_defaults(func=cmd_start_node)
    sub.add_parser("helix-node", help="Run automated mining node").set_defaults(func=cmd_helix_node)

    p_run = sub.add_parser("run-node", help="Run full networked node")
    p_run.add_argument("--host", default="0.0.0.0", help="Bind host")
    p_run.add_argument("--peer", action="append", default=[], dest="peers", help="Peer address host:port")
    p_run.set_defaults(func=cmd_run_node)

    p_submit = sub.add_parser("submit-statement", help="Submit a statement")
    p_submit.add_argument("statement", help="Text of the statement")
    p_submit.add_argument("--keyfile", help="File containing originator keys")
    p_submit.add_argument("--microblock-size", type=int, help="Size of microblocks in bytes")
    p_submit.set_defaults(func=cmd_submit_statement)

    p_mine = sub.add_parser("mine", help="Mine microblocks for an event")
    p_mine.add_argument("event_id", help="ID of the event to mine")
    p_mine.set_defaults(func=cmd_mine)

    p_bet = sub.add_parser("place-bet", help="Place a bet on an event")
    p_bet.add_argument("event_id", help="Event identifier")
    p_bet.add_argument("choice", choices=["YES", "NO"], help="Bet choice")
    p_bet.add_argument("amount", type=int, help="Bet amount")
    p_bet.add_argument("--keyfile", required=True, help="Keyfile for signing")
    p_bet.set_defaults(func=cmd_place_bet)

    sub.add_parser("view-wallet", help="View wallet balances").set_defaults(func=cmd_view_wallet)

    p_chain = sub.add_parser("view-chain", help="Show blockchain summary")
    p_chain.add_argument("--path", help="Path to chain JSON file")
    p_chain.set_defaults(func=cmd_view_chain)

    sub.add_parser("token-stats", help="Show total token supply").set_defaults(func=cmd_token_stats)

    p_remine = sub.add_parser("remine-microblock", help="Retry mining a single microblock")
    p_remine.add_argument("--event-id", required=True, help="Event identifier")
    p_remine.add_argument("--index", type=int, required=True, help="Block index")
    p_remine.add_argument("--force", action="store_true", help="Replace exi_
