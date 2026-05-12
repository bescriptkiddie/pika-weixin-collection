from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .store import (
    CONTENT_ITEMS_FILE,
    DATA_DIR,
    read_json,
    read_jsonl,
    summary_from_text,
    write_jsonl,
)

TAG_TAXONOMY_FILE = DATA_DIR / "tag_taxonomy.json"
TAG_TAXONOMY_EXAMPLE_FILE = DATA_DIR / "tag_taxonomy.example.json"
TOPIC_TAGS_FILE = DATA_DIR / "topic_tags.jsonl"

DEFAULT_TAXONOMY = {
    "version": 1,
    "max_tags_per_item": 5,
    "min_score": 2,
    "tags": [],
}

DECISION_SCORE_DELTA = {
    "adopted": 0.25,
    "dig_deeper": 0.2,
    "rewrite": 0.1,
    "candidate": 0.0,
    "not_relevant": -0.2,
    "rejected": -0.35,
}

SOURCE_TYPE_TAGS = {
    "github_repo": ["开发工程"],
    "wechat_article": [],
}


@dataclass
class TaggingResult:
    content_items_file: str
    topic_tags_file: str
    taxonomy_file: str
    using_example_taxonomy: bool
    total: int
    tagged: int
    untagged: int
    updated: int
    tag_counts: dict[str, int]


def _load_taxonomy(path: str | Path | None = None, *, allow_example: bool = True) -> dict[str, Any]:
    taxonomy_path = Path(path) if path else TAG_TAXONOMY_FILE
    using_example = False
    if not taxonomy_path.exists() and allow_example and TAG_TAXONOMY_EXAMPLE_FILE.exists():
        taxonomy_path = TAG_TAXONOMY_EXAMPLE_FILE
        using_example = True

    raw = read_json(taxonomy_path, DEFAULT_TAXONOMY) if taxonomy_path.exists() else DEFAULT_TAXONOMY
    tags = raw.get("tags") if isinstance(raw, dict) else []
    if not isinstance(tags, list):
        tags = []

    normalized_tags = []
    for tag in tags:
        if not isinstance(tag, dict) or not tag.get("name"):
            continue
        keywords = tag.get("keywords") if isinstance(tag.get("keywords"), list) else []
        normalized_tags.append(
            {
                "name": str(tag["name"]),
                "description": str(tag.get("description") or ""),
                "keywords": [str(keyword) for keyword in keywords if str(keyword).strip()],
            }
        )

    return {
        "path": str(taxonomy_path),
        "using_example": using_example,
        "version": raw.get("version", 1) if isinstance(raw, dict) else 1,
        "max_tags_per_item": int(raw.get("max_tags_per_item", 5)) if isinstance(raw, dict) else 5,
        "min_score": int(raw.get("min_score", 2)) if isinstance(raw, dict) else 2,
        "tags": normalized_tags,
    }


def _text_for_tagging(item: dict[str, Any]) -> str:
    fields = [
        item.get("title"),
        item.get("summary"),
        item.get("content_preview"),
        item.get("content_markdown"),
        item.get("source_name"),
        item.get("source_id"),
    ]
    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        fields.extend([metadata.get("human_reason"), metadata.get("path"), metadata.get("account")])
    notes = item.get("feedback_notes")
    if isinstance(notes, list):
        fields.extend(notes)
    return "\n".join(str(field) for field in fields if field)


def _keyword_score(text: str, keyword: str) -> int:
    keyword = keyword.strip()
    if not keyword:
        return 0
    if re.search(r"[\u4e00-\u9fff]", keyword):
        return text.count(keyword.lower()) * 2
    pattern = re.compile(rf"(?<![a-z0-9_]){re.escape(keyword.lower())}(?![a-z0-9_])", re.I)
    return len(pattern.findall(text)) * 2


def classify_item(item: dict[str, Any], taxonomy: dict[str, Any]) -> dict[str, Any]:
    text = _text_for_tagging(item).lower()
    scored: list[tuple[str, int, list[str]]] = []

    for tag in taxonomy["tags"]:
        matched_keywords: list[str] = []
        score = 0
        for keyword in tag["keywords"]:
            keyword_score = _keyword_score(text, keyword)
            if keyword_score:
                score += keyword_score
                matched_keywords.append(keyword)
        if score >= taxonomy["min_score"]:
            scored.append((tag["name"], score, matched_keywords[:8]))

    for source_tag in SOURCE_TYPE_TAGS.get(str(item.get("source_type") or ""), []):
        if not any(tag == source_tag for tag, _, _ in scored):
            scored.append((source_tag, taxonomy["min_score"], ["source_type"]))

    scored.sort(key=lambda row: (-row[1], row[0]))
    picked = scored[: max(1, taxonomy["max_tags_per_item"])]
    if not picked:
        picked = [("待分类", 0, [])]
    auto_tags = [tag for tag, _, _ in picked]
    existing_tags = item.get("tags") if isinstance(item.get("tags"), list) else []

    merged_tags: list[str] = []
    for tag in [*existing_tags, *auto_tags]:
        if tag and tag not in merged_tags:
            merged_tags.append(str(tag))

    decision = str(item.get("human_decision") or "candidate")
    base_score = float(item.get("score") or 0)
    tag_score = sum(score for _, score, _ in picked)
    adjusted_score = round(base_score + min(tag_score / 50, 0.4) + DECISION_SCORE_DELTA.get(decision, 0.0), 4)

    return {
        "tags": merged_tags,
        "auto_tags": auto_tags,
        "tag_scores": {tag: score for tag, score, _ in picked},
        "tag_evidence": {tag: keywords for tag, _, keywords in picked},
        "score": adjusted_score,
    }


def apply_tags_to_content_items(
    *,
    content_items_path: str | Path = CONTENT_ITEMS_FILE,
    taxonomy_path: str | Path | None = None,
    topic_tags_path: str | Path = TOPIC_TAGS_FILE,
) -> TaggingResult:
    content_path = Path(content_items_path)
    taxonomy = _load_taxonomy(taxonomy_path, allow_example=True)
    rows = read_jsonl(content_path)
    updated = 0
    topic_rows: list[dict[str, Any]] = []

    for item in rows:
        before = json.dumps(
            {
                "tags": item.get("tags"),
                "auto_tags": item.get("auto_tags"),
                "tag_scores": item.get("tag_scores"),
                "score": item.get("score"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        result = classify_item(item, taxonomy)
        item.update(result)
        for tag in result["auto_tags"]:
            topic_rows.append(
                {
                    "item_id": item.get("id"),
                    "tag": tag,
                    "source_type": item.get("source_type"),
                    "source_id": item.get("source_id"),
                    "title": item.get("title"),
                    "score": result["tag_scores"].get(tag, 0),
                    "human_decision": item.get("human_decision") or "candidate",
                }
            )
        after = json.dumps(
            {
                "tags": item.get("tags"),
                "auto_tags": item.get("auto_tags"),
                "tag_scores": item.get("tag_scores"),
                "score": item.get("score"),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if before != after:
            updated += 1

    write_jsonl(content_path, rows)
    write_jsonl(Path(topic_tags_path), topic_rows)

    tag_counts = Counter(tag for item in rows for tag in item.get("tags", []) if tag)
    tagged = sum(1 for item in rows if item.get("tags"))
    return TaggingResult(
        content_items_file=str(content_path),
        topic_tags_file=str(topic_tags_path),
        taxonomy_file=taxonomy["path"],
        using_example_taxonomy=bool(taxonomy["using_example"]),
        total=len(rows),
        tagged=tagged,
        untagged=len(rows) - tagged,
        updated=updated,
        tag_counts=dict(tag_counts.most_common()),
    )


def get_tagging_overview(
    *,
    content_items_path: str | Path = CONTENT_ITEMS_FILE,
    taxonomy_path: str | Path | None = None,
    topic_tags_path: str | Path = TOPIC_TAGS_FILE,
) -> dict[str, Any]:
    taxonomy = _load_taxonomy(taxonomy_path, allow_example=True)
    rows = read_jsonl(Path(content_items_path))
    topic_rows = read_jsonl(Path(topic_tags_path))
    tag_counts = Counter(tag for item in rows for tag in item.get("tags", []) if tag)
    auto_tag_counts = Counter(tag for item in rows for tag in item.get("auto_tags", []) if tag)
    tagged = sum(1 for item in rows if item.get("tags"))

    return {
        "taxonomy_file": taxonomy["path"],
        "using_example_taxonomy": taxonomy["using_example"],
        "taxonomy_tags": taxonomy["tags"],
        "content_items_file": str(content_items_path),
        "topic_tags_file": str(topic_tags_path),
        "total_items": len(rows),
        "tagged_items": tagged,
        "untagged_items": len(rows) - tagged,
        "topic_mentions": len(topic_rows),
        "tag_counts": dict(tag_counts.most_common()),
        "auto_tag_counts": dict(auto_tag_counts.most_common()),
    }


def preview_tags_for_items(limit: int = 20) -> list[dict[str, Any]]:
    rows = read_jsonl(CONTENT_ITEMS_FILE)[: max(0, limit)]
    return [
        {
            "id": row.get("id"),
            "title": row.get("title"),
            "source_name": row.get("source_name"),
            "tags": row.get("tags") or [],
            "auto_tags": row.get("auto_tags") or [],
            "summary": row.get("summary") or summary_from_text(str(row.get("content_markdown") or ""), 120),
        }
        for row in rows
    ]
