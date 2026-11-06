"""Tests that prove each variant's quirk behaves as the README promises.

Run:  python -m pytest -q      (from this folder)
Each test reloads the app with a different MOCK_VARIANT, because the variant is read once
when the module is imported.
"""

import importlib

import pytest
from fastapi.testclient import TestClient


def load(variant: int, **env) -> tuple:
    """Import the app fresh for one variant and return (module, client)."""
    import os

    os.environ["MOCK_VARIANT"] = str(variant)
    for key, value in env.items():
        os.environ[key] = str(value)
    import app as module

    module = importlib.reload(module)
    module.reset_state()
    return module, TestClient(module.app)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in ("MOCK_SLOW_SECONDS", "MOCK_TOKEN_CALLS", "MOCK_RATE_LIMIT", "MOCK_RATE_WINDOW"):
        monkeypatch.delenv(key, raising=False)


def test_meta_describes_the_variant():
    _, client = load(3)
    assert client.get("/v1/meta").json()["pagination"] == "offset"


def test_page_pagination_walks_all_records_variant_1_skipping_errors():
    module, client = load(1)
    seen, page = [], 1
    while True:
        response = client.get(f"/v1/{module.ENTITY}", params={"page": page, "page_size": 50})
        if response.status_code == 500:  # the quirk: every 20th call fails; a real client retries
            continue
        body = response.json()
        seen += [r["id"] for r in body["items"]]
        if not body["has_more"]:
            break
        page += 1
    assert seen == list(range(1, module.TOTAL + 1))


def test_variant_1_every_twentieth_call_is_500():
    module, client = load(1)
    codes = [client.get(f"/v1/{module.ENTITY}").status_code for _ in range(20)]
    assert codes[-1] == 500
    assert codes[:-1] == [200] * 19


def test_variant_2_every_seventh_call_is_429_with_retry_after():
    module, client = load(2)
    responses = [client.get(f"/v1/{module.ENTITY}") for _ in range(7)]
    assert responses[-1].status_code == 429
    assert responses[-1].headers["Retry-After"] == "1"


def test_variant_2_cursor_pagination_reaches_the_end():
    module, client = load(2)
    ids, cursor = [], None
    for _ in range(100):
        params = {"limit": 50, **({"cursor": cursor} if cursor else {})}
        response = client.get(f"/v1/{module.ENTITY}", params=params)
        if response.status_code == 429:
            continue
        body = response.json()
        ids += [r["id"] for r in body["items"]]
        cursor = body["next_cursor"]
        if cursor is None:
            break
    assert ids == list(range(1, module.TOTAL + 1))


def test_variant_3_offset_pages_repeat_a_record():
    module, client = load(3)
    first = client.get(f"/v1/{module.ENTITY}", params={"offset": 0, "limit": 10}).json()["items"]
    second = client.get(f"/v1/{module.ENTITY}", params={"offset": 10, "limit": 10}).json()["items"]
    assert first[-1]["id"] == second[0]["id"]


def test_variant_4_some_records_lack_fields():
    module, client = load(4)
    items = client.get(f"/v1/{module.ENTITY}", params={"page": 1, "page_size": 30}).json()["items"]
    assert any("status" not in item for item in items)
    assert any("category" not in item for item in items)


def test_variant_5_every_fifth_call_is_slow():
    module, client = load(5, MOCK_SLOW_SECONDS="0.2")
    import time

    durations = []
    for _ in range(5):
        start = time.perf_counter()
        client.get(f"/v1/{module.ENTITY}")
        durations.append(time.perf_counter() - start)
    assert durations[-1] >= 0.2
    assert max(durations[:-1]) < 0.2


def test_variant_6_dates_arrive_in_three_formats():
    module, client = load(6)
    items = client.get(f"/v1/{module.ENTITY}", params={"offset": 0, "limit": 30}).json()["items"]
    formats = {
        (
            "-" in i["created"] and "/" not in i["created"] and "," not in i["created"],
            "/" in i["created"],
            "," in i["created"],
        )
        for i in items
    }
    assert len(formats) == 3


def test_variant_7_needs_a_token_and_it_expires():
    module, client = load(7, MOCK_TOKEN_CALLS="3")
    assert client.get(f"/v1/{module.ENTITY}").status_code == 401  # no token
    token = client.post("/v1/token").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    codes = [client.get(f"/v1/{module.ENTITY}", headers=headers).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 401]
    fresh = client.post("/v1/token").json()["access_token"]
    assert (
        client.get(
            f"/v1/{module.ENTITY}", headers={"Authorization": f"Bearer {fresh}"}
        ).status_code
        == 200
    )


def test_variant_8_reports_rate_limit_in_headers_and_then_blocks():
    module, client = load(8, MOCK_RATE_LIMIT="3", MOCK_RATE_WINDOW="60")
    first = client.get(f"/v1/{module.ENTITY}")
    assert first.headers["X-RateLimit-Limit"] == "3"
    assert first.headers["X-RateLimit-Remaining"] == "2"
    codes = [client.get(f"/v1/{module.ENTITY}").status_code for _ in range(3)]
    assert codes[-1] == 429


def test_unknown_entity_is_404():
    _, client = load(1)
    assert client.get("/v1/unknown").status_code == 404


def test_create_requires_a_name():
    module, client = load(8)
    assert client.post(f"/v1/{module.ENTITY}", json={}).status_code == 422
    assert client.post(f"/v1/{module.ENTITY}", json={"name": "x"}).status_code == 201
