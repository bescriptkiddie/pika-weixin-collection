from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
GENERATION_DIR = ROOT / "data" / "generation"
DRAFTS_FILE = GENERATION_DIR / "drafts.jsonl"
GEO_FILE = GENERATION_DIR / "geo_variants.jsonl"
GENERATION_READY_REVIEW_STATUSES = {"approved", "applied"}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
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
                rows.append(value)
    return rows


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


@dataclass
class GeoVariantResult:
    geo_file: str
    created: int
    geo_id: str
    draft_id: str
    title: str
    topic: str
    sample_titles: list[str]
    qa_count: int
    faq_count: int
    status: str
    review_required: bool
    source_run_id: str = ""
    source_task_id: str = ""
    source_packet_id: str = ""


def update_geo_variant_status(draft_id: str, packet_status: str, *, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    target_status = "approved" if packet_status in {"approved", "edited"} else "rejected"
    rows = _read_jsonl(GEO_FILE)
    updated = 0
    for row in rows:
        if str(row.get("draft_id") or "") != draft_id:
            continue
        row["status"] = target_status
        if target_status in GENERATION_READY_REVIEW_STATUSES:
            row.update(_applied_trace_fields(trace))
        updated += 1
    _write_jsonl(GEO_FILE, rows)
    return {
        "file": str(GEO_FILE),
        "draft_id": draft_id,
        "status": target_status,
        "updated": updated,
    }


def build_geo_variants(draft_id: str, trace: dict[str, Any] | None = None) -> GeoVariantResult:
    drafts = _read_jsonl(DRAFTS_FILE)
    draft = next((row for row in drafts if str(row.get("id") or "") == draft_id), None)
    if draft is None:
        raise RuntimeError("草稿不存在")
    if str(draft.get("status") or "") not in GENERATION_READY_REVIEW_STATUSES:
        raise RuntimeError("草稿尚未批准，不能生成 GEO 变体")

    title = str(draft.get("title") or "未命名文章")
    topic = str(draft.get("topic") or title)
    sources = draft.get("sources") or []
    geo_id = f"geo:{draft_id}"
    existing_variant = next((row for row in _read_jsonl(GEO_FILE) if str(row.get("id") or "") == geo_id), None)
    variant_status = _preserve_review_status(existing_variant)
    sample_titles = [
        title,
        f"{topic} 的结构化理解与实践路径",
        f"如何把 {topic} 变成可复用的知识资产",
    ]
    variant = {
        "id": geo_id,
        "draft_id": draft_id,
        "title": title,
        "topic": topic,
        "qa_summary": [
            {"q": f"{topic} 是什么？", "a": f"{title} 围绕 {topic} 提供了一个结构化解释。"},
            {"q": f"为什么 {topic} 值得关注？", "a": "它关联到持续内容积累、知识复用和后续文章生成。"},
        ],
        "faq": [
            {"question": f"这篇内容的核心观点是什么？", "answer": "先用内容池筛选，再把高价值条目沉淀进知识库，最后形成文章产出。"},
            {"question": "它和普通内容整理有什么不同？", "answer": "它强调来源可回溯、知识沉淀和可持续生成。"},
        ],
        "claim_blocks": [
            {"claim": title, "source_count": len(sources), "sources": sources},
        ],
        "title_variants": [
            title,
            f"{topic} 的结构化理解与实践路径",
            f"如何把 {topic} 变成可复用的知识资产",
        ],
        "lede_variants": [
            f"围绕 {topic}，这份草稿尝试把零散信息整理成可引用、可扩展的知识表达。",
            f"如果目标是让生成式引擎更容易理解 {topic}，最关键的是把观点、证据和结构讲清楚。",
        ],
        "sample_titles": sample_titles,
        "status": variant_status,
        **_preserve_source_trace_fields(existing_variant, trace),
        **_preserve_applied_trace_fields(existing_variant),
    }
    variants = _upsert_rows(_read_jsonl(GEO_FILE), [variant], key_getter=lambda row: str(row.get("id") or ""))
    _write_jsonl(GEO_FILE, variants)
    return GeoVariantResult(
        geo_file=str(GEO_FILE),
        created=1,
        geo_id=geo_id,
        draft_id=draft_id,
        title=title,
        topic=topic,
        sample_titles=sample_titles,
        qa_count=len(variant.get("qa_summary") or []),
        faq_count=len(variant.get("faq") or []),
        status=variant_status,
        review_required=variant_status == "candidate",
        source_run_id=str(variant.get("source_run_id") or ""),
        source_task_id=str(variant.get("source_task_id") or ""),
        source_packet_id=str(variant.get("source_packet_id") or ""),
    )


def list_geo_variants() -> dict[str, Any]:
    return {
        "geo_file": str(GEO_FILE),
        "variants": _read_jsonl(GEO_FILE),
    }
