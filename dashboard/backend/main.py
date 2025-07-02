from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from helix import signature_utils
from helix.event_manager import (
    create_event,
    save_event,
    load_event,
    list_events as list_saved_events,
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

# ---------------------
# API ROUTES COME FIRST
# ---------------------

EVENTS_DIR = Path("data/events")
FINALIZED_FILE = Path("finalized_statements.jsonl")

class SubmitRequest(BaseModel):
    statement: str
    wallet_id: str
    microblock_size: int = 3

@app.post("/api/submit")
async def submit_statement(req: SubmitRequest) -> dict:
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
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@app.get("/api/balance/{wallet_id}")
async def wallet_balance(wallet_id: str) -> dict:
    balances = load_balances("wallet.json")
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
