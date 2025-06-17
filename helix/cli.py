import argparse
import hashlib
import json
import socket
from pathlib import Path

from . import (
    event_manager,
    nested_miner,
    betting_interface,
    signature_utils,
    merkle_utils,
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

    missed: list[str] = []
    invalid: list[str] = []
    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            ev = event_manager.load_event(str(path))
            eid = ev.get("header", {}).get("statement_id", path.stem)
            for idx, block in enumerate(ev.get("microblocks", [])):
                seed = ev.get("seeds", [None])[idx]
                if seed is None:
                    missed.append(f"{eid}:{idx}")
                else:
                    try:
                        if not event_manager.verify_seed_chain(seed, block):
                            invalid.append(f"{eid}:{idx}")
                    except Exception:
                        invalid.append(f"{eid}:{idx}")
    if missed:
        print("missed microblocks:")
        for m in missed:
            print(m)
    if invalid:
        print("invalid seeds:")
        for m in invalid:
            print(m)


def cmd_mine(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    path = events_dir / f"{args.event_id}.json"
    if not path.exists():
        raise SystemExit("Event not found")
    event = event_manager.load_event(str(path))
    for idx, block in enumerate(event.get("microblocks", [])):
        if event.get("seeds", [None])[idx] is not None:
            continue
        result = nested_miner.find_nested_seed(block)
        if result is None:
            print(f"No seed found for block {idx}")
            continue
        chain, _depth = result
        if not nested_miner.verify_nested_seed(chain, block):
            print(f"Verification failed for block {idx}")
            continue
        event_manager.accept_mined_seed(event, idx, chain)
    event_manager.save_event(event, str(events_dir))


def cmd_remine_microblock(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    path = events_dir / f"{args.event_id}.json"
    if not path.exists():
        raise SystemExit("Event not found")
    event = event_manager.load_event(str(path))
    block = event["microblocks"][args.index]
    result = nested_miner.find_nested_seed(block)
    if result is None:
        print("No seed found")
        return
    chain, _depth = result
    if not nested_miner.verify_nested_seed(chain, block):
        print("Verification failed")
        return
    if event.get("seeds", [None])[args.index] is not None and not args.force:
        print("seed already exists; use --force to replace")
    else:
        event_manager.accept_mined_seed(event, args.index, chain)
        event_manager.save_event(event, str(events_dir))


def cmd_reassemble(args: argparse.Namespace) -> None:
    if args.path:
        event = event_manager.load_event(args.path)
    else:
        events_dir = Path(args.data_dir) / "events"
        event_path = events_dir / f"{args.event_id}.json"
        event = event_manager.load_event(str(event_path))
    statement = event_manager.reassemble_microblocks(event["microblocks"])
    digest = event_manager.sha256(statement.encode("utf-8"))
    expected = event.get("header", {}).get("statement_id")
    if digest != expected:
        raise SystemExit("SHA-256 mismatch")
    author = event.get("originator_pub")
    if author:
        print(f"Author: {author}")
    for idx, seed in enumerate(event.get("seeds", [])):
        length = len(seed) if seed is not None else 0
        print(f"Block {idx}: seed_len={length}")
    print(statement)


def cmd_verify_statement(args: argparse.Namespace) -> None:
    """Verify and output a finalized statement."""
    events_dir = Path(args.data_dir) / "events"
    path = events_dir / f"{args.statement_hash}.json"
    if not path.exists():
        raise SystemExit("Event not found")

    event = event_manager.load_event(str(path))

    blocks = event.get("microblocks", [])
    seeds = event.get("seeds", [])

    if len(blocks) != len(seeds) or any(s is None for s in seeds):
        raise SystemExit("missing mined seeds")

    for idx, block in enumerate(blocks):
        seed_chain = seeds[idx]
        if not event_manager.verify_seed_chain(seed_chain, block):
            raise SystemExit(f"invalid seed for block {idx}")

    root, _tree = merkle_utils.build_merkle_tree(blocks)
    hdr_root = event.get("header", {}).get("merkle_root")
    if isinstance(hdr_root, str):
        hdr_root = bytes.fromhex(hdr_root)
    if hdr_root != root:
        raise SystemExit("Merkle root mismatch")

    statement = event_manager.reassemble_microblocks(blocks)
    digest = event_manager.sha256(statement.encode("utf-8"))
    if digest != args.statement_hash:
        raise SystemExit("SHA-256 mismatch")

    print(statement)


def cmd_token_stats(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    total = get_total_supply(str(events_dir))
    print(f"Total HLX Issued: {total:.4f}")


def cmd_view_chain(args: argparse.Namespace) -> None:
    base = Path(args.data_dir)
    if args.path:
        chain_path = Path(args.path)
    else:
        chain_path = base / "blockchain.jsonl"
        if not chain_path.exists():
            alt = base / "chain.json"
            if alt.exists():
                chain_path = alt
    blocks = load_chain(str(chain_path))
    if not blocks:
        print("No chain data found")
        return
    for height, block in enumerate(blocks):
        bid = block.get("id") or block.get("block_id")
        events = block.get("events") or block.get("event_ids") or []
        if isinstance(events, str):
            events_list = [events]
        else:
            events_list = events
        ts = block.get("timestamp")
        miner = block.get("miner")
        evts = ",".join(events_list)
        print(f"{height} {bid} {evts} {ts} {miner}")


def cmd_view_event(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event_path = events_dir / f"{args.event_id}.json"
    if not event_path.exists():
        raise SystemExit("Event not found")

    event = event_manager.load_event(str(event_path))

    mined = sum(1 for m in event.get("mined_status", []) if m)
    total = event.get("header", {}).get("block_count", len(event.get("microblocks", [])))

    status = "open"
    if event.get("is_closed"):
        status = "resolved" if "payouts" in event else "closed"

    merkle_root = event.get("header", {}).get("merkle_root")

    print(f"Statement: {event.get('statement', '')}")
    print(f"Status: {status}")
    print(f"Microblocks: {mined}/{total}")
    if merkle_root is not None:
        print(f"Merkle Root: {merkle_root}")
    else:
        print("Merkle Root: None")

    print("Microblock Details:")
    tree = event.get("merkle_tree", [])
    for idx, block in enumerate(event.get("microblocks", [])):
        mined_flag = event.get("mined_status", [False])[idx]
        print(f"  {idx}: {block.hex()} mined={mined_flag}")
        seed = event.get("seeds", [None])[idx]
        if seed is not None:
            if isinstance(seed, (bytes, bytearray)):
                chain = nested_miner._decode_chain(seed, len(block))
                chain_hex = [s.hex() for s in chain]
            else:
                chain_hex = [s.hex() for s in seed]
            valid_seed = event_manager.verify_seed_chain(seed, block)
            print(f"    Seed Chain: {chain_hex}")
            print(f"    Seed Valid: {valid_seed}")
        else:
            print("    Seed Chain: None")
        if merkle_root is not None and tree:
            proof = merkle_utils.generate_merkle_proof(idx, tree)
            valid_proof = merkle_utils.verify_merkle_proof(block, proof, merkle_root, idx)
            print(f"    Merkle Proof: {valid_proof}")
        else:
            print("    Merkle Proof: False")

    bets = event.get("bets", {})
    yes_total = sum(b.get("amount", 0) for b in bets.get("YES", []))
    no_total = sum(b.get("amount", 0) for b in bets.get("NO", []))
    print(f"Votes: YES={yes_total} NO={no_total}")
    if "payouts" in event:
        resolution = "YES" if yes_total > no_total else "NO"
        print(f"Resolution: {resolution}")
        print("Rewards:")
        print(json.dumps(event.get("payouts"), indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="helix-cli")
    parser.add_argument("--data-dir", default="data", help="Directory for node data")
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser("doctor", help="Check local node files")
    p_doc.set_defaults(func=cmd_doctor)

    p_mine = sub.add_parser("mine", help="Mine microblocks for an event")
    p_mine.add_argument("event_id", help="Event identifier")
    p_mine.set_defaults(func=cmd_mine)

    p_rem = sub.add_parser("remine-microblock", help="Retry mining a single microblock")
    p_rem.add_argument("--event-id", required=True, help="Event identifier")
    p_rem.add_argument("--index", type=int, required=True, help="Block index")
    p_rem.add_argument("--force", action="store_true", help="Replace existing seed")
    p_rem.set_defaults(func=cmd_remine_microblock)

    p_reasm = sub.add_parser("reassemble", help="Reassemble statement from event")
    group = p_reasm.add_mutually_exclusive_group(required=True)
    group.add_argument("--event-id", help="Event identifier")
    group.add_argument("--path", help="Path to event JSON file")
    p_reasm.set_defaults(func=cmd_reassemble)

    sub.add_parser("token-stats", help="Show total token supply").set_defaults(func=cmd_token_stats)

    p_chain = sub.add_parser("view-chain", help="Show blockchain summary")
    p_chain.add_argument("--path", help="Path to chain JSON file")
    p_chain.set_defaults(func=cmd_view_chain)

    p_view = sub.add_parser("view-event", help="Show event details")
    p_view.add_argument("event_id", help="Event identifier")
    p_view.set_defaults(func=cmd_view_event)

    p_verify = sub.add_parser(
        "verify-statement", help="Verify statement integrity"
    )
    p_verify.add_argument("statement_hash", help="Statement hash")
    p_verify.set_defaults(func=cmd_verify_statement)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


__all__ = [
    "main",
    "build_parser",
    "cmd_doctor",
    "cmd_mine",
    "cmd_reassemble",
    "cmd_token_stats",
    "cmd_view_chain",
    "cmd_remine_microblock",
    "cmd_view_event",
    "cmd_verify_statement",
]
