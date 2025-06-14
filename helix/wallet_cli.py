import argparse
import json
from pathlib import Path

from . import signature_utils
from . import betting_interface
from . import event_manager
from .ledger import load_balances


def cmd_wallet_create(args: argparse.Namespace) -> None:
    pub, priv = signature_utils.generate_keypair()
    signature_utils.save_keys(args.keyfile, pub, priv)
    print(f"Created new keypair at {args.keyfile}")
    print(f"Public key: {pub}")


def cmd_wallet_balance(args: argparse.Namespace) -> None:
    balances_file = Path(args.data_dir) / "balances.json"
    balances = load_balances(str(balances_file))
    print(json.dumps(balances, indent=2))


def cmd_bet(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event_path = events_dir / f"{args.event}.json"
    if not event_path.exists():
        raise SystemExit("Event not found")
    bet = betting_interface.submit_bet(args.event, args.choice, args.amount, args.keyfile)
    event = event_manager.load_event(str(event_path))
    betting_interface.record_bet(event, bet)
    event_manager.save_event(event, str(events_dir))
    print("Bet recorded")


def cmd_list_bets(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event_path = events_dir / f"{args.event}.json"
    if not event_path.exists():
        raise SystemExit("Event not found")
    event = event_manager.load_event(str(event_path))
    print(json.dumps(event.get("bets", {}), indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="helix")
    sub = parser.add_subparsers(dest="command", required=True)

    wallet = sub.add_parser("wallet", help="Wallet management")
    wallet_sub = wallet.add_subparsers(dest="wallet_cmd", required=True)

    p_create = wallet_sub.add_parser("create", help="Generate a keypair")
    p_create.add_argument("keyfile", help="Path to save keys")
    p_create.set_defaults(func=cmd_wallet_create)

    p_balance = wallet_sub.add_parser("balance", help="Show balances")
    p_balance.add_argument("--data-dir", default="data", help="Node data directory")
    p_balance.set_defaults(func=cmd_wallet_balance)

    p_bet = sub.add_parser("bet", help="Submit a bet")
    p_bet.add_argument("--event", required=True, help="Event identifier")
    p_bet.add_argument("--choice", required=True, choices=["YES", "NO"], help="Bet choice")
    p_bet.add_argument("--amount", required=True, type=int, help="Bet amount")
    p_bet.add_argument("--keyfile", required=True, help="Keyfile with signing keys")
    p_bet.add_argument("--data-dir", default="data", help="Node data directory")
    p_bet.set_defaults(func=cmd_bet)

    p_list = sub.add_parser("list-bets", help="List bets for an event")
    p_list.add_argument("--event", required=True, help="Event identifier")
    p_list.add_argument("--data-dir", default="data", help="Node data directory")
    p_list.set_defaults(func=cmd_list_bets)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":  # pragma: no cover - manual execution
    main()

__all__ = ["main", "build_parser"]
