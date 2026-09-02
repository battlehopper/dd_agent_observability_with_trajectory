"""Captura local de sessões Trajectory em JSONL (espelho do materializado)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSION_DIR = Path(".trajectory/sessions")


def append_event(session_id: str, event: dict[str, Any], enabled: bool = True) -> Path | None:
    if not enabled:
        return None
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSION_DIR / f"session-{session_id}.jsonl"
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
