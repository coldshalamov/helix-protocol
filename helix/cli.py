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
from .ledger import load_balances, compression_stats
from .ledger import get_total_supply


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


def cmd_token_stats(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    total = get_total_supply(str(events_dir))
    print(f"Total HLX Issued: {total:.4f}")


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
        _, private_key = signature_utils.load_keys(args.keyfile)
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
            print(f"✔ Block {idx} mined")
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


def cmd_place_bet(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event_path = events_dir / f"{args.event_id}.json"
    if not event_path.exists():
        print("Event not found")
        return
    event = _load_event(event_path)
    bet = betting_interface.submit_bet(
        args.event_id, args.choice, args.amount, args.keyfile
    )
    betting_interface.record_bet(event, bet)
    event_manager.save_event(event, str(events_dir))
    print("Bet recorded")


def cmd_view_wallet(args: argparse.Namespace) -> None:
    balances_file = Path(args.data_dir) / "balances.json"
    balances = load_balances(str(balances_file))
    if not balances:
        print("Wallet empty")
        return
    print(json.dumps(balances, indent=2))


def cmd_helix_node(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    events_dir = data_dir / "events"
    balances_file = data_dir / "balances.json"
    wallet_file = data_dir / "wallet.txt"

    pub, _ = signature_utils.load_or_create_keys(str(wallet_file))
    print(f"Using wallet {wallet_file} (pubkey {pub})")

    network = LocalGossipNetwork()
    node = HelixNode(
        events_dir=str(events_dir),
        balances_file=str(balances_file),
        node_id=pub[:8],
        network=network,
        genesis_file=_default_genesis_file(),
    )

    threading.Thread(target=node._message_loop, daemon=True).start()

    def miner_loop() -> None:
        while True:
            for event in list(node.events.values()):
                if not event.get("is_closed"):
                    node.mine_event(event)
            time.sleep(0.1)

    threading.Thread(target=miner_loop, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def cmd_run_node(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    events_dir = data_dir / "events"
    balances_file = data_dir / "balances.json"
    wallet_file = data_dir / "wallet.txt"

    pub, _ = signature_utils.load_or_create_keys(str(wallet_file))
    print(f"Using wallet {wallet_file} (pubkey {pub})")

    transport = TCPGossipTransport(host=args.host, port=args.port)
    network = SocketGossipNetwork(transport)
    node = HelixNode(
        events_dir=str(events_dir),
        balances_file=str(balances_file),
        node_id=pub[:8],
        network=network,
        genesis_file=_default_genesis_file(),
    )

    for peer in args.peers:
        try:
            host, port_str = peer.split(":", 1)
            transport.add_peer(Peer(host, int(port_str)))
        except ValueError:
            print(f"Invalid peer address: {peer}")

    threading.Thread(target=node._message_loop, daemon=True).start()

    def miner_loop() -> None:
        while True:
            for event in list(node.events.values()):
                if not event.get("is_closed"):
                    node.mine_event(event)
            time.sleep(0.1)

    threading.Thread(target=miner_loop, daemon=True).start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        transport.close()


def cmd_reassemble(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    if args.path is not None:
        event_path = Path(args.path)
    else:
        event_path = events_dir / f"{args.event_id}.json"

    if not event_path.exists():
        print("Event not found")
        return

    event = _load_event(event_path)
    statement = event_manager.reassemble_microblocks(event["microblocks"])

    if statement != event.get("statement"):
        raise SystemExit("Padding trim verification failed")

    print(statement)


def cmd_doctor(args: argparse.Namespace) -> None:
    ok = True

    genesis_path = Path("genesis.json")
    if not genesis_path.exists():
        print("WARNING: genesis.json not found")
        ok = False
        alt = Path(__file__).resolve().parent / "genesis.json"
        if alt.exists():
            genesis_path = alt
    if genesis_path.exists():
        digest = hashlib.sha256(genesis_path.read_bytes()).hexdigest()
        if digest != GENESIS_HASH:
            print("WARNING: genesis.json hash mismatch - update GENESIS_HASH or regenerate the file")
            ok = False

    data_dir = Path(args.data_dir)
    wallet_file = data_dir / "wallet.txt"
    if not wallet_file.exists():
        print(f"WARNING: no wallet file found at {wallet_file} - run 'helix helix-node' or generate keys")
        ok = False

    peers_file = data_dir / "peers.json"
    peers: list[str] = []
    if peers_file.exists():
        try:
            peers = json.loads(peers_file.read_text())
        except Exception:
            peers = []
    if not peers:
        print("WARNING: no peers connected - create peers.json or start another node")
        ok = False

    events_dir = data_dir / "events"
    unmined: list[str] = []
    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            try:
                event = event_manager.load_event(str(path))
            except Exception:
                continue
            if not all(event.get("mined_status", [])):
                unmined.append(path.stem)
    if unmined:
        print("WARNING: unmined events detected - run 'helix mine <id>' to finish mining")
        for eid in unmined:
            print(f"  - {eid}")
        ok = False

    if ok:
        print("No issues detected")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="helix-cli")
    parser.add_argument("--data-dir", default="data", help="Directory for node data")
    parser.add_argument("--port", type=int, default=8000, help="Gossip port")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start-node", help="Start a Helix node")
    p_start.set_defaults(func=cmd_start_node)

    p_autonode = sub.add_parser("helix-node", help="Run automated mining node")
    p_autonode.set_defaults(func=cmd_helix_node)

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

    p_wallet = sub.add_parser("view-wallet", help="View wallet balances")
    p_wallet.set_defaults(func=cmd_view_wallet)

    p_tstats = sub.add_parser("token-stats", help="Show total token supply")
    p_tstats.set_defaults(func=cmd_token_stats)

    p_remine = sub.add_parser("remine-microblock", help="Retry mining a single microblock")
    p_remine.add_argument("--event-id", required=True, help="Event identifier")
    p_remine.add_argument("--index", type=int, required=True, help="Block index")
    p_remine.add_argument("--force", action="store_true", help="Replace existing seed if a shorter one is found")
    p_remine.set_defaults(func=cmd_remine_microblock)

    p_status = sub.add_parser("status", help="Show node status")
    p_status.set_defaults(func=cmd_status)

    p_reassemble = sub.add_parser("reassemble", help="Reassemble an event")
    group = p_reassemble.add_mutually_exclusive_group(required=True)
    group.add_argument("--event-id", help="Event identifier")
    group.add_argument("--path", help="Path to event JSON file")
    p_reassemble.set_defaults(func=cmd_reassemble)

    p_doctor = sub.add_parser("doctor", help="Check configuration for problems")
    p_doctor.set_defaults(func=cmd_doctor)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

__all__ = ["main"]
