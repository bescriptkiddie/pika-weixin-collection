from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"

CONTENT_ITEMS_FILE = DATA_DIR / "content_items.jsonl"
FEEDBACK_EVENTS_FILE = DATA_DIR / "feedback_events.jsonl"
EXTERNAL_SOURCES_FILE = DATA_DIR / "external_sources.json"
EXTERNAL_SOURCES_EXAMPLE_FILE = DATA_DIR / "external_sources.example.json"

PRESERVED_ITEM_FIELDS = {
    "human_decision",
    "feedback_notes",
    "last_feedback_at",
    "last_feedback_event",
    "score",
    "status",
    "tags",
    "auto_tags",
    "tag_scores",
    "tag_evidence",
}


def now_local_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_slug(text: str, fallback: str = "item", max_len: int = 80) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", text).strip(" .-_")
    name = re.sub(r"\s+", "-", name)
    return (name or fallback)[:max_len].strip(".-_") or fallback


def content_hash(*parts: str) -> str:
    payload = "\n".join(part for part in parts if part)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def summary_from_text(text: str, limit: int = 180) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "..."


def detail_to_markdown(detail: Any, fallback: str = "") -> str:
    if isinstance(detail, list):
        parts = [str(part).strip() for part in detail if str(part).strip()]
    elif isinstance(detail, str) and detail.strip():
        parts = [detail.strip()]
    else:
        parts = [fallback.strip()] if fallback.strip() else []
    return "\n\n".join(parts)


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def load_external_source_configs(
    config_path: str | Path | None = None,
    *,
    allow_example: bool = True,
) -> dict[str, Any]:
    path = Path(config_path) if config_path else EXTERNAL_SOURCES_FILE
    using_example = False
    if not path.exists() and allow_example and EXTERNAL_SOURCES_EXAMPLE_FILE.exists():
        path = EXTERNAL_SOURCES_EXAMPLE_FILE
        using_example = True

    if not path.exists():
        return {
            "path": str(path),
            "using_example": using_example,
            "sources": [],
        }

    raw = read_json(path, [])
    sources = raw.get("sources", []) if isinstance(raw, dict) else raw
    if not isinstance(sources, list):
        sources = []

    normalized: list[dict[str, Any]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        if not source.get("id") or not source.get("type"):
            continue
        normalized.append(
            {
                "id": str(source["id"]),
                "type": str(source["type"]),
                "name": str(source.get("name") or source["id"]),
                "url": str(source.get("url") or ""),
                "enabled": bool(source.get("enabled", True)),
                "human_reason": str(source.get("human_reason") or ""),
                "options": source.get("options") if isinstance(source.get("options"), dict) else {},
            }
        )

    return {
        "path": str(path),
        "using_example": using_example,
        "sources": normalized,
    }


def wechat_article_to_content_item(account: str, article: dict[str, Any], detail: Any = None) -> dict[str, Any] | None:
    article_id = str(article.get("id") or "").strip()
    if not article_id or article.get("is_deleted"):
        return None

    title = str(article.get("title") or "未命名文章").strip()
    digest = str(article.get("digest") or "").strip()
    content_markdown = detail_to_markdown(detail, digest)
    summary = str(article.get("summary") or "").strip() or summary_from_text(digest or content_markdown)
    published_at = str(article.get("create_time") or "")
    url = str(article.get("link") or "")
    tags = article.get("tags") if isinstance(article.get("tags"), list) else []
    item_hash = content_hash(title, digest, content_markdown, url)

    return {
        "id": f"wechat_article:{article_id}",
        "source_type": "wechat_article",
        "source_id": account,
        "source_name": account,
        "title": title,
        "url": url,
        "author": account,
        "published_at": published_at,
        "fetched_at": published_at,
        "summary": summary,
        "tags": tags,
        "score": article.get("score", 0.0),
        "content_hash": item_hash,
        "dedupe_key": f"wechat_article:{item_hash[:16]}",
        "status": "candidate",
        "content_markdown": content_markdown,
        "references": [
            {"type": "url", "url": url},
            {"type": "wechat_article", "account": account, "article_id": article_id},
        ],
        "human_decision": "candidate",
        "feedback_notes": [],
        "metadata": {
            "origin": "wechat-official-account",
            "article_id": article_id,
            "account": account,
            "cover": article.get("cover") or "",
            "item_show_type": article.get("item_show_type"),
        },
    }


def build_wechat_content_items(
    message_info: dict[str, Any] | None = None,
    detail_texts: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if message_info is None:
        message_info = read_json(DATA_DIR / "message_info.json", {})
    if detail_texts is None:
        detail_texts = read_json(DATA_DIR / "message_detail_text.json", {})

    items: list[dict[str, Any]] = []
    for account, account_data in message_info.items():
        blogs = account_data.get("blogs", []) if isinstance(account_data, dict) else []
        for article in blogs:
            if not isinstance(article, dict):
                continue
            detail = detail_texts.get(article.get("id")) if isinstance(detail_texts, dict) else None
            item = wechat_article_to_content_item(account, article, detail)
            if item:
                items.append(item)
    return items


def upsert_content_items(
    items: list[dict[str, Any]],
    *,
    path: str | Path = CONTENT_ITEMS_FILE,
) -> dict[str, Any]:
    target = Path(path)
    existing = read_jsonl(target)
    by_id = {str(item.get("id")): item for item in existing if item.get("id")}
    inserted = 0
    updated = 0

    for item in items:
        item_id = str(item.get("id") or "").strip()
        if not item_id:
            continue
        previous = by_id.get(item_id, {})
        merged = {**previous, **item}
        for field in PRESERVED_ITEM_FIELDS:
            if field in previous and previous[field] not in (None, "", [], {}):
                merged[field] = previous[field]
        if previous:
            updated += 1
        else:
            inserted += 1
        by_id[item_id] = merged

    ordered = sorted(
        by_id.values(),
        key=lambda row: str(row.get("published_at") or row.get("fetched_at") or ""),
        reverse=True,
    )
    write_jsonl(target, ordered)
    return {
        "content_items_file": str(target),
        "inserted": inserted,
        "updated": updated,
        "total": len(ordered),
    }


def sync_wechat_content_items(*, path: str | Path = CONTENT_ITEMS_FILE) -> dict[str, Any]:
    items = build_wechat_content_items()
    result = upsert_content_items(items, path=path)
    result["source_type"] = "wechat_article"
    result["normalized"] = len(items)
    return result


def list_content_items(
    *,
    limit: int = 100,
    source_type: str | None = None,
    tag: str | None = None,
    human_decision: str | None = None,
    include_content: bool = False,
    path: str | Path = CONTENT_ITEMS_FILE,
) -> list[dict[str, Any]]:
    rows = read_jsonl(Path(path))
    if source_type:
        rows = [row for row in rows if row.get("source_type") == source_type]
    if tag:
        rows = [row for row in rows if tag in (row.get("tags") or [])]
    if human_decision:
        rows = [row for row in rows if row.get("human_decision") == human_decision]
    rows = rows[: max(0, limit)]
    if include_content:
        return rows
    trimmed: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        content = str(item.get("content_markdown") or "")
        item.pop("content_markdown", None)
        item["content_preview"] = summary_from_text(content, 240)
        trimmed.append(item)
    return trimmed


def record_feedback_event(
    *,
    item_id: str,
    event: str,
    human_decision: str,
    feedback_note: str = "",
    suggested_action: str = "",
    channel: str = "local_web",
    weight: float = 1.0,
    content_items_path: str | Path = CONTENT_ITEMS_FILE,
    feedback_events_path: str | Path = FEEDBACK_EVENTS_FILE,
) -> dict[str, Any]:
    created_at = now_local_iso()
    feedback = {
        "item_id": item_id,
        "event": event,
        "human_decision": human_decision,
        "feedback_note": feedback_note,
        "suggested_action": suggested_action,
        "channel": channel,
        "weight": weight,
        "created_at": created_at,
    }
    append_jsonl(Path(feedback_events_path), feedback)

    rows = read_jsonl(Path(content_items_path))
    updated_item: dict[str, Any] | None = None
    for item in rows:
        if item.get("id") != item_id:
            continue
        item["human_decision"] = human_decision
        item["last_feedback_at"] = created_at
        item["last_feedback_event"] = event
        notes = item.get("feedback_notes")
        if not isinstance(notes, list):
            notes = []
        if feedback_note:
            notes.append(feedback_note)
        item["feedback_notes"] = notes[-20:]
        updated_item = item
        break
    if updated_item is not None:
        write_jsonl(Path(content_items_path), rows)

    response_item = None
    if updated_item is not None:
        response_item = dict(updated_item)
        content = str(response_item.pop("content_markdown", "") or "")
        response_item["content_preview"] = summary_from_text(content, 240)

    return {
        "event": feedback,
        "updated_item": response_item,
        "item_found": updated_item is not None,
    }


def count_wechat_candidates() -> int:
    message_info = read_json(DATA_DIR / "message_info.json", {})
    total = 0
    for account_data in message_info.values():
        blogs = account_data.get("blogs", []) if isinstance(account_data, dict) else []
        total += sum(1 for blog in blogs if isinstance(blog, dict) and not blog.get("is_deleted"))
    return total


def get_content_loop_overview() -> dict[str, Any]:
    items = read_jsonl(CONTENT_ITEMS_FILE)
    feedback_events = read_jsonl(FEEDBACK_EVENTS_FILE)
    source_configs = load_external_source_configs(allow_example=True)
    source_types = Counter(str(item.get("source_type") or "unknown") for item in items)
    human_decisions = Counter(str(item.get("human_decision") or "candidate") for item in items)
    tag_counts = Counter(tag for item in items for tag in item.get("tags", []) if tag)
    auto_tag_counts = Counter(tag for item in items for tag in item.get("auto_tags", []) if tag)
    tagged_items = sum(1 for item in items if item.get("tags"))
    ai_summaries = sum(1 for item in items if item.get("ai_summary"))
    ai_tagged = sum(1 for item in items if item.get("ai_tags"))

    last_update = ""
    if CONTENT_ITEMS_FILE.exists():
        last_update = datetime.fromtimestamp(CONTENT_ITEMS_FILE.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

    sources = source_configs["sources"]
    return {
        "content_items": len(items),
        "feedback_events": len(feedback_events),
        "wechat_candidates": count_wechat_candidates(),
        "external_sources": len(sources),
        "enabled_external_sources": sum(1 for source in sources if source.get("enabled")),
        "source_types": dict(source_types),
        "human_decisions": dict(human_decisions),
        "tagged_items": tagged_items,
        "ai_summaries": ai_summaries,
        "ai_tagged": ai_tagged,
        "tag_counts": dict(tag_counts.most_common()),
        "auto_tag_counts": dict(auto_tag_counts.most_common()),
        "content_items_file": str(CONTENT_ITEMS_FILE),
        "feedback_events_file": str(FEEDBACK_EVENTS_FILE),
        "source_config_file": source_configs["path"],
        "source_config_is_example": bool(source_configs["using_example"]),
        "last_content_pool_update": last_update,
    }
