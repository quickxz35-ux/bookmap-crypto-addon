#!/usr/bin/env python3
"""Small terminal client for the local Brain Bridge."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://127.0.0.1:5000"


def _request_json(url: str, payload: dict | None = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    with urllib.request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the local Brain Bridge from the terminal.")
    parser.add_argument("query", nargs="*", help="Query text, e.g. BTC or 'BTC setup'")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"Bridge base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--health", action="store_true", help="Check bridge health instead of asking a question")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")

    try:
        if args.health:
            payload = _request_json(f"{base_url}/health")
            print(json.dumps(payload, indent=2))
            return 0

        query = " ".join(args.query).strip()
        if not query:
            query = "BTC"

        payload = _request_json(f"{base_url}/ask", {"query": query})
        print(f"Verdict: {payload.get('verdict', '')}")
        print(f"Score: {payload.get('score', '')}")
        print(f"Logs: {payload.get('logs', '')}")
        return 0
    except urllib.error.URLError as exc:
        print(f"Bridge error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - terminal helper
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
