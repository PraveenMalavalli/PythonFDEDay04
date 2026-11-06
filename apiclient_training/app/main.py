"""Run via: uv run python -m app.main list --page-size 2"""

import argparse
import json
import logging
import sys
from collections.abc import Sequence

from app.exceptions import APIClientError
from app.services.api_client import APIClient

logger = logging.getLogger(__name__)


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Training API client")
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    parser.add_argument("-t", "--timeout", type=float, default=5.0)

    subparsers = parser.add_subparsers(dest="action", required=True)

    listing = subparsers.add_parser("list", help="List all records across pages")
    listing.add_argument("-p", "--page-size", type=int, default=20)

    one = subparsers.add_parser("get", help="Get one record")
    one.add_argument("id", type=int)

    creation = subparsers.add_parser("create", help="Create a record")
    creation.add_argument("name")
    creation.add_argument("--status", choices=["active", "inactive"], default="active")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    args = make_parser().parse_args(argv)
    try:
        with APIClient(base_url=args.base_url, timeout=args.timeout) as client:
            if args.action == "list":
                output = [
                    item.model_dump(mode="json") for item in client.iter_items(page_size=args.page_size)
                ]
            elif args.action == "get":
                output = client.get_item(args.id).model_dump(mode="json")
            else:
                output = client.create_item(args.name, args.status).model_dump(mode="json")
    except (APIClientError, ValueError) as exc:
        logger.error("API client failed: %s", exc)
        return 1
    sys.stdout.write(json.dumps(output, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
