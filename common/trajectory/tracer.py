"""Tracer Trajectory: spans LLM Observability sem dd-trace.

Emite o mesmo transporte HTTP que o Trajectory usa para Datadog LLM Observability,
com o contrato de tags documentado em docs/LLM-OBS-SPAN-TAGS.md do datadog-labs/trajectory.
"""

from __future__ import annotations

import contextvars
import logging
import time
import traceback
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

from common.config import Settings, get_settings
from common.trajectory.context import DistributedContext, extract_context
from common.trajectory.exporter import TrajectoryExporter
from common.trajectory.session import append_event
from common.trajectory.tags import base_tags, format_tag_list

logger = logging.getLogger(__name__)

ROOT_PARENT_ID = "undefined"

_current_span: contextvars.ContextVar["TrajectorySpan | None"] = contextvars.ContextVar(
    "trajectory_current_span", default=None
)
_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trajectory_session_id", default=None
)
_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trajectory_trace_id", default=None
)
_span_buffers: contextvars.ContextVar[list[list["TrajectorySpan"]] | None] = contextvars.ContextVar(
    "trajectory_span_buffers", default=None
)
_distributed_parent_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "trajectory_distributed_parent_id", default=None
)


def new_id(bits: int = 64) -> str:
    raw = uuid.uuid4().hex
    return raw[: bits // 4]


def now_ns() -> int:
    return time.time_ns()


def _push_buffer() -> list["TrajectorySpan"]:
    stack = list(_span_buffers.get() or [])
    buf: list[TrajectorySpan] = []
    stack.append(buf)
    _span_buffers.set(stack)
    return buf


def _current_buffer() -> list["TrajectorySpan"]:
    stack = _span_buffers.get()
    if not stack:
        return _push_buffer()
    return stack[-1]


def _pop_buffer() -> list["TrajectorySpan"]:
    stack = list(_span_buffers.get() or [])
    if not stack:
        return []
    buf = stack.pop()
    _span_buffers.set(stack)
    return buf


@dataclass
class TrajectorySpan:
    name: str
    kind: str
    span_id: str
    trace_id: str
    parent_id: str
    start_ns: int
    service: str
    session_id: str
    semantic_type: str = ""
    model_name: str | None = None
    model_provider: str | None = None
    input_value: str | None = None
    input_messages: list[dict[str, str]] | None = None
    output_value: str | None = None
    output_messages: list[dict[str, str]] | None = None
    output_documents: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    extra_tags: dict[str, str] = field(default_factory=dict)
    status: str = "ok"
    error: dict[str, str] | None = None
    duration_ns: int = 0
    span_links: list[dict[str, str]] = field(default_factory=list)

    def annotate(
        self,
        *,
        input_value: str | None = None,
        output_value: str | None = None,
        input_messages: list[dict[str, str]] | None = None,
        output_messages: list[dict[str, str]] | None = None,
        output_documents: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
        metrics: dict[str, float] | None = None,
        tags: dict[str, str] | None = None,
        model_name: str | None = None,
        model_provider: str | None = None,
    ) -> None:
        if input_value is not None:
            self.input_value = input_value
        if output_value is not None:
            self.output_value = output_value
        if input_messages is not None:
            self.input_messages = input_messages
        if output_messages is not None:
            self.output_messages = output_messages
        if output_documents is not None:
            self.output_documents = output_documents
        if metadata:
            self.metadata.update(metadata)
        if metrics:
            self.metrics.update(metrics)
        if tags:
            self.extra_tags.update(tags)
        if model_name is not None:
            self.model_name = model_name
        if model_provider is not None:
            self.model_provider = model_provider

    def finish(self, error: BaseException | None = None) -> None:
        self.duration_ns = max(0, now_ns() - self.start_ns)
        if error is not None:
            self.status = "error"
            self.error = {
                "type": type(error).__name__,
                "message": str(error),
                "stack": traceback.format_exc(),
            }

    def to_api_span(self, settings: Settings) -> dict[str, Any]:
        tags = base_tags(
            ml_app=settings.dd_llmobs_ml_app,
            service=self.service,
            version=settings.trajectory_version,
            env=settings.dd_env,
            client_source=settings.trajectory_client_source,
            capture_level=settings.trajectory_capture_level,
            extra={
                "trajectory.trace_type": "turn",
                "trajectory.session_id": self.session_id,
                "trajectory.semantic_type": self.semantic_type or self.kind,
                **self.extra_tags,
            },
        )
        if self.kind == "llm":
            tags["trajectory.llm_call"] = "true"
            if self.model_name:
                tags["gen_ai.request.model"] = self.model_name
        io_input: dict[str, Any] = {}
        if self.input_messages:
            io_input["messages"] = self.input_messages
        if self.input_value is not None:
            io_input["value"] = self.input_value
        io_output: dict[str, Any] = {}
        if self.output_messages:
            io_output["messages"] = self.output_messages
        if self.output_documents:
            io_output["documents"] = self.output_documents
        if self.output_value is not None:
            io_output["value"] = self.output_value
        meta: dict[str, Any] = {"kind": self.kind, "metadata": {k: _meta_value(v) for k, v in self.metadata.items()}}
        if io_input:
            meta["input"] = io_input
        if io_output:
            meta["output"] = io_output
        if self.model_name:
            meta["model_name"] = self.model_name
        if self.model_provider:
            meta["model_provider"] = self.model_provider
        if self.error:
            meta["error"] = self.error
        if self.span_links:
            meta["metadata"]["span_links"] = str(self.span_links)
        payload: dict[str, Any] = {
            "name": self.name,
            "span_id": self.span_id,
            "trace_id": self.trace_id,
            "parent_id": self.parent_id or ROOT_PARENT_ID,
            "start_ns": self.start_ns,
            "duration": float(self.duration_ns),
            "meta": meta,
            "status": self.status,
            "session_id": self.session_id,
            "service": self.service,
            "ml_app": settings.dd_llmobs_ml_app,
            "tags": format_tag_list(tags),
        }
        if self.metrics:
            payload["metrics"] = {k: float(v) for k, v in self.metrics.items()}
        return payload


def _meta_value(value: Any) -> str | float | bool:
    if isinstance(value, bool) or isinstance(value, float) or isinstance(value, int):
        return value if not isinstance(value, int) else float(value)
    return str(value)


class TrajectoryTracer:
    def __init__(self, service: str, settings: Settings | None = None):
        self.service = service
        self.settings = settings or get_settings()
        self.exporter = TrajectoryExporter(self.settings)

    def current_span(self) -> TrajectorySpan | None:
        return _current_span.get()

    def session_id(self) -> str:
        sid = _session_id.get()
        if sid:
            return sid
        sid = f"sess-{new_id(128)}"
        _session_id.set(sid)
        return sid

    def inject_distributed_headers(self) -> dict[str, str]:
        span = self.current_span()
        if span is None:
            return {}
        ctx = DistributedContext(
            trace_id=span.trace_id,
            parent_id=span.span_id,
            session_id=span.session_id,
            ml_app=self.settings.dd_llmobs_ml_app,
            span_link=span.span_id,
        )
        return ctx.as_headers()

    def activate_distributed_headers(self, headers: dict[str, str]) -> DistributedContext | None:
        ctx = extract_context(headers)
        if ctx is None:
            return None
        _trace_id.set(ctx.trace_id)
        _session_id.set(ctx.session_id)
        _distributed_parent_id.set(ctx.parent_id)
        _current_span.set(None)
        _push_buffer()
        return ctx

    def start_turn(self, session_id: str | None = None) -> str:
        sid = session_id or f"sess-{new_id(128)}"
        _session_id.set(sid)
        _trace_id.set(new_id(128))
        _distributed_parent_id.set(None)
        _current_span.set(None)
        _span_buffers.set([[]])
        append_event(
            sid,
            {"event": "session_start", "client_source": self.settings.trajectory_client_source},
            enabled=self.settings.trajectory_local_capture,
        )
        return sid

    @contextmanager
    def span(
        self,
        name: str,
        kind: str,
        *,
        semantic_type: str = "",
        input_value: str | None = None,
        extra_tags: dict[str, str] | None = None,
    ) -> Iterator[TrajectorySpan]:
        if not self.settings.trajectory_enabled:
            dummy = TrajectorySpan(
                name=name,
                kind=kind,
                span_id=new_id(),
                trace_id=_trace_id.get() or new_id(128),
                parent_id=ROOT_PARENT_ID,
                start_ns=now_ns(),
                service=self.service,
                session_id=self.session_id(),
            )
            yield dummy
            return

        parent = _current_span.get()
        trace_id = _trace_id.get() or (parent.trace_id if parent else new_id(128))
        _trace_id.set(trace_id)
        session_id = self.session_id()
        distributed_parent = _distributed_parent_id.get()
        if parent:
            parent_id = parent.span_id
        elif distributed_parent:
            parent_id = distributed_parent
        else:
            parent_id = ROOT_PARENT_ID
        is_local_root = parent is None
        span = TrajectorySpan(
            name=name,
            kind=kind,
            span_id=new_id(),
            trace_id=trace_id,
            parent_id=parent_id,
            start_ns=now_ns(),
            service=self.service,
            session_id=session_id,
            semantic_type=semantic_type or kind,
            extra_tags=dict(extra_tags or {}),
            input_value=input_value,
        )
        token = _current_span.set(span)
        err: BaseException | None = None
        try:
            yield span
        except BaseException as exc:
            err = exc
            raise
        finally:
            span.finish(err)
            _current_span.reset(token)
            _current_buffer().append(span)
            append_event(
                session_id,
                {
                    "event": "span",
                    "name": span.name,
                    "kind": span.kind,
                    "span_id": span.span_id,
                    "parent_id": span.parent_id,
                    "trace_id": span.trace_id,
                    "status": span.status,
                    "duration_ns": span.duration_ns,
                    "input": span.input_value,
                    "output": span.output_value,
                },
                enabled=self.settings.trajectory_local_capture,
            )
            if is_local_root:
                self.flush()

    def flush(self) -> dict[str, Any] | None:
        finished = _pop_buffer()
        if not finished:
            return None
        payload = {
            "data": {
                "type": "span",
                "attributes": {
                    "ml_app": self.settings.dd_llmobs_ml_app,
                    "session_id": finished[-1].session_id,
                    "tags": format_tag_list(
                        base_tags(
                            ml_app=self.settings.dd_llmobs_ml_app,
                            service=self.service,
                            version=self.settings.trajectory_version,
                            env=self.settings.dd_env,
                            client_source=self.settings.trajectory_client_source,
                            capture_level=self.settings.trajectory_capture_level,
                        )
                    ),
                    "spans": [span.to_api_span(self.settings) for span in finished],
                },
            }
        }
        result = self.exporter.export(payload)
        return result
