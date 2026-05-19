from __future__ import annotations

import inspect
from typing import Any, Callable

from .models import ExecutionRun, ExecutionTask, FailureState, ReviewPacket
from .review import build_review_packet
from .store import (
    append_event,
    build_run_id,
    build_task_id,
    now_local_iso,
    write_artifact,
    write_review_packets,
    write_run,
    write_tasks,
)


class ExecutionActionError(RuntimeError):
    def __init__(self, message: str, run_id: str, failure_state: dict[str, Any]):
        super().__init__(message)
        self.run_id = run_id
        self.failure_state = failure_state


SummaryBuilder = Callable[[dict[str, Any]], str]
ReviewBuilder = Callable[[dict[str, Any]], ReviewPacket | None]
ActionBuilder = Callable[..., dict[str, Any]]


def _infer_failure_state(task_kind: str, result: dict[str, Any]) -> FailureState | None:
    errors = result.get("errors")
    failed = result.get("failed")
    if isinstance(errors, list) and errors:
        return FailureState(
            scope="task",
            stage=task_kind,
            code="partial_failure",
            message=f"{task_kind} 产生 {len(errors)} 个错误",
            retryable=True,
            degraded=True,
            action_hint="查看错误列表并按需重试",
            occurred_at=now_local_iso(),
        )
    if isinstance(failed, int) and failed > 0:
        return FailureState(
            scope="task",
            stage=task_kind,
            code="partial_failure",
            message=f"{task_kind} 有 {failed} 条处理失败",
            retryable=True,
            degraded=True,
            action_hint="检查失败条目后重试",
            occurred_at=now_local_iso(),
        )
    return None


def _run_action(action: ActionBuilder, execution_context: dict[str, Any]) -> dict[str, Any]:
    try:
        signature = inspect.signature(action)
    except (TypeError, ValueError):
        return action()
    required_parameters = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        and parameter.default is inspect.Parameter.empty
    ]
    if required_parameters:
        return action(execution_context)
    return action()


def execute_sync_action(
    *,
    intent: str,
    task_kind: str,
    context: dict[str, Any],
    artifact_type: str,
    action: ActionBuilder,
    summarize: SummaryBuilder,
    trigger: str = "user",
    build_review: ReviewBuilder | None = None,
) -> dict[str, Any]:
    started_at = now_local_iso()
    run_id = build_run_id(intent)
    run = ExecutionRun(
        run_id=run_id,
        intent=intent,
        status="running",
        trigger=trigger,
        started_at=started_at,
        context=context,
    )
    task = ExecutionTask(
        task_id=build_task_id(task_kind),
        run_id=run_id,
        kind=task_kind,
        status="running",
        input_ref=context,
        started_at=started_at,
    )
    run.current_task = task.task_id
    write_run(run)
    write_tasks(run_id, [task])
    append_event(run_id, "run_started", f"开始执行 {intent}", {"intent": intent, "trigger": trigger})
    append_event(run_id, "task_started", f"开始任务 {task_kind}", {"task_id": task.task_id, "context": context})
    execution_context = {
        "run_id": run_id,
        "task_id": task.task_id,
        "intent": intent,
        "trigger": trigger,
        "context": context,
    }

    try:
        result = _run_action(action, execution_context)
        finished_at = now_local_iso()
        artifact = write_artifact(
            run_id,
            task.task_id,
            artifact_type,
            result,
            meta={"intent": intent, "task_kind": task_kind},
        )
        failure = _infer_failure_state(task_kind, result)
        review_packet = build_review(result) if build_review is not None else None
        if review_packet is not None:
            review_packet.run_id = run_id
            review_packet.task_id = task.task_id
        task.status = "completed"
        task.finished_at = finished_at
        task.output_ref = {"artifact_id": artifact["artifact_id"], "path": artifact["path"]}
        if review_packet is not None:
            task.status = "waiting_human"
            write_review_packets(run_id, [review_packet])
            run.status = "action_required"
            append_event(
                run_id,
                "run_waiting_human",
                f"{task_kind} 等待人工确认",
                {"task_id": task.task_id, "packet_id": review_packet.packet_id, "kind": review_packet.kind},
            )
        elif failure is not None:
            task.failure_state = failure.to_dict()
            run.status = "degraded"
            run.failure_state = failure.to_dict()
            append_event(
                run_id,
                "run_degraded",
                failure.message,
                {"task_id": task.task_id, "failure_state": failure.to_dict()},
            )
        else:
            run.status = "completed"
        run.summary = summarize(result)
        run.finished_at = finished_at
        write_tasks(run_id, [task])
        write_run(run)
        append_event(run_id, "task_completed", run.summary, {"task_id": task.task_id, "artifact": artifact})
        append_event(run_id, "run_completed", run.summary, {"run_id": run_id, "status": run.status})
        return {
            "run": run.to_dict(),
            "task": task.to_dict(),
            "artifact": artifact,
            "failure_state": failure.to_dict() if failure is not None else None,
            "review_packet": review_packet.to_dict() if review_packet is not None else None,
            "result": result,
        }
    except Exception as exc:
        finished_at = now_local_iso()
        failure = FailureState(
            scope="task",
            stage=task_kind,
            code="exception",
            message=str(exc),
            retryable=False,
            degraded=False,
            action_hint="查看错误快照并修复后重试",
            occurred_at=finished_at,
        )
        task.status = "failed"
        task.finished_at = finished_at
        task.failure_state = failure.to_dict()
        run.status = "failed"
        run.finished_at = finished_at
        run.summary = f"{intent} 执行失败"
        run.failure_state = failure.to_dict()
        error_artifact = write_artifact(
            run_id,
            task.task_id,
            "error_snapshot",
            {"error": str(exc), "intent": intent, "task_kind": task_kind},
            meta={"intent": intent, "task_kind": task_kind},
        )
        task.output_ref = {"artifact_id": error_artifact["artifact_id"], "path": error_artifact["path"]}
        write_tasks(run_id, [task])
        write_run(run)
        append_event(
            run_id,
            "task_failed",
            str(exc),
            {"task_id": task.task_id, "failure_state": failure.to_dict(), "artifact": error_artifact},
        )
        append_event(run_id, "run_failed", run.summary, {"run_id": run_id, "status": run.status})
        raise ExecutionActionError(str(exc), run_id, failure.to_dict()) from exc
