import argparse
import csv
import os
import random
import time

from helix.miner import generate_microblock


def mine_random_seed(target: bytes, max_seed_len: int) -> tuple[bytes, int, float]:
    """Return ``(seed, attempts, elapsed)`` for mining ``target``."""
    attempts = 0
    start = time.perf_counter()
    while True:
        seed_len = random.randint(1, max_seed_len)
        seed = os.urandom(seed_len)
        output = generate_microblock(seed)[: len(target)]
        attempts += 1
        if output == target:
            elapsed = time.perf_counter() - start
            return seed, attempts, elapsed


def run_trials(size: int, trials: int, max_seed_len: int) -> list[dict]:
    results = []
    for i in range(trials):
        target = os.urandom(size)
        seed, attempts, elapsed = mine_random_seed(target, max_seed_len)
        ratio = size / len(seed)
        aps = attempts / elapsed if elapsed > 0 else 0.0
        results.append(
            {
                "microblock_size": size,
                "trial": i + 1,
                "time_seconds": round(elapsed, 6),
                "attempts": attempts,
                "attempts_per_sec": round(aps, 2),
                "seed_length": len(seed),
                "target_length": size,
                "compression_ratio": round(ratio, 2),
            }
        )
    return results


def simulate_event(size: int, count: int, max_seed_len: int) -> None:
    """Simulate mining ``count`` blocks and print total compression."""
    total_target = 0
    total_seed = 0
    for _ in range(count):
        target = os.urandom(size)
        seed, _, _ = mine_random_seed(target, max_seed_len)
        total_target += size
        total_seed += len(seed)
    ratio = total_target / total_seed if total_seed else 0.0
    print(f"Multi-block event: {count} blocks of {size} bytes -> "
          f"compression ratio {ratio:.2f}x")


def save_csv(results: list[dict], path: str) -> None:
    fieldnames = [
        "microblock_size",
        "trial",
        "time_seconds",
        "attempts",
        "attempts_per_sec",
        "seed_length",
        "target_length",
        "compression_ratio",
    ]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Helix miner")
    parser.add_argument("sizes", type=int, nargs="+", help="microblock sizes")
    parser.add_argument("--trials", type=int, default=1, help="trials per size")
    parser.add_argument("--max-seed", type=int, default=32, help="max seed length")
    parser.add_argument(
        "--csv", type=str, default="benchmark_results.csv", help="output CSV file"
    )
    parser.add_argument(
        "--multi-block",
        type=int,
        default=0,
        help="simulate multi-block mining with given count",
    )
    args = parser.parse_args()

    all_results: list[dict] = []
    for size in args.sizes:
        results = run_trials(size, args.trials, args.max_seed)
        for r in results:
            print(
                f"size={r['microblock_size']} trial={r['trial']} "
                f"time={r['time_seconds']:.4f}s attempts={r['attempts']} "
                f"aps={r['attempts_per_sec']:.1f} seed={r['seed_length']}/"
                f"{r['target_length']} ratio={r['compression_ratio']:.2f}x"
            )
        all_results.extend(results)

    save_csv(all_results, args.csv)
    print(f"Results saved to {args.csv}")

    if args.multi_block > 0 and args.sizes:
        simulate_event(args.sizes[0], args.multi_block, args.max_seed)


if __name__ == "__main__":  # pragma: no cover - manual use
    main()
