from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from src.content_loop.feedback_projection import apply_feedback_projection
from src.content_loop.store import CONTENT_ITEMS_FILE, FEEDBACK_PROJECTION_FILE, read_jsonl

DEFAULT_EXPORT_ROOT = Path(__file__).parent.parent.parent / "data" / "llm_wiki" / "wechat_oa"
KNOWLEDGE_INDEX_DIR = Path(__file__).parent.parent.parent / "data" / "knowledge_index"
CARDS_INDEX_FILE = KNOWLEDGE_INDEX_DIR / "cards.jsonl"
TOPICS_INDEX_FILE = KNOWLEDGE_INDEX_DIR / "topics.jsonl"
KNOWLEDGE_STATUS_APPROVED = "approved"
KNOWLEDGE_STATUS_APPLIED = "applied"
GENERATION_READY_KNOWLEDGE_STATUSES = {KNOWLEDGE_STATUS_APPROVED, KNOWLEDGE_STATUS_APPLIED}


def _knowledge_status(value: Any) -> str:
    return str(value or "").strip()


def _is_applied_knowledge_status(value: Any) -> bool:
    return _knowledge_status(value) == KNOWLEDGE_STATUS_APPLIED


@dataclass
class LLMWikiExportResult:
    export_root: str
    raw_sources_dir: str
    exported: int
    skipped: int
    accounts: int


@dataclass
class KnowledgeCandidatesResult:
    export_root: str
    candidates: int
    entities: int
    concepts: int
    synthesis: int
    cards_index_file: str
    topics_index_file: str
    sample_titles: list[str]
    candidate_card_ids: list[str]
    candidate_topic_ids: list[str]
    source_run_id: str = ""
    source_task_id: str = ""
    source_packet_id: str = ""


@dataclass
class TopicSynthesisCandidatesResult:
    export_root: str
    synthesis: int
    topics_index_file: str
    sample_titles: list[str]
    candidate_topic_ids: list[str]
    source_run_id: str = ""
    source_task_id: str = ""
    source_packet_id: str = ""


def _is_locked_knowledge_status(value: Any) -> bool:
    return _knowledge_status(value) in {KNOWLEDGE_STATUS_APPROVED, KNOWLEDGE_STATUS_APPLIED}


def _candidate_status(existing_row: dict[str, Any] | None) -> str:
    existing_status = _knowledge_status(existing_row.get("status")) if isinstance(existing_row, dict) else ""
    return existing_status if _is_locked_knowledge_status(existing_status) else "candidate"


def _load_projected_items(*, projected_action: str | None = None, item_ids: list[str] | None = None) -> list[dict[str, Any]]:
    rows = apply_feedback_projection(read_jsonl(CONTENT_ITEMS_FILE), projection_path=FEEDBACK_PROJECTION_FILE)
    selected = [row for row in rows if str(row.get("human_decision") or "candidate") in {"adopted", "dig_deeper", "rewrite"}]
    selected_ids = {str(item_id) for item_id in (item_ids or []) if str(item_id).strip()}
    if selected_ids:
        selected = [row for row in selected if str(row.get("id") or "") in selected_ids]
    if projected_action:
        selected = [row for row in selected if str(row.get("projected_action") or "") == projected_action]
    return selected


def _yaml_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dedupe_jsonable_list(values: list[Any]) -> list[Any]:
    deduped: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


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


def _safe_filename(text: str, fallback: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", text).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = fallback
    return name[:80].rstrip(". ")


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


def _detail_to_markdown(detail: Any, digest: str) -> str:
    if isinstance(detail, list):
        parts = [str(part).strip() for part in detail if str(part).strip()]
    elif isinstance(detail, str) and detail.strip():
        parts = [detail.strip()]
    else:
        parts = [digest.strip()] if digest.strip() else []

    if not parts:
        return "_正文缓存为空，等待下一次采集补全。_"
    return "\n\n".join(parts)


def _upsert_rows(
    existing_rows: list[dict[str, Any]],
    new_rows: list[dict[str, Any]],
    *,
    key_getter: Callable[[dict[str, Any]], str],
) -> list[dict[str, Any]]:
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


def _ensure_wiki_dirs(root: Path) -> None:
    (root / "raw" / "sources" / "wechat").mkdir(parents=True, exist_ok=True)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "entities").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "concepts").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "synthesis").mkdir(parents=True, exist_ok=True)
    (root / "wiki" / "queries").mkdir(parents=True, exist_ok=True)
    (root / ".llm-wiki").mkdir(parents=True, exist_ok=True)


def _write_project_scaffold(root: Path) -> None:
    _ensure_wiki_dirs(root)

    purpose = root / "purpose.md"
    if not purpose.exists():
        purpose.write_text(
            "\n".join([
                "# 公众号知识库目标",
                "",
                "把持续采集的内容沉淀为可检索、可关联、可追溯的个人知识库。",
                "",
                "重点关注：主题、观点、方法、实体、长期趋势。",
                "",
            ]),
            encoding="utf-8",
        )

    schema = root / "schema.md"
    if not schema.exists():
        schema.write_text(
            "\n".join([
                "# Wiki Schema",
                "",
                "- `wiki/sources/`: 单篇来源摘要。",
                "- `wiki/entities/`: 人物、公司、产品、项目。",
                "- `wiki/concepts/`: 概念、方法、主题。",
                "- `wiki/synthesis/`: 跨来源综合页。",
                "- `wiki/queries/`: 常用查询与提问模板。",
                "",
                "所有页面必须保留 `sources` 字段，指向原始来源。",
                "",
            ]),
            encoding="utf-8",
        )

    index = root / "wiki" / "index.md"
    if not index.exists():
        index.write_text("# Index\n\n- [[overview]]\n- [[queries/content-questions]]\n", encoding="utf-8")

    overview = root / "wiki" / "overview.md"
    if not overview.exists():
        overview.write_text(
            "---\ntype: synthesis\ntitle: 知识库概览\ntags: []\nrelated: []\nsources: []\n---\n\n# 知识库概览\n\n等待摄入后生成。\n",
            encoding="utf-8",
        )

    log = root / "wiki" / "log.md"
    if not log.exists():
        log.write_text("# Log\n", encoding="utf-8")

    query = root / "wiki" / "queries" / "content-questions.md"
    if not query.exists():
        query.write_text(
            "# 内容查询模板\n\n- 哪些主题最近被反复提及？\n- 哪些知识卡片缺少原始来源？\n- 某个主题当前有哪些综合页、实体页、概念页？\n",
            encoding="utf-8",
        )


def _refresh_wiki_navigation(root: Path, cards: list[dict[str, Any]], topics: list[dict[str, Any]]) -> None:
    entity_links = sorted({f"- [[{Path(str(card.get('wiki_path') or '')).stem}]]" for card in cards if str(card.get('kind') or '') == 'entity' and _is_applied_knowledge_status(card.get('status'))})
    concept_links = sorted({f"- [[{Path(str(card.get('wiki_path') or '')).stem}]]" for card in cards if str(card.get('kind') or '') == 'concept' and _is_applied_knowledge_status(card.get('status'))})
    topic_links = sorted({f"- [[{Path(str(topic.get('wiki_path') or '')).stem}]]" for topic in topics if _is_applied_knowledge_status(topic.get('status'))})

    index_lines = [
        "# Index",
        "",
        "- [[overview]]",
        "- [[queries/content-questions]]",
        "",
        "## Entities",
        *entity_links,
        "",
        "## Concepts",
        *concept_links,
        "",
        "## Synthesis",
        *topic_links,
        "",
    ]
    (root / "wiki" / "index.md").write_text("\n".join(index_lines), encoding="utf-8")

    overview_lines = [
        "---",
        "type: synthesis",
        f"title: {_yaml_value('知识库概览')}",
        "tags: []",
        "related: []",
        "sources: []",
        "---",
        "",
        "# 知识库概览",
        "",
        f"- 实体页：{len(entity_links)}",
        f"- 概念页：{len(concept_links)}",
        f"- 主题综合页：{len(topic_links)}",
        "",
        "## 最近可用入口",
        "",
        *(entity_links[:5] or ["- 暂无实体页"]),
        "",
        *(concept_links[:5] or ["- 暂无概念页"]),
        "",
        *(topic_links[:5] or ["- 暂无综合页"]),
        "",
    ]
    (root / "wiki" / "overview.md").write_text("\n".join(overview_lines), encoding="utf-8")


def _article_markdown(account: str, article: dict[str, Any], detail: Any) -> str:
    title = str(article.get("title") or "未命名文章").strip()
    digest = str(article.get("digest") or "").strip()
    tags = article.get("tags") if isinstance(article.get("tags"), list) else []
    body = _detail_to_markdown(detail, digest)

    frontmatter = [
        "---",
        "type: source",
        "source_type: wechat_article",
        f"title: {_yaml_value(title)}",
        f"account: {_yaml_value(account)}",
        f"article_id: {_yaml_value(article.get('id') or '')}",
        f"url: {_yaml_value(article.get('link') or '')}",
        f"published_at: {_yaml_value(article.get('create_time') or '')}",
        f"digest: {_yaml_value(digest)}",
        f"tags: {_yaml_value(tags)}",
        "origin: wechat-official-account",
        "sources: []",
        "---",
        "",
    ]
    meta = [
        f"# {title}",
        "",
        f"- 公众号：{account}",
        f"- 发布时间：{article.get('create_time') or ''}",
        f"- 原文链接：{article.get('link') or ''}",
        "",
    ]
    if digest:
        meta.extend(["## 摘要", "", digest, ""])
    meta.extend(["## 正文", "", body, ""])
    return "\n".join(frontmatter + meta)


def export_llm_wiki_sources(export_root: str | Path | None = DEFAULT_EXPORT_ROOT, trace: dict[str, Any] | None = None) -> LLMWikiExportResult:

    from src.utils.data_manager import data_manager

    root = Path(export_root) if export_root is not None else DEFAULT_EXPORT_ROOT
    _write_project_scaffold(root)

    data_manager.reload("name2fakeid")
    data_manager.reload("message_info")
    data_manager.reload("message_detail_text")

    tracked_accounts = set(data_manager.name2fakeid.keys())
    exported = 0
    skipped = 0
    accounts_seen = 0
    raw_root = root / "raw" / "sources" / "wechat"

    for account, account_data in data_manager.message_info.items():
        if tracked_accounts and account not in tracked_accounts:
            continue
        blogs = account_data.get("blogs", []) if isinstance(account_data, dict) else []
        if not blogs:
            continue
        accounts_seen += 1
        account_dir = raw_root / _safe_filename(account, "account")
        account_dir.mkdir(parents=True, exist_ok=True)

        for article in blogs:
            if not isinstance(article, dict) or article.get("is_deleted"):
                skipped += 1
                continue
            article_id = str(article.get("id") or "")
            if not article_id:
                skipped += 1
                continue
            date = str(article.get("create_time") or "unknown").split(" ")[0]
            title = _safe_filename(str(article.get("title") or ""), "untitled")
            suffix = _safe_filename(article_id, "article")[-24:]
            dest = account_dir / f"{date}-{title}-{suffix}.md"
            detail = data_manager.message_detail_text.get(article_id)
            dest.write_text(_article_markdown(account, article, detail), encoding="utf-8")
            exported += 1

    if exported:
        _append_wiki_log(root, f"原始素材导出：exported={exported}, skipped={skipped}, accounts={accounts_seen}", trace=trace)

    return LLMWikiExportResult(
        export_root=str(root),
        raw_sources_dir=str(raw_root),
        exported=exported,
        skipped=skipped,
        accounts=accounts_seen,
    )


def build_knowledge_candidates(*, export_root: str | Path | None = DEFAULT_EXPORT_ROOT, limit: int = 30, projected_action: str | None = None, item_ids: list[str] | None = None, trace: dict[str, Any] | None = None) -> KnowledgeCandidatesResult:
    root = Path(export_root) if export_root is not None else DEFAULT_EXPORT_ROOT
    _write_project_scaffold(root)
    selected = _load_projected_items(projected_action=projected_action, item_ids=item_ids)[: max(0, limit)]

    KNOWLEDGE_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    existing_cards = _read_jsonl(CARDS_INDEX_FILE)
    cards: list[dict[str, Any]] = []
    entities = 0
    concepts = 0

    for item in selected:
        tags = item.get("tags") or []
        sources = item.get("references") or []
        title = str(item.get("title") or "未命名条目")
        summary = str(item.get("ai_summary") or item.get("summary") or item.get("content_preview") or "")
        source_name = str(item.get("source_name") or item.get("source_id") or "")
        item_id = str(item.get("id") or "")
        projected_score = round(float(item.get("projected_score") or item.get("score") or 0.0), 4)
        projection_delta = round(float(item.get("feedback_projection_delta") or 0.0), 4)
        projection_reasons = item.get("feedback_projection_reasons") if isinstance(item.get("feedback_projection_reasons"), list) else []
        projected_action_value = str(item.get("projected_action") or "")
        projected_action_label = str(item.get("projected_action_label") or "")
        projected_action_reason = str(item.get("projected_action_reason") or "")

        card_kind = "entity" if source_name and source_name != title else "concept"
        if card_kind == "entity":
            entities += 1
        else:
            concepts += 1

        slug = _safe_filename(title, "card")
        wiki_dir = root / "wiki" / ("entities" if card_kind == "entity" else "concepts")
        wiki_path = wiki_dir / f"{slug}.md"
        card_id = f"knowledge:{item_id}"
        existing_card = next((row for row in existing_cards if str(row.get("id") or "") == card_id), None)
        if _is_locked_knowledge_status((existing_card or {}).get("status")):
            continue
        card = {
            "id": card_id,
            "kind": card_kind,
            "title": title,
            "summary": summary,
            "tags": tags,
            "sources": sources,
            "source_item_id": item_id,
            "wiki_path": str(wiki_path.relative_to(root)),
            "projected_score": projected_score,
            "feedback_projection_delta": projection_delta,
            "feedback_projection_reasons": projection_reasons,
            "projected_action": projected_action_value,
            "projected_action_label": projected_action_label,
            "projected_action_reason": projected_action_reason,
            **_candidate_trace_fields(trace),
            "status": _candidate_status(existing_card),
        }
        cards.append(card)

    merged_cards = _upsert_rows(existing_cards, cards, key_getter=lambda row: str(row.get("id") or ""))
    _write_jsonl(CARDS_INDEX_FILE, merged_cards)

    sample_titles = [str(item.get("title") or "") for item in selected[:3] if str(item.get("title") or "")]
    candidate_card_ids = [str(card.get("id") or "") for card in cards if str(card.get("id") or "")]
    if cards:
        _append_wiki_log(root, f"知识候选生成：cards={len(cards)}, topics=0, sample_titles={sample_titles[:3]}", trace=trace)

    return KnowledgeCandidatesResult(
        export_root=str(root),
        candidates=len(cards),
        entities=entities,
        concepts=concepts,
        synthesis=0,
        cards_index_file=str(CARDS_INDEX_FILE),
        topics_index_file=str(TOPICS_INDEX_FILE),
        sample_titles=sample_titles,
        candidate_card_ids=candidate_card_ids,
        candidate_topic_ids=[],
        source_run_id=str((trace or {}).get("run_id") or ""),
        source_task_id=str((trace or {}).get("task_id") or ""),
        source_packet_id=str((trace or {}).get("packet_id") or ""),
    )


def build_topic_synthesis_candidates(*, export_root: str | Path | None = DEFAULT_EXPORT_ROOT, limit: int = 30, item_ids: list[str] | None = None, trace: dict[str, Any] | None = None) -> TopicSynthesisCandidatesResult:
    root = Path(export_root) if export_root is not None else DEFAULT_EXPORT_ROOT
    _write_project_scaffold(root)
    selected = _load_projected_items(projected_action="build_topic_synthesis", item_ids=item_ids)[: max(0, limit)]

    KNOWLEDGE_INDEX_DIR.mkdir(parents=True, exist_ok=True)
    existing_topics = _read_jsonl(TOPICS_INDEX_FILE)
    topics_by_id: dict[str, dict[str, Any]] = {}

    for item in selected:
        tags = item.get("tags") or []
        if not tags:
            tags = item.get("ai_tags") or []
        if not tags:
            continue
        sources = item.get("references") or []
        title = str(item.get("title") or "未命名条目")
        summary = str(item.get("ai_summary") or item.get("summary") or item.get("content_preview") or "")
        item_id = str(item.get("id") or "")
        category = str(item.get("ai_category") or "待分类")
        projected_score = round(float(item.get("projected_score") or item.get("score") or 0.0), 4)
        projection_delta = round(float(item.get("feedback_projection_delta") or 0.0), 4)
        projection_reasons = item.get("feedback_projection_reasons") if isinstance(item.get("feedback_projection_reasons"), list) else []
        projected_action_value = str(item.get("projected_action") or "")
        projected_action_label = str(item.get("projected_action_label") or "")
        projected_action_reason = str(item.get("projected_action_reason") or "")
        topic_name = str(tags[0])
        topic_id = f"topic:{_safe_filename(topic_name, 'topic')}"
        existing_topic = next((row for row in existing_topics if str(row.get("id") or "") == topic_id), None)
        if _is_locked_knowledge_status((existing_topic or {}).get("status")):
            continue
        current = topics_by_id.get(topic_id)

        source_item_ids: list[str] = []
        if current and isinstance(current.get("source_item_ids"), list):
            source_item_ids.extend([str(value) for value in current.get("source_item_ids", []) if str(value)])
        source_item_ids.append(item_id)

        merged_sources: list[Any] = []
        if current and isinstance(current.get("sources"), list):
            merged_sources.extend(current.get("sources", []))
        merged_sources.extend(sources)

        merged_reasons: list[Any] = []
        if current and isinstance(current.get("feedback_projection_reasons"), list):
            merged_reasons.extend(current.get("feedback_projection_reasons", []))
        merged_reasons.extend(projection_reasons)

        sample_titles: list[str] = []
        if current and isinstance(current.get("sample_titles"), list):
            sample_titles.extend([str(value) for value in current.get("sample_titles", []) if str(value)])
        sample_titles.append(title)

        top_score = max(projected_score, float(current.get("projected_score") or 0.0)) if current else projected_score
        top_delta = max(projection_delta, float(current.get("feedback_projection_delta") or 0.0)) if current else projection_delta
        combined_summary = summary
        if current and str(current.get("summary") or ""):
            existing_summary = str(current.get("summary") or "")
            combined_summary = existing_summary if len(existing_summary) >= len(summary) else summary

        topics_by_id[topic_id] = {
            "id": topic_id,
            "title": topic_name,
            "category": category,
            "source_item_id": item_id,
            "source_item_ids": list(dict.fromkeys(source_item_ids)),
            "source_title": title,
            "sample_titles": list(dict.fromkeys(sample_titles))[:5],
            "summary": combined_summary,
            "sources": _dedupe_jsonable_list(merged_sources),
            "wiki_path": str((root / 'wiki' / 'synthesis' / f"{_safe_filename(topic_name, 'topic')}.md").relative_to(root)),
            "projected_score": round(top_score, 4),
            "feedback_projection_delta": round(top_delta, 4),
            "feedback_projection_reasons": merged_reasons,
            "projected_action": projected_action_value,
            "projected_action_label": projected_action_label,
            "projected_action_reason": projected_action_reason,
            **_candidate_trace_fields(trace),
            "status": _candidate_status(existing_topic),
        }

    topics = list(topics_by_id.values())
    merged_topics = _upsert_rows(existing_topics, topics, key_getter=lambda row: str(row.get("id") or ""))
    _write_jsonl(TOPICS_INDEX_FILE, merged_topics)

    sample_titles = [str(topic.get("title") or "") for topic in topics[:3] if str(topic.get("title") or "")]
    candidate_topic_ids = [str(topic.get("id") or "") for topic in topics if str(topic.get("id") or "")]
    if topics:
        _append_wiki_log(root, f"主题综合候选生成：topics={len(topics)}, sample_titles={sample_titles[:3]}", trace=trace)

    return TopicSynthesisCandidatesResult(
        export_root=str(root),
        synthesis=len(topics),
        topics_index_file=str(TOPICS_INDEX_FILE),
        sample_titles=sample_titles,
        candidate_topic_ids=candidate_topic_ids,
        source_run_id=str((trace or {}).get("run_id") or ""),
        source_task_id=str((trace or {}).get("task_id") or ""),
        source_packet_id=str((trace or {}).get("packet_id") or ""),
    )



def _wiki_link(path_value: str) -> str:
    return f"[[{Path(path_value).stem}]]"


def _related_topic_links(topics: list[dict[str, Any]], source_item_id: str) -> list[str]:
    links: list[str] = []
    for topic in topics:
        if not _is_applied_knowledge_status(topic.get("status")):
            continue
        source_item_ids = topic.get("source_item_ids") if isinstance(topic.get("source_item_ids"), list) else []
        item_ids = {str(value) for value in source_item_ids if str(value)}
        item_ids.add(str(topic.get("source_item_id") or ""))
        if source_item_id not in item_ids:
            continue
        wiki_path = str(topic.get("wiki_path") or "")
        if wiki_path:
            links.append(_wiki_link(wiki_path))
    return sorted(set(links))


def _related_card_links(cards: list[dict[str, Any]], source_item_ids: list[str], current_wiki_path: str) -> list[str]:
    links: list[str] = []
    source_ids = {str(value) for value in source_item_ids if str(value)}
    for card in cards:
        if not _is_applied_knowledge_status(card.get("status")):
            continue
        card_source_ids = card.get("source_item_ids") if isinstance(card.get("source_item_ids"), list) else []
        item_ids = {str(value) for value in card_source_ids if str(value)}
        item_ids.add(str(card.get("source_item_id") or ""))
        if not item_ids.intersection(source_ids):
            continue
        wiki_path = str(card.get("wiki_path") or "")
        if not wiki_path or wiki_path == current_wiki_path:
            continue
        links.append(_wiki_link(wiki_path))
    return sorted(set(links))


def _append_wiki_log(root: Path, message: str, *, trace: dict[str, Any] | None = None) -> None:
    log_path = root / 'wiki' / 'log.md'
    existing = log_path.read_text(encoding='utf-8') if log_path.exists() else '# Log\n'
    trace_suffix = ""
    if trace:
        trace_parts = []
        run_id = str(trace.get('run_id') or '').strip()
        task_id = str(trace.get('task_id') or '').strip()
        packet_id = str(trace.get('packet_id') or '').strip()
        if run_id:
            trace_parts.append(f"run_id={run_id}")
        if task_id:
            trace_parts.append(f"task_id={task_id}")
        if packet_id:
            trace_parts.append(f"packet_id={packet_id}")
        if trace_parts:
            trace_suffix = ", " + ", ".join(trace_parts)
    existing += f"\n- {message}{trace_suffix}\n"
    log_path.write_text(existing, encoding='utf-8')




def _source_lines(sources: list[Any]) -> list[str]:
    if not sources:
        return ["- 暂无来源"]
    lines: list[str] = []
    for source in sources:
        if isinstance(source, dict):
            url = str(source.get("url") or "")
            if url:
                label = str(source.get("type") or "source")
                lines.append(f"- {label}: {url}")
                continue
            lines.append(f"- {json.dumps(source, ensure_ascii=False, sort_keys=True)}")
            continue
        text = str(source).strip()
        if text:
            lines.append(f"- {text}")
    return lines or ["- 暂无来源"]




def _knowledge_apply_reject_reason(row: dict[str, Any] | None) -> str:
    if not isinstance(row, dict):
        return "未找到对应记录"
    status = _knowledge_status(row.get("status"))
    if not status:
        return "状态缺失"
    if status == KNOWLEDGE_STATUS_APPLIED:
        return "已入库"
    if status == KNOWLEDGE_STATUS_APPROVED:
        return "未命中当前请求范围"
    if status == "candidate":
        return "仍待审批"
    if status == "rejected":
        return "已被拒绝"
    return f"当前状态为 {status}"

def apply_reviewed_knowledge_candidates(*, export_root: str | Path | None = DEFAULT_EXPORT_ROOT, card_ids: list[str] | None = None, topic_ids: list[str] | None = None, trace: dict[str, Any] | None = None) -> dict[str, Any]:
    root = Path(export_root) if export_root is not None else DEFAULT_EXPORT_ROOT
    _write_project_scaffold(root)
    cards = _read_jsonl(CARDS_INDEX_FILE)
    topics = _read_jsonl(TOPICS_INDEX_FILE)
    requested_card_ids_input = [str(card_id).strip() for card_id in (card_ids or []) if str(card_id).strip()]
    requested_topic_ids_input = [str(topic_id).strip() for topic_id in (topic_ids or []) if str(topic_id).strip()]
    selected_card_ids = set(requested_card_ids_input)
    selected_topic_ids = set(requested_topic_ids_input)
    apply_all_cards = not selected_card_ids and not selected_topic_ids
    apply_all_topics = not selected_topic_ids and not selected_card_ids
    written_cards = 0
    written_topics = 0
    selected_cards: list[dict[str, Any]] = []
    selected_topics: list[dict[str, Any]] = []

    requested_card_ids = requested_card_ids_input[:]
    requested_topic_ids = requested_topic_ids_input[:]
    if apply_all_cards:
        requested_card_ids = [str(card.get('id') or '') for card in cards if _knowledge_status(card.get('status')) == KNOWLEDGE_STATUS_APPROVED and str(card.get('id') or '')]
    if apply_all_topics:
        requested_topic_ids = [str(topic.get('id') or '') for topic in topics if _knowledge_status(topic.get('status')) == KNOWLEDGE_STATUS_APPROVED and str(topic.get('id') or '')]

    for card in cards:
        if _knowledge_status(card.get('status')) != KNOWLEDGE_STATUS_APPROVED:
            continue
        if selected_card_ids and str(card.get('id') or '') not in selected_card_ids:
            continue
        if not apply_all_cards and not selected_card_ids:
            continue
        selected_cards.append(card)
        card['status'] = KNOWLEDGE_STATUS_APPLIED
        card.update(_applied_trace_fields(trace))

    for topic in topics:
        if _knowledge_status(topic.get('status')) != KNOWLEDGE_STATUS_APPROVED:
            continue
        if selected_topic_ids and str(topic.get('id') or '') not in selected_topic_ids:
            continue
        if not apply_all_topics and not selected_topic_ids:
            continue
        selected_topics.append(topic)
        topic['status'] = KNOWLEDGE_STATUS_APPLIED
        topic.update(_applied_trace_fields(trace))

    accepted_card_ids = [str(card.get('id') or '') for card in selected_cards if str(card.get('id') or '')]
    accepted_topic_ids = [str(topic.get('id') or '') for topic in selected_topics if str(topic.get('id') or '')]
    accepted_card_id_set = set(accepted_card_ids)
    accepted_topic_id_set = set(accepted_topic_ids)
    rejected_card_ids = [card_id for card_id in requested_card_ids if card_id not in accepted_card_id_set]
    rejected_topic_ids = [topic_id for topic_id in requested_topic_ids if topic_id not in accepted_topic_id_set]
    card_by_id = {str(card.get('id') or ''): card for card in cards if str(card.get('id') or '')}
    topic_by_id = {str(topic.get('id') or ''): topic for topic in topics if str(topic.get('id') or '')}
    rejected_card_reasons = {card_id: _knowledge_apply_reject_reason(card_by_id.get(card_id)) for card_id in rejected_card_ids}
    rejected_topic_reasons = {topic_id: _knowledge_apply_reject_reason(topic_by_id.get(topic_id)) for topic_id in rejected_topic_ids}

    for card in selected_cards:
        path = root / str(card.get('wiki_path') or '')
        path.parent.mkdir(parents=True, exist_ok=True)
        related = _related_topic_links(topics, str(card.get('source_item_id') or ''))
        path.write_text(
            "\n".join([
                "---",
                f"type: {card.get('kind')}",
                f"title: {_yaml_value(card.get('title') or '')}",
                f"tags: {_yaml_value(card.get('tags') or [])}",
                f"related: {_yaml_value(related)}",
                f"sources: {_yaml_value(card.get('sources') or [])}",
                "---",
                "",
                f"# {card.get('title') or ''}",
                "",
                str(card.get('summary') or ''),
                "",
                f"- 来源数：{len(card.get('sources') or [])}",
                *([""] + ["## 相关主题", "", *related, ""] if related else []),
                "## 来源",
                "",
                *_source_lines(card.get('sources') or []),
                "",
            ]),
            encoding='utf-8',
        )
        written_cards += 1

    for topic in selected_topics:
        path = root / str(topic.get('wiki_path') or '')
        path.parent.mkdir(parents=True, exist_ok=True)
        topic_source_item_ids = topic.get('source_item_ids') if isinstance(topic.get('source_item_ids'), list) else []
        related = _related_card_links(
            cards,
            [str(value) for value in topic_source_item_ids if str(value)] or [str(topic.get('source_item_id') or '')],
            str(topic.get('wiki_path') or ''),
        )
        path.write_text(
            "\n".join([
                "---",
                "type: synthesis",
                f"title: {_yaml_value(topic.get('title') or '')}",
                f"related: {_yaml_value(related)}",
                f"sources: {_yaml_value(topic.get('sources') or [])}",
                "---",
                "",
                f"# {topic.get('title') or ''}",
                "",
                str(topic.get('summary') or ''),
                "",
                f"- 来源数：{len(topic.get('sources') or [])}",
                *([""] + ["## 相关卡片", "", *related, ""] if related else []),
                "## 来源",
                "",
                *_source_lines(topic.get('sources') or []),
                "",
            ]),
            encoding='utf-8',
        )
        written_topics += 1

    _write_jsonl(CARDS_INDEX_FILE, cards)
    _write_jsonl(TOPICS_INDEX_FILE, topics)

    if written_cards or written_topics or rejected_card_ids or rejected_topic_ids:
        card_titles = [str(card.get('title') or '') for card in cards if _is_applied_knowledge_status(card.get('status')) and (not selected_card_ids or str(card.get('id') or '') in selected_card_ids)][:3]
        topic_titles = [str(topic.get('title') or '') for topic in topics if _is_applied_knowledge_status(topic.get('status')) and (not selected_topic_ids or str(topic.get('id') or '') in selected_topic_ids)][:3]
        _append_wiki_log(
            root,
            f"知识入库：cards={written_cards}, topics={written_topics}, rejected_cards={rejected_card_ids}, rejected_topics={rejected_topic_ids}, rejected_card_reasons={rejected_card_reasons}, rejected_topic_reasons={rejected_topic_reasons}, card_titles={card_titles}, topic_titles={topic_titles}",
            trace=trace,
        )

    _refresh_wiki_navigation(root, cards, topics)

    return {
        'export_root': str(root),
        'written_cards': written_cards,
        'written_topics': written_topics,
        'cards_index_file': str(CARDS_INDEX_FILE),
        'topics_index_file': str(TOPICS_INDEX_FILE),
        'requested_ids': {
            'cards': requested_card_ids,
            'topics': requested_topic_ids,
        },
        'accepted_ids': {
            'cards': accepted_card_ids,
            'topics': accepted_topic_ids,
        },
        'rejected_ids': {
            'cards': rejected_card_ids,
            'topics': rejected_topic_ids,
        },
        'rejected_reasons': {
            'cards': rejected_card_reasons,
            'topics': rejected_topic_reasons,
        },
    }


def list_knowledge_candidates() -> dict[str, Any]:
    cards = _read_jsonl(CARDS_INDEX_FILE)
    topics = _read_jsonl(TOPICS_INDEX_FILE)
    return {
        'cards_index_file': str(CARDS_INDEX_FILE),
        'topics_index_file': str(TOPICS_INDEX_FILE),
        'cards': cards,
        'topics': topics,
    }


def update_knowledge_candidate_status(packet_status: str, *, card_ids: list[str] | None = None, topic_ids: list[str] | None = None) -> dict[str, Any]:
    cards = _read_jsonl(CARDS_INDEX_FILE)
    topics = _read_jsonl(TOPICS_INDEX_FILE)
    target_status = KNOWLEDGE_STATUS_APPROVED if packet_status in {'approved', 'edited'} else 'rejected'
    selected_card_ids = {str(card_id) for card_id in (card_ids or []) if str(card_id).strip()}
    selected_topic_ids = {str(topic_id) for topic_id in (topic_ids or []) if str(topic_id).strip()}
    update_all_cards = not selected_card_ids and not selected_topic_ids
    update_all_topics = not selected_topic_ids and not selected_card_ids
    updated_cards = 0
    updated_topics = 0
    for row in cards:
        if selected_card_ids and str(row.get('id') or '') not in selected_card_ids:
            continue
        if not selected_card_ids and not update_all_cards:
            continue
        if _knowledge_status(row.get('status')) != 'candidate':
            continue
        row['status'] = target_status
        updated_cards += 1
    for row in topics:
        if selected_topic_ids and str(row.get('id') or '') not in selected_topic_ids:
            continue
        if not selected_topic_ids and not update_all_topics:
            continue
        if _knowledge_status(row.get('status')) != 'candidate':
            continue
        row['status'] = target_status
        updated_topics += 1
    _write_jsonl(CARDS_INDEX_FILE, cards)
    _write_jsonl(TOPICS_INDEX_FILE, topics)
    return {
        'cards': updated_cards,
        'topics': updated_topics,
        'status': target_status,
    }
