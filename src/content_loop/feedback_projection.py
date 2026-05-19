from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from src.content_loop.store import CONTENT_ITEMS_FILE, FEEDBACK_EVENTS_FILE, DATA_DIR, read_jsonl, write_jsonl

FEEDBACK_PROJECTION_FILE = DATA_DIR / "feedback_projection.jsonl"
KNOWLEDGE_INDEX_DIR = DATA_DIR / "knowledge_index"
KNOWLEDGE_CARDS_FILE = KNOWLEDGE_INDEX_DIR / "cards.jsonl"
GENERATION_READY_KNOWLEDGE_STATUSES = {"approved", "applied"}

DECISION_PRIORITY_DELTA = {
    "adopted": 0.3,
    "dig_deeper": 0.25,
    "rewrite": 0.15,
    "candidate": 0.0,
    "not_relevant": -0.25,
    "rejected": -0.4,
}

ACTION_TEMPLATE_HINT = {
    "raise_item_score": "raise_priority",
    "raise_topic_priority": "raise_topic_priority",
    "adjust_generation_template": "adjust_generation_template",
    "lower_item_score": "lower_priority",
}

ITEM_ACTION_BY_DECISION = {
    "adopted": "build_knowledge_candidate",
    "dig_deeper": "build_topic_synthesis",
    "rewrite": "prepare_rewrite_brief",
    "candidate": "keep_observing",
    "not_relevant": "lower_priority",
    "rejected": "drop_from_pipeline",
}

ITEM_ACTION_BY_HINT = {
    "raise_priority": "build_knowledge_candidate",
    "raise_topic_priority": "build_topic_synthesis",
    "adjust_generation_template": "prepare_rewrite_brief",
    "lower_priority": "lower_priority",
}


def _projection_row(scope: str, key: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": scope,
        "key": key,
        **metrics,
    }


def _build_item_projection_action(reasons: list[dict[str, Any]]) -> dict[str, Any]:
    action_reasons = [reason for reason in reasons if str(reason.get("scope") or "") == "action"]
    positive_reasons = [reason for reason in reasons if float(reason.get("priority_delta") or 0.0) > 0]
    negative_reasons = [reason for reason in reasons if float(reason.get("priority_delta") or 0.0) < 0]

    if action_reasons:
        strongest = action_reasons[0]
        hint = str(strongest.get("strategy_hint") or "")
        action = ITEM_ACTION_BY_HINT.get(hint, hint or "keep_observing")
        return {
            "action": action,
            "reason": str(strongest.get("key") or ""),
            "scope": "action",
        }
    if positive_reasons:
        strongest = positive_reasons[0]
        decision = str(strongest.get("dominant_decision") or "candidate")
        return {
            "action": ITEM_ACTION_BY_DECISION.get(decision, "keep_observing"),
            "reason": str(strongest.get("key") or ""),
            "scope": str(strongest.get("scope") or "tag"),
        }
    if negative_reasons:
        strongest = negative_reasons[-1]
        decision = str(strongest.get("dominant_decision") or "candidate")
        return {
            "action": ITEM_ACTION_BY_DECISION.get(decision, "keep_observing"),
            "reason": str(strongest.get("key") or ""),
            "scope": str(strongest.get("scope") or "tag"),
        }
    return {
        "action": "keep_observing",
        "reason": "",
        "scope": "",
    }




def _projection_label(action: str) -> str:
    labels = {
        "build_knowledge_candidate": "进入知识候选",
        "build_topic_synthesis": "进入主题综合",
        "prepare_rewrite_brief": "准备生成写作提纲",
        "keep_observing": "继续观察",
        "lower_priority": "降低优先级",
        "drop_from_pipeline": "移出后续链路",
    }
    return labels.get(action, action)


def _knowledge_card_status_by_item(*, cards_file: str | Path | None = None) -> dict[str, list[str]]:
    target = Path(cards_file) if cards_file is not None else KNOWLEDGE_CARDS_FILE
    mapping: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(target):
        item_id = str(row.get("source_item_id") or "")
        status = str(row.get("status") or "")
        if not item_id or not status:
            continue
        mapping[item_id].append(status)
    return {item_id: list(dict.fromkeys(statuses)) for item_id, statuses in mapping.items()}


def _ready_knowledge_card_ids_by_item(*, cards_file: str | Path | None = None) -> dict[str, list[str]]:
    target = Path(cards_file) if cards_file is not None else KNOWLEDGE_CARDS_FILE
    mapping: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(target):
        if str(row.get("status") or "") not in GENERATION_READY_KNOWLEDGE_STATUSES:
            continue
        item_id = str(row.get("source_item_id") or "")
        card_id = str(row.get("id") or "")
        if not item_id or not card_id:
            continue
        mapping[item_id].append(card_id)
    return {item_id: list(dict.fromkeys(card_ids)) for item_id, card_ids in mapping.items()}
def _candidate_knowledge_card_ids_by_item(*, cards_file: str | Path | None = None) -> dict[str, list[str]]:
    target = Path(cards_file) if cards_file is not None else KNOWLEDGE_CARDS_FILE
    mapping: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(target):
        if str(row.get("status") or "") != "candidate":
            continue
        item_id = str(row.get("source_item_id") or "")
        card_id = str(row.get("id") or "")
        if not item_id or not card_id:
            continue
        mapping[item_id].append(card_id)
    return {item_id: list(dict.fromkeys(card_ids)) for item_id, card_ids in mapping.items()}


def _topic_candidate_status_by_tag(*, topics_file: str | Path | None = None) -> dict[str, list[str]]:
    target = Path(topics_file) if topics_file is not None else DATA_DIR / "knowledge_index" / "topics.jsonl"
    mapping: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(target):
        topic_name = str(row.get("title") or "")
        status = str(row.get("status") or "")
        if not topic_name or not status:
            continue
        mapping[topic_name].append(status)
    return {topic_name: list(dict.fromkeys(statuses)) for topic_name, statuses in mapping.items()}


def _brief_status_by_knowledge_card(*, briefs_file: str | Path | None = None) -> dict[str, list[str]]:
    target = Path(briefs_file) if briefs_file is not None else DATA_DIR / "generation" / "generation_briefs.jsonl"
    mapping: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(target):
        card_id = str(row.get("knowledge_card_id") or "")
        status = str(row.get("status") or "")
        if not card_id or not status:
            continue
        mapping[card_id].append(status)
    return {card_id: list(dict.fromkeys(statuses)) for card_id, statuses in mapping.items()}


def _draft_status_by_brief(*, drafts_file: str | Path | None = None) -> dict[str, list[str]]:
    target = Path(drafts_file) if drafts_file is not None else DATA_DIR / "generation" / "drafts.jsonl"
    mapping: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(target):
        brief_id = str(row.get("brief_id") or "")
        status = str(row.get("status") or "")
        if not brief_id or not status:
            continue
        mapping[brief_id].append(status)
    return {brief_id: list(dict.fromkeys(statuses)) for brief_id, statuses in mapping.items()}


def _geo_status_by_draft(*, geo_file: str | Path | None = None) -> dict[str, list[str]]:
    target = Path(geo_file) if geo_file is not None else DATA_DIR / "generation" / "geo_variants.jsonl"
    mapping: dict[str, list[str]] = defaultdict(list)
    for row in read_jsonl(target):
        draft_id = str(row.get("draft_id") or "")
        status = str(row.get("status") or "")
        if not draft_id or not status:
            continue
        mapping[draft_id].append(status)
    return {draft_id: list(dict.fromkeys(statuses)) for draft_id, statuses in mapping.items()}


def _recommended_action_execution_meta(
    action: str,
    items: list[dict[str, Any]],
    *,
    knowledge_card_ids_by_item: dict[str, list[str]] | None = None,
    knowledge_card_status_by_item: dict[str, list[str]] | None = None,
    candidate_knowledge_card_ids_by_item: dict[str, list[str]] | None = None,
    pending_review_packet_ids_by_card: dict[str, list[str]] | None = None,
    pending_review_packet_ids_by_brief: dict[str, list[str]] | None = None,
    pending_review_packet_ids_by_draft: dict[str, list[str]] | None = None,
    pending_review_packet_ids_by_geo: dict[str, list[str]] | None = None,
    brief_status_by_card: dict[str, list[str]] | None = None,
    draft_status_by_brief: dict[str, list[str]] | None = None,
    geo_status_by_draft: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    item_ids = [str(item.get("id") or "") for item in items if str(item.get("id") or "")]
    sample_titles = [str(item.get("title") or "") for item in items[:3] if str(item.get("title") or "")]
    if action == "build_knowledge_candidate":
        candidate_card_index = candidate_knowledge_card_ids_by_item or {}
        pending_packet_index = pending_review_packet_ids_by_card or {}
        ready_item_ids: list[str] = []
        pending_item_ids: list[str] = []
        applied_item_ids: list[str] = []
        pending_card_ids: list[str] = []
        applied_titles: list[str] = []
        pending_titles: list[str] = []
        ready_titles: list[str] = []
        blocked_reason_by_item: dict[str, str] = {}

        for item in items:
            item_id = str(item.get("id") or "")
            title = str(item.get("title") or "")
            statuses = set((knowledge_card_status_by_item or {}).get(item_id, []))
            candidate_card_ids = [card_id for card_id in candidate_card_index.get(item_id, []) if card_id]
            if candidate_card_ids or "candidate" in statuses:
                pending_item_ids.append(item_id)
                pending_card_ids.extend(candidate_card_ids)
                if item_id:
                    blocked_reason_by_item[item_id] = "待审批知识候选"
                if title:
                    pending_titles.append(title)
                continue
            if statuses.intersection(GENERATION_READY_KNOWLEDGE_STATUSES):
                applied_item_ids.append(item_id)
                if item_id:
                    blocked_reason_by_item[item_id] = "已存在知识沉淀"
                if title:
                    applied_titles.append(title)
                continue
            ready_item_ids.append(item_id)
            if title:
                ready_titles.append(title)

        pending_packet_ids: list[str] = []
        for card_id in pending_card_ids:
            pending_packet_ids.extend(pending_packet_index.get(card_id, []))
        pending_packet_ids = list(dict.fromkeys(packet_id for packet_id in pending_packet_ids if packet_id))
        pending_count = len(pending_item_ids)
        applied_count = len([title for title in applied_titles if title])
        blocked_count = pending_count + applied_count
        if pending_count and applied_count:
            blocked_reason = "部分条目已有待审批知识候选，部分条目已沉淀到知识库。"
        elif pending_count:
            blocked_reason = "当前动作已有待审批知识候选，先在人工闸门中批准后再继续。"
        elif applied_count:
            blocked_reason = "当前动作对应条目已存在知识沉淀，无需重复生成知识候选。"
        else:
            blocked_reason = ""
        return {
            "actionable": bool(ready_item_ids),
            "execution_kind": "build_knowledge_candidates",
            "execution_label": "立即生成知识候选",
            "execution_blocked_reason": blocked_reason,
            "precondition_statuses": ["candidate"],
            "precondition_passed": bool(ready_item_ids),
            "ready_count": len(ready_item_ids),
            "blocked_count": blocked_count,
            "blocked_item_ids": list(dict.fromkeys(pending_item_ids + applied_item_ids)),
            "blocked_reason_by_item": blocked_reason_by_item,
            "blocked_sample_titles": (pending_titles + applied_titles)[:3],
            "pending_approval_label": "待审批知识候选",
            "pending_approval_count": pending_count,
            "pending_approval_item_ids": pending_item_ids,
            "missing_candidate_item_ids": [],
            "pending_approval_card_ids": list(dict.fromkeys(pending_card_ids)),
            "pending_approval_packet_ids": pending_packet_ids,
            "pending_approval_sample_titles": pending_titles[:3],
            "missing_candidate_count": 0,
            "missing_candidate_sample_titles": [],
            "fallback_actionable": False,
            "fallback_execution_kind": "",
            "fallback_execution_label": "",
            "fallback_execution_params": {},
            "execution_params": {
                "projected_action": action,
                "item_ids": ready_item_ids,
            },
        }
    if action == "build_topic_synthesis":
        topic_status_by_tag = _topic_candidate_status_by_tag()
        pending_topic_packets_by_tag = _pending_topic_review_packet_ids_by_tag()
        ready_items: list[dict[str, Any]] = []
        blocked_titles: list[str] = []
        blocked_item_ids: list[str] = []
        pending_titles: list[str] = []
        pending_item_ids: list[str] = []
        applied_titles: list[str] = []
        applied_item_ids: list[str] = []
        missing_tag_item_ids: list[str] = []
        ready_item_ids: list[str] = []
        pending_packet_ids: list[str] = []
        pending_count = 0
        applied_count = 0
        blocked_reason_by_item: dict[str, str] = {}

        for item in items:
            tags = item.get("tags") if isinstance(item.get("tags"), list) else []
            if not tags:
                tags = item.get("ai_tags") if isinstance(item.get("ai_tags"), list) else []
            topic_name = next((str(tag).strip() for tag in tags if str(tag).strip()), "")
            title = str(item.get("title") or "")
            item_id = str(item.get("id") or "")
            if not topic_name:
                if item_id:
                    missing_tag_item_ids.append(item_id)
                    blocked_item_ids.append(item_id)
                    blocked_reason_by_item[item_id] = "缺少主题标签"
                if title:
                    blocked_titles.append(title)
                continue
            statuses = set(topic_status_by_tag.get(topic_name, []))
            if "candidate" in statuses:
                pending_count += 1
                if item_id:
                    pending_item_ids.append(item_id)
                    blocked_item_ids.append(item_id)
                    blocked_reason_by_item[item_id] = "待审批主题综合"
                pending_packet_ids.extend(pending_topic_packets_by_tag.get(topic_name, []))
                if title:
                    pending_titles.append(title)
                continue
            if statuses.intersection({"approved", "applied"}):
                applied_count += 1
                if item_id:
                    applied_item_ids.append(item_id)
                    blocked_item_ids.append(item_id)
                    blocked_reason_by_item[item_id] = "已存在主题沉淀"
                if title:
                    applied_titles.append(title)
                continue
            ready_items.append(item)
            if item_id:
                ready_item_ids.append(item_id)

        blocked_titles = blocked_titles[:3]
        pending_titles = pending_titles[:3]
        applied_titles = applied_titles[:3]
        blocked_count = len(items) - len(ready_items)
        if pending_count and applied_count:
            blocked_reason = "部分条目已有待审批主题综合，部分条目对应主题已入库。"
        elif pending_count:
            blocked_reason = "当前动作已有待审批主题综合，先在人工闸门中批准后再继续。"
        elif applied_count:
            blocked_reason = "当前动作对应主题已存在知识沉淀，无需重复生成主题综合。"
        elif blocked_titles:
            blocked_reason = "存在缺少主题标签的条目，先补标签后再生成主题综合。"
        else:
            blocked_reason = ""
        return {
            "actionable": bool(ready_items),
            "execution_kind": "build_topic_synthesis",
            "execution_label": "立即生成主题综合候选",
            "execution_blocked_reason": blocked_reason,
            "precondition_statuses": ["candidate"],
            "precondition_passed": bool(ready_items),
            "ready_count": len(ready_items),
            "blocked_count": blocked_count,
            "blocked_item_ids": list(dict.fromkeys(blocked_item_ids)),
            "blocked_reason_by_item": blocked_reason_by_item,
            "blocked_sample_titles": (blocked_titles + pending_titles + applied_titles)[:3],
            "pending_approval_label": "待审批主题综合",
            "pending_approval_count": pending_count,
            "pending_approval_item_ids": pending_item_ids,
            "missing_candidate_item_ids": missing_tag_item_ids,
            "pending_approval_card_ids": [],
            "pending_approval_packet_ids": list(dict.fromkeys(packet_id for packet_id in pending_packet_ids if packet_id)),
            "pending_approval_sample_titles": pending_titles,
            "missing_candidate_count": len(missing_tag_item_ids),
            "missing_candidate_sample_titles": blocked_titles,
            "fallback_actionable": bool(missing_tag_item_ids),
            "fallback_execution_kind": "ai_enrich" if missing_tag_item_ids else "",
            "fallback_execution_label": "先补 AI 分类总结" if missing_tag_item_ids else "",
            "fallback_execution_params": {
                "item_ids": missing_tag_item_ids,
            } if missing_tag_item_ids else {},
            "execution_params": {
                "projected_action": action,
                "item_ids": ready_item_ids,
            },
        }
    if action == "prepare_rewrite_brief":
        brief_status_index = brief_status_by_card or {}
        draft_status_index = draft_status_by_brief or {}
        geo_status_index = geo_status_by_draft or {}
        card_index = knowledge_card_ids_by_item or {}
        status_index = knowledge_card_status_by_item or {}
        candidate_card_index = candidate_knowledge_card_ids_by_item or {}
        pending_packet_index = pending_review_packet_ids_by_card or {}
        pending_brief_packet_index = pending_review_packet_ids_by_brief or {}
        pending_draft_packet_index = pending_review_packet_ids_by_draft or {}
        pending_geo_packet_index = pending_review_packet_ids_by_geo or {}

        ready_brief_item_ids: list[str] = []
        ready_brief_card_ids: list[str] = []
        ready_draft_item_ids: list[str] = []
        ready_draft_brief_ids: list[str] = []
        ready_geo_item_ids: list[str] = []
        ready_geo_draft_ids: list[str] = []
        pending_approval_item_ids: list[str] = []
        pending_candidate_item_ids: list[str] = []
        pending_brief_item_ids: list[str] = []
        pending_draft_item_ids: list[str] = []
        pending_geo_item_ids: list[str] = []
        pending_approval_card_ids: list[str] = []
        pending_approval_brief_ids: list[str] = []
        pending_approval_draft_ids: list[str] = []
        missing_candidate_item_ids: list[str] = []
        completed_geo_item_ids: list[str] = []
        completed_geo_titles: list[str] = []
        pending_approval_sample_titles: list[str] = []
        missing_candidate_sample_titles: list[str] = []
        blocked_reason_by_item: dict[str, str] = {}

        for item in items:
            item_id = str(item.get("id") or "")
            if not item_id:
                continue
            title = str(item.get("title") or "")
            candidate_card_ids = [card_id for card_id in candidate_card_index.get(item_id, []) if card_id]
            if candidate_card_ids:
                pending_approval_item_ids.append(item_id)
                pending_candidate_item_ids.append(item_id)
                pending_approval_card_ids.extend(candidate_card_ids)
                blocked_reason_by_item[item_id] = "待审批知识候选"
                if title:
                    pending_approval_sample_titles.append(title)
                continue

            matched_card_ids = [card_id for card_id in card_index.get(item_id, []) if card_id]
            if matched_card_ids:
                candidate_brief_ids: list[str] = []
                approved_brief_ids: list[str] = []
                for card_id in matched_card_ids:
                    brief_id = f"brief:{card_id}"
                    statuses = set(brief_status_index.get(card_id, []))
                    if "candidate" in statuses:
                        candidate_brief_ids.append(brief_id)
                    elif statuses.intersection({"approved", "applied"}):
                        approved_brief_ids.append(brief_id)
                if candidate_brief_ids:
                    pending_approval_item_ids.append(item_id)
                    pending_brief_item_ids.append(item_id)
                    pending_approval_brief_ids.extend(candidate_brief_ids)
                    blocked_reason_by_item[item_id] = "待审批写作提纲"
                    if title:
                        pending_approval_sample_titles.append(title)
                    continue

                if approved_brief_ids:
                    candidate_draft_ids: list[str] = []
                    approved_draft_ids: list[str] = []
                    for brief_id in approved_brief_ids:
                        draft_id = f"draft:{brief_id}"
                        statuses = set(draft_status_index.get(brief_id, []))
                        if "candidate" in statuses:
                            candidate_draft_ids.append(draft_id)
                        elif statuses.intersection({"approved", "applied"}):
                            approved_draft_ids.append(draft_id)
                    if candidate_draft_ids:
                        pending_approval_item_ids.append(item_id)
                        pending_draft_item_ids.append(item_id)
                        pending_approval_draft_ids.extend(candidate_draft_ids)
                        blocked_reason_by_item[item_id] = "待审批草稿"
                        if title:
                            pending_approval_sample_titles.append(title)
                        continue

                    if approved_draft_ids:
                        candidate_geo_draft_ids: list[str] = []
                        completed_geo_draft_ids: list[str] = []
                        for draft_id in approved_draft_ids:
                            statuses = set(geo_status_index.get(draft_id, []))
                            if "candidate" in statuses:
                                candidate_geo_draft_ids.append(draft_id)
                            elif statuses.intersection({"approved", "applied"}):
                                completed_geo_draft_ids.append(draft_id)
                        if candidate_geo_draft_ids:
                            pending_approval_item_ids.append(item_id)
                            pending_geo_item_ids.append(item_id)
                            pending_approval_draft_ids.extend(candidate_geo_draft_ids)
                            blocked_reason_by_item[item_id] = "待审批 GEO"
                            if title:
                                pending_approval_sample_titles.append(title)
                            continue

                        next_geo_draft_ids = [draft_id for draft_id in approved_draft_ids if draft_id not in completed_geo_draft_ids]
                        if next_geo_draft_ids:
                            ready_geo_item_ids.append(item_id)
                            ready_geo_draft_ids.extend(next_geo_draft_ids)
                            continue

                        completed_geo_item_ids.append(item_id)
                        blocked_reason_by_item[item_id] = "已生成 GEO 变体"
                        if title:
                            completed_geo_titles.append(title)
                        continue

                    ready_draft_item_ids.append(item_id)
                    ready_draft_brief_ids.extend(approved_brief_ids)
                    continue

                ready_brief_item_ids.append(item_id)
                ready_brief_card_ids.extend(matched_card_ids)
                continue

            statuses = set(status_index.get(item_id, []))
            if statuses.intersection({"approved", "applied"}):
                blocked_reason_by_item[item_id] = "缺少知识候选"
            missing_candidate_item_ids.append(item_id)
            if title:
                missing_candidate_sample_titles.append(title)

        ready_brief_item_ids = list(dict.fromkeys(ready_brief_item_ids))
        ready_brief_card_ids = list(dict.fromkeys(ready_brief_card_ids))
        ready_draft_item_ids = list(dict.fromkeys(ready_draft_item_ids))
        ready_draft_brief_ids = list(dict.fromkeys(ready_draft_brief_ids))
        ready_geo_item_ids = list(dict.fromkeys(ready_geo_item_ids))
        ready_geo_draft_ids = list(dict.fromkeys(ready_geo_draft_ids))
        pending_approval_card_ids = list(dict.fromkeys(pending_approval_card_ids))
        pending_approval_brief_ids = list(dict.fromkeys(pending_approval_brief_ids))
        pending_approval_draft_ids = list(dict.fromkeys(pending_approval_draft_ids))
        pending_approval_item_ids = list(dict.fromkeys(pending_approval_item_ids))
        missing_candidate_item_ids = list(dict.fromkeys(missing_candidate_item_ids))
        completed_geo_item_ids = list(dict.fromkeys(completed_geo_item_ids))

        pending_approval_packet_ids: list[str] = []
        for card_id in pending_approval_card_ids:
            pending_approval_packet_ids.extend(pending_packet_index.get(card_id, []))
        for brief_id in pending_approval_brief_ids:
            pending_approval_packet_ids.extend(pending_brief_packet_index.get(brief_id, []))
        for draft_id in pending_approval_draft_ids:
            pending_approval_packet_ids.extend(pending_draft_packet_index.get(draft_id, []))
            pending_approval_packet_ids.extend(pending_geo_packet_index.get(draft_id, []))
        pending_approval_packet_ids = list(dict.fromkeys(packet_id for packet_id in pending_approval_packet_ids if packet_id))

        pending_kinds: list[str] = []
        if pending_candidate_item_ids:
            pending_kinds.append("待审批知识候选")
        if pending_brief_item_ids:
            pending_kinds.append("待审批写作提纲")
        if pending_draft_item_ids:
            pending_kinds.append("待审批草稿")
        if pending_geo_item_ids:
            pending_kinds.append("待审批 GEO")
        if len(pending_kinds) == 1:
            pending_label = pending_kinds[0]
        elif len(pending_kinds) > 1:
            pending_label = "待审批生成结果"
        else:
            pending_label = ""

        execution_kind = ""
        execution_label = ""
        execution_params: dict[str, Any] = {"projected_action": action, "item_ids": []}
        precondition_statuses: list[str] = []
        ready_count = 0
        actionable = False
        if ready_geo_draft_ids:
            execution_kind = "build_geo_variants"
            execution_label = "立即生成 GEO 变体"
            execution_params = {
                "projected_action": action,
                "item_ids": ready_geo_item_ids,
                "draft_ids": ready_geo_draft_ids,
            }
            precondition_statuses = ["approved", "applied"]
            ready_count = len(ready_geo_item_ids)
            actionable = True
        elif ready_draft_brief_ids:
            execution_kind = "build_generation_draft"
            execution_label = "立即生成草稿"
            execution_params = {
                "projected_action": action,
                "item_ids": ready_draft_item_ids,
                "brief_ids": ready_draft_brief_ids,
            }
            precondition_statuses = ["approved", "applied"]
            ready_count = len(ready_draft_item_ids)
            actionable = True
        elif ready_brief_card_ids:
            execution_kind = "build_generation_briefs"
            execution_label = "立即生成写作提纲"
            execution_params = {
                "projected_action": action,
                "item_ids": ready_brief_item_ids,
                "knowledge_card_ids": ready_brief_card_ids,
            }
            precondition_statuses = ["approved", "applied"]
            ready_count = len(ready_brief_item_ids)
            actionable = True

        pending_approval_count = len(pending_approval_item_ids)
        missing_candidate_count = len(missing_candidate_item_ids)
        blocked_count = pending_approval_count + missing_candidate_count + len(completed_geo_item_ids)
        blocked_sample_titles = (pending_approval_sample_titles + missing_candidate_sample_titles + completed_geo_titles)[:3]

        if not actionable:
            if pending_geo_item_ids:
                execution_kind = "build_geo_variants"
                execution_label = "立即生成 GEO 变体"
                precondition_statuses = ["approved", "applied"]
                execution_params = {
                    "projected_action": action,
                    "item_ids": [],
                    "draft_ids": [],
                }
            elif pending_draft_item_ids:
                execution_kind = "build_generation_draft"
                execution_label = "立即生成草稿"
                precondition_statuses = ["approved", "applied"]
                execution_params = {
                    "projected_action": action,
                    "item_ids": [],
                    "brief_ids": [],
                }
            elif pending_brief_item_ids or ready_brief_card_ids or completed_geo_item_ids:
                execution_kind = "build_generation_briefs"
                execution_label = "立即生成写作提纲"
                precondition_statuses = ["approved", "applied"]
                execution_params = {
                    "projected_action": action,
                    "item_ids": [],
                    "knowledge_card_ids": [],
                }
            elif pending_candidate_item_ids or missing_candidate_item_ids:
                execution_kind = "build_generation_briefs"
                execution_label = "立即生成写作提纲"
                precondition_statuses = ["approved", "applied"]
                execution_params = {
                    "projected_action": action,
                    "item_ids": [],
                    "knowledge_card_ids": [],
                }

        if not actionable:
            if pending_approval_count and missing_candidate_count:
                blocked_reason = f"部分条目已有{pending_label}，其余条目还未生成知识候选。"
            elif pending_approval_count and completed_geo_titles:
                blocked_reason = f"部分条目已有{pending_label}，其余条目已生成 GEO 变体。"
            elif missing_candidate_count and completed_geo_titles:
                blocked_reason = "部分条目缺少知识候选，其余条目已生成 GEO 变体。"
            elif pending_approval_count:
                blocked_reason = f"当前动作已有{pending_label}，先在人工闸门中批准后再继续。"
            elif completed_geo_titles:
                blocked_reason = "当前动作对应条目已生成 GEO 变体，无需重复生成。"
            else:
                blocked_reason = "当前动作缺少可用知识卡片，先生成并批准知识候选。"
        else:
            if pending_approval_count and missing_candidate_count:
                blocked_reason = f"其余条目仍有{pending_label}和待生成的知识候选。"
            elif pending_approval_count and completed_geo_titles:
                blocked_reason = f"其余条目仍有{pending_label}，且部分条目已生成 GEO 变体。"
            elif missing_candidate_count and completed_geo_titles:
                blocked_reason = "其余条目仍需先生成知识候选，且部分条目已生成 GEO 变体。"
            elif pending_approval_count:
                blocked_reason = f"其余条目仍有{pending_label}。"
            elif missing_candidate_count:
                blocked_reason = "其余条目仍需先生成知识候选。"
            elif completed_geo_titles:
                blocked_reason = "部分条目已生成 GEO 变体。"
            else:
                blocked_reason = ""

        fallback_actionable = bool(missing_candidate_item_ids)
        return {
            "actionable": actionable,
            "execution_kind": execution_kind,
            "execution_label": execution_label,
            "execution_blocked_reason": blocked_reason,
            "precondition_statuses": precondition_statuses,
            "precondition_passed": actionable,
            "ready_count": ready_count,
            "blocked_count": blocked_count,
            "blocked_item_ids": list(dict.fromkeys(pending_approval_item_ids + missing_candidate_item_ids + completed_geo_item_ids)),
            "blocked_reason_by_item": blocked_reason_by_item,
            "blocked_sample_titles": blocked_sample_titles,
            "pending_approval_label": pending_label,
            "pending_approval_count": pending_approval_count,
            "pending_approval_item_ids": pending_approval_item_ids,
            "missing_candidate_item_ids": missing_candidate_item_ids,
            "pending_approval_card_ids": pending_approval_card_ids,
            "pending_approval_packet_ids": pending_approval_packet_ids,
            "pending_approval_sample_titles": pending_approval_sample_titles[:3],
            "missing_candidate_count": missing_candidate_count,
            "missing_candidate_sample_titles": missing_candidate_sample_titles[:3],
            "fallback_actionable": fallback_actionable,
            "fallback_execution_kind": "build_knowledge_candidates" if fallback_actionable else "",
            "fallback_execution_label": "先生成知识候选" if fallback_actionable else "",
            "fallback_execution_params": {
                "projected_action": "prepare_rewrite_brief",
                "item_ids": missing_candidate_item_ids,
            } if fallback_actionable else {},
            "execution_params": execution_params,
        }
    return {
        "actionable": False,
        "execution_kind": "",
        "execution_label": "",
        "execution_blocked_reason": "当前动作仅供观察，不进入自动执行。",
        "precondition_statuses": [],
        "precondition_passed": False,
        "ready_count": 0,
        "blocked_count": len(item_ids),
        "blocked_item_ids": item_ids,
        "blocked_reason_by_item": {},
        "blocked_sample_titles": sample_titles,
        "pending_approval_label": "",
        "pending_approval_count": 0,
        "pending_approval_item_ids": [],
        "missing_candidate_item_ids": [],
        "pending_approval_card_ids": [],
        "pending_approval_packet_ids": [],
        "pending_approval_sample_titles": [],
        "missing_candidate_count": 0,
        "missing_candidate_sample_titles": [],
        "fallback_actionable": False,
        "fallback_execution_kind": "",
        "fallback_execution_label": "",
        "fallback_execution_params": {},
        "execution_params": {},
    }


def _pending_knowledge_review_packet_ids_by_card(*, runs_dir: str | Path | None = None) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    root = Path(runs_dir) if runs_dir is not None else DATA_DIR / "runs"
    if not root.exists():
        return {}
    for review_file in root.glob("*/review_packets.json"):
        for row in read_jsonl(review_file):
            if str(row.get("kind") or "") != "knowledge_candidates_review":
                continue
            if str(row.get("status") or "open") != "open":
                continue
            payload = row.get("candidate_payload") if isinstance(row.get("candidate_payload"), dict) else {}
            card_ids = payload.get("candidate_card_ids") if isinstance(payload.get("candidate_card_ids"), list) else []
            packet_id = str(row.get("packet_id") or "")
            if not packet_id:
                continue
            for card_id in card_ids:
                card_text = str(card_id or "")
                if card_text:
                    mapping[card_text].append(packet_id)
    return {card_id: list(dict.fromkeys(packet_ids)) for card_id, packet_ids in mapping.items()}


def _pending_brief_review_packet_ids_by_brief(*, runs_dir: str | Path | None = None) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    root = Path(runs_dir) if runs_dir is not None else DATA_DIR / "runs"
    if not root.exists():
        return {}
    for review_file in root.glob("*/review_packets.json"):
        for row in read_jsonl(review_file):
            if str(row.get("kind") or "") != "generation_briefs_review":
                continue
            if str(row.get("status") or "open") != "open":
                continue
            payload = row.get("candidate_payload") if isinstance(row.get("candidate_payload"), dict) else {}
            brief_ids = payload.get("brief_ids") if isinstance(payload.get("brief_ids"), list) else []
            packet_id = str(row.get("packet_id") or "")
            if not packet_id:
                continue
            for brief_id in brief_ids:
                brief_text = str(brief_id or "")
                if brief_text:
                    mapping[brief_text].append(packet_id)
    return {brief_id: list(dict.fromkeys(packet_ids)) for brief_id, packet_ids in mapping.items()}


def _pending_draft_review_packet_ids_by_draft(*, runs_dir: str | Path | None = None) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    root = Path(runs_dir) if runs_dir is not None else DATA_DIR / "runs"
    if not root.exists():
        return {}
    for review_file in root.glob("*/review_packets.json"):
        for row in read_jsonl(review_file):
            if str(row.get("kind") or "") != "draft_review":
                continue
            if str(row.get("status") or "open") != "open":
                continue
            payload = row.get("candidate_payload") if isinstance(row.get("candidate_payload"), dict) else {}
            draft_id = str(payload.get("draft_id") or "")
            packet_id = str(row.get("packet_id") or "")
            if draft_id and packet_id:
                mapping[draft_id].append(packet_id)
    return {draft_id: list(dict.fromkeys(packet_ids)) for draft_id, packet_ids in mapping.items()}


def _pending_geo_review_packet_ids_by_draft(*, runs_dir: str | Path | None = None) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    root = Path(runs_dir) if runs_dir is not None else DATA_DIR / "runs"
    if not root.exists():
        return {}
    for review_file in root.glob("*/review_packets.json"):
        for row in read_jsonl(review_file):
            if str(row.get("kind") or "") != "geo_review":
                continue
            if str(row.get("status") or "open") != "open":
                continue
            payload = row.get("candidate_payload") if isinstance(row.get("candidate_payload"), dict) else {}
            draft_id = str(payload.get("draft_id") or "")
            packet_id = str(row.get("packet_id") or "")
            if draft_id and packet_id:
                mapping[draft_id].append(packet_id)
    return {draft_id: list(dict.fromkeys(packet_ids)) for draft_id, packet_ids in mapping.items()}


def _pending_topic_review_packet_ids_by_tag(*, runs_dir: str | Path | None = None) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = defaultdict(list)
    root = Path(runs_dir) if runs_dir is not None else DATA_DIR / "runs"
    if not root.exists():
        return {}
    for review_file in root.glob("*/review_packets.json"):
        for row in read_jsonl(review_file):
            if str(row.get("kind") or "") != "topic_synthesis_review":
                continue
            if str(row.get("status") or "open") != "open":
                continue
            payload = row.get("candidate_payload") if isinstance(row.get("candidate_payload"), dict) else {}
            packet_id = str(row.get("packet_id") or "")
            if not packet_id:
                continue
            topic_ids = payload.get("candidate_topic_ids") if isinstance(payload.get("candidate_topic_ids"), list) else []
            sample_titles = payload.get("sample_titles") if isinstance(payload.get("sample_titles"), list) else []
            for topic_id in topic_ids:
                topic_text = str(topic_id or "")
                if topic_text.startswith("topic:"):
                    mapping[topic_text.removeprefix("topic:")].append(packet_id)
            for title in sample_titles:
                title_text = str(title or "").strip()
                if title_text:
                    mapping[title_text].append(packet_id)
    return {key: list(dict.fromkeys(packet_ids)) for key, packet_ids in mapping.items()}
def build_feedback_projection(
    *,
    content_items_path: str | Path = CONTENT_ITEMS_FILE,
    feedback_events_path: str | Path = FEEDBACK_EVENTS_FILE,
    projection_path: str | Path = FEEDBACK_PROJECTION_FILE,
) -> dict[str, Any]:
    items = read_jsonl(Path(content_items_path))
    events = read_jsonl(Path(feedback_events_path))
    item_by_id = {str(item.get("id") or ""): item for item in items if item.get("id")}

    tag_stats: dict[str, Counter[str]] = defaultdict(Counter)
    source_stats: dict[str, Counter[str]] = defaultdict(Counter)
    action_stats: dict[str, Counter[str]] = defaultdict(Counter)
    projections: list[dict[str, Any]] = []

    for event in events:
        item = item_by_id.get(str(event.get("item_id") or ""))
        if not item:
            continue
        decision = str(event.get("human_decision") or "candidate")
        action = str(event.get("suggested_action") or "")
        source_id = str(item.get("source_id") or item.get("source_name") or "")
        for tag_name in item.get("tags") or []:
            tag_stats[str(tag_name)][decision] += 1
        if source_id:
            source_stats[source_id][decision] += 1
        if action:
            action_stats[action][decision] += 1

    for tag_name, counter in sorted(tag_stats.items()):
        total = sum(counter.values())
        delta = round(sum(DECISION_PRIORITY_DELTA.get(decision, 0.0) * count for decision, count in counter.items()), 4)
        dominant = counter.most_common(1)[0][0] if counter else "candidate"
        projections.append(_projection_row("tag", tag_name, {
            "total_feedback": total,
            "priority_delta": delta,
            "dominant_decision": dominant,
            "decision_counts": dict(counter),
        }))

    for source_id, counter in sorted(source_stats.items()):
        total = sum(counter.values())
        delta = round(sum(DECISION_PRIORITY_DELTA.get(decision, 0.0) * count for decision, count in counter.items()), 4)
        dominant = counter.most_common(1)[0][0] if counter else "candidate"
        projections.append(_projection_row("source", source_id, {
            "total_feedback": total,
            "priority_delta": delta,
            "dominant_decision": dominant,
            "decision_counts": dict(counter),
        }))

    for action, counter in sorted(action_stats.items()):
        total = sum(counter.values())
        dominant = counter.most_common(1)[0][0] if counter else "candidate"
        projections.append(_projection_row("action", action, {
            "total_feedback": total,
            "strategy_hint": ACTION_TEMPLATE_HINT.get(action, action),
            "dominant_decision": dominant,
            "decision_counts": dict(counter),
        }))

    write_jsonl(Path(projection_path), projections)
    return {
        "projection_file": str(projection_path),
        "feedback_events": len(events),
        "projected_items": len(projections),
        "tag_rules": sum(1 for row in projections if row.get("scope") == "tag"),
        "source_rules": sum(1 for row in projections if row.get("scope") == "source"),
        "action_rules": sum(1 for row in projections if row.get("scope") == "action"),
    }


def _recommended_action_key(action: str, execution_kind: str) -> str:
    if action == "prepare_rewrite_brief" and execution_kind:
        return f"{action}:{execution_kind}"
    return action


def load_feedback_projection(*, projection_path: str | Path = FEEDBACK_PROJECTION_FILE) -> list[dict[str, Any]]:
    return read_jsonl(Path(projection_path))


def apply_feedback_projection(
    rows: list[dict[str, Any]],
    *,
    projection_path: str | Path = FEEDBACK_PROJECTION_FILE,
) -> list[dict[str, Any]]:
    projections = load_feedback_projection(projection_path=projection_path)
    tag_rules = {row["key"]: row for row in projections if row.get("scope") == "tag" and row.get("key")}
    source_rules = {row["key"]: row for row in projections if row.get("scope") == "source" and row.get("key")}
    action_rules = {row["key"]: row for row in projections if row.get("scope") == "action" and row.get("key")}
    adjusted: list[dict[str, Any]] = []

    for row in rows:
        item = dict(row)
        reasons: list[dict[str, Any]] = []
        delta = 0.0
        source_key = str(item.get("source_id") or item.get("source_name") or "")
        if source_key and source_key in source_rules:
            rule = source_rules[source_key]
            rule_delta = float(rule.get("priority_delta") or 0.0)
            delta += rule_delta
            reasons.append({
                "scope": "source",
                "key": source_key,
                "priority_delta": round(rule_delta, 4),
                "dominant_decision": str(rule.get("dominant_decision") or "candidate"),
                "total_feedback": int(rule.get("total_feedback") or 0),
            })
        for tag_name in item.get("tags") or []:
            rule = tag_rules.get(str(tag_name))
            if not rule:
                continue
            rule_delta = float(rule.get("priority_delta") or 0.0)
            delta += rule_delta
            reasons.append({
                "scope": "tag",
                "key": str(tag_name),
                "priority_delta": round(rule_delta, 4),
                "dominant_decision": str(rule.get("dominant_decision") or "candidate"),
                "total_feedback": int(rule.get("total_feedback") or 0),
            })
        last_feedback_event = str(item.get("last_feedback_event") or "")
        if last_feedback_event and last_feedback_event in action_rules:
            action_rule = action_rules[last_feedback_event]
            reasons.append({
                "scope": "action",
                "key": last_feedback_event,
                "priority_delta": 0.0,
                "dominant_decision": str(action_rule.get("dominant_decision") or "candidate"),
                "total_feedback": int(action_rule.get("total_feedback") or 0),
                "strategy_hint": str(action_rule.get("strategy_hint") or ""),
            })
        reasons.sort(
            key=lambda reason: (
                float(reason.get("priority_delta") or 0.0),
                int(reason.get("total_feedback") or 0),
                str(reason.get("key") or ""),
            ),
            reverse=True,
        )
        item["projected_score"] = round(float(item.get("score") or 0.0) + delta, 4)
        item["feedback_projection_delta"] = round(delta, 4)
        item["feedback_projection_reasons"] = reasons
        item_action = _build_item_projection_action(reasons)
        item["projected_action"] = item_action["action"]
        item["projected_action_label"] = _projection_label(item_action["action"])
        item["projected_action_reason"] = item_action["reason"]
        item["projected_action_scope"] = item_action["scope"]
        adjusted.append(item)

    adjusted.sort(
        key=lambda row: (
            float(row.get("projected_score") or row.get("score") or 0.0),
            str(row.get("published_at") or row.get("fetched_at") or ""),
        ),
        reverse=True,
    )
    return adjusted


def summarize_feedback_projection(
    *,
    projection_path: str | Path = FEEDBACK_PROJECTION_FILE,
    content_items_path: str | Path = CONTENT_ITEMS_FILE,
) -> dict[str, Any]:
    rows = load_feedback_projection(projection_path=projection_path)
    projection = Path(projection_path)
    top_positive = sorted(
        [row for row in rows if row.get("scope") in {"tag", "source"}],
        key=lambda row: float(row.get("priority_delta") or 0.0),
        reverse=True,
    )[:5]
    top_negative = sorted(
        [row for row in rows if row.get("scope") in {"tag", "source"}],
        key=lambda row: float(row.get("priority_delta") or 0.0),
    )[:5]
    top_actions = sorted(
        [row for row in rows if row.get("scope") == "action"],
        key=lambda row: (int(row.get("total_feedback") or 0), str(row.get("key") or "")),
        reverse=True,
    )[:5]
    projected_items = apply_feedback_projection(read_jsonl(Path(content_items_path)), projection_path=projection_path)
    knowledge_card_ids_by_item = _ready_knowledge_card_ids_by_item(cards_file=KNOWLEDGE_CARDS_FILE)
    knowledge_card_status_by_item = _knowledge_card_status_by_item(cards_file=KNOWLEDGE_CARDS_FILE)
    candidate_knowledge_card_ids_by_item = _candidate_knowledge_card_ids_by_item(cards_file=KNOWLEDGE_CARDS_FILE)
    pending_review_packet_ids_by_card = _pending_knowledge_review_packet_ids_by_card()
    pending_review_packet_ids_by_brief = _pending_brief_review_packet_ids_by_brief()
    brief_status_by_card = _brief_status_by_knowledge_card()
    draft_status_by_brief = _draft_status_by_brief()
    geo_status_by_draft = _geo_status_by_draft()
    pending_review_packet_ids_by_draft = _pending_draft_review_packet_ids_by_draft()
    pending_review_packet_ids_by_geo = _pending_geo_review_packet_ids_by_draft()
    items_by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in projected_items:
        items_by_action[str(item.get("projected_action") or "keep_observing")].append(item)
    grouped_actions: list[tuple[str, str, list[dict[str, Any]]]] = []
    for action, items in items_by_action.items():
        if action != "prepare_rewrite_brief":
            grouped_actions.append((action, action, items))
            continue
        stage_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in items:
            item_execution_meta = _recommended_action_execution_meta(
                action,
                [item],
                knowledge_card_ids_by_item=knowledge_card_ids_by_item,
                knowledge_card_status_by_item=knowledge_card_status_by_item,
                candidate_knowledge_card_ids_by_item=candidate_knowledge_card_ids_by_item,
                pending_review_packet_ids_by_card=pending_review_packet_ids_by_card,
                pending_review_packet_ids_by_brief=pending_review_packet_ids_by_brief,
                pending_review_packet_ids_by_draft=pending_review_packet_ids_by_draft,
                pending_review_packet_ids_by_geo=pending_review_packet_ids_by_geo,
                brief_status_by_card=brief_status_by_card,
                draft_status_by_brief=draft_status_by_brief,
                geo_status_by_draft=geo_status_by_draft,
            )
            stage_key = item_execution_meta["execution_kind"] or "build_generation_briefs"
            stage_groups[stage_key].append(item)
        for stage_key, stage_items in stage_groups.items():
            grouped_actions.append((action, stage_key, stage_items))

    recommended_actions = []
    for action, stage_key, items in sorted(
        grouped_actions,
        key=lambda row: (
            len(row[2]),
            max(float(item.get("projected_score") or item.get("score") or 0.0) for item in row[2]),
            row[1],
            row[0],
        ),
        reverse=True,
    )[:5]:
        scores = [round(float(item.get("projected_score") or item.get("score") or 0.0), 4) for item in items]
        execution_meta = _recommended_action_execution_meta(
            action,
            items,
            knowledge_card_ids_by_item=knowledge_card_ids_by_item,
            knowledge_card_status_by_item=knowledge_card_status_by_item,
            candidate_knowledge_card_ids_by_item=candidate_knowledge_card_ids_by_item,
            pending_review_packet_ids_by_card=pending_review_packet_ids_by_card,
            pending_review_packet_ids_by_brief=pending_review_packet_ids_by_brief,
            pending_review_packet_ids_by_draft=pending_review_packet_ids_by_draft,
            pending_review_packet_ids_by_geo=pending_review_packet_ids_by_geo,
            brief_status_by_card=brief_status_by_card,
            draft_status_by_brief=draft_status_by_brief,
            geo_status_by_draft=geo_status_by_draft,
        )
        reason_counts = Counter(
            reason for reason in execution_meta["blocked_reason_by_item"].values() if str(reason)
        )
        blocked_reason_breakdown = [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda row: (-row[1], row[0]))
        ]
        recommended_actions.append({
            "action": action,
            "action_key": _recommended_action_key(action, execution_meta["execution_kind"] or stage_key),
            "label": _projection_label(action),
            "count": len(items),
            "top_score": max(scores) if scores else 0.0,
            "score_range": {
                "min": min(scores) if scores else 0.0,
                "max": max(scores) if scores else 0.0,
            },
            "actionable": execution_meta["actionable"],
            "execution_kind": execution_meta["execution_kind"],
            "execution_label": execution_meta["execution_label"],
            "execution_blocked_reason": execution_meta["execution_blocked_reason"],
            "precondition_statuses": execution_meta["precondition_statuses"],
            "precondition_passed": execution_meta["precondition_passed"],
            "ready_count": execution_meta["ready_count"],
            "blocked_count": execution_meta["blocked_count"],
            "blocked_item_ids": execution_meta["blocked_item_ids"],
            "blocked_reason_by_item": execution_meta["blocked_reason_by_item"],
            "blocked_reason_breakdown": blocked_reason_breakdown,
            "blocked_sample_titles": execution_meta["blocked_sample_titles"],
            "pending_approval_label": execution_meta["pending_approval_label"],
            "pending_approval_count": execution_meta["pending_approval_count"],
            "pending_approval_item_ids": execution_meta["pending_approval_item_ids"],
            "missing_candidate_item_ids": execution_meta["missing_candidate_item_ids"],
            "pending_approval_card_ids": execution_meta["pending_approval_card_ids"],
            "pending_approval_packet_ids": execution_meta["pending_approval_packet_ids"],
            "pending_approval_sample_titles": execution_meta["pending_approval_sample_titles"],
            "missing_candidate_count": execution_meta["missing_candidate_count"],
            "missing_candidate_sample_titles": execution_meta["missing_candidate_sample_titles"],
            "fallback_actionable": execution_meta["fallback_actionable"],
            "fallback_execution_kind": execution_meta["fallback_execution_kind"],
            "fallback_execution_label": execution_meta["fallback_execution_label"],
            "fallback_execution_params": execution_meta["fallback_execution_params"],
            "execution_params": execution_meta["execution_params"],
            "item_ids": [str(item.get("id") or "") for item in items if str(item.get("id") or "")],
            "sample_titles": [str(item.get("title") or "") for item in items[:3] if str(item.get("title") or "")],
            "sample_ids": [str(item.get("id") or "") for item in items[:3] if str(item.get("id") or "")],
        })
    top_projected_items = [
        {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "source_name": str(item.get("source_name") or item.get("source_id") or ""),
            "projected_score": round(float(item.get("projected_score") or item.get("score") or 0.0), 4),
            "feedback_projection_delta": round(float(item.get("feedback_projection_delta") or 0.0), 4),
            "projected_action": str(item.get("projected_action") or ""),
            "projected_action_label": str(item.get("projected_action_label") or ""),
            "projected_action_reason": str(item.get("projected_action_reason") or ""),
        }
        for item in projected_items[:5]
    ]
    return {
        "projection_file": str(projection_path),
        "rows": len(rows),
        "scope_counts": {
            "tag": sum(1 for row in rows if row.get("scope") == "tag"),
            "source": sum(1 for row in rows if row.get("scope") == "source"),
            "action": sum(1 for row in rows if row.get("scope") == "action"),
        },
        "updated_at": datetime.fromtimestamp(projection.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S") if projection.exists() else "",
        "top_positive": top_positive,
        "top_negative": top_negative,
        "top_actions": top_actions,
        "recommended_actions": recommended_actions,
        "top_projected_items": top_projected_items,
    }
