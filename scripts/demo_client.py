#!/usr/bin/env python3
"""Cliente de demo: POST /chat no gateway."""

from __future__ import annotations

import argparse
import json
import os
import sys

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo client do agente retail")
    parser.add_argument(
        "--url",
        default=os.environ.get("GATEWAY_URL", "http://localhost:8001"),
        help="Base URL do gateway",
    )
    parser.add_argument(
        "--message",
        default="Status do pedido BR-10482 e estoque do SKU-7781",
        help="Mensagem do cliente",
    )
    args = parser.parse_args()
    health = httpx.get(f"{args.url.rstrip('/')}/health", timeout=5.0)
    health.raise_for_status()
    print("health:", json.dumps(health.json(), ensure_ascii=False))
    resp = httpx.post(
        f"{args.url.rstrip('/')}/chat",
        json={"message": args.message},
        timeout=30.0,
    )
    resp.raise_for_status()
    print("chat:", json.dumps(resp.json(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except httpx.HTTPError as exc:
        print(f"erro: {exc}", file=sys.stderr)
        raise SystemExit(1)
