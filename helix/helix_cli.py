import argparse
import json
from pathlib import Path

from . import event_manager
from . import minihelix
from . import miner
from . import signature_utils
from . import betting_interface
from .ledger import load_balances

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
    event = event_manager.create_event(args.text, normalize=args.normalize)
    for idx, block in enumerate(event["microblocks"]):
        seed = minihelix.mine_seed(block)
        if seed is None or not minihelix.verify_seed(seed, block):
            print(f"Failed to mine microblock {idx}")
            continue
        event["seeds"][idx] = seed
        event_manager.mark_mined(event, idx)
    path = event_manager.save_event(event, str(EVENTS_DIR))
    print(f"Statement ID: {event['header']['statement_id']}")
    print(f"Saved to {path}")


def cmd_mine_statement(args: argparse.Namespace) -> None:
    """Mine ``args.text`` using :func:`miner.find_seed` and save the event."""
    event = event_manager.create_event(args.text, normalize=args.normalize)
    block_total = len(event["microblocks"])
    for idx, block in enumerate(event["microblocks"], start=1):
        print(f"Mining microblock {idx}/{block_total} ...")
        seed = miner.find_seed(block)
        if seed is None:
            print(f"No seed found for block {idx - 1}")
            continue
        if not minihelix.verify_seed(seed, block):
            print(f"Seed verification failed for block {idx - 1}")
            continue
        event["seeds"][idx - 1] = seed
        event_manager.mark_mined(event, idx - 1)

    path = event_manager.save_event(event, str(EVENTS_DIR))
    statement = event_manager.reassemble_microblocks(event["microblocks"])
    print(f"Statement ID: {event['header']['statement_id']}")
    print(f"Saved to {path}")
    print(f"Reassembled: {statement}")


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
    p_submit.add_argument("--text", required=True, help="Statement text")
    p_submit.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize statement before hashing",
    )
    p_submit.set_defaults(func=cmd_submit_statement)

    p_mine = sub.add_parser("mine-statement", help="Mine microblocks for a statement")
    p_mine.add_argument("--text", required=True, help="Statement text")
    p_mine.add_argument(
        "--normalize",
        action="store_true",
        help="Normalize statement before hashing",
    )
    p_mine.set_defaults(func=cmd_mine_statement)

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
