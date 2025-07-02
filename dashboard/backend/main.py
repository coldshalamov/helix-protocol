from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

try:
    from helix.ledger import load_balances, get_total_supply
except Exception:  # pragma: no cover - optional fallback
    from ledger import load_balances, get_total_supply  # type: ignore

from helix.event_manager import list_events, submit_statement

app = FastAPI()

EVENTS_DIR = Path("data/events")
FINALIZED_FILE = Path("finalized_statements.jsonl")


class StatementSubmission(BaseModel):
    statement: str
    wallet_id: str


@app.get("/api/events")
def get_events() -> list[dict]:
    """Return all stored events."""
    return list_events()


@app.get("/api/statements")
async def list_statements() -> list[dict]:
    """Return summary of the last 10 finalized statements."""
    if not FINALIZED_FILE.exists():
        return []

    lines = FINALIZED_FILE.read_text().splitlines()
    statements: list[dict] = []
    for line in lines[-10:]:
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


@app.get("/api/statement/{statement_id}")
async def get_statement(statement_id: str) -> dict:
    """Return the full event JSON for ``statement_id``."""
    path = EVENTS_DIR / f"{statement_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Statement not found")
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - invalid file
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/balance/{wallet_id}")
async def wallet_balance(wallet_id: str) -> dict:
    """Return HLX balance for ``wallet_id``."""
    balances = load_balances("wallet.json")
    balance = balances.get(wallet_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="Wallet not found")
    return {"wallet_id": wallet_id, "balance": balance}


@app.get("/api/supply")
async def total_supply() -> dict:
    """Return total HLX supply."""
    supply = get_total_supply("supply.json")
    return {"total_supply": supply}


@app.post("/api/submit")
async def submit(submission: StatementSubmission) -> dict:
    """Submit a new statement and return its identifier."""
    try:
        statement_id = submit_statement(submission.statement, submission.wallet_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return {"statement_id": statement_id}


if __name__ == "__main__":  # pragma: no cover - manual start
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
