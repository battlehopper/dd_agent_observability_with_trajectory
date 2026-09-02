"""Exportador HTTP para Datadog LLM Observability (transporte usado pelo Trajectory)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx

from common.config import Settings

logger = logging.getLogger(__name__)
EXPORT_DIR = Path(".trajectory/export")


class TrajectoryExporter:
    """Envia spans no contrato da API HTTP de LLM Observability — sem dd-trace."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def export(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._write_local(payload)
        if not self.settings.trajectory_export or not self.settings.dd_llmobs_enabled:
            return {"ok": True, "exported": False, "reason": "export_disabled"}
        if not self.settings.dd_api_key:
            return {"ok": True, "exported": False, "reason": "missing_api_key"}
        try:
            response = httpx.post(
                self.settings.llmobs_intake_url,
                headers={
                    "DD-API-KEY": self.settings.dd_api_key,
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=10.0,
            )
            return {
                "ok": response.status_code in (200, 202),
                "exported": True,
                "status_code": response.status_code,
                "body": response.text[:500],
            }
        except httpx.HTTPError as exc:
            logger.warning("Trajectory export failed: %s", exc)
            return {"ok": False, "exported": True, "error": str(exc)}

    def _write_local(self, payload: dict[str, Any]) -> None:
        if not self.settings.trajectory_local_capture:
            return
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        spans: list[dict[str, Any]] = list(
            payload.get("data", {}).get("attributes", {}).get("spans") or []
        )
        trace_id = "unknown"
        for span in spans:
            trace_id = span.get("trace_id") or trace_id
            break
        path = EXPORT_DIR / f"trace-{trace_id}.json"
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                old = existing.get("data", {}).get("attributes", {}).get("spans") or []
                merged = {s.get("span_id"): s for s in old}
                for span in spans:
                    merged[span.get("span_id")] = span
                payload["data"]["attributes"]["spans"] = list(merged.values())
            except (json.JSONDecodeError, OSError, TypeError):
                payload["data"]["attributes"]["spans"] = spans
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
