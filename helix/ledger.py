def apply_mining_results(
    event: Dict[str, Any],
    balances: Dict[str, float],
    *,
    journal_file: str = "ledger_journal.jsonl",
) -> None:
    """Apply compression rewards and delta bonuses for ``event`` to ``balances``.

    Rewards are calculated from the byte savings of each mined microblock and
    applied cumulatively. If a microblock is further compressed later, only the
    additional savings are rewarded to the new miner. All payouts are logged to
    ``journal_file`` with ``compression_reward`` as the reason.
    """

    miners = event.get("miners") or []
    microblocks = event.get("microblocks") or []
    seeds = event.get("seeds") or []
    header = event.get("block_header", {})
    block_hash = header.get("block_id", event.get("header", {}).get("statement_id", ""))

    credited = event.setdefault("_credited_lengths", [0] * len(miners))

    def _to_bytes(seed_entry: Any) -> bytes | None:
        if seed_entry is None:
            return None
        if isinstance(seed_entry, (bytes, bytearray)):
            return bytes(seed_entry)
        if isinstance(seed_entry, list):
            if not seed_entry:
                return None
            if isinstance(seed_entry[0], int):
                return bytes(seed_entry)
            return _to_bytes(seed_entry[-1])
        return None

    # Compression rewards with stacking
    for idx, miner in enumerate(miners):
        if not miner or idx >= len(seeds) or idx >= len(microblocks):
            continue

        seed_bytes = _to_bytes(seeds[idx])
        block_hex = microblocks[idx]
        block_bytes = (
            bytes.fromhex(block_hex) if isinstance(block_hex, str) else block_hex
        )

        if not seed_bytes or not isinstance(block_bytes, (bytes, bytearray)):
            continue

        saved = len(block_bytes) - len(seed_bytes)
        already = credited[idx] if idx < len(credited) else 0
        delta = saved - already
        if delta <= 0:
            continue

        balances[miner] = balances.get(miner, 0.0) + float(delta)
        log_ledger_event(
            "mint",
            miner,
            float(delta),
            "compression_reward",
            block_hash,
            journal_file=journal_file,
        )
        credited[idx] = saved

    event["_credited_lengths"] = credited

    # Delta bonus logic
    global _BLOCK_HEADERS, _PENDING_BONUS, _VERIFICATION_QUEUE

    current_finalizer = header.get("finalizer") or header.get("miner")
    block_id = header.get("block_id")

    # Process queued verification from prior block
    if _VERIFICATION_QUEUE:
        prev_hdr, granted, grant_block = _VERIFICATION_QUEUE.pop(0)
        miner = _PENDING_BONUS.pop(grant_block, None)
        if miner:
            if miner == current_finalizer:
                balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                log_ledger_event(
                    "mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block
                )
            elif granted and prev_hdr:
                parent = _BLOCK_HEADERS.get(prev_hdr.get("parent_id"))
                if parent and delta_claim_valid(prev_hdr, parent):
                    balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                    log_ledger_event(
                        "mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block
                    )
                else:
                    log_ledger_event(
                        "burn", miner, _BONUS_AMOUNT, "delta_penalty", grant_block
                    )
            else:
                balances[miner] = balances.get(miner, 0.0) + _BONUS_AMOUNT
                log_ledger_event(
                    "mint", miner, _BONUS_AMOUNT, "delta_bonus", grant_block
                )

    if header:
        # Pay bonus to previous block finalizer
        prev_hdr = _BLOCK_HEADERS.get(header.get("parent_id"))
        if prev_hdr:
            prev_finalizer = prev_hdr.get("finalizer") or prev_hdr.get("miner")
            if prev_finalizer:
                balances[prev_finalizer] = balances.get(prev_finalizer, 0.0) + _BONUS_AMOUNT
                log_ledger_event(
                    "mint", prev_finalizer, _BONUS_AMOUNT, "delta_bonus", block_id
                )

        # Queue verification for this block's grant
        if block_id:
            _BLOCK_HEADERS[block_id] = header
            _VERIFICATION_QUEUE.append((prev_hdr, bool(prev_hdr), block_id))
            if current_finalizer:
                _PENDING_BONUS[block_id] = current_finalizer
