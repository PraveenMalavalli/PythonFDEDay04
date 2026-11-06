"""Typed httpx client with timeouts, retry policy, and page iteration."""

import logging
import math
import random
import secrets
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, date
from email.utils import parsedate_to_datetime
from typing import Literal, Self

import httpx
from pydantic import ValidationError

from app.exceptions import APIClientError, APIHTTPError, PaginationError, ResponseValidationError
from app.models.item import (
    APIMeta,
    Item,
    PageResult,
    OffsetResult,
    CursorResult,
)

logger = logging.getLogger(__name__)
formatter = logging.Formatter('%(lineno)d:%(levelname)s:%(name)s:%(message)s')

fileHandler = logging.FileHandler("client.log")
fileHandler.setFormatter(formatter)

logger.addHandler(fileHandler)
logger.setLevel(logging.INFO)

logger.propagate = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


class APIClient:
    """Client for the practice /items API; GET requests are safe to retry.

    POST requests include an Idempotency-Key. Only retry POST on real APIs
    if the provider explicitly supports this header or equivalent semantics.
    """

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        max_retries: int = 3,
        backoff_base: float = 0.5,
        backoff_cap: float = 8.0,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        jitter: Callable[[], float] = random.random,
        now: Callable[[], datetime] = _utc_now,
    ) -> None:
        if timeout <= 0 or not math.isfinite(timeout):
            raise ValueError("timeout must be a finite positive number")
        if max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if backoff_base <= 0 or backoff_cap <= 0:
            raise ValueError("backoff durations must be positive")
        self.timeout = httpx.Timeout(timeout)
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_cap = backoff_cap
        self._sleep = sleep
        self._jitter = jitter
        self._now = now
        self._http = httpx.Client(base_url=base_url, timeout=self.timeout, transport=transport)
        self._meta: APIMeta | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, _exc_type: object, _exc_value: object, _traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _delay(self, response: httpx.Response, attempt: int) -> float:
        """Respect valid Retry-After seconds or HTTP dates; otherwise use full jitter."""
        value = response.headers.get("Retry-After")
        if value:
            try:
                seconds = float(value)
            except ValueError:
                seconds = -1.0
            if math.isfinite(seconds) and seconds >= 0:
                return seconds
            try:
                when = parsedate_to_datetime(value)
                if when.tzinfo is None:
                    when = when.replace(tzinfo=UTC)
                return max(0.0, (when - self._now()).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass

        maximum = min(self.backoff_cap, self.backoff_base * (2**attempt))
        return maximum * min(1.0, max(0.0, self._jitter()))

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, int | str] | None = None,
        json_body: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> object:
        for attempt in range(self.max_retries + 1):
            try:
                response = self._http.request(
                    method,
                    path,
                    params=params,
                    json=json_body,
                    headers=headers,
                    timeout=self.timeout,
                )
            except httpx.TimeoutException as exc:
                raise APIClientError("Request timed out") from exc
            except httpx.TransportError as exc:
                raise APIClientError("Network transport failed") from exc

            retryable = (
                    method.upper() == "GET"
                    and (
                        response.status_code == 429
                        or 500 <= response.status_code <= 599
                    )
                )
            if retryable and attempt < self.max_retries:
                delay = self._delay(response, attempt)
                logger.warning(
                    "HTTP %d; retry %d of %d in %.2f seconds",
                    response.status_code,
                    attempt + 1,
                    self.max_retries,
                    delay,
                )
                self._sleep(delay)
                continue
            if not 200 <= response.status_code < 300:
                raise APIHTTPError(response.status_code)

            try:
                return response.json()
            except ValueError as exc:
                raise ResponseValidationError("Server did not return valid JSON") from exc

        raise AssertionError("Unreachable retry loop termination")

    def get_meta(self) -> APIMeta:
        if self._meta is None:
            payload = self._request("GET", "/v1/meta")

            try:
                self._meta = APIMeta.model_validate(payload)
            except ValidationError as exc:
                raise ResponseValidationError(
                    "Invalid API metadata"
                ) from exc

        return self._meta

    def get_item(self, item_id: int) -> Item:
        if item_id < 1:
            raise ValueError("item_id must be positive")
        meta = self.get_meta()

        payload = self._request(
            "GET",
            f"/v1/{meta.entity}/{item_id}",
        )
        try:
            return Item.model_validate(payload)
        except ValidationError as exc:
            raise ResponseValidationError("Invalid item record") from exc

    def create_item(self, name: str, status: Literal["active", "inactive", "pending"] = "active") -> Item:
        """Create an item; the demo server honors the Idempotency-Key header."""
        meta = self.get_meta()
        path = f"/v1/{meta.entity}"

        payload = self._request(
            "POST",
            path,
            json_body={"name": name, "status": status, "category": "alpha","created": date.today().isoformat()},
            headers={"Idempotency-Key": secrets.token_hex(16)},
        )
        try:
            return Item.model_validate(payload)
        except ValidationError as exc:
            raise ResponseValidationError("Invalid created item record") from exc

    
    
    def iter_items(
        self,
        *,
        page_size: int = 20,
        max_pages: int = 1000,
    ) -> Iterator[Item]:

        if page_size < 1 or max_pages < 1:
            raise ValueError("Invalid pagination settings")

        meta = self.get_meta()

        path = f"/v1/{meta.entity}"
        size = min(page_size, 100)

        page_number = 1
        offset = 0
        cursor: str | None = None

        seen_ids: set[int] = set()
        seen_cursors: set[str] = set()

        for _ in range(max_pages):

            # Select parameters based on server metadata
            params: dict[str, int | str]

            if meta.pagination == "page":
                params = {
                    "page": page_number,
                    "page_size": size,
                }

            elif meta.pagination == "offset":
                params = {
                    "offset": offset,
                    "limit": size,
                }

            else:
                params = {"limit": size}

                if cursor is not None:
                    params["cursor"] = cursor

            # Send request using the selected parameters
            logger.info(f"Requesting offset={offset}, limit={size}")
            payload = self._request(
                "GET",
                path,
                params=params,
            )

            # Validate the response according to its style
            try:
                logger.info(f"Payload: {payload}\nPagination: {meta.pagination}")
                if meta.pagination == "page":
                    result = PageResult.model_validate(payload)
                    records = result.items

                elif meta.pagination == "offset":
                    logger.info(payload)
                    result = OffsetResult.model_validate(payload)
                    records = result.items

                else:
                    result = CursorResult.model_validate(payload)
                    records = result.items

            except ValidationError as exc:
                logger.error("Pydantic validation failed:\n%s", exc)

                raise ResponseValidationError(
                    f"Invalid paginated API response: {exc}"
                ) from exc

            # Return each unique, validated item
            for item in records:
                if item.id not in seen_ids:
                    seen_ids.add(item.id)
                    yield item

            # Determine how to request the next page
            if isinstance(result, PageResult):
                if not result.has_more:
                    return

                page_number += 1

            elif isinstance(result, OffsetResult):
                if len(seen_ids) >= meta.total:
                    return

                if not records:
                    raise PaginationError(
                        "Empty page before all records were found"
                    )

                offset += result.limit

            elif isinstance(result, CursorResult):
                next_cursor = result.next_cursor

                if next_cursor is None:
                    return

                if next_cursor in seen_cursors:
                    raise PaginationError(
                        "Repeated pagination cursor"
                    )

                seen_cursors.add(next_cursor)
                cursor = next_cursor

        raise PaginationError(
            f"Pagination exceeded max_pages={max_pages}"
        )


