import argparse
import hashlib
from pathlib import Path
from typing import Any, List

from helix import event_manager, minihelix


def sha256_hex(data: bytes) -> str:
    """Return hex encoded SHA-256 digest."""
    return hashlib.sha256(data).hexdigest()


def _to_bytes(seed: Any) -> bytes:
    """Return ``seed`` converted to ``bytes``."""
    if isinstance(seed, bytes):
        return seed
    if isinstance(seed, bytearray):
        return bytes(seed)
    if isinstance(seed, list):
        return bytes(seed)
    if isinstance(seed, str):
        try:
            return bytes.fromhex(seed)
        except ValueError:
            pass
    raise TypeError("invalid seed type")


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    """Return validation details for ``event``."""
    micro_size = event.get("header", {}).get("microblock_size", minihelix.DEFAULT_MICROBLOCK_SIZE)

    seeds = event.get("seeds", [])
    blocks: List[bytes] = []
    seed_valid = True

    for idx, seed in enumerate(seeds):
        try:
            block = minihelix.unpack_seed(_to_bytes(seed), micro_size)
            blocks.append(block)
        except Exception:
            seed_valid = False
            break

    statement_bytes = b"".join(blocks).rstrip(b"\x00")
    statement = statement_bytes.decode("utf-8", errors="replace")

    stmt_match = statement == event.get("statement", "")
    hash_match = sha256_hex(statement_bytes) == event.get("header", {}).get("statement_id")

    return {
        "statement": statement,
        "statement_match": stmt_match,
        "hash_match": hash_match,
        "seed_valid": seed_valid,
    }


def print_summary(result: dict[str, Any]) -> None:
    print(
        f"Statement reconstruction: {'✓' if result['statement_match'] else '✗'}"
    )
    print(f"Statement ID match: {'✓' if result['hash_match'] else '✗'}")
    print(f"Seed unpack validity: {'✓' if result['seed_valid'] else '✗'}")


def main(argv: List[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Validate finalized Helix event")
    parser.add_argument("event_id", help="Event identifier")
    parser.add_argument("--events-dir", default="data/events", help="Events directory")
    args = parser.parse_args(argv)

    path = Path(args.events_dir) / f"{args.event_id}.json"
    if not path.exists():
        raise SystemExit("Event file not found")

    event = event_manager.load_event(str(path))
    result = validate_event(event)
    print_summary(result)

    if not all([result["statement_match"], result["hash_match"], result["seed_valid"]]):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
