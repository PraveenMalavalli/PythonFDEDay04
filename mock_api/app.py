"""Training Mock API.

A small, deliberately imperfect web API that trainees call in week 1 (days 4 and 5) and in
the Week 2 check. Real partner systems are not perfect: they time out, rate-limit you, repeat
records, drop fields and change formats. This service imitates that, in a *repeatable* way,
so a trainee can learn to write a client that survives it.

HOW TO RUN (from this folder):
    MOCK_VARIANT=3 uvicorn app:app --port 9000
Then try:   curl -s "http://127.0.0.1:9000/v1/meta" | jq
            curl -s "http://127.0.0.1:9000/v1/parcels?offset=0&limit=5" | jq

The variant number (1 to 8) decides the business story, the pagination style and the quirk.
The quirks are *counted*, not random, so every run behaves the same (a mentor can predict it):

| Variant | Domain     | Entity         | Pagination | Quirk                                           |
|---------|------------|----------------|------------|-------------------------------------------------|
| 1       | Library    | books          | page       | every 20th call returns 500 (about 5%)          |
| 2       | Clinic     | patients       | cursor     | every 7th call returns 429 with Retry-After     |
| 3       | Parcels    | parcels        | offset     | the last record of a page repeats on the next   |
| 4       | Helpdesk   | tickets        | page       | some records lack `status` or `category`        |
| 5       | Water      | outage-reports | cursor     | some calls are very slow (need timeouts)        |
| 6       | Retail     | products       | offset     | `created` arrives in three different formats    |
| 7       | Training   | courses        | cursor     | the token stops working part-way (401)          |
| 8       | HR leave   | employees      | page       | rate limit is reported in response headers      |

All data is synthetic. Nothing here is real.
"""

import base64
import os
import random
import time
from datetime import date, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# ----------------------------------------------------------------------------- variants
# variant: (domain, entity path name, pagination style, quirk id)
VARIANTS = {
    1: ("Library", "books", "page", "error_500"),
    2: ("Clinic", "patients", "cursor", "rate_limit_429"),
    3: ("Parcels", "parcels", "offset", "duplicates"),
    4: ("Helpdesk", "tickets", "page", "missing_fields"),
    5: ("Water utility", "outage-reports", "cursor", "slow"),
    6: ("Retail", "products", "offset", "date_formats"),
    7: ("Training centre", "courses", "cursor", "token_expiry"),
    8: ("HR leave", "employees", "page", "header_limits"),
}

# ----------------------------------------------------------------------------- settings
# Read from the environment so a mentor can change behaviour without editing code.
VARIANT = int(os.environ.get("MOCK_VARIANT", "1"))
SEED = int(os.environ.get("MOCK_SEED", "42"))
TOTAL = int(os.environ.get("MOCK_TOTAL", "237"))  # not a multiple of the page size on purpose
SLOW_SECONDS = float(os.environ.get("MOCK_SLOW_SECONDS", "3"))
TOKEN_LIFETIME_CALLS = int(os.environ.get("MOCK_TOKEN_CALLS", "30"))
RATE_LIMIT = int(os.environ.get("MOCK_RATE_LIMIT", "25"))
RATE_WINDOW_SECONDS = float(os.environ.get("MOCK_RATE_WINDOW", "10"))

DOMAIN, ENTITY, PAGING, QUIRK = VARIANTS[VARIANT]

STATUSES = ["active", "inactive", "pending"]
CATEGORIES = ["alpha", "bravo", "charlie", "delta", "echo"]
NAMES = ["Atlas", "Birch", "Cedar", "Dune", "Ember", "Fjord", "Grove", "Harbor", "Iris", "Juniper"]


def make_records(total: int, seed: int) -> list[dict]:
    """Build the same synthetic records every time for the same seed."""
    rng = random.Random(seed)
    start = date(2025, 1, 1)
    records = []
    for i in range(1, total + 1):
        records.append(
            {
                "id": i,
                "name": f"{rng.choice(NAMES)} {i:04d}",
                "status": rng.choice(STATUSES),
                "category": rng.choice(CATEGORIES),
                "created": (start + timedelta(days=rng.randint(0, 600))).isoformat(),
            }
        )
    return records


RECORDS = make_records(TOTAL, SEED)

# ----------------------------------------------------------------------------- state
# Counters live in memory. POST /v1/_reset puts them back to zero (used by tests).
state = {"calls": 0, "token_calls": 0, "token": "token-1", "window_start": 0.0, "window_calls": 0}

app = FastAPI(title=f"Training Mock API (variant {VARIANT}: {DOMAIN})")


def reset_state() -> None:
    state.update(
        {"calls": 0, "token_calls": 0, "token": "token-1", "window_start": 0.0, "window_calls": 0}
    )


# ----------------------------------------------------------------------------- quirks
def apply_pre_quirks(request: Request) -> JSONResponse | None:
    """Run before the real work. Return a response to stop early, or None to carry on."""
    state["calls"] += 1
    n = state["calls"]

    if QUIRK == "error_500" and n % 20 == 0:
        return JSONResponse({"error": "internal_error"}, status_code=500)

    if QUIRK == "rate_limit_429" and n % 7 == 0:
        return JSONResponse(
            {"error": "too_many_requests"}, status_code=429, headers={"Retry-After": "1"}
        )

    if QUIRK == "token_expiry":
        header = request.headers.get("authorization", "")
        if header != f"Bearer {state['token']}":
            return JSONResponse({"error": "unauthorised"}, status_code=401)
        state["token_calls"] += 1
        if state["token_calls"] > TOKEN_LIFETIME_CALLS:
            return JSONResponse({"error": "token_expired"}, status_code=401)

    if QUIRK == "header_limits":
        now = time.monotonic()
        if now - state["window_start"] > RATE_WINDOW_SECONDS:
            state["window_start"] = now
            state["window_calls"] = 0
        state["window_calls"] += 1
        if state["window_calls"] > RATE_LIMIT:
            retry = max(1, int(RATE_WINDOW_SECONDS - (now - state["window_start"])))
            return JSONResponse(
                {"error": "too_many_requests"},
                status_code=429,
                headers={"Retry-After": str(retry), **rate_headers()},
            )
    return None


def rate_headers() -> dict[str, str]:
    """Headers a client should read to stay under the limit (variant 8)."""
    remaining = max(0, RATE_LIMIT - state["window_calls"])
    reset_in = max(0, int(RATE_WINDOW_SECONDS - (time.monotonic() - state["window_start"])))
    return {
        "X-RateLimit-Limit": str(RATE_LIMIT),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset_in),
    }


def shape(record: dict) -> dict:
    """Apply data quirks to one record (copy, never change the stored one)."""
    out = dict(record)
    if QUIRK == "missing_fields" and record["id"] % 7 == 0:
        out.pop("status", None)
    if QUIRK == "missing_fields" and record["id"] % 11 == 0:
        out.pop("category", None)
    if QUIRK == "date_formats":
        d = date.fromisoformat(record["created"])
        out["created"] = [d.isoformat(), d.strftime("%d/%m/%Y"), d.strftime("%b %d, %Y")][
            record["id"] % 3
        ]
    return out


# ----------------------------------------------------------------------------- routes
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/v1/meta")
def meta() -> dict:
    """Tells the trainee which story and pagination style they have."""
    return {
        "variant": VARIANT,
        "domain": DOMAIN,
        "entity": ENTITY,
        "pagination": PAGING,
        "total": TOTAL,
    }


@app.post("/v1/_reset")
def reset() -> dict[str, str]:
    reset_state()
    return {"status": "reset"}


@app.post("/v1/token")
def token() -> dict[str, str]:
    """Variant 7: get a fresh token (the old one stops working after a number of calls)."""
    state["token_calls"] = 0
    state["token"] = f"token-{int(time.time() * 1000)}"
    return {"access_token": state["token"], "token_type": "Bearer"}


def encode_cursor(position: int) -> str:
    return base64.urlsafe_b64encode(f"pos:{position}".encode()).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(base64.urlsafe_b64decode(cursor.encode()).decode().split(":")[1])
    except (ValueError, IndexError) as exc:
        raise HTTPException(status_code=400, detail="bad cursor") from exc


@app.get("/v1/{entity}")
def list_records(
    entity: str,
    request: Request,
    page: int = 1,
    page_size: int = 20,
    offset: int = 0,
    limit: int = 20,
    cursor: str | None = None,
):
    if entity != ENTITY:
        raise HTTPException(status_code=404, detail="unknown entity")
    early = apply_pre_quirks(request)
    if early is not None:
        return early

    if QUIRK == "slow" and state["calls"] % 5 == 0:
        time.sleep(SLOW_SECONDS)

    headers = rate_headers() if QUIRK == "header_limits" else {}

    if PAGING == "page":
        size = max(1, min(page_size, 100))
        start = (max(page, 1) - 1) * size
        items = RECORDS[start : start + size]
        body = {
            "items": [shape(r) for r in items],
            "page": page,
            "page_size": size,
            "total": TOTAL,
            "has_more": start + size < TOTAL,
        }
    elif PAGING == "offset":
        size = max(1, min(limit, 100))
        start = max(offset, 0)
        # Variant 3: step back by one so the previous page's last record repeats.
        real_start = max(start - 1, 0) if QUIRK == "duplicates" and start > 0 else start
        items = RECORDS[real_start : real_start + size]
        body = {
            "items": [shape(r) for r in items],
            "offset": offset,
            "limit": size,
            "total": TOTAL,
        }
    else:  # cursor
        size = max(1, min(limit, 100))
        start = decode_cursor(cursor) if cursor else 0
        items = RECORDS[start : start + size]
        nxt = start + size
        body = {
            "items": [shape(r) for r in items],
            "next_cursor": encode_cursor(nxt) if nxt < TOTAL else None,
        }
    return JSONResponse(body, headers=headers)


@app.get("/v1/{entity}/{record_id}")
def get_record(entity: str, record_id: int, request: Request):
    if entity != ENTITY:
        raise HTTPException(status_code=404, detail="unknown entity")
    early = apply_pre_quirks(request)
    if early is not None:
        return early
    if not 1 <= record_id <= TOTAL:
        raise HTTPException(status_code=404, detail="not found")
    return shape(RECORDS[record_id - 1])


@app.post("/v1/{entity}", status_code=201)
def create_record(entity: str, request: Request, body: dict):
    """Accept a record. It is not stored (this is a training API); it returns it with an id."""
    if entity != ENTITY:
        raise HTTPException(status_code=404, detail="unknown entity")
    early = apply_pre_quirks(request)
    if early is not None:
        return early
    if "name" not in body:
        raise HTTPException(status_code=422, detail="name is required")
    return {**body, "id": TOTAL + 1}
