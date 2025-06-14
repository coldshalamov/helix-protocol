import argparse
import json
from pathlib import Path

from .helix_node import HelixNode
from . import event_manager
from . import nested_miner
from . import minihelix
from . import betting_interface
from .ledger import load_balances


def _load_event(path: Path) -> dict:
    return event_manager.load_event(str(path))


def cmd_start_node(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    balances_file = Path(args.data_dir) / "balances.json"
    node = HelixNode(events_dir=str(events_dir), balances_file=str(balances_file))
    print(f"Starting node on port {args.port} with data dir {args.data_dir}")
    node.run()


def cmd_submit_statement(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event = event_manager.create_event(args.statement, keyfile=args.keyfile)
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
        result = nested_miner.find_nested_seed(block)
        if result is None:
            print(f"No seed found for block {idx}")
            continue
        chain, _ = result
        seed = chain[0]
        if not minihelix.verify_seed(seed, block):
            print(f"Seed verification failed for block {idx}")
            continue
        event["seeds"][idx] = seed
        event_manager.mark_mined(event, idx)
        print(f"Mined microblock {idx}")
    event_manager.save_event(event, str(events_dir))


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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="helix-cli")
    parser.add_argument("--data-dir", default="data", help="Directory for node data")
    parser.add_argument("--port", type=int, default=8000, help="Gossip port")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start-node", help="Start a Helix node")
    p_start.set_defaults(func=cmd_start_node)

    p_submit = sub.add_parser("submit-statement", help="Submit a statement")
    p_submit.add_argument("statement", help="Text of the statement")
    p_submit.add_argument("--keyfile", help="File containing originator keys")
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

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()

__all__ = ["main"]
