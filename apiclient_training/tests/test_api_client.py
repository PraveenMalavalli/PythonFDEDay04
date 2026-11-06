"""Additional offline tests for the dynamic Training Mock API client.

Place in tests/test_api_client_additional.py.
Assumes APIClient supports get_meta, get_item, create_item and iter_items,
with page, offset and cursor pagination as previously discussed.
No test contacts a real server; all requests use httpx.MockTransport.
"""

import json

import httpx
import pytest

from app.exceptions import APIClientError, APIHTTPError, PaginationError, ResponseValidationError
from app.services.api_client import APIClient

BASE_URL = "http://testserver"


def meta_payload(entity: str = "parcels", pagination: str = "offset", total: int = 3) -> dict:
    return {
        "variant": 3,
        "domain": "Training",
        "entity": entity,
        "pagination": pagination,
        "total": total,
    }


def parcel(item_id: int, name: str | None = None) -> dict:
    return {
        "id": item_id,
        "name": name or f"Parcel {item_id}",
        "status": "active",
        "category": "alpha",
        "created": "2025-01-01",
    }

def test_get_meta() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/v1/meta"
        return httpx.Response(200, json=meta_payload(total=237))

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        first = api.get_meta()
        second = api.get_meta()

    assert first.entity == "parcels"
    assert first.pagination == "offset"
    assert first.total == 237
    assert first is second  # metadata cached
    assert calls == 1


def test_get_item() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload())
        assert request.method == "GET"
        assert request.url.path == "/v1/parcels/2"
        return httpx.Response(200, json=parcel(2))

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        result = api.get_item(2)

    assert result.id == 2
    assert result.name == "Parcel 2"


def test_invalid_item() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload())
        broken = parcel(1)
        del broken["category"]
        return httpx.Response(200, json=broken)

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(ResponseValidationError):
            api.get_item(1)


def test_invalid_json() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="not-json"))
    with APIClient(BASE_URL, transport=transport) as api:
        with pytest.raises(ResponseValidationError):
            api.get_meta()


def test_page_pagination() -> None:
    requested_pages: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload("books", "page", 3))
        assert request.url.path == "/v1/books"
        page = int(request.url.params["page"])
        requested_pages.append(page)
        assert request.url.params["page_size"] == "2"
        if page == 1:
            return httpx.Response(200, json={
                "items": [parcel(1), parcel(2)], "page": 1,
                "page_size": 2, "total": 3, "has_more": True,
            })
        assert page == 2
        return httpx.Response(200, json={
            "items": [parcel(3)], "page": 2,
            "page_size": 2, "total": 3, "has_more": False,
        })

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        records = list(api.iter_items(page_size=2))

    assert [r.id for r in records] == [1, 2, 3]
    assert requested_pages == [1, 2]


def test_offset_pagination() -> None:
    requested_offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload(total=3))
        assert request.url.path == "/v1/parcels"
        offset = int(request.url.params["offset"])
        requested_offsets.append(offset)
        assert request.url.params["limit"] == "2"
        ids = [1, 2] if offset == 0 else [3]
        return httpx.Response(200, json={
            "items": [parcel(i) for i in ids],
            "offset": offset, "limit": 2, "total": 3,
        })

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        records = list(api.iter_items(page_size=2))

    assert [r.id for r in records] == [1, 2, 3]
    assert requested_offsets == [0, 2]


def test_cursor_pagination() -> None:
    seen_cursors: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload("patients", "cursor", 3))
        assert request.url.path == "/v1/patients"
        assert request.url.params["limit"] == "2"
        token = request.url.params.get("cursor")
        seen_cursors.append(token)
        if token is None:
            return httpx.Response(200, json={
                "items": [parcel(1), parcel(2)], "next_cursor": "next-2",
            })
        assert token == "next-2"
        return httpx.Response(200, json={
            "items": [parcel(3)], "next_cursor": None,
        })

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        records = list(api.iter_items(page_size=2))

    assert [r.id for r in records] == [1, 2, 3]
    assert seen_cursors == [None, "next-2"]


def test_duplicate_records() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload(total=3))
        offset = int(request.url.params["offset"])
        assert offset in (0, 2)
        ids = [1, 2] if offset == 0 else [2, 3]
        return httpx.Response(200, json={
            "items": [parcel(i) for i in ids],
            "offset": offset, "limit": 2, "total": 3,
        })

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        records = list(api.iter_items(page_size=2))

    assert [r.id for r in records] == [1, 2, 3]


def test_retry_500() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(500)
        return httpx.Response(200, json=meta_payload())

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler),
                   sleep=lambda _: None) as api:
        assert api.get_meta().entity == "parcels"

    assert attempts == 2


def test_retry_429() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=meta_payload())

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler),
                   sleep=lambda _: None) as api:
        assert api.get_meta().entity == "parcels"

    assert attempts == 2


def test_retry_after() -> None:
    delays: list[float] = []
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "3"})
        return httpx.Response(200, json=meta_payload())

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler),
                   sleep=delays.append) as api:
        api.get_meta()

    assert attempts == 2
    assert delays == [3.0]


def test_exponential_backoff() -> None:
    statuses = iter((500, 503, 200))
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json=meta_payload())

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler),
                   max_retries=2, backoff_base=1.0, jitter=lambda: 0.5,
                   sleep=delays.append) as api:
        api.get_meta()

    assert delays == [0.5, 1.0]


def test_max_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler),
                   max_retries=2, sleep=lambda _: None) as api:
        with pytest.raises(APIHTTPError) as exc:
            api.get_meta()

    assert exc.value.status_code == 503
    assert calls == 3  # initial attempt + 2 retries


def test_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(APIClientError, match="timed out"):
            api.get_meta()


def test_every_request_has_timeout() -> None:
    captured: list[object] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.extensions.get("timeout"))
        return httpx.Response(200, json=meta_payload())

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler), timeout=7.0) as api:
        api.get_meta()

    assert captured == [{"connect": 7.0, "read": 7.0, "write": 7.0, "pool": 7.0}]


@pytest.mark.parametrize("page_size", [0, -1])
def test_invalid_page_size(page_size: int) -> None:
    transport = httpx.MockTransport(lambda _: pytest.fail("Unexpected network call"))
    with APIClient(BASE_URL, transport=transport) as api:
        with pytest.raises(ValueError):
            list(api.iter_items(page_size=page_size))


def test_max_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload("books", "page", 100))
        page = int(request.url.params["page"])
        return httpx.Response(200, json={
            "items": [parcel(page)], "page": page, "page_size": 1,
            "total": 100, "has_more": True,
        })

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(PaginationError, match="max_pages"):
            list(api.iter_items(page_size=1, max_pages=2))


def test_create_item() -> None:
    sent: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload(total=237))
        assert request.method == "POST"
        assert request.url.path == "/v1/parcels"
        sent.append(json.loads(request.content))
        return httpx.Response(201, json=parcel(238, "New Parcel"))

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        created = api.create_item("New Parcel")

    assert created.id == 238
    assert created.name == "New Parcel"
    assert sent[0]["name"] == "New Parcel"


def test_post_not_retried() -> None:
    post_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal post_calls
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload())
        assert request.method == "POST"
        post_calls += 1
        return httpx.Response(503)

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler),
                   sleep=lambda _: None, max_retries=2) as api:
        with pytest.raises(APIHTTPError):
            api.create_item("New Parcel")

    assert post_calls == 1  # safe default for providers without POST idempotency


def test_repeated_cursor_detected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/meta":
            return httpx.Response(200, json=meta_payload("patients", "cursor", 100))
        return httpx.Response(200, json={
            "items": [parcel(1)], "next_cursor": "same-token",
        })

    with APIClient(BASE_URL, transport=httpx.MockTransport(handler)) as api:
        with pytest.raises(PaginationError, match="cursor"):
            list(api.iter_items(page_size=1, max_pages=5))
