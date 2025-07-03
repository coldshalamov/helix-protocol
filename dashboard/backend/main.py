from __future__ import annotations

import json
import base64
import math
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from helix import signature_utils
from helix.event_manager import (
    create_event,
    save_event,
    load_event,
    list_events as list_saved_events,
    get_bets_for_event,
)
from helix.utils import compression_ratio

try:
    from helix.ledger import load_balances, get_total_supply
except Exception:
    from ledger import load_balances, get_total_supply  # type: ignore

try:
    from helix.event_manager import submit_statement as submit_event_statement
except Exception:
    from event_manager import submit_statement as submit_event_statement  # type: ignore

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EVENTS_DIR = Path("data/events")
FINALIZED_FILE = Path("finalized_statements.jsonl")

class SubmitRequest(BaseModel):
    statement: str
    wallet_id: str
    microblock_size: int = 3

@app.post("/api/submit")
async def submit_statement(req: SubmitRequest) -> dict:
    """Create a new statement event and return its ID."""
    try:
        event = create_event(
            req.statement,
            microblock_size=req.microblock_size,
            private_key=signature_utils.load_keys("wallet.json")[1],
        )
        save_event(event, str(EVENTS_DIR))
        return {
            "event_id": event["header"]["statement_id"],
            "block_count": event["header"]["block_count"],
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

@app.get("/api/statements")
async def list_statements(limit: int = 10) -> list[dict]:
    if not FINALIZED_FILE.exists() or limit <= 0:
        return []
    lines = FINALIZED_FILE.read_text().splitlines()[-limit:]
    statements: list[dict] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except Exception:
            continue
        statements.append(
            {
                "statement_id": entry.get("statement_id"),
                "timestamp": entry.get("timestamp"),
                "delta_seconds": entry.get("delta_seconds"),
                "compression_ratio": entry.get("compression_ratio"),
            }
        )
    return statements

@app.get("/api/statements/history")
async def list_statement_history(limit: int = 10) -> list[dict]:
    """Return finalized statement history sorted from newest to oldest."""
    if not FINALIZED_FILE.exists() or limit <= 0:
        return []

    entries: list[dict] = []
    for line in FINALIZED_FILE.read_text().splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if "timestamp" not in item:
            continue
        entries.append(item)

    entries.sort(key=lambda e: e.get("timestamp", 0), reverse=True)
    results: list[dict] = []
    for entry in entries[:limit]:
        sid = entry.get("statement_id")
        statement = entry.get("statement")
        seeds = entry.get("seeds")
        compression = entry.get("compression_ratio")
        path = EVENTS_DIR / f"{sid}.json"
        if path.exists():
            try:
                event = load_event(str(path))
                statement = event.get("statement", statement)
                seeds = event.get("seeds", seeds)
                seeds = [
                    s.hex() if isinstance(s, (bytes, bytearray)) else s
                    for s in seeds
                ]
                compression = compression_ratio(event)
            except Exception:
                pass

        if isinstance(seeds, list):
            seeds = [s.hex() if isinstance(s, (bytes, bytearray)) else s for s in seeds]

        results.append(
            {
                "statement_id": sid,
                "finalized": True,
                "timestamp": entry.get("timestamp"),
                "statement": statement,
                "seeds": seeds,
                "compression_ratio": compression,
            }
        )

    return results

@app.get("/api/statements/active_status")
async def list_active_statements() -> list[dict]:
    """Return all active (unfinalized) statements sorted newest first."""
    if not EVENTS_DIR.exists():
        return []

    entries: list[tuple[float, dict]] = []
    for path in EVENTS_DIR.glob("*.json"):
        try:
            event = load_event(str(path))
        except Exception:
            continue
        if event.get("finalized"):
            continue
        header = event.get("header", {})
        statement = event.get("statement", "")
        micro_size = int(header.get("microblock_size", 0))
        block_count = int(header.get("block_count", math.ceil(len(statement) / micro_size))) if micro_size else 0
        seeds = event.get("seeds", [None] * block_count)
        mined_blocks = []
        for idx, seed in enumerate(seeds):
            if not seed:
                continue
            if isinstance(seed, list):
                seed_hex = bytes(seed).hex()
            elif isinstance(seed, str):
                seed_hex = seed
            else:
                seed_hex = bytes(seed).hex()
            mined_blocks.append({"index": idx, "seed": seed_hex})
        unmined_blocks = [idx for idx, seed in enumerate(seeds) if not seed]
        header_b64 = base64.b64encode(json.dumps(header).encode("utf-8")).decode("ascii")
        submitted_at = int(path.stat().st_mtime)
        entry = {
            "statement_id": header.get("statement_id", path.stem),
            "statement": statement,
            "header": header_b64,
            "microblock_size": micro_size,
            "microblock_count": block_count,
            "mined_blocks": mined_blocks,
            "unmined_blocks": unmined_blocks,
            "submitted_at": submitted_at,
            "wallet_id": event.get("originator_pub"),
            "finalized": False,
        }
        entries.append((submitted_at, entry))

    entries.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in entries]


@app.get("/api/pending")
async def list_pending() -> list[dict]:
    """Return pending statements with encoded microblocks."""

    if not EVENTS_DIR.exists():
        return []

    results: list[dict] = []
    for path in EVENTS_DIR.glob("*.json"):
        try:
            event = load_event(str(path))
        except Exception:
            continue
        if event.get("finalized"):
            continue
        header = event.get("header", {})
        blocks = event.get("microblocks", [])
        microblocks = [base64.b64encode(b).decode("ascii") for b in blocks]
        seeds = []
        for idx, seed in enumerate(event.get("seeds", [])):
            if not seed:
                continue
            if isinstance(seed, (bytes, bytearray)):
                seed_hex = seed.hex()
            elif isinstance(seed, str):
                seed_hex = seed
            else:
                seed_hex = bytes(seed).hex()
            seeds.append({"index": idx, "seed": seed_hex})
        block_size = len(blocks[0]) if blocks else header.get("microblock_size", 0)
        payload_length = header.get("payload_length") or sum(len(b) for b in blocks)
        results.append(
            {
                "statement_id": header.get("statement_id"),
                "author": header.get("author_id"),
                "previous_hash": header.get("previous_hash"),
                "microblocks": microblocks,
                "block_size": block_size,
                "payload_length": payload_length,
                "seeds": seeds,
            }
        )

    return results

@app.get("/api/events")
async def list_events() -> list[dict]:
    if not EVENTS_DIR.exists():
        return []
    events: list[dict] = []
    for path in sorted(EVENTS_DIR.glob("*.json")):
        try:
            event = load_event(str(path))
        except Exception:
            continue
        if not event.get("is_closed") and not event.get("finalized"):
            continue
        header = event.get("header", {})
        evt_id = header.get("statement_id", path.stem)
        events.append(
            {
                "id": evt_id,
                "statement": event.get("statement"),
                "compression": compression_ratio(event),
            }
        )
    return events

@app.get("/api/statement/{statement_id}")
async def get_statement(statement_id: str) -> dict:
    path = EVENTS_DIR / f"{statement_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Statement not found")
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - invalid file
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/bets/status/{statement_id}")
async def bet_status(statement_id: str) -> dict:
    """Return total HLX bet on TRUE and FALSE for ``statement_id``."""
    path = EVENTS_DIR / f"{statement_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Statement not found")

    try:
        event = load_event(str(path))
    except Exception as exc:  # pragma: no cover - invalid file
        raise HTTPException(status_code=500, detail=str(exc))

    yes_bets, no_bets = get_bets_for_event(event)
    total_true = sum(float(b.get("amount", 0)) for b in yes_bets)
    total_false = sum(float(b.get("amount", 0)) for b in no_bets)

    return {
        "statement_id": statement_id,
        "total_true_bets": total_true,
        "total_false_bets": total_false,
    }

@app.get("/api/balance/{wallet_id}")
async def wallet_balance(wallet_id: str) -> dict:
    """Return HLX balance for ``wallet_id``."""
    balances = load_balances("balances.json")
    balance = balances.get(wallet_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"wallet_id": wallet_id, "balance": balance}

@app.get("/api/supply")
async def total_supply() -> dict:
    supply = get_total_supply("supply.json")
    return {"total_supply": supply}

@app.get("/api/events/summary")
def get_events_summary() -> list[dict]:
    return list_saved_events("data")

# ---------------------------
# FRONTEND STATIC FILES LAST
# ---------------------------

frontend_build = Path("dashboard/frontend/build")
if frontend_build.exists():
    app.mount("/", StaticFiles(directory=frontend_build, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
