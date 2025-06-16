import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


def check_pynacl() -> None:
    """Ensure PyNaCl is installed."""
    if importlib.util.find_spec("nacl") is None:
        print(
            "PyNaCl is not installed. Install dependencies with 'pip install -r requirements.txt'."
        )
        sys.exit(1)


def reset_test_dirs() -> None:
    """Remove leftover test artifacts and recreate clean dirs."""
    dirs = ["events", "a_events", "b_events", "archives"]
    files = [
        "blockchain.jsonl",
        "a_chain.jsonl",
        "b_chain.jsonl",
        "a_bal.json",
        "b_bal.json",
    ]

    for name in dirs:
        path = Path(name)
        if path.exists():
            shutil.rmtree(path)
    for name in files:
        path = Path(name)
        if path.exists():
            path.unlink()

    Path("events").mkdir(exist_ok=True)


def run_pytest() -> int:
    """Run pytest and print a simple summary."""
    proc = subprocess.run(["pytest", "-vv"], capture_output=True, text=True)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    summary = ""
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith("=") and "in" in line:
            summary = line.strip("=").strip()
            break
    if summary:
        print("Test summary:", summary)
    else:
        print("No summary information found.")
    return proc.returncode


def main() -> None:
    check_pynacl()
    reset_test_dirs()
    sys.exit(run_pytest())


if __name__ == "__main__":
    main()
