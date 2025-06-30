def resolve_payouts(
    event_id: str,
    winning_side: str,
    *,
    events_dir: str = "data/events",
    balances_file: str = "data/balances.json",
    supply_file: str = "supply.json",
) -> Dict[str, float]:
    """Distribute betting payouts for ``event_id`` according to ``winning_side``.

    Parameters
    ----------
    event_id:
        Identifier of the finalized event stored under ``events_dir``.
    winning_side:
        The outcome of the event, either ``"YES"`` or ``"NO"``.

    Returns
    -------
    dict
        Mapping of public keys to payout amounts applied to the ledger.
    """

    if winning_side not in {"YES", "NO"}:
        raise ValueError("winning_side must be 'YES' or 'NO'")

    evt_path = Path(events_dir) / f"{event_id}.json"
    if not evt_path.exists():
        raise FileNotFoundError(evt_path)

    event = load_event(str(evt_path))

    yes_bets, no_bets = get_bets_for_event(event)

    yes_total = sum(b.get("amount", 0) for b in yes_bets)
    no_total = sum(b.get("amount", 0) for b in no_bets)
    unaligned_total = float(event.get("unaligned_funds", 0.0))

    winning_bets = yes_bets if winning_side == "YES" else no_bets
    winning_total = yes_total if winning_side == "YES" else no_total
    losing_total = no_total if winning_side == "YES" else yes_total

    payouts: Dict[str, float] = {}

    if winning_total:
        pot_share = losing_total + unaligned_total
        for bet in winning_bets:
            pub = bet.get("pubkey")
            amt = bet.get("amount", 0)
            if not pub:
                continue
            bonus = (amt / winning_total) * pot_share if pot_share else 0.0
            payouts[pub] = payouts.get(pub, 0.0) + amt + bonus

    # Update ledger balances
    from . import ledger

    balances = ledger.load_balances(balances_file)

    # Apply any mining results recorded on the event
    apply_mining_results(event, balances)

    for acct, amount in payouts.items():
        balances[acct] = balances.get(acct, 0.0) + float(amount)

    ledger.save_balances(balances, balances_file)

    burn_amount = losing_total + unaligned_total
    if burn_amount:
        ledger.update_total_supply(-float(burn_amount), path=supply_file)

    event["resolved_payouts"] = payouts
    event["resolution"] = winning_side
    save_event(event, events_dir)

    return payouts
