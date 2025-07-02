def list_events(directory: str = "data") -> List[Dict[str, Any]]:
    """Return a summary of all events stored in ``directory``."""

    events_dir = Path(directory) / "events"
    if not events_dir.exists():
        return []

    summaries: List[Dict[str, Any]] = []
    for path in sorted(events_dir.glob("*.json")):
        try:
            evt = load_event(str(path))
        except Exception:
            continue
        header = evt.get("header", {})
        sid = header.get("statement_id", path.stem)
        mined = sum(1 for m in evt.get("mined_status", []) if m)
        total = header.get("block_count", len(evt.get("microblocks", [])))
        summaries.append(
            {
                "statement_id": sid,
                "closed": evt.get("is_closed", False),
                "mined": mined,
                "total": total,
                "statement": evt.get("statement", ""),
            }
        )

    return summaries


def submit_statement(
    statement: str,
    wallet_id: str,
    *,
    wallet_file: str = "wallet.json",
    events_dir: str = "data/events",
) -> str:
    """Create and store a new statement event using ``wallet_id``.

    The wallet keys are loaded from ``wallet_file`` and used to sign the
    statement.  The resulting event is persisted to ``events_dir`` and the
    event identifier is returned.
    """

    try:
        pub, priv = load_wallet(Path(wallet_file))
    except Exception:
        pub, priv = signature_utils.generate_keypair()

    if wallet_id and wallet_id != pub:
        # Wallet mismatch is not fatal but warn via logging
        logging.warning("wallet_id does not match wallet file")

    event = create_event(statement, private_key=priv)
    save_event(event, events_dir)
    return event["header"]["statement_id"]
