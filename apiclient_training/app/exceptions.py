"""Distinct errors so callers can handle failures appropriately."""


class APIClientError(RuntimeError):
    """Base error raised by this client."""


class APIHTTPError(APIClientError):
    """Server returned a non-success HTTP response."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"HTTP request failed with status {status_code}")


class ResponseValidationError(APIClientError):
    """Response JSON does not match the documented model."""


class PaginationError(APIClientError):
    """Pagination data is unsafe or inconsistent."""
