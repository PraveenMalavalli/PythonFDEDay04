# Training Mock API exercise — complete guided practice

This is a **local example**, not the actual “Training Mock API” from the assignment.
The named API instructions weren't present in the accessible Files. Substitute the real
base URL, endpoints, JSON fields, authentication and pagination rules once available.

## 0. Setup in Ubuntu WSL

From the project directory:

```bash
uv sync --group dev
# If you don't have jq: sudo apt update && sudo apt install -y jq
curl --version
jq --version
```

The project uses the familiar `app/models`, `app/services`, `app/main.py`, `tests` layout.

## 1. Start a LOCAL practice API (terminal 1)

```bash
uv run python -m tools.mock_server
```

Leave that terminal open. The server only listens on 127.0.0.1 (your own WSL environment)
and returns `GET /items?page=1&per_page=2`, `GET /items/1`, and `POST /items`.

## 2. Curl exploration (terminal 2)

```bash
BASE_URL='http://127.0.0.1:8765'

# -i includes response HEADERS and BODY (do not pipe this to jq)
curl -i "$BASE_URL/items/1"

# -s is silent. -S restores visible curl errors. GET returns JSON.
curl -sS "$BASE_URL/items?page=1&per_page=2"

# -H supplies a request header
curl -sS -H 'Accept: application/json' "$BASE_URL/items/1"

# -X sets the HTTP method; -d sends JSON body; -H sets content type
curl -sS -X POST -H 'Content-Type: application/json' \
  -d '{"name":"HTTPX","status":"active"}' "$BASE_URL/items"

# -o writes the response BODY to a file
curl -sS -o page.json "$BASE_URL/items?page=1&per_page=2"
cat page.json

# Follow-up: observe response status while discarding body
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE_URL/items/1"
```

`-d` usually implies POST, so `-X POST` is included here to practice that required flag.
`-i` mixes headers into the output, so avoid sending it directly to `jq`.

## 3. jq exploration

The practice server returns a page:

```json
{
  "data": [
    {"id": 1, "name": "Python", "status": "active"},
    {"id": 2, "name": "Java", "status": "inactive"}
  ],
  "next_page": 2
}
```

```bash
curl -sS "$BASE_URL/items?page=1&per_page=2" | jq '.'
curl -sS "$BASE_URL/items?page=1&per_page=2" | jq '.data | .[0]'
curl -sS "$BASE_URL/items?page=1&per_page=2" | jq '.data[0].name'
curl -sS "$BASE_URL/items?page=1&per_page=2" | jq '.data[] | select(.status == "active")'
curl -sS "$BASE_URL/items?page=1&per_page=2" | jq '.data | length'
# Using -o result from previous step:
jq '.next_page' page.json
```

- `.`: the entire current JSON value
- `.[0]`: first element when the current value is an array
- `.field`: value of a field on an object, e.g. `.name`
- `select(condition)`: filter items to those matching a condition
- `length`: length of an array or object; also works on some other types

## 4. One request using Python HTTPX

```python
import httpx

with httpx.Client(timeout=5.0) as client:
    response = client.get("http://127.0.0.1:8765/items", params={"page": 1, "per_page": 2})
    response.raise_for_status()
    data = response.json()

print(data["data"][0]["name"])
```

This is equivalent to curl GET. The code in `app/services/api_client.py` adds retries,
validation and pagination to this basic call.

## 5. Run the completed Python API client

```bash
uv run python -m app.main list --page-size 2
uv run python -m app.main get 1
uv run python -m app.main create "Pytest" --status active
```

For a different host use `--base-url` **before** the command name:

```bash
uv run python -m app.main --base-url http://127.0.0.1:8765 list --page-size 2
```

### How the Python files fit together

| File | Purpose |
|---|---|
| `app/main.py` | CLI entry point (argparse); writes JSON to stdout |
| `app/models/item.py` | Pydantic models validating **each** returned record and page |
| `app/services/api_client.py` | HTTPX requests, timeouts, retry policy, pagination iterator |
| `app/exceptions.py` | Specific errors for HTTP, validation and pagination |
| `tools/mock_server.py` | Local, optional API for learning curl/jq |
| `tests/test_api_client.py` | Offline HTTPX `MockTransport` tests |
| `docs/SDK_VS_REST.md` | Required SDK-versus-REST decision note |

## 6. How retries work

- A call has a **5-second default HTTPX timeout** (overridable).
- For **429** (rate limit) or any **5xx**, wait then retry, up to `max_retries=3`.
- Prefer a valid `Retry-After` value: seconds or an HTTP-date.
- Otherwise wait up to `min(8, 0.5 * 2**attempt)` seconds, multiplied by random jitter.
- On ordinary **400**, **401**, **403**, **404**, do **not** retry.
- After all retries fail, raise `APIHTTPError`.
- POST requests carry the same `Idempotency-Key` on retries. **Real APIs must
  explicitly support idempotency for retried writes**; otherwise disable write retries.
- Network/timeout exceptions become `APIClientError` and are not retried in this example.

Example fallback exponential maximum delays: attempt 1 <=0.5s, attempt 2 <=1s,
attempt 3 <=2s. Jitter randomizes the actual wait so all clients do not retry together.

## 7. Pagination and validation

`for item in client.iter_items(page_size=2):` requests page 1, yields its items,
then follows `next_page` until null. Items are Pydantic validated on every page.
Malformed records raise `ResponseValidationError`, not silent corruption.
A page loop or excessive page count raises `PaginationError`.

## 8. Tests — no external network

```bash
uv run python -m pytest -v
uv run ruff check .
uv run ruff format --check .
uv run pyright
```

All unit tests use `httpx.MockTransport(handler)`, which calls a fake function instead
of opening a TCP connection. The `sleep` and random-jitter callbacks are injected
for deterministic, instant tests.

## 9. Completion checklist

- [ ] Can start the local mock server and fetch `/items` with curl
- [ ] Have used `-i -s -H -d -X -o` and can explain each
- [ ] Have used jq `.`, `.[0]`, `.field`, `select`, and `length`
- [ ] Can explain HTTP GET vs POST
- [ ] Can use HTTPX with `timeout` and `raise_for_status()`
- [ ] Can explain 429, 500, 503, exponential backoff, jitter, `Retry-After`
- [ ] Can trace the iterator across multiple pages
- [ ] Understand why Pydantic rejects invalid API records
- [ ] `pytest` passes with zero network use
- [ ] Run Ruff and Pyright; fix any reported issues
- [ ] Read `docs/SDK_VS_REST.md` and understand when an official SDK is preferable
- [ ] Adapt schema, paths, authentication, pagination to the actual Training Mock API

## Actual provider API checklist (once instructions are available)

1. Read the real README and determine base URL, endpoints and required authentication.
2. Explore GET endpoints with curl first; **never commit real tokens**.
3. Inspect actual JSON and change `Item` / `ItemsPage` to match.
4. Check if pagination uses page numbers, offsets, a `next` URL or cursors.
5. Confirm whether the provider supports POST idempotency keys before retrying writes.
6. Add `MockTransport` tests for the real page and error shapes.
