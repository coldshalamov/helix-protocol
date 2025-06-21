```python
import argparse
import hashlib
import json
import socket
from pathlib import Path

from . import (
    event_manager,
    nested_miner,
    exhaustive_miner,
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
        chain = exhaustive_miner.exhaustive_mine(block)
        if chain is None:
            print(f"No seed found for block {idx}")
            continue
        _depth = len(chain)
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
    chain = exhaustive_miner.exhaustive_mine(block)
    if chain is None:
        print("No seed found")
        return
    _depth = len(chain)
    if not nested_miner.verify_nested_seed(chain, block):
        print("Verification failed")
        return
    if event.get("seeds", [None])[args.index] is not None and not args.force:
        print("seed already exists; use --force to replace")
    else:
        event_manager.accept_mined_seed(event, args.index, chain)
        event_manager.save_event(event, str(events_dir))
```
