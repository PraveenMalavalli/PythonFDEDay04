"""Local practice server. Start: uv run python -m tools.mock_server.

For curl exploration only; unit tests use httpx.MockTransport instead.
"""

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit

logger = logging.getLogger(__name__)

ITEMS: list[dict[str, object]] = [
    {"id": 1, "name": "Python", "status": "active"},
    {"id": 2, "name": "Java", "status": "inactive"},
    {"id": 3, "name": "SQL", "status": "active"},
    {"id": 4, "name": "Docker", "status": "active"},
    {"id": 5, "name": "Git", "status": "inactive"},
]


class MockHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    idempotent_responses: ClassVar[dict[str, dict[str, object]]] = {}

    def _send(self, status: int, body: object) -> None:
        data = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler method name
        parsed = urlsplit(self.path)
        if parsed.path == "/items":
            params = parse_qs(parsed.query)
            try:
                page = int(params.get("page", ["1"])[0])
                per_page = int(params.get("per_page", ["2"])[0])
                if page < 1 or per_page < 1 or per_page > 100:
                    raise ValueError("invalid page")
            except ValueError:
                self._send(400, {"error": "Invalid pagination parameters"})
                return
            start = (page - 1) * per_page
            end = start + per_page
            next_page = page + 1 if end < len(ITEMS) else None
            self._send(200, {"data": ITEMS[start:end], "next_page": next_page})
            return
        if parsed.path.startswith("/items/"):
            try:
                item_id = int(parsed.path.split("/")[-1])
            except ValueError:
                self._send(404, {"error": "Not found"})
                return
            for item in ITEMS:
                if item["id"] == item_id:
                    self._send(200, item)
                    return
            self._send(404, {"error": "Not found"})
            return
        self._send(404, {"error": "Not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler method name
        if urlsplit(self.path).path != "/items":
            self._send(404, {"error": "Not found"})
            return
        key = self.headers.get("Idempotency-Key")
        if key and key in self.idempotent_responses:
            self._send(200, self.idempotent_responses[key])
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Body must be an object")
            name = payload.get("name")
            status = payload.get("status", "active")
            if not isinstance(name, str) or not name.strip() or status not in (
                "active", "inactive"
            ):
                raise ValueError("Invalid record")
        except (ValueError, json.JSONDecodeError):
            self._send(400, {"error": "Invalid JSON or item data"})
            return
        item: dict[str, object] = {"id": len(ITEMS) + 1, "name": name, "status": status}
        ITEMS.append(item)
        if key:
            self.idempotent_responses[key] = item
        self._send(201, item)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    server = ThreadingHTTPServer(("127.0.0.1", 8765), MockHandler)
    logger.info("Practice API available at http://127.0.0.1:8765")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Stopping practice API")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
