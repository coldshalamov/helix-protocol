import argparse
import json
from pathlib import Path

from . import event_manager
from . import minihelix
from . import signature_utils
from . import betting_interface
from .ledger import load_balances
from .helix_node import GossipNode, LocalGossipNetwork

EVENTS_DIR = Path("events")
BALANCES_FILE = Path("balances.json")


def _load_event(event_id: str) -> dict:
    path = EVENTS_DIR / f"{event_id}.json"
    if not path.exists():
        raise SystemExit("Event not found")
    return event_manager.load_event(str(path))


def _save_event(event: dict) -> None:
    event_manager.save_event(event, str(EVENTS_DIR))


def cmd_generate_keys(args: argparse.Namespace) -> None:
    pub, priv = signature_utils.generate_keypair()
    signature_utils.save_keys(args.out, pub, priv)
    print(f"Public key: {pub}")
    print(f"Private key saved to {args.out}")


def cmd_submit_statement(args: argparse.Namespace) -> None:
    event = event_manager.create_event(
        args.statement,
        microblock_size=args.microblock_size,
        keyfile=args.keyfile,
        normalize=args.normalize,
    )

    network = LocalGossipNetwork()
    node = GossipNode("CLI", network)
    node.send_message({"type": "NEW_STATEMENT", "event": event})

    print(f"Statement ID: {event['header']['statement_id']}")
    print("Event submitted via gossip")


def cmd_show_balance(args: argparse.Namespace) -> None:
    pub, _ = signature_utils.load_keys(args.wallet)
    balances = load_balances(str(BALANCES_FILE))
    print(balances.get(pub, 0))


def cmd_place_bet(args: argparse.Namespace) -> None:
    event = _load_event(args.event_id)
    bet = betting_interface.submit_bet(
        args.event_id, args.choice, args.amount, args.wallet
    )
    betting_interface.record_bet(event, bet)
    _save_event(event)
    print("Bet recorded")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="helix")
    sub = parser.add_subparsers(dest="command", required=True)

    p_submit = sub.add_parser("submit-statement", help="Submit a statement")
    p_submit.add_argument("statement", help="Statement text")
    p_submit.add_argument(
        "--keyfile",
        required=True,
        help="File containing originator keys",
    )
    p_submit.add_argument(
        "--microblock-size",
        type=int,
        default=4,
        help="Microblock size in bytes",
    )
    p_submit.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize statement before hashing",
    )
    p_submit.set_defaults(func=cmd_submit_statement)

    p_gen = sub.add_parser("generate-keys", help="Generate a keypair")
    p_gen.add_argument("--out", required=True, help="Output file for keys")
    p_gen.set_defaults(func=cmd_generate_keys)

    p_balance = sub.add_parser("show-balance", help="Show wallet balance")
    p_balance.add_argument("--wallet", required=True, help="Wallet file")
    p_balance.set_defaults(func=cmd_show_balance)

    p_bet = sub.add_parser("place-bet", help="Submit a bet on an event")
    p_bet.add_argument("--wallet", required=True, help="Wallet file")
    p_bet.add_argument("--event-id", required=True, help="Target event id")
    p_bet.add_argument("--choice", required=True, choices=["YES", "NO"], help="Bet choice")
    p_bet.add_argument("--amount", required=True, type=int, help="Bet amount")
    p_bet.set_defaults(func=cmd_place_bet)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

__all__ = ["main", "build_parser"]
