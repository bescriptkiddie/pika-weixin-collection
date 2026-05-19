from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.content_loop.store import CONTENT_ITEMS_FILE, read_jsonl

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_INDEX_DIR = ROOT / "data" / "knowledge_index"
CARDS_INDEX_FILE = KNOWLEDGE_INDEX_DIR / "cards.jsonl"
TOPICS_INDEX_FILE = KNOWLEDGE_INDEX_DIR / "topics.jsonl"
GENERATION_DIR = ROOT / "data" / "generation"
BRIEFS_FILE = GENERATION_DIR / "generation_briefs.jsonl"
DRAFTS_FILE = GENERATION_DIR / "drafts.jsonl"
REVISION_TASKS_FILE = GENERATION_DIR / "revision_tasks.jsonl"
GENERATION_READY_KNOWLEDGE_STATUSES = {"approved", "applied"}
GENERATION_READY_REVIEW_STATUSES = {"approved", "applied"}


@dataclass
class GenerationBriefResult:
    briefs_file: str
    created: int
    total_candidates: int
    brief_ids: list[str]
    sample_titles: list[str]
    source_run_id: str = ""
    source_task_id: str = ""
    source_packet_id: str = ""


@dataclass
class DraftBuildResult:
    drafts_file: str
    created: int
    draft_id: str
    brief_id: str
    title: str
    topic: str
    sample_titles: list[str]
    summary: str
    status: str
    review_required: bool
    source_run_id: str = ""
    source_task_id: str = ""
    source_packet_id: str = ""


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _upsert_rows(existing_rows: list[dict[str, Any]], new_rows: list[dict[str, Any]], *, key_getter: Callable[[dict[str, Any]], str]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    new_by_key = {key_getter(row): row for row in new_rows if key_getter(row)}
    seen_keys: set[str] = set()
    for row in existing_rows:
        key = key_getter(row)
        replacement = new_by_key.get(key)
        if replacement is not None:
            merged.append(replacement)
            seen_keys.add(key)
            continue
        merged.append(row)
        if key:
            seen_keys.add(key)
    for row in new_rows:
        key = key_getter(row)
        if key and key in seen_keys:
            continue
        merged.append(row)
        if key:
            seen_keys.add(key)
    return merged


def _preserve_review_status(existing_row: dict[str, Any] | None, default_status: str = "candidate") -> str:
    if isinstance(existing_row, dict):
        existing_status = str(existing_row.get("status") or "")
        if existing_status in {"approved", "applied"}:
            return existing_status
    return default_status


def _candidate_trace_fields(trace: dict[str, Any] | None) -> dict[str, str]:
    if not trace:
        return {}
    fields: dict[str, str] = {}
    run_id = str(trace.get("run_id") or "").strip()
    task_id = str(trace.get("task_id") or "").strip()
    packet_id = str(trace.get("packet_id") or "").strip()
    if run_id:
        fields["source_run_id"] = run_id
    if task_id:
        fields["source_task_id"] = task_id
    if packet_id:
        fields["source_packet_id"] = packet_id
    return fields


def _applied_trace_fields(trace: dict[str, Any] | None) -> dict[str, str]:
    if not trace:
        return {}
    fields: dict[str, str] = {}
    run_id = str(trace.get("run_id") or "").strip()
    task_id = str(trace.get("task_id") or "").strip()
    packet_id = str(trace.get("packet_id") or "").strip()
    if run_id:
        fields["applied_run_id"] = run_id
    if task_id:
        fields["applied_task_id"] = task_id
    if packet_id:
        fields["applied_packet_id"] = packet_id
    return fields


def _preserve_source_trace_fields(existing_row: dict[str, Any] | None, trace: dict[str, Any] | None) -> dict[str, str]:
    fields = _candidate_trace_fields(trace)
    if not isinstance(existing_row, dict):
        return fields
    existing_status = str(existing_row.get("status") or "")
    if existing_status not in {"approved", "applied"}:
        return fields
    for key in ("source_run_id", "source_task_id", "source_packet_id"):
        value = str(existing_row.get(key) or "").strip()
        if value:
            fields[key] = value
    return fields


def _preserve_applied_trace_fields(existing_row: dict[str, Any] | None) -> dict[str, str]:
    fields: dict[str, str] = {}
    if not isinstance(existing_row, dict):
        return fields
    existing_status = str(existing_row.get("status") or "")
    if existing_status not in {"approved", "applied"}:
        return fields
    for key in ("applied_run_id", "applied_task_id", "applied_packet_id"):
        value = str(existing_row.get(key) or "").strip()
        if value:
            fields[key] = value
    return fields


def update_generation_status(kind: str, item_id: str, packet_status: str, *, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    target_status = "approved" if packet_status in {"approved", "edited"} else "rejected"
    path = BRIEFS_FILE if kind == "brief" else DRAFTS_FILE
    rows = read_jsonl(path)
    updated = 0
    for row in rows:
        if item_id and str(row.get("id") or "") != item_id:
            continue
        if not item_id and str(row.get("status") or "") != "candidate":
            continue
        row["status"] = target_status
        if target_status in GENERATION_READY_REVIEW_STATUSES:
            row.update(_applied_trace_fields(trace))
        updated += 1
    _write_jsonl(path, rows)
    return {
        "kind": kind,
        "file": str(path),
        "item_id": item_id,
        "status": target_status,
        "updated": updated,
    }


def build_generation_briefs(limit: int = 10, projected_action: str | None = None, knowledge_card_ids: list[str] | None = None, trace: dict[str, Any] | None = None) -> GenerationBriefResult:
    cards = read_jsonl(CARDS_INDEX_FILE)
    topics = read_jsonl(TOPICS_INDEX_FILE)
    source_items = {str(row.get("id") or ""): row for row in read_jsonl(CONTENT_ITEMS_FILE)}
    candidates = sorted(
        [row for row in cards if str(row.get("status") or "") in GENERATION_READY_KNOWLEDGE_STATUSES],
        key=lambda row: (
            float(row.get("projected_score") or 0.0),
            float(row.get("feedback_projection_delta") or 0.0),
            str(row.get("title") or ""),
        ),
        reverse=True,
    )
    selected_card_ids = {str(card_id) for card_id in (knowledge_card_ids or []) if str(card_id).strip()}
    if selected_card_ids:
        candidates = [row for row in candidates if str(row.get("id") or "") in selected_card_ids]
    if projected_action:
        candidates = [row for row in candidates if str(row.get("projected_action") or "") == projected_action]
    selected = candidates[: max(0, limit)]
    created = 0
    brief_ids: list[str] = []
    new_briefs: list[dict[str, Any]] = []

    for card in selected:
        source_item = source_items.get(str(card.get("source_item_id") or ""), {})
        topic = next((row for row in topics if row.get("source_item_id") == card.get("source_item_id")), None)
        brief_id = f"brief:{card.get('id')}"
        existing_brief = next((row for row in read_jsonl(BRIEFS_FILE) if str(row.get("id") or "") == brief_id), None)
        brief = {
            "id": brief_id,
            "title": str(card.get("title") or "未命名 brief"),
            "topic": str((topic or {}).get("title") or card.get("title") or ""),
            "source_item_id": str(card.get("source_item_id") or ""),
            "knowledge_card_id": str(card.get("id") or ""),
            "summary": str(card.get("summary") or source_item.get("summary") or ""),
            "outline": [
                "问题背景",
                "核心观点",
                "关键证据",
                "可延展方向",
            ],
            "sources": card.get("sources") or source_item.get("references") or [],
            "projected_score": round(float(card.get("projected_score") or 0.0), 4),
            "feedback_projection_delta": round(float(card.get("feedback_projection_delta") or 0.0), 4),
            "feedback_projection_reasons": card.get("feedback_projection_reasons") if isinstance(card.get("feedback_projection_reasons"), list) else [],
            "projected_action": str(card.get("projected_action") or ""),
            "projected_action_label": str(card.get("projected_action_label") or ""),
            "projected_action_reason": str(card.get("projected_action_reason") or ""),
            "status": _preserve_review_status(existing_brief),
            **_preserve_source_trace_fields(existing_brief, trace),
            **_preserve_applied_trace_fields(existing_brief),
        }
        new_briefs.append(brief)
        if brief["status"] == "candidate":
            brief_ids.append(str(brief["id"]))

    briefs = _upsert_rows(read_jsonl(BRIEFS_FILE), new_briefs, key_getter=lambda row: str(row.get("id") or ""))
    _write_jsonl(BRIEFS_FILE, briefs)

    sample_titles = [str(card.get("title") or "") for card in selected[:3] if str(card.get("title") or "")]
    created = len(brief_ids)

    return GenerationBriefResult(
        briefs_file=str(BRIEFS_FILE),
        created=created,
        total_candidates=len(candidates),
        brief_ids=brief_ids,
        sample_titles=sample_titles,
        source_run_id=str((trace or {}).get("run_id") or ""),
        source_task_id=str((trace or {}).get("task_id") or ""),
        source_packet_id=str((trace or {}).get("packet_id") or ""),
    )


def build_draft_from_brief(brief_id: str, trace: dict[str, Any] | None = None) -> DraftBuildResult:
    briefs = read_jsonl(BRIEFS_FILE)
    brief = next((row for row in briefs if str(row.get("id") or "") == brief_id), None)
    if brief is None:
        raise RuntimeError("写作提纲不存在")
    if str(brief.get("status") or "") not in GENERATION_READY_REVIEW_STATUSES:
        raise RuntimeError("写作提纲尚未批准，不能生成草稿")

    draft_id = f"draft:{brief_id}"
    existing_draft = next((row for row in read_jsonl(DRAFTS_FILE) if str(row.get("id") or "") == draft_id), None)
    draft_status = _preserve_review_status(existing_draft)
    draft = {
        "id": draft_id,
        "brief_id": brief_id,
        "title": str(brief.get("title") or "未命名草稿"),
        "topic": str(brief.get("topic") or ""),
        "content": "\n".join([
            f"# {brief.get('title') or ''}",
            "",
            "## 问题背景",
            str(brief.get("summary") or ""),
            "",
            "## 核心观点",
            "等待补充。",
            "",
            "## 关键证据",
            "- 待从知识卡片与来源中补充",
            "",
            "## 可延展方向",
            "- 待人工改写或补充",
            "",
        ]),
        "sources": brief.get("sources") or [],
        "status": draft_status,
        **_preserve_source_trace_fields(existing_draft, trace),
        **_preserve_applied_trace_fields(existing_draft),
    }
    drafts = _upsert_rows(read_jsonl(DRAFTS_FILE), [draft], key_getter=lambda row: str(row.get("id") or ""))
    _write_jsonl(DRAFTS_FILE, drafts)
    return DraftBuildResult(
        drafts_file=str(DRAFTS_FILE),
        created=1,
        draft_id=draft_id,
        brief_id=brief_id,
        title=str(draft.get("title") or ""),
        topic=str(draft.get("topic") or ""),
        sample_titles=[str(draft.get("title") or "")],
        summary=str(brief.get("summary") or ""),
        status=draft_status,
        review_required=draft_status == "candidate",
        source_run_id=str(draft.get("source_run_id") or ""),
        source_task_id=str(draft.get("source_task_id") or ""),
        source_packet_id=str(draft.get("source_packet_id") or ""),
    )


def list_generation_briefs() -> dict[str, Any]:
    return {
        "briefs_file": str(BRIEFS_FILE),
        "briefs": read_jsonl(BRIEFS_FILE),
    }


def list_drafts() -> dict[str, Any]:
    return {
        "drafts_file": str(DRAFTS_FILE),
        "drafts": read_jsonl(DRAFTS_FILE),
    }
