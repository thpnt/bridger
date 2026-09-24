"""Invocation-local monotonic timing; no runtime or recovery decisions live here."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any
from uuid import uuid4

from bridger.contracts.runtime_metrics import ModelCall, TimedOperation, ToolCall

_active: ContextVar[RuntimeMetricsCollector | None] = ContextVar(
    "runtime_metrics", default=None
)
_target: ContextVar[str | None] = ContextVar("runtime_target", default=None)
_cycle: ContextVar[str | None] = ContextVar("runtime_cycle", default=None)
_attempt: ContextVar[int] = ContextVar("runtime_attempt", default=1)


def current_collector() -> RuntimeMetricsCollector | None:
    return _active.get()


def current_target() -> str | None:
    return _target.get()


def current_cycle() -> str | None:
    return _cycle.get()


def current_attempt() -> int:
    return _attempt.get()


class RuntimeMetricsCollector:
    def __init__(
        self,
        *,
        clock_ns: Callable[[], int] = time.perf_counter_ns,
        utc_now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.init_run_id = f"init-{uuid4().hex}"
        self.clock_ns = clock_ns
        self.utc_now = utc_now
        self.started_ns = clock_ns()
        self.started_at = utc_now().isoformat()
        self.lock = Lock()
        self.spans: list[TimedOperation] = []
        self.model_calls: list[ModelCall] = []
        self.tool_calls: list[ToolCall] = []
        self.backoffs: list[tuple[str | None, str | None, str, float]] = []
        self.fleet_run_id: str | None = None
        self.repository_id: str | None = None
        self.revision: str | None = None
        self.model: str | None = None
        self.configured_concurrency: int | None = None
        self.target_ids: dict[str, str] = {}
        self.resumed = False
        self.reused = False
        self.failed_stage: str | None = None

    @contextmanager
    def activate(self) -> Iterator[None]:
        token = _active.set(self)
        try:
            yield
        finally:
            _active.reset(token)

    @contextmanager
    def target(self, task_id: str) -> Iterator[None]:
        token = _target.set(task_id)
        try:
            yield
        finally:
            _target.reset(token)

    @contextmanager
    def cycle(self, cycle_id: str) -> Iterator[None]:
        token = _cycle.set(cycle_id)
        try:
            yield
        finally:
            _cycle.reset(token)

    @contextmanager
    def attempt(self, number: int) -> Iterator[None]:
        token = _attempt.set(number)
        try:
            yield
        finally:
            _attempt.reset(token)

    @contextmanager
    def span(self, name: str, **fields: Any) -> Iterator[dict[str, Any]]:
        started_at = self.utc_now().isoformat()
        started_ns = self.clock_ns()
        status = "completed"
        try:
            yield fields
        except BaseException:
            status = "failed"
            self.failed_stage = self.failed_stage or name
            raise
        finally:
            elapsed = max(0, (self.clock_ns() - started_ns) / 1_000_000)
            ended_at = self.utc_now().isoformat()
            item = TimedOperation(
                name=name,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=elapsed,
                status=status,
                target_task_id=fields.get("target_task_id"),
                cycle_id=fields.get("cycle_id"),
                cycle_number=fields.get("cycle_number"),
                mode=fields.get("mode"),
                repair=fields.get("repair"),
                outcome=fields.get("outcome"),
            )
            with self.lock:
                self.spans.append(item)

    def add_model(self, call: ModelCall) -> None:
        with self.lock:
            self.model_calls.append(call)

    def add_tool(self, call: ToolCall) -> None:
        with self.lock:
            self.tool_calls.append(call)

    def add_backoff(self, duration_ms: float) -> None:
        started_at = (self.utc_now() - timedelta(milliseconds=duration_ms)).isoformat()
        with self.lock:
            self.backoffs.append(
                (current_target(), current_cycle(), started_at, duration_ms)
            )
