"""Contrato de tags Trajectory para LLM Observability (sem dd-trace)."""

from __future__ import annotations

import socket
from typing import Mapping


def base_tags(
    *,
    ml_app: str,
    service: str,
    version: str,
    env: str,
    client_source: str,
    capture_level: str,
    extra: Mapping[str, str] | None = None,
) -> dict[str, str]:
    tags = {
        "ml_app": ml_app,
        "service": service,
        "trajectory.version": version,
        "host": socket.gethostname() or "unknown",
        "env": env,
        "trajectory.client_source": client_source,
        "trajectory.capture_level": capture_level,
        "trajectory.format_version": "1",
    }
    if extra:
        tags.update({k: v for k, v in extra.items() if v is not None})
    return tags


def format_tag_list(tags: Mapping[str, str]) -> list[str]:
    return [f"{k}:{v}" for k, v in tags.items() if v not in (None, "")]
