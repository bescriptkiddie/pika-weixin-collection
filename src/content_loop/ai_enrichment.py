from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.llm.model_client import chat_content_loop_llm, content_loop_llm_status

from .store import (
    CONTENT_ITEMS_FILE,
    now_local_iso,
    read_jsonl,
    summary_from_text,
    write_jsonl,
)
from .tagging import _load_taxonomy


@dataclass
class AIEnrichmentResult:
    content_items_file: str
    total_candidates: int
    processed: int
    skipped: int
    failed: int
    model: str
    errors: list[dict[str, str]]


def _parse_json_object(content: str) -> dict[str, Any]:
    text = content.strip()
    block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if block:
        text = block.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    bracket = re.search(r"\{[\s\S]*\}", text)
    if bracket:
        data = json.loads(bracket.group(0))
        if isinstance(data, dict):
            return data
    raise ValueError(f"模型输出不是 JSON object: {content[:160]!r}")


def _item_text(item: dict[str, Any], max_chars: int) -> str:
    content = str(item.get("content_markdown") or "")
    preview = "\n".join(
        [
            f"标题：{item.get('title') or ''}",
            f"来源：{item.get('source_name') or item.get('source_id') or ''}",
            f"已有摘要：{item.get('summary') or ''}",
            f"已有标签：{', '.join(item.get('tags') or [])}",
            "正文片段：",
            content,
        ]
    )
    return preview[:max_chars]


def _allowed_tags(taxonomy: dict[str, Any]) -> list[str]:
    names = [tag["name"] for tag in taxonomy.get("tags", []) if tag.get("name")]
    if "待分类" not in names:
        names.append("待分类")
    return names


def _system_prompt(allowed_tags: list[str]) -> str:
    return f"""你是本地内容池的中文分类与摘要助手。请只基于给定内容判断，不要编造来源没有的信息。

允许标签只能从下面列表选择，最多 5 个：
{", ".join(allowed_tags)}

输出必须是 JSON object，结构如下：
{{
  "summary": "50-140字中文摘要，保留具体对象和观点",
  "tags": ["只能从允许标签中选择"],
  "category": "一句话内容类型，如 技术分析/市场观点/产品案例/低价值广告/待分类",
  "confidence": 0.0,
  "why": "20字以内解释分类依据"
}}

规则：
- 如果内容是推广、带货、课程、优惠、引流，tags 必须包含「低价值广告」。
- 如果证据不足，tags 用「待分类」，confidence 低于 0.5。
- 不要输出 Markdown，不要输出 JSON 之外的文字。"""


def _sanitize_ai_result(data: dict[str, Any], allowed_tags: list[str], fallback_tags: list[str]) -> dict[str, Any]:
    allowed = set(allowed_tags)
    tags: list[str] = []
    for tag in data.get("tags", []):
        tag = str(tag).strip()
        if tag in allowed and tag not in tags:
            tags.append(tag)
    if not tags:
        tags = [tag for tag in fallback_tags if tag in allowed][:5] or ["待分类"]

    summary = summary_from_text(str(data.get("summary") or ""), 180)
    category = summary_from_text(str(data.get("category") or ""), 40)
    why = summary_from_text(str(data.get("why") or ""), 80)
    try:
        confidence = float(data.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        "summary": summary,
        "tags": tags[:5],
        "category": category or "待分类",
        "confidence": confidence,
        "why": why,
    }


def ai_enrich_content_items(
    *,
    limit: int = 30,
    only_missing: bool = True,
    source_type: str | None = None,
    tag: str | None = None,
    item_ids: list[str] | None = None,
    max_chars: int = 3200,
    content_items_path: str | Path = CONTENT_ITEMS_FILE,
    taxonomy_path: str | Path | None = None,
) -> AIEnrichmentResult:
    status = content_loop_llm_status()
    if not status["configured"]:
        raise RuntimeError("内容闭环 LLM 未配置，请设置 CONTENT_LOOP_LLM_BASE_URL 和 CONTENT_LOOP_LLM_API_KEY")

    path = Path(content_items_path)
    rows = read_jsonl(path)
    taxonomy = _load_taxonomy(taxonomy_path, allow_example=True)
    allowed_tags = _allowed_tags(taxonomy)
    item_id_set = set(item_ids or [])

    candidates: list[dict[str, Any]] = []
    for item in rows:
        if source_type and item.get("source_type") != source_type:
            continue
        if tag and tag not in (item.get("tags") or []):
            continue
        if item_id_set and item.get("id") not in item_id_set:
            continue
        if only_missing and item.get("ai_summary") and item.get("ai_tags"):
            continue
        candidates.append(item)

    limit = max(0, min(limit, len(candidates)))
    selected = candidates[:limit]
    processed = 0
    failed = 0
    errors: list[dict[str, str]] = []
    now = now_local_iso()

    for item in selected:
        fallback_tags = item.get("auto_tags") if isinstance(item.get("auto_tags"), list) else item.get("tags") or []
        messages = [
            {"role": "system", "content": _system_prompt(allowed_tags)},
            {"role": "user", "content": _item_text(item, max_chars=max_chars)},
        ]
        try:
            raw = chat_content_loop_llm(messages)
            parsed = _sanitize_ai_result(_parse_json_object(raw), allowed_tags, fallback_tags)
            original_summary = item.get("original_summary")
            if original_summary is None:
                item["original_summary"] = item.get("summary") or ""
            item["ai_summary"] = parsed["summary"]
            item["summary"] = parsed["summary"] or item.get("summary") or ""
            item["ai_tags"] = parsed["tags"]
            item["ai_category"] = parsed["category"]
            item["ai_confidence"] = parsed["confidence"]
            item["ai_rationale"] = parsed["why"]
            item["ai_model"] = status["model"]
            item["ai_enriched_at"] = now
            merged_tags: list[str] = []
            for tag_name in [*(item.get("tags") or []), *parsed["tags"]]:
                if tag_name and tag_name not in merged_tags:
                    merged_tags.append(tag_name)
            item["tags"] = merged_tags
            item.pop("ai_error", None)
            processed += 1
        except Exception as exc:  # noqa: BLE001 - keep batch running
            failed += 1
            item["ai_error"] = str(exc)
            errors.append({"item_id": str(item.get("id") or ""), "error": str(exc)})

    if selected:
        write_jsonl(path, rows)

    return AIEnrichmentResult(
        content_items_file=str(path),
        total_candidates=len(candidates),
        processed=processed,
        skipped=len(candidates) - len(selected),
        failed=failed,
        model=str(status["model"]),
        errors=errors,
    )


def get_ai_enrichment_overview(*, content_items_path: str | Path = CONTENT_ITEMS_FILE) -> dict[str, Any]:
    rows = read_jsonl(Path(content_items_path))
    status = content_loop_llm_status()
    return {
        **status,
        "base_url": status["base_url"],
        "api_key_hint": "已配置" if status["has_api_key"] else "未配置",
        "ai_summaries": sum(1 for item in rows if item.get("ai_summary")),
        "ai_tagged": sum(1 for item in rows if item.get("ai_tags")),
        "ai_errors": sum(1 for item in rows if item.get("ai_error")),
    }
