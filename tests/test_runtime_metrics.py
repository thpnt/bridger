"""Local timing accounting; provider requests here are in-memory fakes."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest
from typer.testing import CliRunner

import bridger.cli as cli
from bridger.contracts.memory.persistence import TaskEvent
from bridger.contracts.runtime_metrics import ModelCall, TimedOperation, ToolCall
from bridger.init_pipeline import InitMode, RepositoryBrainBuildResult
from bridger.llm.errors import LLMError
from bridger.llm.models import LLMCompactionRequest, LLMOperation, LLMRequest
from bridger.llm.profiles import LLMProfile, RetryPolicy
from bridger.llm.providers.openai import OpenAILLMClient
from bridger.memory.runtime.provider_recovery import run_provider_with_retry
from bridger.repository_brain.runtime_metrics import (
    build_runtime_metrics_report,
    load_runtime_metrics_report,
    persist_runtime_metrics_report,
)
from bridger.runtime_timing import RuntimeMetricsCollector, current_attempt

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _at(ms: int) -> str:
    return (BASE + timedelta(milliseconds=ms)).isoformat()


def _span(name: str, start: int, duration: int, **fields: object) -> TimedOperation:
    return TimedOperation(
        name=name,
        started_at=_at(start),
        ended_at=_at(start + duration),
        duration_ms=duration,
        status="completed",
        **fields,
    )


def _report(metrics: RuntimeMetricsCollector, root: Path):
    return build_runtime_metrics_report(
        metrics,
        bridger_root=root,
        mode="full",
        fresh=False,
        model="test-model",
        reasoning_effort="high",
        model_profile="balanced",
        status="completed",
    )


def test_fake_clock_and_event_driven_cycle_repair_accounting(tmp_path: Path) -> None:
    ticks = [0]
    metrics = RuntimeMetricsCollector(
        clock_ns=lambda: ticks[0],
        utc_now=lambda: BASE + timedelta(microseconds=ticks[0] / 1000),
    )
    with metrics.span("extract_facts"):
        ticks[0] = 125_000_000
    assert metrics.spans[0].duration_ms == 125

    metrics.started_at = _at(0)
    metrics.target_ids = {"A": "a", "B": "b", "C": "c"}
    metrics.fleet_run_id = "fleet-1"
    metrics.configured_concurrency = 3
    metrics.spans.extend(
        [
            _span("memory_fleet", 0, 10_000),
            _span("target_execution", 0, 10_000),
            _span("target_step", 0, 10_000, target_task_id="A", outcome="done"),
            _span("target_step", 0, 6_000, target_task_id="B", outcome="done"),
            _span("target_step", 0, 4_000, target_task_id="C", outcome="done"),
            _span(
                "context_hydration",
                0,
                50,
                target_task_id="A",
                cycle_number=1,
                mode="initial",
            ),
            _span(
                "worker_cycle",
                50,
                1000,
                target_task_id="A",
                cycle_number=1,
                outcome="finalization-requested",
                repair=False,
            ),
            _span(
                "worker_cycle",
                2000,
                1000,
                target_task_id="A",
                cycle_number=2,
                outcome="finalization-requested",
                repair=True,
            ),
        ]
    )
    metrics.model_calls.append(
        ModelCall(
            operation="memory_agent_worker",
            role="worker",
            target_task_id="A",
            cycle_id="cycle-1",
            provider="openai",
            model="test-model",
            started_at=_at(100),
            duration_ms=600,
            status="completed",
            attempt=1,
        )
    )
    metrics.model_calls.append(
        ModelCall(
            operation="memory_agent_worker",
            role="worker",
            target_task_id="B",
            cycle_id="cycle-b",
            provider="openai",
            model="test-model",
            started_at=_at(100),
            duration_ms=600,
            status="completed",
            attempt=1,
        )
    )
    metrics.tool_calls.append(
        ToolCall(
            target_task_id="A",
            cycle_id="cycle-1",
            tool="read_file",
            call_id="call-1",
            started_at=_at(700),
            duration_ms=200,
            status="completed",
        )
    )
    path = tmp_path / "runtime" / "fleet-1" / "events.jsonl"
    path.parent.mkdir(parents=True)
    events = [
        TaskEvent(
            event_id="event-1",
            fleet_run_id="fleet-1",
            target_task_id="A",
            sequence=1,
            event_type="cycle_finished",
            timestamp=_at(1050),
            payload={"cycle_number": 1, "cycle_id": "cycle-1"},
        ),
        TaskEvent(
            event_id="event-2",
            fleet_run_id="fleet-1",
            target_task_id="A",
            sequence=2,
            event_type="finalization_requested",
            timestamp=_at(2000),
            payload={},
        ),
        TaskEvent(
            event_id="event-3",
            fleet_run_id="fleet-1",
            target_task_id="A",
            sequence=3,
            event_type="cycle_finished",
            timestamp=_at(3000),
            payload={"cycle_number": 2, "cycle_id": "cycle-2"},
        ),
        TaskEvent(
            event_id="event-4",
            fleet_run_id="fleet-1",
            target_task_id="A",
            sequence=4,
            event_type="target_accepted",
            timestamp=_at(8000),
            payload={},
        ),
    ]
    path.write_text(
        "".join(event.model_dump_json() + "\n" for event in events) + "{bad}\n"
    )
    ticks[0] = 10_000_000_000

    report = _report(metrics, tmp_path)
    assert report.targets[0].cycles[0].other_harness_ms == 200
    assert report.targets[0].cycles[0].mode == "initial"
    assert report.targets[0].repair_cycles == 1
    assert report.targets[0].repair_penalty_ms == 6000
    assert report.total_target_work_ms == 20_000
    assert report.effective_parallel_speedup == 2
    assert report.target_execution_wall_ms == 10_000
    assert report.average_active_targets == 2
    assert report.concurrency_utilization == pytest.approx(2 / 3)
    assert report.total_barrier_wait_ms == 0
    assert report.batches == []
    assert report.critical_path_steps == ["target_execution"]
    assert report.model_provider_wait_ms == 1200
    assert report.model_by_role["worker"] == {"calls": 2, "total_duration_ms": 1200}
    assert report.model_wall_ms == 600
    assert (
        report.model_wall_ms + report.tool_wall_ms + report.other_harness_ms
        == report.total_duration_ms
    )
    saved = persist_runtime_metrics_report(report, tmp_path)
    assert load_runtime_metrics_report(saved) == report


def test_provider_attempts_retry_and_compaction_use_fake_transport() -> None:
    ticks = [0]
    metrics = RuntimeMetricsCollector(
        clock_ns=lambda: ticks[0],
        utc_now=lambda: BASE + timedelta(microseconds=ticks[0] / 1000),
    )

    class Responses:
        calls = 0

        async def create(self, **_payload: object) -> dict[str, object]:
            self.calls += 1
            if self.calls == 1:
                ticks[0] += 100_000_000
                raise openai.APITimeoutError(
                    request=httpx.Request("POST", "https://example.test")
                )
            ticks[0] += 200_000_000
            return {
                "status": "completed",
                "output_text": "ok",
                "output": [],
                "usage": {
                    "input_tokens": 5,
                    "output_tokens": 3,
                    "input_tokens_details": {"cached_tokens": 2},
                    "output_tokens_details": {"reasoning_tokens": 1},
                },
            }

        async def compact(self, **_payload: object) -> dict[str, object]:
            ticks[0] += 50_000_000
            return {
                "output": [{"type": "compaction", "encrypted_content": "opaque"}],
                "usage": {"input_tokens": 2},
            }

    async def fake_sleep(_seconds: float) -> None:
        ticks[0] += 1_000_000_000

    client = OpenAILLMClient(
        openai_client=SimpleNamespace(responses=Responses()),
        profile=LLMProfile(
            name="test",
            provider="openai",
            model="test-model",
            retry_policy=RetryPolicy(max_attempts=2),
        ),
        sleep=fake_sleep,
        clock=lambda: ticks[0] / 1_000_000_000,
        metrics=metrics,
    )

    async def run() -> None:
        with metrics.activate(), metrics.target("target-1"), metrics.cycle("cycle-1"):
            await client.generate(
                LLMRequest(operation=LLMOperation.MEMORY_AGENT_WORKER)
            )
            await client.compact(
                LLMCompactionRequest(
                    operation=LLMOperation.MEMORY_AGENT_WORKER,
                    instructions="compact",
                    continuation_ref="response-1",
                )
            )

    asyncio.run(run())
    assert [
        (call.status, call.attempt, call.duration_ms) for call in metrics.model_calls
    ] == [
        ("failed", 1, 100),
        ("completed", 2, 200),
        ("completed", 1, 50),
    ]
    assert metrics.model_calls[1].cached_input_tokens == 2
    assert metrics.model_calls[1].reasoning_tokens == 1
    assert metrics.model_calls[2].role == "compaction"
    assert metrics.backoffs == [("target-1", "cycle-1", _at(100), 1000)]


def test_runtime_owned_retry_keeps_attempt_and_backoff_identity() -> None:
    ticks = [0]
    metrics = RuntimeMetricsCollector(clock_ns=lambda: ticks[0])
    attempts: list[int] = []

    async def operation() -> str:
        attempts.append(current_attempt())
        if len(attempts) == 1:
            raise LLMError("retry", retryable=True)
        return "done"

    async def before_attempt(_attempt: int) -> None:
        pass

    async def sleep(_seconds: float) -> None:
        ticks[0] += 1_000_000_000

    async def run() -> str:
        with metrics.activate(), metrics.target("target-1"), metrics.cycle("cycle-1"):
            return await run_provider_with_retry(
                operation, before_attempt=before_attempt, sleep=sleep
            )

    assert asyncio.run(run()) == "done"
    assert attempts == [1, 2]
    assert [
        (target, cycle, duration)
        for target, cycle, _start, duration in metrics.backoffs
    ] == [("target-1", "cycle-1", 1000)]


@pytest.mark.parametrize("corrupt", [False, True])
def test_cli_runtime_summary_and_corrupt_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, corrupt: bool
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    metrics = RuntimeMetricsCollector()
    path = persist_runtime_metrics_report(_report(metrics, tmp_path), tmp_path)
    if corrupt:
        path.write_text("not json")
    publication = tmp_path / "published" / "brain.json"
    monkeypatch.setattr(
        cli,
        "build_repository_brain",
        lambda *_args, **_kwargs: RepositoryBrainBuildResult(
            mode=InitMode.FULL,
            graph_build=SimpleNamespace(snapshot_root=tmp_path / "graph"),
            publication_path=publication,
            runtime_metrics_report_path=path,
        ),
    )

    result = CliRunner().invoke(cli.app, ["init"])

    assert result.exit_code == 0
    assert str(publication) in result.output
    if corrupt:
        assert "Runtime report could not be rendered" in result.output
    else:
        assert "Runtime" in result.output
        assert "Effective speedup" in result.output
        assert str(path) in result.output
