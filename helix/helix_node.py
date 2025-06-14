def mine_event(self, event: dict) -> None:
    evt_id = event["header"]["statement_id"]
    for idx, block in enumerate(event["microblocks"]):
        if event.get("is_closed"):
            break
        if event["seeds"][idx]:
            continue
        simulate_mining(idx)

        best_seed: Optional[bytes] = None
        best_depth = 0

        # Attempt flat mining
        seed = find_seed(block)
        if seed and verify_seed(seed, block):
            best_seed = seed
            best_depth = 1

        # Attempt nested mining with increasing depth
        for depth in range(2, self.max_nested_depth + 1):
            if best_seed is not None and best_depth <= depth:
                break
            result = nested_miner.find_nested_seed(block, max_depth=depth)
            if result:
                chain, found_depth = result
                candidate = chain[0]
                if (
                    best_seed is None
                    or found_depth < best_depth
                    or (found_depth == best_depth and len(candidate) < len(best_seed))
                ):
                    best_seed = candidate
                    best_depth = found_depth

        if best_seed is not None:
            previous_seed = event["seeds"][idx]
            previous_depth = event["seed_depths"][idx]

            # Call reward-aware acceptance function
            event_manager.accept_mined_seed(event, idx, best_seed, best_depth)

            # Emit debug info on rejection
            if previous_seed is not None and event["seeds"][idx] == previous_seed:
                reason = []
                if len(best_seed) != len(previous_seed):
                    reason.append("same length")
                if best_depth >= previous_depth:
                    reason.append("depth not improved")
                print(f"Seed for block {idx} rejected ({', '.join(reason)})")

            event_manager.save_event(event, self.events_dir)

            if event.get("is_closed"):
                self.finalize_event(event)
                break
