def cmd_mine(args: argparse.Namespace) -> None:
    events_dir = Path(args.data_dir) / "events"
    event_path = events_dir / f"{args.event_id}.json"
    if not event_path.exists():
        print("Event not found")
        return
    event = _load_event(event_path)
    for idx, block in enumerate(event["microblocks"]):
        if event["mined_status"][idx]:
            continue
        offset = 0
        while True:
            result = nested_miner.find_nested_seed(
                block,
                start_nonce=offset,
                attempts=10_000,
            )
            offset += 10_000
            if result is None:
                continue
            encoded = result
            if not nested_miner.verify_nested_seed(encoded, block):
                continue
            event_manager.accept_mined_seed(event, idx, encoded)
            print(f"✔ Block {idx} mined")
            break
    event_manager.save_event(event, str(events_dir))
