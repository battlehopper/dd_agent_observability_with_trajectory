"""Configuração compartilhada do ecossistema retail (sem dd-trace)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    def llmobs_intake_url(self) -> str:
        site = self.dd_site.lstrip("https://").lstrip("http://")
        return f"https://api.{site}/api/intake/llm-obs/v1/trace/spans"


@lru_cache
def get_settings() -> Settings:
    return Settings()
