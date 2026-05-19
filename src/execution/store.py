from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import ExecutionArtifact, ExecutionRun, ExecutionTask, ReviewPacket

ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT / "data" / "runs"


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def build_run_id(intent: str) -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = uuid4().hex[:8]
    return f"{intent}-{stamp}-{suffix}"


def build_task_id(kind: str) -> str:
    return f"{kind}-{uuid4().hex[:8]}"


def build_packet_id(kind: str) -> str:
    return f"{kind}-{uuid4().hex[:8]}"


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / run_id


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2)


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_json_dumps(data), encoding="utf-8")


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def append_event(run_id: str, event_type: str, message: str, details: dict[str, Any] | None = None) -> None:
    path = run_dir(run_id) / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": now_local_iso(),
        "type": event_type,
        "message": message,
        "details": details or {},
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def read_events(run_id: str, limit: int = 200) -> list[dict[str, Any]]:
    path = run_dir(run_id) / "events.jsonl"
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                entries.append(value)
    return entries[-limit:]


def write_run(run: ExecutionRun) -> None:
    _write_json(run_dir(run.run_id) / "run.json", run.to_dict())


def read_run(run_id: str) -> dict[str, Any] | None:
    path = run_dir(run_id) / "run.json"
    if not path.exists():
        return None
    return _read_json(path, None)


def write_tasks(run_id: str, tasks: list[ExecutionTask]) -> None:
    _write_json(run_dir(run_id) / "tasks.json", [task.to_dict() for task in tasks])


def read_tasks(run_id: str) -> list[dict[str, Any]]:
    return _read_json(run_dir(run_id) / "tasks.json", [])


def write_review_packets(run_id: str, packets: list[ReviewPacket]) -> None:
    _write_json(run_dir(run_id) / "review_packets.json", [packet.to_dict() for packet in packets])


def read_review_packets(run_id: str) -> list[dict[str, Any]]:
    return _read_json(run_dir(run_id) / "review_packets.json", [])


def resolve_review_packet(run_id: str, packet_id: str, *, status: str, resolved_by: str = "local_user", finalize_run: bool = True) -> dict[str, Any] | None:
    packets = read_review_packets(run_id)
    updated = None
    now = now_local_iso()
    for packet in packets:
        if str(packet.get("packet_id") or "") != packet_id:
            continue
        packet["status"] = status
        packet["resolved_at"] = now
        packet["resolved_by"] = resolved_by
        updated = packet
        break
    if updated is None:
        return None
    _write_json(run_dir(run_id) / "review_packets.json", packets)

    run = read_run(run_id) or {}
    tasks = read_tasks(run_id)
    has_open_packets = any(str(packet.get("status") or "open") == "open" for packet in packets)
    if not has_open_packets and run:
        target_task = None
        if tasks:
            target_task_id = str(updated.get("task_id") or "")
            target_task = next((task for task in tasks if str(task.get("task_id") or "") == target_task_id), None)
            if target_task is None:
                target_task = tasks[-1]
            target_task["status"] = "approved" if status in {"approved", "edited"} else "rejected"
            target_task["finished_at"] = now

        if status in {"approved", "edited"}:
            run["summary"] = str(run.get("summary") or "人工闸门已处理")
            run["failure_state"] = None
            if finalize_run:
                run["status"] = "completed"
                run["finished_at"] = now
            else:
                run["status"] = "running"
                run["finished_at"] = ""
            append_event(run_id, "run_resumed", f"人工闸门已处理：{packet_id}", {"packet_id": packet_id, "status": status})
        else:
            run["status"] = "rejected"
            run["finished_at"] = now
            run["summary"] = str(run.get("summary") or "人工闸门已处理")
            run["failure_state"] = {
                "scope": "run",
                "stage": "human_gate",
                "code": "review_rejected",
                "message": f"人工闸门拒绝继续执行：{packet_id}",
                "retryable": False,
                "degraded": False,
                "action_required": "",
                "action_hint": "调整候选内容后重新生成",
                "provider": "",
                "provider_trace": [],
                "verify_type": "",
                "verify_uuid": "",
                "occurred_at": now,
            }
            append_event(run_id, "run_rejected", f"人工闸门拒绝：{packet_id}", {"packet_id": packet_id, "status": status})

        _write_json(run_dir(run_id) / "run.json", run)
        if target_task is not None:
            if status in {"approved", "edited"}:
                target_task["failure_state"] = None
            else:
                target_task["failure_state"] = run["failure_state"]
            _write_json(run_dir(run_id) / "tasks.json", tasks)
    return updated


def _artifact_index_path(run_id: str) -> Path:
    return run_dir(run_id) / "artifacts" / "index.json"


def read_artifact_index(run_id: str) -> list[dict[str, Any]]:
    return _read_json(_artifact_index_path(run_id), [])


def write_artifact(
    run_id: str,
    task_id: str,
    artifact_type: str,
    payload: Any,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    created_at = now_local_iso()
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    checksum = hashlib.sha256(body).hexdigest()
    artifact_id = f"{artifact_type}-{uuid4().hex[:8]}"
    relative_path = Path("artifacts") / f"{task_id}-{artifact_type}.json"
    path = run_dir(run_id) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, payload)
    artifact = ExecutionArtifact(
        artifact_id=artifact_id,
        run_id=run_id,
        task_id=task_id,
        type=artifact_type,
        path=str(relative_path),
        checksum=checksum,
        created_at=created_at,
        meta=meta or {},
    )
    index = read_artifact_index(run_id)
    index.append(artifact.to_dict())
    _write_json(_artifact_index_path(run_id), index)
    return artifact.to_dict()


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    runs: list[tuple[float, dict[str, Any]]] = []
    for run_json in RUNS_DIR.glob("*/run.json"):
        try:
            data = _read_json(run_json, None)
        except Exception:
            continue
        if isinstance(data, dict):
            runs.append((run_json.stat().st_mtime, data))
    runs.sort(key=lambda row: row[0], reverse=True)
    return [data for _, data in runs[: max(0, limit)]]


def get_run_detail(run_id: str) -> dict[str, Any] | None:
    run = read_run(run_id)
    if not run:
        return None
    return {
        "run": run,
        "tasks": read_tasks(run_id),
        "events": list(reversed(read_events(run_id))),
        "review_packets": read_review_packets(run_id),
        "artifacts": read_artifact_index(run_id),
    }


def _build_review_packet_preview(packet: dict[str, Any]) -> dict[str, Any]:
    payload = packet.get("candidate_payload") if isinstance(packet.get("candidate_payload"), dict) else {}
    preview: dict[str, Any] = {}
    kind = str(packet.get("kind") or "")
    if kind == "knowledge_candidates_review":
        sample_titles = payload.get("sample_titles") if isinstance(payload.get("sample_titles"), list) else []
        topic_only = not bool(payload.get("candidate_card_ids")) and bool(payload.get("candidate_topic_ids"))
        preview = {
            "label": "主题综合候选" if topic_only else "知识候选",
            "summary": (f"主题 {payload.get('synthesis') or 0} 条" if topic_only else f"候选 {payload.get('candidates') or 0} 条，主题 {payload.get('synthesis') or 0} 条"),
            "items": [str(title) for title in sample_titles[:3] if str(title)],
            "details": {
                "candidates": int(payload.get('candidates') or 0),
                "synthesis": int(payload.get('synthesis') or 0),
                "card_ids": payload.get('candidate_card_ids') if isinstance(payload.get('candidate_card_ids'), list) else [],
                "topic_ids": payload.get('candidate_topic_ids') if isinstance(payload.get('candidate_topic_ids'), list) else [],
                "topic_only": topic_only,
                "source_run_id": str(payload.get('source_run_id') or ''),
                "source_task_id": str(payload.get('source_task_id') or ''),
                "source_packet_id": str(payload.get('source_packet_id') or ''),
            },
        }
    elif kind == "topic_synthesis_review":
        sample_titles = payload.get("sample_titles") if isinstance(payload.get("sample_titles"), list) else []
        preview = {
            "label": "主题综合候选",
            "summary": f"主题 {payload.get('synthesis') or 0} 条",
            "items": [str(title) for title in sample_titles[:3] if str(title)],
            "details": {
                "candidates": int(payload.get('candidates') or 0),
                "synthesis": int(payload.get('synthesis') or 0),
                "card_ids": payload.get('candidate_card_ids') if isinstance(payload.get('candidate_card_ids'), list) else [],
                "topic_ids": payload.get('candidate_topic_ids') if isinstance(payload.get('candidate_topic_ids'), list) else [],
                "topic_only": True,
                "source_run_id": str(payload.get('source_run_id') or ''),
                "source_task_id": str(payload.get('source_task_id') or ''),
                "source_packet_id": str(payload.get('source_packet_id') or ''),
            },
        }
    elif kind == "generation_briefs_review":
        sample_titles = payload.get("sample_titles") if isinstance(payload.get("sample_titles"), list) else []
        preview = {
            "label": "写作提纲",
            "summary": f"创建 {payload.get('created') or 0} 条，候选总数 {payload.get('total_candidates') or 0} 条",
            "items": [str(title) for title in sample_titles[:3] if str(title)],
            "details": {
                "created": int(payload.get('created') or 0),
                "total_candidates": int(payload.get('total_candidates') or 0),
                "brief_ids": payload.get('brief_ids') if isinstance(payload.get('brief_ids'), list) else [],
                "source_run_id": str(payload.get('source_run_id') or ''),
                "source_task_id": str(payload.get('source_task_id') or ''),
                "source_packet_id": str(payload.get('source_packet_id') or ''),
            },
        }
    elif kind == "draft_review":
        preview = {
            "label": "草稿",
            "summary": str(payload.get("title") or payload.get("draft_id") or "待确认草稿"),
            "items": [str(payload.get("title") or payload.get("draft_id") or "")],
            "details": {
                "topic": str(payload.get("topic") or ""),
                "summary": str(payload.get("summary") or ""),
                "source_run_id": str(payload.get('source_run_id') or ''),
                "source_task_id": str(payload.get('source_task_id') or ''),
                "source_packet_id": str(payload.get('source_packet_id') or ''),
            },
        }
    elif kind == "geo_review":
        sample_titles = payload.get("sample_titles") if isinstance(payload.get("sample_titles"), list) else []
        preview = {
            "label": "GEO",
            "summary": str(payload.get("geo_id") or payload.get("draft_id") or "待确认 GEO 变体"),
            "items": [str(title) for title in sample_titles[:3] if str(title)],
            "details": {
                "topic": str(payload.get("topic") or ""),
                "qa_count": int(payload.get("qa_count") or 0),
                "faq_count": int(payload.get("faq_count") or 0),
                "source_run_id": str(payload.get('source_run_id') or ''),
                "source_task_id": str(payload.get('source_task_id') or ''),
                "source_packet_id": str(payload.get('source_packet_id') or ''),
                "applied_run_id": str(payload.get('applied_run_id') or ''),
                "applied_task_id": str(payload.get('applied_task_id') or ''),
                "applied_packet_id": str(payload.get('applied_packet_id') or ''),
            },
        }
    else:
        preview = {
            "label": kind or "review",
            "summary": str(packet.get("reason") or ""),
        }
    return preview


def _build_review_packet_follow_up(packet: dict[str, Any]) -> dict[str, Any] | None:
    payload = packet.get("candidate_payload") if isinstance(packet.get("candidate_payload"), dict) else {}
    kind = str(packet.get("kind") or "")
    if kind == "knowledge_candidates_review":
        return {"action": "apply_reviewed_knowledge", "label": "批准并入库"}
    if kind == "topic_synthesis_review":
        return {"action": "apply_reviewed_knowledge", "label": "批准并写入主题综合"}
    if kind == "generation_briefs_review":
        brief_ids = payload.get("brief_ids") if isinstance(payload.get("brief_ids"), list) else []
        normalized_brief_ids = [str(brief_id) for brief_id in brief_ids if str(brief_id)]
        first_brief_id = normalized_brief_ids[0] if normalized_brief_ids else ""
        if first_brief_id:
            if len(normalized_brief_ids) > 1:
                follow_up = {
                    "action": "build_generation_draft",
                    "target_id": first_brief_id,
                    "target_ids": normalized_brief_ids,
                    "count": len(normalized_brief_ids),
                    "label": f"批准并生成 {len(normalized_brief_ids)} 个草稿",
                }
                return follow_up
            return {"action": "build_generation_draft", "target_id": first_brief_id, "label": "批准并生成草稿"}
    if kind == "draft_review":
        draft_id = str(payload.get("draft_id") or "")
        if draft_id:
            return {"action": "build_geo_variants", "target_id": draft_id, "label": "批准并生成 GEO 变体"}
    return None

def list_open_review_packets(limit: int = 100) -> list[dict[str, Any]]:
    if not RUNS_DIR.exists():
        return []
    packets: list[dict[str, Any]] = []
    for review_file in RUNS_DIR.glob("*/review_packets.json"):
        run_id = review_file.parent.name
        try:
            rows = _read_json(review_file, [])
        except Exception:
            continue
        if not isinstance(rows, list):
            continue
        run = read_run(run_id) or {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            if str(row.get("status") or "open") != "open":
                continue
            preview = _build_review_packet_preview(row)
            follow_up = _build_review_packet_follow_up(row)
            packets.append({
                **row,
                "run_id": str(row.get("run_id") or run_id),
                "run_intent": str(run.get("intent") or ""),
                "run_status": str(run.get("status") or ""),
                "run_summary": str(run.get("summary") or ""),
                "started_at": str(run.get("started_at") or ""),
                "preview": preview,
                "follow_up": follow_up,
            })
    packets.sort(key=lambda row: (str(row.get("started_at") or ""), str(row.get("packet_id") or "")), reverse=True)
    return packets[: max(0, limit)]


def get_latest_run_detail() -> dict[str, Any] | None:
    runs = list_runs(limit=1)
    if not runs:
        return None
    run_id = str(runs[0].get("run_id") or "")
    if not run_id:
        return None
    return get_run_detail(run_id)
