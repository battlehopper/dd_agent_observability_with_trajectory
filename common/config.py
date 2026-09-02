"""Configuração compartilhada do ecossistema retail (sem dd-trace)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

SITE_ALIASES = {
    "us1": "datadoghq.com",
    "us3": "us3.datadoghq.com",
    "us5": "us5.datadoghq.com",
    "eu": "datadoghq.eu",
    "ap1": "ap1.datadoghq.com",
    "ap2": "ap2.datadoghq.com",
}


def normalize_dd_site(raw: str) -> str:
    site = (raw or "").strip().lower()
    for prefix in ("https://", "http://"):
        if site.startswith(prefix):
            site = site[len(prefix) :]
    site = site.strip("/")
    if site.startswith("app."):
        site = site[4:]
    if site.startswith("api."):
        site = site[4:]
    return SITE_ALIASES.get(site, site)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dd_api_key: str = ""
    dd_site: str = "datadoghq.com"
    dd_env: str = "dev"
    dd_llmobs_ml_app: str = "retail-assistant"
    dd_llmobs_enabled: bool = True

    dd_service_gateway: str = "retail-gateway"
    dd_service_processor: str = "retail-processor"

    trajectory_enabled: bool = True
    trajectory_export: bool = True
    trajectory_local_capture: bool = True
    trajectory_version: str = "0.1.0"
    trajectory_client_source: str = "retail-multiagent"
    trajectory_capture_level: str = "full"

    use_mock_llm: Literal["auto", "true", "false"] = "auto"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8001
    processor_host: str = "0.0.0.0"
    processor_port: int = 8002
    processor_url: str = "http://localhost:8002"

    @property
    def mock_llm(self) -> bool:
        if self.use_mock_llm == "true":
            return True
        if self.use_mock_llm == "false":
            return False
        return not bool(self.openai_api_key)

    @property
    def dd_site_normalized(self) -> str:
        return normalize_dd_site(self.dd_site)

    @property
    def llmobs_intake_url(self) -> str:
        return f"https://api.{self.dd_site_normalized}/api/intake/llm-obs/v1/trace/spans"

    @property
    def api_key_configured(self) -> bool:
        return bool(self.dd_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
