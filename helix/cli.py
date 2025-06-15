import argparse
import hashlib
import json
from pathlib import Path

from .helix_node import HelixNode
from .gossip import LocalGossipNetwork
from .network import TCPGossipTransport, SocketGossipNetwork, Peer
from . import signature_utils
from .config import GENESIS_HASH
import threading
import time
from . import event_manager
from . import signature_utils as su
from . import nested_miner
from . import minihelix
from . import betting_interface
from .ledger import load_balances, compression_stats

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

def cmd_status(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    balances_file = Path(args.data_dir) / "balances.json"
    node = HelixNode(events_dir=str(events_dir), balances_file=str(balances_file))
    known_peers = len(node.known_peers)
    total_events = len(node.events)
    finalized_events = sum(1 for e in node.events.values() if e.get("is_closed"))
    saved, hlx = compression_stats(str(events_dir))
    balances = load_balances(str(balances_file))
    print(f"Known peers: {known_peers}")
    print(f"Events loaded: {total_events}")
    print(f"Events finalized: {finalized_events}")
    print(f"Compression saved: {saved} bytes")
    print(f"HLX awarded: {hlx}")
    print("Balances:")
    print(json.dumps(balances, indent=2))

def _load_event(path: Path) -> dict:
    return event_manager.load_event(str(path))

def cmd_start_node(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    balances_file = Path(args.data_dir) / "balances.json"
    node = HelixNode(
        events_dir=str(events_dir),
        balances_file=str(balances_file),
        genesis_file=_default_genesis_file(),
    )
    print(f"Starting node on port {args.port} with data dir {args.data_dir}")
    node.run()

def cmd_submit_statement(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    private_key = None
    if args.keyfile:
        _, private_key = su.load_keys(args.keyfile)
    microblock_size = (
        args.microblock_size
        if args.microblock_size is not None
        else event_manager.DEFAULT_MICROBLOCK_SIZE
    )
    event = event_manager.create_event(
        args.statement,
        microblock_size=microblock_size,
        private_key=private_key,
    )
    path = event_manager.save_event(event, str(events_dir))
    print(f"Statement saved to {path}")
    print(f"Statement ID: {event['header']['statement_id']}")

def cmd_mine(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event_path = events_dir / f"{args.event_id}.json"
    if not event_path.exists():
        print("Event not found")
        return
    event = _load_event(event_path)
    for idx, block in enumerate(event["microblocks"]):
        if event["mined_status"][idx]:
            continue
        offset = 0
        while True:
            result = nested_miner.find_nested_seed(
                block,
                start_nonce=offset,
                attempts=10_000,
            )
            offset += 10_000
            if result is None:
                continue
            encoded = result
            if not nested_miner.verify_nested_seed(encoded, block):
                continue
            event_manager.accept_mined_seed(event, idx, encoded)
            print(f"\u2714 Block {idx} mined")
            break
    event_manager.save_event(event, str(events_dir))

def cmd_remine_microblock(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event_path = events_dir / f"{args.event_id}.json"
    if not event_path.exists():
        print("Event not found")
        return
    event = _load_event(event_path)
    if event.get("is_closed"):
        print("Event is closed")
        return
    index = args.index
    if index < 0 or index >= len(event["microblocks"]):
        print("Invalid index")
        return
    if event["mined_status"][index] and not args.force:
        print("Microblock already mined; use --force to replace")
        return
    block = event["microblocks"][index]
    result = nested_miner.find_nested_seed(block)
    if result is None:
        print(f"No seed found for block {index}")
        return
    encoded = result
    if not nested_miner.verify_nested_seed(encoded, block):
        print(f"Seed verification failed for block {index}")
        return
    event_manager.accept_mined_seed(event, index, encoded)
    event_manager.save_event(event, str(events_dir))
    print(f"Remined microblock {index}")
