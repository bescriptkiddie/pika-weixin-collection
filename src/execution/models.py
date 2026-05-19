from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class FailureState:
    scope: str
    stage: str
    code: str
    message: str
    retryable: bool = False
    degraded: bool = False
    action_required: str = ""
    action_hint: str = ""
    provider: str = ""
    provider_trace: list[dict[str, Any]] = field(default_factory=list)
    verify_type: str = ""
    verify_uuid: str = ""
    occurred_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionArtifact:
    artifact_id: str
    run_id: str
    task_id: str
    type: str
    path: str
    checksum: str
    created_at: str
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionTask:
    task_id: str
    run_id: str
    kind: str
    status: str
    depends_on: list[str] = field(default_factory=list)
    attempt: int = 1
    input_ref: dict[str, Any] = field(default_factory=dict)
    output_ref: dict[str, Any] = field(default_factory=dict)
    provider_trace_ref: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    failure_state: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewPacket:
    packet_id: str
    run_id: str
    task_id: str
    kind: str
    reason: str
    candidate_payload: dict[str, Any] = field(default_factory=dict)
    suggested_action: str = ""
    status: str = "open"
    resolved_at: str = ""
    resolved_by: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExecutionRun:
    run_id: str
    intent: str
    status: str
    trigger: str
    started_at: str
    finished_at: str = ""
    summary: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    current_task: str = ""
    failure_state: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
