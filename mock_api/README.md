# Training Mock API

A small, deliberately imperfect API for week 1 and the Week 2 check. It behaves like a real
partner system: it fails sometimes, limits your speed, repeats records, drops fields and
changes formats. The behaviour is **counted, not random**, so a mentor can predict it and a
trainee can reproduce it.

## Start it

```bash
# one-time: install what it needs (uv writes the exact versions into uv.lock)
uv sync

# run variant 3 (parcels) on port 9000
MOCK_VARIANT=3 uv run uvicorn app:app --port 9000
```

On Windows PowerShell: `$env:MOCK_VARIANT=3; uv run uvicorn app:app --port 9000`.

Try it from a second terminal:

```bash
curl -s http://127.0.0.1:9000/v1/meta | jq
curl -s "http://127.0.0.1:9000/v1/parcels?offset=0&limit=5" | jq
```

## The eight variants

| Variant | Domain | Entity path | Pagination | Quirk |
|---|---|---|---|---|
| 1 | Library | `books` | page | Every 20th call returns 500 |
| 2 | Clinic | `patients` | cursor | Every 7th call returns 429 with `Retry-After: 1` |
| 3 | Parcels | `parcels` | offset | The last record of a page repeats at the start of the next |
| 4 | Helpdesk | `tickets` | page | Some records lack `status` or `category` |
| 5 | Water utility | `outage-reports` | cursor | Every 5th call is slow (set `MOCK_SLOW_SECONDS`) |
| 6 | Retail | `products` | offset | `created` arrives in three formats |
| 7 | Training centre | `courses` | cursor | Needs a token from `POST /v1/token`; it stops working after 30 calls |
| 8 | HR leave | `employees` | page | Rate limit reported in `X-RateLimit-*` headers; 429 when exceeded |

Give each trainee the variant that matches their number (trainee 9 uses variant 1).

## Settings (environment variables, all optional)

| Name | Default | Meaning |
|---|---|---|
| `MOCK_VARIANT` | 1 | Which variant to run (1 to 8) |
| `MOCK_SEED` | 42 | Seed for the synthetic records (same seed, same data) |
| `MOCK_TOTAL` | 237 | Number of records; not a multiple of the page size on purpose |
| `MOCK_SLOW_SECONDS` | 3 | How long a slow call sleeps (variant 5) |
| `MOCK_TOKEN_CALLS` | 30 | Calls a token lasts (variant 7) |
| `MOCK_RATE_LIMIT` | 25 | Calls allowed per window (variant 8) |
| `MOCK_RATE_WINDOW` | 10 | Window length in seconds (variant 8) |

`POST /v1/_reset` puts all counters back to zero, which is handy between lab attempts.

## Check that it works

```bash
uv run pytest -q
```

## Run it in a container

Use `Dockerfile` here (replace the placeholders first, see `../PLACEHOLDERS.md`):

```bash
docker build -t mock-api:<TAG> .
docker run --rm -p 127.0.0.1:9000:8000 -e MOCK_VARIANT=3 mock-api:<TAG>
```

All data is synthetic. Do not point this at anything real.
