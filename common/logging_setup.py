"""Logs visíveis no `docker compose logs` da EC2."""

from __future__ import annotations

import logging

from common.config import Settings


def configure_logging(settings: Settings, service: str) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        force=True,
    )
    log = logging.getLogger("retail")
    key_state = "set" if settings.api_key_configured else "MISSING"
    log.info(
        "startup service=%s ml_app=%s env=%s site=%s intake=%s api_key=%s export=%s",
        service,
        settings.dd_llmobs_ml_app,
        settings.dd_env,
        settings.dd_site_normalized,
        settings.llmobs_intake_url,
        key_state,
        settings.trajectory_export,
    )
    if not settings.api_key_configured:
        log.error("DD_API_KEY não chegou no container — traces não vão para o Datadog.")
