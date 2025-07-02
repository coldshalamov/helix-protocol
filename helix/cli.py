import argparse
import hashlib
import json
import socket
from pathlib import Path

from . import (
    event_manager,
    betting_interface,
    signature_utils,
    helix_cli,
)
from .ledger import load_balances, compression_stats, get_total_supply
from .config import GENESIS_HASH
from .blockchain import load_chain


def cmd_doctor(args: argparse.Namespace) -> None:
    base = Path(args.data_dir)
    genesis = base / "genesis.json"
    if not genesis.exists():
        print("genesis.json not found")
    else:
        digest = hashlib.sha256(genesis.read_bytes()).hexdigest()
        if digest != GENESIS_HASH:
            print("hash mismatch")
    wallet = base / "wallet.txt"
    if not wallet.exists():
        print("no wallet file")
    events_dir = base / "events"
    unmined: list[str] = []
    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            ev = event_manager.load_event(str(path))
            if not ev.get("is_closed"):
                unmined.append(ev.get("header", {}).get("statement_id", path.stem))
    if unmined:
        print("unmined events detected")
        for eid in unmined:
            print(eid)

    peers_file = base / "peers.json"
    peers: list[dict] = []
    if not peers_file.exists():
        print("no peers file")
    else:
        try:
            peers = json.loads(peers_file.read_text())
        except Exception:
            print("peer list invalid")
            peers = []
        if not peers:
            print("no peers configured")

    chain_file = base / "blockchain.jsonl"
    chain = load_chain(str(chain_file)) if chain_file.exists() else []
    local_height = len(chain)
    mismatch = False
    if peers:
        for peer in peers:
            host = peer.get("host")
            port = peer.get("port")
            if not host or not isinstance(port, int):
                continue
            try:
                with socket.create_connection((host, port), timeout=1) as sock:
                    sock.sendall(json.dumps({"type": "GET_HEIGHT"}).encode("utf-8"))
                    data = sock.recv(65536)
                reply = json.loads(data.decode("utf-8"))
                height = int(reply.get("height"))
                if height != local_height:
                    mismatch = True
            except Exception:
                continue
        if mismatch:
            print("block height mismatch with peers")







def cmd_view_chain(args: argparse.Namespace) -> None:
    base = Path(args.data_dir)
    chain_path = base / "chain.json"
    blocks = load_chain(str(chain_path))
    if not blocks:
        print("No chain data found")
        return
    events_dir = base / "events"
    for idx, block in enumerate(blocks):
        bid = block.get("block_id") or block.get("id", "")
        evt_ids = block.get("event_ids") or block.get("events") or []
        if isinstance(evt_ids, list):
            evt_field = ",".join(evt_ids)
        else:
            evt_field = evt_ids
        ts = block.get("timestamp", 0)
        miner = block.get("miner", "")
        print(f"{idx} {bid} {evt_field} {ts} {miner}")


def cmd_view_event(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    path = events_dir / f"{args.event_id}.json"
    if not path.exists():
        raise SystemExit("Event not found")
    event = event_manager.load_event(str(path))

    statement = event.get("statement", "")
    status = "resolved" if event.get("is_closed") else "open"
    print(f"Statement: {statement}")
    print(f"Status: {status}")
    bets = event.get("bets", {})
    yes = len(bets.get("YES", []))
    no = len(bets.get("NO", []))
    print(f"Votes: YES={yes} NO={no}")
    if status == "resolved":
        yes_total = sum(b.get("amount", 0) for b in bets.get("YES", []))
        no_total = sum(b.get("amount", 0) for b in bets.get("NO", []))
        resolution = "YES" if yes_total >= no_total else "NO"
        print(f"Resolution: {resolution}")
        print("Rewards:")
        payouts = event.get("payouts", {})
        print(json.dumps(payouts))


def cmd_reassemble(args: argparse.Namespace) -> None:
    if args.event_id:
        events_dir = Path(args.data_dir) / "events"
        path = events_dir / f"{args.event_id}.json"
    else:
        path = Path(args.path)
    if not path.exists():
        raise SystemExit("Event not found")
    event = event_manager.load_event(str(path))
    print(event.get("statement", ""))


def cmd_verify_statement(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    path = events_dir / f"{args.event_id}.json"
    if not path.exists():
        raise SystemExit("Event file not found")
    event = event_manager.load_event(str(path))
    _ = event_manager.verify_statement(event)
    print(event.get("statement", ""))


def cmd_token_stats(args: argparse.Namespace) -> None:
    helix_cli.cmd_token_stats(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="helix", description="Legacy CLI")
    parser.add_argument("--data-dir", default="data", help="Data directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doctor = sub.add_parser("doctor", help="Check node state")
    p_doctor.set_defaults(func=cmd_doctor)



    p_reasm = sub.add_parser("reassemble", help="Reassemble statement")
    group = p_reasm.add_mutually_exclusive_group(required=True)
    group.add_argument("--event-id")
    group.add_argument("--path")
    p_reasm.set_defaults(func=cmd_reassemble)

    p_view_evt = sub.add_parser("view-event", help="Display event info")
    p_view_evt.add_argument("event_id")
    p_view_evt.set_defaults(func=cmd_view_event)

    p_chain = sub.add_parser("view-chain", help="Display chain")
    p_chain.set_defaults(func=cmd_view_chain)

    p_verify = sub.add_parser("verify-statement", help="Verify statement")
    p_verify.add_argument("event_id")
    p_verify.set_defaults(func=cmd_verify_statement)

    p_stats = sub.add_parser("token-stats", help="Show token stats")
    p_stats.set_defaults(func=cmd_token_stats)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


__all__ = [
    "main",
    "build_parser",
    "cmd_doctor",
    "cmd_view_chain",
    "cmd_view_event",
    "cmd_reassemble",
    "cmd_verify_statement",
    "cmd_token_stats",
]
