import json
from pathlib import Path


def main() -> None:
    events_dir = Path("data/events")
    if not events_dir.exists():
        print("No events directory found:", events_dir)
        return

    genesis_id = None
    genesis_file = Path("genesis.json")
    if genesis_file.exists():
        try:
            with open(genesis_file, "r", encoding="utf-8") as gf:
                genesis_id = json.load(gf).get("header", {}).get("statement_id")
        except Exception:
            genesis_id = None

    updated = []
    for path in events_dir.rglob("*.json"):
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception as e:
            print(f"Skipping {path}: {e}")
            continue

        header = data.get("header", {})
        has_parent_key = "parent_id" in header
        parent_value = header.get("parent_id") if has_parent_key else None
        filename_match = genesis_id is not None and path.stem == genesis_id

        if not has_parent_key:
            header["parent_id"] = None
            data["header"] = header
            updated.append(path)
        elif parent_value is not None and filename_match:
            header["parent_id"] = None
            data["header"] = header
            updated.append(path)

        if updated and updated[-1] == path:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
                fh.write("\n")

    if updated:
        print("Updated files:")
        for p in updated:
            print(f" - {p}")
    else:
        print("No files updated.")


if __name__ == "__main__":
    main()
