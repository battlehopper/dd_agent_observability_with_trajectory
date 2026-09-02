"""Markers Trajectory: regras YAML avaliadas sobre tool calls do agente retail."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MARKERS_PATH = REPO_ROOT / ".trajectory" / "markers.yaml"


@dataclass
class MarkerHit:
    name: str
    description: str
    severity: str
    tool: str
    detail: str


@dataclass
class MarkerEngine:
    points: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_path(cls, path: Path | None = None) -> "MarkerEngine":
        path = path or DEFAULT_MARKERS_PATH
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(points=list(data.get("points") or []))

    def evaluate(self, tool_events: Iterable[dict[str, Any]]) -> list[MarkerHit]:
        hits: list[MarkerHit] = []
        events = list(tool_events)
        for point in self.points:
            match = point.get("match") or {}
            tools = {t.lower() for t in (match.get("tool") or [])}
            keywords = [k.lower() for k in (match.get("keywords") or [])]
            for event in events:
                tool = str(event.get("tool") or "").lower()
                blob = f"{event.get('input', '')} {event.get('output', '')}".lower()
                if tools and tool not in tools:
                    continue
                if keywords and not any(k in blob or k in tool for k in keywords):
                    continue
                hits.append(
                    MarkerHit(
                        name=point.get("name", "unnamed"),
                        description=point.get("description", ""),
                        severity=point.get("severity", "info"),
                        tool=tool,
                        detail=str(event.get("input") or "")[:200],
                    )
                )
                break
        return hits
