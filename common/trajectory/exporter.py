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
        self.last_result: dict[str, Any] = {"exported": False, "reason": "no_flush_yet"}

    def status(self) -> dict[str, Any]:
        return {
            "export_enabled": bool(self.settings.trajectory_export and self.settings.dd_llmobs_enabled),
            "api_key_configured": self.settings.api_key_configured,
            "dd_site": self.settings.dd_site_normalized,
            "intake_url": self.settings.llmobs_intake_url,
            "ml_app": self.settings.dd_llmobs_ml_app,
            "env": self.settings.dd_env,
            "last_export": dict(self.last_result),
        }

    def export(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._write_local(payload)
        if not self.settings.trajectory_export or not self.settings.dd_llmobs_enabled:
            self.last_result = {"ok": True, "exported": False, "reason": "export_disabled"}
            logger.warning("Trajectory export skipped: export_disabled")
            return self.last_result
        if not self.settings.api_key_configured:
            self.last_result = {"ok": True, "exported": False, "reason": "missing_api_key"}
            logger.error(
                "Trajectory export skipped: DD_API_KEY vazia. "
                "Preencha .env e recrie os containers (docker compose up -d --force-recreate)."
            )
            return self.last_result
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
            self.last_result = {
                "ok": response.status_code in (200, 202),
                "exported": True,
                "status_code": response.status_code,
                "body": response.text[:500],
                "intake_url": self.settings.llmobs_intake_url,
            }
            if self.last_result["ok"]:
                logger.info(
                    "Trajectory export ok status=%s site=%s ml_app=%s spans=%s",
                    response.status_code,
                    self.settings.dd_site_normalized,
                    self.settings.dd_llmobs_ml_app,
                    len(payload.get("data", {}).get("attributes", {}).get("spans") or []),
                )
            else:
                logger.error(
                    "Trajectory export rejected status=%s site=%s body=%s",
                    response.status_code,
                    self.settings.dd_site_normalized,
                    response.text[:500],
                )
            return self.last_result
        except httpx.HTTPError as exc:
            logger.error("Trajectory export failed: %s", exc)
            self.last_result = {"ok": False, "exported": True, "error": str(exc)}
            return self.last_result

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
