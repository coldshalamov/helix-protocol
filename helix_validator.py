import argparse
import hashlib
from pathlib import Path
from typing import Any, List

from helix import event_manager, minihelix, nested_miner
from helix.merkle_utils import build_merkle_tree


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_seed(encoded: bytes) -> bytes:
    """Return the base seed from encoded seed chain bytes."""
    if not encoded or len(encoded) < 2:
        return b""
    seed_len = encoded[1]
    return encoded[2 : 2 + seed_len]


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    micro_size = event["header"].get("microblock_size", minihelix.DEFAULT_MICROBLOCK_SIZE)
    block_count = event["header"].get("block_count", len(event.get("seeds", [])))

    reconstructed_blocks: List[bytes] = []
    seed_valid = True
    bad_index: int | None = None
    for idx in range(block_count):
        enc = event.get("seeds", [None])[idx]
        if enc is None:
            seed_valid = False
            bad_index = idx
            break
        seed = _parse_seed(enc)
        block = minihelix.G(seed, micro_size)
        if not nested_miner.verify_nested_seed(enc, block):
            seed_valid = False
            bad_index = idx
            break
        reconstructed_blocks.append(block)

    statement_bytes = b"".join(reconstructed_blocks).rstrip(b"\x00")
    statement = statement_bytes.decode("utf-8", errors="replace")

    stmt_match = statement == event.get("statement", "")
    hash_match = sha256_hex(statement_bytes) == event.get("header", {}).get("statement_id")

    root, tree = build_merkle_tree(reconstructed_blocks)
    hdr_root = event.get("header", {}).get("merkle_root")
    merkle_match = hdr_root == root
    if merkle_match and event.get("merkle_tree"):
        merkle_match = tree == event["merkle_tree"]

    orig_bytes = micro_size * block_count
    comp_bytes = sum(len(s) for s in event.get("seeds", []) if s is not None)
    reduction = 100.0 * (1 - (comp_bytes / orig_bytes)) if orig_bytes else 0.0

    return {
        "statement": statement,
        "statement_match": stmt_match,
        "hash_match": hash_match,
        "merkle_match": merkle_match,
        "seed_valid": seed_valid,
        "bad_index": bad_index,
        "orig_bytes": orig_bytes,
        "comp_bytes": comp_bytes,
        "reduction": reduction,
        "block_count": block_count,
        "statement_id": event.get("header", {}).get("statement_id"),
    }


def print_summary(result: dict[str, Any]) -> None:
    status = "✓" if all(
        [result["statement_match"], result["hash_match"], result["merkle_match"], result["seed_valid"]]
    ) else "✗"
    print(f"[{status}] Statement ID: {result['statement_id']}")
    print(f"    Microblocks: {result['block_count']}")
    print(f"    Reconstructed: {'✔' if result['statement_match'] else '✖'}")
    print(f"    Merkle Verified: {'✔' if result['merkle_match'] else '✖'}")
    print(f"    Seed Chain Valid: {'✔' if result['seed_valid'] else '✖'}")
    if not result['seed_valid'] and result['bad_index'] is not None:
        print(f"        Failed at microblock {result['bad_index']}")
    print(
        f"    Compression: {result['orig_bytes']} → {result['comp_bytes']} bytes ({result['reduction']:.1f}%)"
    )
    if not result["hash_match"]:
        print("    Statement hash mismatch")


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


if __name__ == "__main__":
    main()
