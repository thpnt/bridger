"""Rich presentation for Repository Brain initialization progress."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.spinner import Spinner
from rich.status import Status
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from bridger.contracts.memory.core import (
    CompletionStatus,
    FleetPhase,
    FleetRunState,
    MemoryFleetSpec,
    TargetCompletionState,
    TargetPhase,
    TargetTaskSpec,
    TargetTaskState,
)
from bridger.contracts.memory.persistence import TaskEvent
from bridger.contracts.token_usage import TokenUsage
from bridger.init_pipeline import (
    InitMode,
    ReasoningEffort,
    RepositoryBrainBuildResult,
)
from bridger.progress import InitStage
from bridger.repository_brain.token_usage import load_token_usage_report

BRIDGER_THEME = Theme(
    {
        "bridger.brand": "bold cyan",
        "bridger.active": "cyan",
        "bridger.success": "green",
        "bridger.warning": "yellow",
        "bridger.error": "red",
        "bridger.muted": "dim",
    }
)

_ACTIVE_STAGE_LABELS = {
    InitStage.PREPARE_REPOSITORY: "Preparing repository",
    InitStage.EXTRACT_FACTS: "Extracting repository facts",
    InitStage.BUILD_GRAPH: "Building graph intelligence",
    InitStage.PUBLISH_GRAPH: "Publishing graph snapshot",
    InitStage.MODEL_ENRICHMENT: "Generating graph enrichment",
    InitStage.INITIALIZE_MEMORY_FLEET: "Initializing memory fleet",
    InitStage.PUBLISH_REPOSITORY_BRAIN: "Publishing Repository Brain",
}
_COMPLETED_STAGE_LABELS = {
    InitStage.PREPARE_REPOSITORY: "Repository prepared",
    InitStage.EXTRACT_FACTS: "Repository facts extracted",
    InitStage.BUILD_GRAPH: "Graph intelligence built",
    InitStage.PUBLISH_GRAPH: "Graph snapshot published",
    InitStage.MODEL_ENRICHMENT: "Graph enrichment generated",
    InitStage.INITIALIZE_MEMORY_FLEET: "Memory fleet initialized",
    InitStage.PUBLISH_REPOSITORY_BRAIN: "Repository Brain published",
}
_ERROR_TARGET_PHASES = {
    TargetPhase.BLOCKED,
    TargetPhase.EXHAUSTED,
    TargetPhase.FAILED,
    TargetPhase.STOPPED,
}
_PENDING_TARGET_PHASES = {
    TargetPhase.FINALIZING,
    TargetPhase.VALIDATING,
    TargetPhase.REVIEWING,
}
_REPAIR_EVENT_TYPES = {
    "fleet_repair_routed",
    "fleet_review_repair_routed",
}


@dataclass(slots=True)
class TargetProgressView:
    """Transient CLI projection of one target's authoritative state."""

    target_task_id: str
    target_id: str
    phase: TargetPhase
    obligations: dict[str, CompletionStatus]

    @property
    def total(self) -> int:
        """Return the target's semantic obligation count."""
        return len(self.obligations)

    @property
    def resolved(self) -> int:
        """Return obligations whose authoritative status is terminal."""
        return sum(
            status is not CompletionStatus.UNINVESTIGATED
            for status in self.obligations.values()
        )

    @property
    def percentage(self) -> int:
        """Return semantic resolution percentage, including the 0/0 case."""
        if self.total == 0:
            return 100
        return round(self.resolved * 100 / self.total)

    @property
    def accepted(self) -> bool:
        """Return whether the target lifecycle has authoritatively accepted."""
        return self.phase is TargetPhase.ACCEPTED


@dataclass(slots=True)
class FleetProgressView:
    """Transient CLI projection of one memory fleet."""

    fleet_run_id: str
    phase: FleetPhase
    targets: dict[str, TargetProgressView]


class RichInitProgressPresenter:
    """Project init observations into interactive or append-only Rich output."""

    def __init__(
        self,
        *,
        console: Console,
        mode: InitMode,
        reasoning: ReasoningEffort,
    ) -> None:
        self._console = console
        self._mode = mode
        self._reasoning = reasoning
        self._interactive = console.is_terminal
        self._fleet: FleetProgressView | None = None
        self._live: Live | None = None
        self._status: Status | None = None
        self._current_stage: InitStage | None = None
        self._last_target_output: dict[str, tuple[int, TargetPhase]] = {}
        self._last_fleet_output: FleetPhase | None = None
        self._lock = Lock()
        self._started = False
        self._closed = False
        self._theme_pushed = False

    @property
    def fleet(self) -> FleetProgressView | None:
        """Return the current transient projection for tests and inspection."""
        return self._fleet

    def start(self) -> None:
        """Render the init heading once."""
        if self._started:
            return
        self._started = True
        self._console.push_theme(BRIDGER_THEME)
        self._theme_pushed = True
        if self._interactive:
            self._console.print(
                Panel.fit(
                    Text.assemble(
                        (self._mode.value, "bridger.active"),
                        ("  •  reasoning ", "bridger.muted"),
                        (self._reasoning.value, "bridger.active"),
                    ),
                    title="Bridger init",
                    border_style="bridger.brand",
                )
            )
            return
        self._console.print(
            Text(
                f"Bridger init: {self._mode.value}, "
                f"reasoning {self._reasoning.value}"
            )
        )

    def stage_started(self, stage: InitStage) -> None:
        """Render a newly started deterministic or publication stage."""
        if stage is InitStage.PUBLISH_REPOSITORY_BRAIN:
            self._finish_live_dashboard()
            if self._interactive:
                self._console.print(
                    Text("✓ Memory fleet accepted", style="bridger.success")
                )
        self._complete_current_stage()
        self._current_stage = stage
        label = _ACTIVE_STAGE_LABELS[stage]
        if self._interactive:
            self._status = self._console.status(
                Text(label, style="bridger.active"),
                spinner="dots",
                spinner_style="bridger.active",
            )
            self._status.start()
            return
        self._console.print(Text(f"[stage] {label}"))

    def fleet_initialized(
        self,
        fleet_spec: MemoryFleetSpec,
        target_specs: Sequence[TargetTaskSpec],
        target_states: Sequence[TargetTaskState],
        completion_states: Sequence[TargetCompletionState],
        fleet_state: FleetRunState,
    ) -> None:
        """Seed a detached projection from one complete authoritative snapshot."""
        states_by_task = {state.target_task_id: state for state in target_states}
        completions_by_task = {
            state.target_task_id: state for state in completion_states
        }
        targets: dict[str, TargetProgressView] = {}
        for spec in target_specs:
            state = states_by_task.get(spec.target_task_id)
            completion = completions_by_task.get(spec.target_task_id)
            if state is None or completion is None:
                continue
            targets[spec.target_task_id] = TargetProgressView(
                target_task_id=spec.target_task_id,
                target_id=spec.target_id,
                phase=state.phase,
                obligations={
                    item.obligation_id: item.status for item in completion.items
                },
            )
        with self._lock:
            self._fleet = FleetProgressView(
                fleet_run_id=fleet_spec.fleet_run_id,
                phase=fleet_state.phase,
                targets=targets,
            )
            renderable = self._render_fleet()
        self._complete_current_stage()
        if self._interactive:
            self._live = Live(
                renderable,
                console=self._console,
                refresh_per_second=8,
                transient=False,
            )
            self._live.start(refresh=True)
            return
        self._console.print(Text(f"[fleet] {len(targets)} targets initialized"))
        if fleet_state.phase is not FleetPhase.INITIALIZED:
            self._emit_fleet_line(fleet_state.phase)

    def runtime_event(self, event: TaskEvent) -> None:
        """Apply one committed event to the transient projection."""
        try:
            with self._lock:
                changed_targets, fleet_changed = self._project_event(event)
                if not changed_targets and not fleet_changed:
                    return
                renderable = self._render_fleet() if self._interactive else None
        except Exception:
            return
        if self._interactive:
            if self._live is not None and renderable is not None:
                self._live.update(renderable, refresh=False)
            return
        for target_task_id in changed_targets:
            self._emit_target_line(target_task_id)
        if fleet_changed and self._fleet is not None:
            self._emit_fleet_line(self._fleet.phase)

    def succeeded(self, result: RepositoryBrainBuildResult) -> None:
        """Render final artifacts and the persisted model-token audit."""
        self._finish_live_dashboard()
        if result.publication_path is None:
            if not self._interactive:
                self._current_stage = None
                self._console.print(
                    Text(
                        "Deterministic graph snapshot published at "
                        f"{result.graph_build.snapshot_root}"
                    ),
                    soft_wrap=True,
                )
                return
            self._complete_current_stage("Deterministic graph snapshot published")
            self._console.print(
                Text(str(result.graph_build.snapshot_root)), soft_wrap=True
            )
            return
        self._complete_current_stage()
        if result.token_usage_report_path is not None:
            try:
                self._render_token_usage_report(result.token_usage_report_path)
            except Exception:
                self._console.print(
                    Text(
                        "! Token usage report could not be rendered: "
                        f"{result.token_usage_report_path}",
                        style="bridger.warning",
                    )
                )
        self._console.print(
            Text(f"Repository Brain published at {result.publication_path}"),
            soft_wrap=True,
        )

    def failed(self, error: BaseException) -> None:
        """Render the active stage and normal build failure."""
        self._finish_live_dashboard()
        self._stop_status()
        if self._current_stage is not None:
            self._console.print(
                Text(
                    f"✗ {_ACTIVE_STAGE_LABELS[self._current_stage]}",
                    style="bridger.error",
                )
            )
            self._current_stage = None
        elif self._fleet is not None:
            self._console.print(
                Text(
                    (
                        "✗ Memory fleet execution"
                        if self._interactive
                        else "[fleet] execution failed"
                    ),
                    style="bridger.error",
                )
            )
        self._console.print(
            Text(f"Repository Brain build failed: {error}", style="bridger.error")
        )

    def close(self) -> None:
        """Idempotently release Rich live/status resources."""
        if self._closed:
            return
        self._closed = True
        try:
            self._finish_live_dashboard()
            self._stop_status()
        finally:
            if self._theme_pushed:
                self._console.pop_theme()
                self._theme_pushed = False

    def _project_event(self, event: TaskEvent) -> tuple[set[str], bool]:
        if self._fleet is None:
            return set(), False
        changed_targets: set[str] = set()
        fleet_changed = False
        payload = event.payload

        if event.event_type == "completion_updated":
            target = self._fleet.targets.get(event.target_task_id or "")
            obligation_id = payload.get("obligation_id")
            status_value = payload.get("status")
            if (
                target is not None
                and isinstance(obligation_id, str)
                and obligation_id in target.obligations
                and isinstance(status_value, str)
            ):
                try:
                    status = CompletionStatus(status_value)
                except ValueError:
                    status = None
                if (
                    status is not None
                    and target.obligations[obligation_id] is not status
                ):
                    target.obligations[obligation_id] = status
                    changed_targets.add(target.target_task_id)

        if event.event_type in _REPAIR_EVENT_TYPES:
            affected = payload.get("affected_target_task_ids")
            if isinstance(affected, list):
                for target_task_id in affected:
                    if not isinstance(target_task_id, str):
                        continue
                    target = self._fleet.targets.get(target_task_id)
                    if target is not None and target.phase is not TargetPhase.REPAIR:
                        target.phase = TargetPhase.REPAIR
                        changed_targets.add(target_task_id)

        to_phase = payload.get("to_phase")
        if isinstance(to_phase, str) and event.target_task_id is not None:
            target = self._fleet.targets.get(event.target_task_id)
            if target is not None:
                target_phase: TargetPhase | None
                try:
                    target_phase = TargetPhase(to_phase)
                except ValueError:
                    target_phase = None
                if target_phase is not None and target.phase is not target_phase:
                    target.phase = target_phase
                    changed_targets.add(target.target_task_id)
        elif isinstance(to_phase, str):
            fleet_phase: FleetPhase | None
            try:
                fleet_phase = FleetPhase(to_phase)
            except ValueError:
                fleet_phase = (
                    FleetPhase.RUNNING
                    if event.event_type == "phase_transition"
                    and to_phase == "scheduled"
                    else None
                )
            if fleet_phase is not None and self._fleet.phase is not fleet_phase:
                self._fleet.phase = fleet_phase
                fleet_changed = True

        return changed_targets, fleet_changed

    def _render_fleet(self) -> Group:
        if self._fleet is None:
            return Group()
        accepted = sum(target.accepted for target in self._fleet.targets.values())
        heading = Table.grid(expand=True)
        heading.add_column(style="bridger.brand")
        heading.add_column(justify="right", style="bridger.muted")
        heading.add_row(
            "Memory fleet",
            f"{accepted} / {len(self._fleet.targets)} accepted",
        )

        table = Table(box=box.SIMPLE_HEAD, expand=True, padding=(0, 1))
        table.add_column("", width=1, no_wrap=True)
        table.add_column("Target", ratio=2, no_wrap=True)
        show_progress_bar = self._console.width >= 120
        if show_progress_bar:
            table.add_column("Progress", ratio=3)
        table.add_column("Obligations", justify="right", no_wrap=True)
        table.add_column("%", justify="right", no_wrap=True)
        table.add_column("State", no_wrap=True)
        bar_width = max(8, min(24, self._console.width - 56))
        for target in self._fleet.targets.values():
            total = target.total or 1
            completed = target.resolved if target.total else 1
            row: list[str | Text | ProgressBar | Spinner] = [
                self._target_status(target.phase),
                Text(target.target_id),
            ]
            if show_progress_bar:
                row.append(
                    ProgressBar(total=total, completed=completed, width=bar_width)
                )
            row.extend(
                [
                    f"{target.resolved}/{target.total}",
                    f"{target.percentage}%",
                    Text(target.phase.value, style=self._phase_style(target.phase)),
                ]
            )
            table.add_row(*row)
        footer = Text.assemble(
            ("Fleet: ", "bridger.muted"),
            (self._fleet.phase.value, self._fleet_phase_style(self._fleet.phase)),
        )
        return Group(heading, table, footer)

    @staticmethod
    def _target_status(phase: TargetPhase) -> Text | Spinner:
        if phase is TargetPhase.ACCEPTED:
            return Text("✓", style="bridger.success")
        if phase in _ERROR_TARGET_PHASES:
            return Text("✗", style="bridger.error")
        if phase is TargetPhase.REPAIR:
            return Text("!", style="bridger.warning")
        return Spinner("dots", style="bridger.active")

    @staticmethod
    def _phase_style(phase: TargetPhase) -> str:
        if phase is TargetPhase.ACCEPTED:
            return "bridger.success"
        if phase in _ERROR_TARGET_PHASES:
            return "bridger.error"
        if phase is TargetPhase.REPAIR:
            return "bridger.warning"
        if phase in _PENDING_TARGET_PHASES:
            return "bridger.muted"
        return "bridger.active"

    @staticmethod
    def _fleet_phase_style(phase: FleetPhase) -> str:
        if phase is FleetPhase.ACCEPTED:
            return "bridger.success"
        if phase in {
            FleetPhase.BLOCKED,
            FleetPhase.EXHAUSTED,
            FleetPhase.FAILED,
            FleetPhase.STOPPED,
        }:
            return "bridger.error"
        if phase is FleetPhase.REPAIRING:
            return "bridger.warning"
        return "bridger.active"

    def _complete_current_stage(self, label: str | None = None) -> None:
        if self._current_stage is None:
            return
        stage = self._current_stage
        self._stop_status()
        if self._interactive:
            self._console.print(
                Text(
                    f"✓ {label or _COMPLETED_STAGE_LABELS[stage]}",
                    style="bridger.success",
                )
            )
        self._current_stage = None

    def _stop_status(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None

    def _finish_live_dashboard(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _emit_target_line(self, target_task_id: str) -> None:
        if self._fleet is None:
            return
        target = self._fleet.targets.get(target_task_id)
        if target is None:
            return
        signature = (target.resolved, target.phase)
        if self._last_target_output.get(target_task_id) == signature:
            return
        self._last_target_output[target_task_id] = signature
        self._console.print(
            Text(
                f"[target] {target.target_id} "
                f"{target.resolved}/{target.total} "
                f"{target.percentage}% {target.phase.value}"
            )
        )

    def _emit_fleet_line(self, phase: FleetPhase) -> None:
        if self._last_fleet_output is phase:
            return
        self._last_fleet_output = phase
        self._console.print(Text(f"[fleet] {phase.value}"))

    def _render_token_usage_report(self, path: Path) -> None:
        report = load_token_usage_report(path)
        table = Table(title="Init token usage")
        table.add_column("Scope")
        for column in ("Input", "Cached", "Uncached", "Output"):
            table.add_column(column, justify="right")

        def add_row(label: str, usage: TokenUsage) -> None:
            table.add_row(
                Text(label),
                str(usage.input_tokens),
                str(usage.cached_input_tokens),
                str(usage.uncached_input_tokens),
                str(usage.output_tokens),
            )

        add_row("Layer 5 enrichment", report.layer5_enrichment)
        for target in report.targets:
            add_row(target.target_id, target.usage)
        add_row("Fleet-only overhead", report.fleet_only_memory_overhead)
        add_row("Memory subtotal", report.memory_total)
        add_row("Init total", report.init_total)
        self._console.print(table)
        self._console.print(
            "Token columns: input, cached input, derived uncached input, output"
        )
        self._console.print(Text(f"Token usage report: {path}"), soft_wrap=True)


__all__ = [
    "BRIDGER_THEME",
    "FleetProgressView",
    "RichInitProgressPresenter",
    "TargetProgressView",
]
