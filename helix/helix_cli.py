import argparse
import json
import hashlib
from pathlib import Path

from . import event_manager
from . import minihelix
from . import miner
from . import signature_utils
from . import betting_interface
from .ledger import load_balances, get_total_supply, compression_stats
from .gossip import GossipNode, LocalGossipNetwork
from .blockchain import load_chain
from . import helix_node
from .config import GENESIS_HASH

EVENTS_DIR = Path("events")
BALANCES_FILE = Path("balances.json")
DATA_EVENTS_DIR = Path("data/events")


def _load_event(event_id: str) -> dict:
    path = EVENTS_DIR / f"{event_id}.json"
    if not path.exists():
        raise SystemExit(f"Event '{event_id}' not found in {EVENTS_DIR}")
    return event_manager.load_event(str(path))


def _save_event(event: dict) -> None:
    event_manager.save_event(event, str(EVENTS_DIR))


def cmd_generate_keys(args: argparse.Namespace) -> None:
    pub, priv = signature_utils.generate_keypair()
    signature_utils.save_keys(args.out, pub, priv)
    print(f"Public key: {pub}")
    print(f"Private key saved to {args.out}")


def initialize_genesis_block() -> None:
    """Placeholder for genesis block initialization."""
    pass


def cmd_init(args: argparse.Namespace) -> None:
    initialize_genesis_block()
    print("\u2714 Genesis block created")
    print("\u2714 1,000 HLX minted to HELIX_FOUNDATION")


def cmd_submit_statement(args: argparse.Namespace) -> None:
    """Create an event from ``args.statement`` and store it on disk."""
    event = event_manager.create_event(
        args.statement,
        microblock_size=args.block_size,
    )

    path = event_manager.save_event(event, str(DATA_EVENTS_DIR))

    event_id = event["header"]["statement_id"]
    block_count = event["header"]["block_count"]

    print(f"Event ID: {event_id}")
    print(f"Blocks created: {block_count}")


def cmd_mine_statement(args: argparse.Namespace) -> None:
    """Mine ``args.text`` using :func:`miner.find_seed` and save the event."""
    event = event_manager.create_event(args.text)
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


def cmd_submit_and_mine(args: argparse.Namespace) -> None:
    """Create, mine and finalize a statement in one step."""
    event = event_manager.create_event(
        args.statement, microblock_size=args.block_size
    )
    helix_node.mine_microblocks(event)
    event_manager.save_event(event, str(EVENTS_DIR))
    if not event.get("is_closed"):
        print("Event could not be fully mined")
        return

    event_manager.finalize_event(event)
    event_manager.save_event(event, str(EVENTS_DIR))
    chain = load_chain("blockchain.jsonl")
    block_id = chain[-1]["block_id"] if chain else "N/A"
    print(f"Event hash: {event['header']['statement_id']}")
    print(f"Block ID: {block_id}")
    print(f"Chain length: {len(chain)}")


def cmd_mine_event(args: argparse.Namespace) -> None:
    """Mine all unmined microblocks for an existing event."""
    events_dir = Path(args.data_dir) / "events"
    path = events_dir / f"{args.event_id}.json"
    if not path.exists():
        raise SystemExit(
            f"Event '{args.event_id}' not found in {events_dir}"
        )

    event = event_manager.load_event(str(path))
    mined, elapsed = helix_node.mine_microblocks(event)
    event_manager.save_event(event, str(events_dir))

    micro_size = event.get("header", {}).get(
        "microblock_size", event_manager.DEFAULT_MICROBLOCK_SIZE
    )
    total_saved = 0
    total_len = 0
    for seed in event.get("seeds", []):
        if seed is None:
            continue
        length = len(seed) if isinstance(seed, (bytes, bytearray)) else len(seed[0])
        total_saved += max(0, micro_size - length)
        total_len += length
    ratio = (micro_size * len(event.get("microblocks", [])) / total_len) if total_len else 0.0

    print(f"Blocks mined: {mined}")
    print(f"Compression ratio: {ratio:.2f}x saved={total_saved}")
    print(f"Mining time: {elapsed:.2f}s")


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


def cmd_list_events(args: argparse.Namespace) -> None:
    """Print a summary of all events in ``args.data_dir``."""
    events_dir = Path(args.data_dir) / "events"
    if not events_dir.exists():
        raise SystemExit(f"Events directory not found: {events_dir}")

    for path in sorted(events_dir.glob("*.json")):
        event = event_manager.load_event(str(path))
        header = event.get("header", {})
        statement_id = header.get("statement_id", path.stem)
        mined = sum(1 for m in event.get("mined_status", []) if m)
        total = header.get("block_count", len(event.get("microblocks", [])))
        line = f"{statement_id} closed={event.get('is_closed', False)} {mined}/{total}"
        if args.show_statement:
            line += f" {event.get('statement', '')}"
        print(line)


def cmd_reassemble_statement(args: argparse.Namespace) -> None:
    """Reconstruct and verify a statement from mined microblocks."""
    if args.path is not None:
        event = event_manager.load_event(args.path)
    else:
        event = _load_event(args.event_id)

    statement = event_manager.reassemble_microblocks(event["microblocks"])
    digest = event_manager.sha256(statement.encode("utf-8"))
    expected = event.get("header", {}).get("statement_id")
    if digest != expected:
        raise SystemExit(
            f"SHA-256 mismatch: expected {expected}, computed {digest}"
        )

    author = event.get("originator_pub")
    print(f"Author: {author}")
    for idx, seed in enumerate(event.get("seeds", [])):
        length = len(seed) if seed is not None else 0
        print(f"Block {idx}: seed_len={length}")
    print(statement)


def cmd_view_chain(args: argparse.Namespace) -> None:
    """Show blockchain information with compression stats."""
    base = Path(args.data_dir)
    chain_path = base / "blockchain.jsonl"
    if not chain_path.exists():
        alt = base / "chain.json"
        if alt.exists():
            chain_path = alt
    blocks = load_chain(str(chain_path))
    if not blocks:
        print("No chain data found")
        return

    events_dir = base / "events"
    for height, block in enumerate(blocks):
        event_ids = block.get("event_ids") or block.get("events") or [block.get("event_id")]
        if isinstance(event_ids, list):
            event_id = event_ids[0] if event_ids else None
        else:
            event_id = event_ids
        block_id = block.get("block_id") or block.get("id")
        saved = 0
        if event_id:
            event_path = events_dir / f"{event_id}.json"
            if event_path.exists():
                event = event_manager.load_event(str(event_path))
                micro_size = event.get("header", {}).get(
                    "microblock_size", event_manager.DEFAULT_MICROBLOCK_SIZE
                )
                for seed in event.get("seeds", []):
                    if seed is None:
                        continue
                    saved += max(0, micro_size - len(seed))
        if args.summary:
            print(f"{height} {event_id} {block_id} {saved}")
        else:
            print(f"height={height} event_id={event_id} block_id={block_id} saved={saved}")


def cmd_finalize(args: argparse.Namespace) -> None:
    """Finalize an event and append the block to the chain."""
    event = _load_event(args.event_id)

    for idx, block in enumerate(event.get("microblocks", [])):
        seed = event.get("seeds", [])[idx]
        if seed is None:
            raise SystemExit(
                f"Cannot finalize: missing seed for block {idx} in event {args.event_id}"
            )
        if not event_manager.nested_miner.verify_nested_seed(seed, block):
            raise SystemExit(
                f"Seed verification failed for block {idx} in event {args.event_id}"
            )

    statement = event_manager.reassemble_microblocks(event["microblocks"])
    digest = event_manager.sha256(statement.encode("utf-8"))
    expected = event.get("header", {}).get("statement_id")
    if digest != expected:
        raise SystemExit(
            f"SHA-256 mismatch: expected {expected}, computed {digest}"
        )

    event_manager.finalize_event(event)
    _save_event(event)
    print("statement verified, block saved, rewards distributed")


def cmd_token_stats(args: argparse.Namespace) -> None:
    """Print overall token distribution statistics."""
    events_dir = Path(args.data_dir) / "events"
    total_hlx = get_total_supply(str(events_dir))
    mined_events = 0
    total_reward = 0.0

    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            event = event_manager.load_event(str(path))
            rewards = event.get("rewards", [])
            refunds = event.get("refunds", [])
            reward = sum(rewards) - sum(refunds)
            if event.get("is_closed"):
                mined_events += 1
                total_reward += reward

    avg_reward = total_reward / mined_events if mined_events else 0.0

    print(f"Total HLX Supply: {total_hlx:.4f}")
    print(f"Total Mined Events: {mined_events}")
    print(f"Average Reward/Event: {avg_reward:.4f}")


def cmd_doctor(args: argparse.Namespace) -> None:
    """Diagnose local node files and print status information."""
    base = Path(args.data_dir)

    # Genesis block check
    genesis = base / "genesis.json"
    if not genesis.exists():
        print("genesis.json not found")
    else:
        digest = hashlib.sha256(genesis.read_bytes()).hexdigest()
        if digest != GENESIS_HASH:
            print("hash mismatch")

    # Microblock counts
    events_dir = base / "events"
    mined = 0
    unmined = 0
    if events_dir.exists():
        for path in events_dir.glob("*.json"):
            ev = event_manager.load_event(str(path))
            statuses = ev.get("mined_status", [False] * len(ev.get("microblocks", [])))
            mined_blocks = sum(1 for m in statuses if m)
            total_blocks = ev.get("header", {}).get(
                "block_count", len(ev.get("microblocks", []))
            )
            mined += mined_blocks
            unmined += total_blocks - mined_blocks
    print(f"Mined microblocks: {mined}")
    print(f"Unmined microblocks: {unmined}")

    # Wallet and balance
    wallet = base / "wallet.txt"
    if wallet.exists():
        try:
            pub, _ = signature_utils.load_keys(str(wallet))
            balances_file = base / "balances.json"
            balances = load_balances(str(balances_file))
            balance = balances.get(pub, 0)
            print(f"Wallet balance: {balance}")
        except Exception:
            print("wallet inaccessible")
    else:
        print("no wallet file")

    # Chain info
    chain_path = base / "blockchain.jsonl"
    if not chain_path.exists():
        alt = base / "chain.json"
        if alt.exists():
            chain_path = alt
    blocks = load_chain(str(chain_path))
    if blocks:
        height = len(blocks) - 1
        ts = blocks[-1].get("timestamp")
        print(f"Latest block: {height} {ts}")
    else:
        print("No chain data found")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="helix",
        description="Command line interface for the Helix protocol",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_doc = sub.add_parser(
        "doctor",
        help="Check local node files",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_doc.add_argument(
        "--data-dir",
        default="data",
        metavar="DIR",
        help="Directory containing node data",
    )
    p_doc.set_defaults(func=cmd_doctor)

    p_submit = sub.add_parser(
        "submit-statement",
        help="Create a new event from the provided statement",
        description="Create a new event and store its microblocks",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_submit.add_argument("statement", metavar="TEXT", help="Statement text")
    p_submit.add_argument(
        "--block-size",
        type=int,
        default=8,
        metavar="BYTES",
        help="Size of each microblock in bytes",
    )
    p_submit.set_defaults(func=cmd_submit_statement)

    p_submit_mine = sub.add_parser(
        "submit-and-mine",
        help="Submit a statement and mine all microblocks",
        description="Create an event, mine it and finalize in one step",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_submit_mine.add_argument("statement", metavar="TEXT", help="Statement text")
    p_submit_mine.add_argument(
        "--block-size",
        type=int,
        default=8,
        metavar="BYTES",
        help="Size of each microblock in bytes",
    )
    p_submit_mine.set_defaults(func=cmd_submit_and_mine)

    p_mine = sub.add_parser(
        "mine-statement",
        help="Mine a statement immediately and save the event",
        description="Mine microblocks for the provided statement",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_mine.add_argument("--text", required=True, metavar="TEXT", help="Statement text")
    p_mine.set_defaults(func=cmd_mine_statement)

    p_evt = sub.add_parser(
        "mine",
        help="Mine remaining microblocks for an event",
        description="Continue mining microblocks for an existing event",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_evt.add_argument("event_id", metavar="EVENT", help="Event identifier")
    p_evt.add_argument(
        "--data-dir",
        default="data",
        metavar="DIR",
        help="Directory containing events",
    )
    p_evt.set_defaults(func=cmd_mine_event)

    p_gen = sub.add_parser(
        "generate-keys",
        help="Generate a new wallet key pair",
        description="Create a public/private key pair for signing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_gen.add_argument(
        "--out",
        required=True,
        metavar="FILE",
        help="Output file for the private key",
    )
    p_gen.set_defaults(func=cmd_generate_keys)

    p_init = sub.add_parser(
        "init",
        help="Create the genesis block",
        description="Initialize the blockchain with the genesis event",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_init.set_defaults(func=cmd_init)

    p_balance = sub.add_parser(
        "show-balance",
        help="Display the balance of a wallet",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_balance.add_argument(
        "--wallet",
        required=True,
        metavar="KEYFILE",
        help="Path to the wallet's private key",
    )
    p_balance.set_defaults(func=cmd_show_balance)

    p_bet = sub.add_parser(
        "place-bet",
        help="Stake HLX on the outcome of an event",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_bet.add_argument("--wallet", required=True, metavar="KEYFILE", help="Wallet file")
    p_bet.add_argument("--event-id", required=True, metavar="EVENT", help="Target event id")
    p_bet.add_argument(
        "--choice",
        required=True,
        choices=["YES", "NO"],
        metavar="CHOICE",
        help="Bet choice",
    )
    p_bet.add_argument(
        "--amount",
        required=True,
        type=int,
        metavar="TOKENS",
        help="Bet amount",
    )
    p_bet.set_defaults(func=cmd_place_bet)

    p_list = sub.add_parser(
        "list-events",
        help="List events in a data directory",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_list.add_argument(
        "--data-dir",
        default="data",
        metavar="DIR",
        help="Directory containing events",
    )
    p_list.add_argument(
        "--show-statement",
        action="store_true",
        help="Include raw statement text",
    )
    p_list.set_defaults(func=cmd_list_events)

    p_stats = sub.add_parser(
        "token-stats",
        help="Display token supply statistics",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_stats.add_argument(
        "--data-dir",
        default="data",
        metavar="DIR",
        help="Directory containing events",
    )
    p_stats.set_defaults(func=cmd_token_stats)

    p_reasm = sub.add_parser(
        "reassemble-statement",
        help="Verify seeds and output the full statement",
        description="Reassemble a statement from its microblocks",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    group = p_reasm.add_mutually_exclusive_group(required=True)
    group.add_argument("--event-id", metavar="EVENT", help="Event identifier")
    group.add_argument("--path", metavar="FILE", help="Path to event JSON file")
    p_reasm.set_defaults(func=cmd_reassemble_statement)

    p_chain = sub.add_parser(
        "view-chain",
        help="Show blockchain data",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_chain.add_argument(
        "--data-dir",
        default="data",
        metavar="DIR",
        help="Directory containing chain and events",
    )
    p_chain.add_argument(
        "--summary",
        action="store_true",
        help="Summary output",
    )
    p_chain.set_defaults(func=cmd_view_chain)

    p_fin = sub.add_parser(
        "finalize",
        help="Finalize a mined event and append it to the chain",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p_fin.add_argument("event_id", metavar="EVENT", help="Event identifier")
    p_fin.set_defaults(func=cmd_finalize)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()

__all__ = [
    "main",
    "build_parser",
    "cmd_init",
    "initialize_genesis_block",
    "cmd_doctor",
    "cmd_token_stats",
    "cmd_submit_and_mine",
]
