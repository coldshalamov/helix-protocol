import argparse
import hashlib
from pathlib import Path
from typing import Any, List

from helix.ledger import load_balances

from helix import event_manager, minihelix, nested_miner


def sha256_hex(data: bytes) -> str:
    """Return hexadecimal SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def _seed_bytes(seed: Any) -> bytes:
    """Return raw bytes for ``seed`` stored in an event."""
    if seed is None:
        return b""
    if isinstance(seed, bytes):
        return seed
    if isinstance(seed, str):
        return bytes.fromhex(seed)
    if isinstance(seed, list):
        if all(isinstance(b, int) for b in seed):
            return bytes(seed)
        return b"".join(
            bytes.fromhex(part) if isinstance(part, str) else bytes(part)
            for part in seed
        )
    return bytes(seed)


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    """Validate integrity of ``event`` using its seeds."""

    micro_size = event.get("microblock_size") or event.get("header", {}).get(
        "microblock_size",
        minihelix.DEFAULT_MICROBLOCK_SIZE,
    )
    seeds = event.get("seeds", [])

    blocks: List[bytes] = []
    seed_valid = True
    for seed in seeds:
        sb = _seed_bytes(seed)
        if not sb:
            seed_valid = False
            break
        block = minihelix.unpack_seed(sb, micro_size)
        if not nested_miner.verify_nested_seed(sb, block):
            seed_valid = False
            break
        blocks.append(block)

    statement_bytes = b"".join(blocks).rstrip(b"\x00")
    reconstructed = statement_bytes.decode("utf-8", "replace")

    stmt_match = reconstructed == event.get("statement", "")
    hash_match = sha256_hex(statement_bytes) == event.get("header", {}).get(
        "statement_id"
    )

    return {
        "statement": reconstructed,
        "statement_match": stmt_match,
        "hash_match": hash_match,
        "seed_valid": seed_valid,
        "statement_id": event.get("header", {}).get("statement_id"),
    }


def print_summary(result: dict[str, Any]) -> None:
    print(f"Reassembly: {'✓' if result['statement_match'] else '✗'}")
    print(f"Hash match: {'✓' if result['hash_match'] else '✗'}")
    print(f"Seed validation: {'✓' if result['seed_valid'] else '✗'}")


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate finalized Helix event")
    parser.add_argument("event_id", help="Event identifier")
    parser.add_argument("--events-dir", default="data/events", help="Events directory")
    parser.add_argument(
        "--check-balance",
        metavar="wallet_id",
        help="Print HLX balance for wallet from wallet.json",
    )
    args = parser.parse_args(argv)

    path = Path(args.events_dir) / f"{args.event_id}.json"
    if not path.exists():
        raise SystemExit("Event file not found")

    event = event_manager.load_event(str(path))
    result = validate_event(event)
    print_summary(result)
    if args.check_balance:
        balances = load_balances("wallet.json")
        print(balances.get(args.check_balance, 0))

    if not all([result["statement_match"], result["hash_match"], result["seed_valid"]]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
