from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.content_loop import feedback_projection, generation_pipeline
from src.llm_wiki_bridge import export_sources


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


class FeedbackProjectionFlowTests(unittest.TestCase):
    def test_apply_feedback_projection_adds_reasons_and_orders_items(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            write_jsonl(projection_path, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.4, "dominant_decision": "adopted", "total_feedback": 3, "decision_counts": {"adopted": 3}},
                {"scope": "source", "key": "source-b", "priority_delta": -0.2, "dominant_decision": "not_relevant", "total_feedback": 2, "decision_counts": {"not_relevant": 2}},
            ])
            rows = [
                {"id": "1", "title": "A", "score": 1.0, "source_id": "source-a", "tags": ["AI"]},
                {"id": "2", "title": "B", "score": 1.1, "source_id": "source-b", "tags": []},
            ]

            adjusted = feedback_projection.apply_feedback_projection(rows, projection_path=projection_path)

            self.assertEqual(adjusted[0]["id"], "1")
            self.assertEqual(adjusted[0]["projected_score"], 1.4)
            self.assertEqual(adjusted[0]["feedback_projection_reasons"][0]["key"], "AI")
            self.assertEqual(adjusted[0]["projected_action"], "build_knowledge_candidate")
            self.assertEqual(adjusted[1]["feedback_projection_delta"], -0.2)

    def test_action_rule_can_drive_projected_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 4, "decision_counts": {"dig_deeper": 4}, "strategy_hint": "raise_topic_priority"},
            ])
            rows = [{"id": "1", "title": "A", "score": 0.1, "source_id": "source-a", "tags": [], "last_feedback_event": "raise_topic_priority"}]

            adjusted = feedback_projection.apply_feedback_projection(rows, projection_path=projection_path)

            self.assertEqual(adjusted[0]["projected_action"], "build_topic_synthesis")
            self.assertEqual(adjusted[0]["projected_action_label"], "进入主题综合")
            self.assertEqual(adjusted[0]["projected_action_reason"], "raise_topic_priority")

    def test_build_knowledge_candidates_uses_projected_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            write_jsonl(content_file, [
                {"id": "item-low", "title": "低分条目", "source_name": "公众号A", "source_id": "source-a", "human_decision": "adopted", "tags": ["普通"], "references": [], "score": 0.1, "summary": "low"},
                {"id": "item-high", "title": "高分条目", "source_name": "公众号B", "source_id": "source-b", "human_decision": "adopted", "tags": ["AI"], "references": [], "score": 0.0, "summary": "high"},
            ])
            write_jsonl(projection_file, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.8, "dominant_decision": "adopted", "total_feedback": 5, "decision_counts": {"adopted": 5}},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_knowledge_candidates(export_root=export_root, limit=2)

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(cards[0]["source_item_id"], "item-high")
            self.assertEqual(cards[0]["projected_score"], 0.8)
            self.assertTrue(cards[0]["feedback_projection_reasons"])
            self.assertEqual(result.candidate_card_ids, ["knowledge:item-high", "knowledge:item-low"])
            self.assertEqual(result.candidate_topic_ids, [])
            self.assertEqual(topics, [])

    def test_build_knowledge_candidates_can_filter_by_projected_action(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            write_jsonl(content_file, [
                {"id": "item-knowledge", "title": "知识条目", "source_name": "来源A", "source_id": "source-a", "human_decision": "adopted", "tags": ["AI"], "references": [], "score": 0.0, "summary": "knowledge"},
                {"id": "item-brief", "title": "改写条目", "source_name": "来源B", "source_id": "source-b", "human_decision": "rewrite", "tags": [], "references": [], "score": 0.0, "summary": "brief", "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(projection_file, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.8, "dominant_decision": "adopted", "total_feedback": 5, "decision_counts": {"adopted": 5}},
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_knowledge_candidates(export_root=export_root, limit=10, projected_action="prepare_rewrite_brief")

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["source_item_id"], "item-brief")
            self.assertEqual(cards[0]["projected_action"], "prepare_rewrite_brief")
            self.assertEqual(result.candidate_topic_ids, [])
            self.assertEqual(topics, [])



    def test_build_knowledge_candidates_skips_existing_applied_item(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            write_jsonl(content_file, [
                {"id": "item-1", "title": "已入库条目", "source_name": "来源A", "source_id": "source-a", "human_decision": "adopted", "tags": ["AI"], "references": ["source-a"], "score": 0.0, "summary": "existing"},
            ])
            write_jsonl(projection_file, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.6, "dominant_decision": "adopted", "total_feedback": 3, "decision_counts": {"adopted": 3}},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "kind": "concept", "title": "已入库条目", "source_item_id": "item-1", "status": "applied"},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_knowledge_candidates(export_root=export_root, limit=10)

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(result.candidates, 0)
            self.assertEqual(result.candidate_card_ids, [])
            self.assertEqual(cards[0]["status"], "applied")
            self.assertEqual(topics, [])

    def test_topic_synthesis_action_accepts_ai_tags_when_tags_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "AI 补标签条目", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": [], "ai_tags": ["AI"], "last_feedback_event": "raise_topic_priority"},
            ])

            summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_topic_synthesis")
            self.assertTrue(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["ready_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["execution_params"]["item_ids"], ["item-1"])

        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            write_jsonl(content_file, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "human_decision": "dig_deeper", "tags": ["AI"], "references": ["source-a"], "score": 0.1, "summary": "summary-1", "last_feedback_event": "raise_topic_priority"},
                {"id": "item-2", "title": "条目二", "source_name": "来源B", "source_id": "source-b", "human_decision": "dig_deeper", "tags": ["AI"], "references": ["source-b"], "score": 0.2, "summary": "summary-2", "last_feedback_event": "raise_topic_priority"},
            ])
            write_jsonl(projection_file, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_topic_synthesis_candidates(export_root=export_root, limit=10)

            topics = read_jsonl(topics_file)
            self.assertEqual(topics[0]["projected_action"], "build_topic_synthesis")
            self.assertEqual(topics[0]["source_item_id"], "item-1")
            self.assertEqual(set(topics[0]["source_item_ids"]), {"item-1", "item-2"})
            self.assertEqual(set(topics[0]["sample_titles"]), {"条目一", "条目二"})
            self.assertEqual(set(topics[0]["sources"]), {"source-a", "source-b"})





    def test_topic_synthesis_action_blocks_pending_topic_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批主题条目", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": ["AI"], "last_feedback_event": "raise_topic_priority"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:AI", "title": "AI", "status": "candidate"},
            ])

            with patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_topic_synthesis")
            self.assertFalse(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["ready_count"], 0)
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["blocked_reason_breakdown"], [{"reason": "待审批主题综合", "count": 1}])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_sample_titles"], ["待审批主题条目"])
            self.assertEqual(summary["recommended_actions"][0]["execution_blocked_reason"], "当前动作已有待审批主题综合，先在人工闸门中批准后再继续。")

    def test_topic_synthesis_action_exposes_pending_packet_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            review_file = Path(tmp) / "runs" / "run-1" / "review_packets.json"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批主题条目", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": ["AI"], "last_feedback_event": "raise_topic_priority"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:AI", "title": "AI", "status": "candidate"},
            ])
            write_jsonl(review_file, [
                {"packet_id": "packet-topic-1", "kind": "topic_synthesis_review", "status": "open", "candidate_payload": {"candidate_topic_ids": ["topic:AI"], "sample_titles": ["AI"], "synthesis": 1}},
            ])

            with patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["pending_approval_packet_ids"], ["packet-topic-1"])

    def test_topic_synthesis_action_blocks_applied_topic(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "已入库主题条目", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": ["AI"], "last_feedback_event": "raise_topic_priority"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:AI", "title": "AI", "status": "applied"},
            ])

            with patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_topic_synthesis")
            self.assertFalse(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["ready_count"], 0)
            self.assertEqual(summary["recommended_actions"][0]["blocked_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["blocked_reason_breakdown"], [{"reason": "已存在主题沉淀", "count": 1}])
            self.assertEqual(summary["recommended_actions"][0]["execution_blocked_reason"], "当前动作对应主题已存在知识沉淀，无需重复生成主题综合。")
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "无标签条目", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": [], "last_feedback_event": "raise_topic_priority"},
            ])

            summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_topic_synthesis")
            self.assertFalse(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["ready_count"], 0)
            self.assertEqual(summary["recommended_actions"][0]["blocked_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["missing_candidate_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["missing_candidate_sample_titles"], ["无标签条目"])
            self.assertTrue(summary["recommended_actions"][0]["fallback_actionable"])
            self.assertEqual(summary["recommended_actions"][0]["fallback_execution_kind"], "ai_enrich")
            self.assertEqual(summary["recommended_actions"][0]["fallback_execution_label"], "先补 AI 分类总结")
            self.assertEqual(summary["recommended_actions"][0]["fallback_execution_params"]["item_ids"], ["item-1"])
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            write_jsonl(content_file, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "human_decision": "dig_deeper", "tags": ["AI"], "references": ["source-a"], "score": 0.1, "summary": "summary-1", "last_feedback_event": "raise_topic_priority"},
            ])
            write_jsonl(projection_file, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:AI", "title": "AI", "source_item_id": "item-1", "status": "applied"},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_topic_synthesis_candidates(export_root=export_root, limit=10)

            topics = read_jsonl(topics_file)
            self.assertEqual(result.synthesis, 0)
            self.assertEqual(result.candidate_topic_ids, [])
            self.assertEqual(len(topics), 1)
            self.assertEqual(topics[0]["status"], "applied")
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            shared_source = {"type": "article", "url": "https://example.com/a"}
            write_jsonl(content_file, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "human_decision": "dig_deeper", "tags": ["AI"], "references": [shared_source], "score": 0.1, "summary": "summary-1", "last_feedback_event": "raise_topic_priority"},
                {"id": "item-2", "title": "条目二", "source_name": "来源B", "source_id": "source-b", "human_decision": "dig_deeper", "tags": ["AI"], "references": [shared_source], "score": 0.2, "summary": "summary-2", "last_feedback_event": "raise_topic_priority"},
            ])
            write_jsonl(projection_file, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                export_sources.build_topic_synthesis_candidates(export_root=export_root, limit=10)

            topics = read_jsonl(topics_file)
            self.assertEqual(len(topics), 1)
            self.assertEqual(topics[0]["sources"], [shared_source])
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            write_jsonl(content_file, [
                {"id": "item-topic", "title": "主题条目", "source_name": "来源A", "source_id": "source-a", "human_decision": "dig_deeper", "tags": ["AI"], "references": ["source-a"], "score": 0.0, "summary": "topic", "last_feedback_event": "raise_topic_priority"},
                {"id": "item-knowledge", "title": "知识条目", "source_name": "来源B", "source_id": "source-b", "human_decision": "adopted", "tags": ["AI"], "references": ["source-b"], "score": 0.0, "summary": "knowledge"},
            ])
            write_jsonl(projection_file, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_topic_synthesis_candidates(export_root=export_root, limit=10)

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(result.synthesis, 1)
            self.assertEqual(result.candidate_topic_ids, ["topic:AI"])
            self.assertEqual(cards, [])
            self.assertEqual(len(topics), 1)
            self.assertEqual(topics[0]["source_item_id"], "item-topic")
            self.assertEqual(topics[0]["projected_action"], "build_topic_synthesis")
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            export_root = Path(tmp) / "llm_wiki"
            write_jsonl(content_file, [
                {"id": "item-a", "title": "条目A", "source_name": "来源A", "source_id": "source-a", "human_decision": "adopted", "tags": ["AI"], "references": [], "score": 0.0, "summary": "a"},
                {"id": "item-b", "title": "条目B", "source_name": "来源B", "source_id": "source-b", "human_decision": "adopted", "tags": ["AI"], "references": [], "score": 0.0, "summary": "b"},
            ])
            write_jsonl(projection_file, [{"scope": "tag", "key": "AI", "priority_delta": 0.5, "dominant_decision": "adopted", "total_feedback": 3, "decision_counts": {"adopted": 3}}])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                export_sources.build_knowledge_candidates(export_root=export_root, limit=10, item_ids=["item-b"])

            cards = read_jsonl(cards_file)
            self.assertEqual(len(cards), 1)
            self.assertEqual(cards[0]["source_item_id"], "item-b")
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "cards.jsonl"
            topics_file = Path(tmp) / "topics.jsonl"
            content_file = Path(tmp) / "content_items.jsonl"
            briefs_file = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "title": "知识候选", "source_item_id": "item-1", "summary": "a", "sources": [], "status": "approved", "projected_score": 0.8, "feedback_projection_delta": 0.8, "projected_action": "build_knowledge_candidate", "projected_action_label": "进入知识候选", "projected_action_reason": "AI"},
                {"id": "knowledge:2", "title": "改写候选", "source_item_id": "item-2", "summary": "b", "sources": [], "status": "applied", "projected_score": 0.5, "feedback_projection_delta": 0.5, "projected_action": "prepare_rewrite_brief", "projected_action_label": "准备改写 brief", "projected_action_reason": "adjust_generation_template"},
            ])
            write_jsonl(topics_file, [])
            write_jsonl(content_file, [])

            with patch.object(generation_pipeline, "CARDS_INDEX_FILE", cards_file), patch.object(generation_pipeline, "TOPICS_INDEX_FILE", topics_file), patch.object(generation_pipeline, "CONTENT_ITEMS_FILE", content_file), patch.object(generation_pipeline, "BRIEFS_FILE", briefs_file):
                result = generation_pipeline.build_generation_briefs(limit=10, projected_action="prepare_rewrite_brief")

            briefs = read_jsonl(briefs_file)
            self.assertEqual(result.created, 1)
            self.assertEqual(briefs[0]["title"], "改写候选")
            self.assertEqual(briefs[0]["projected_action"], "prepare_rewrite_brief")

        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            write_jsonl(projection_path, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.6, "dominant_decision": "adopted", "total_feedback": 4, "decision_counts": {"adopted": 4}},
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": ["AI"], "last_feedback_event": "raise_topic_priority"},
                {"id": "item-2", "title": "条目二", "source_name": "来源B", "source_id": "source-b", "score": 0.0, "tags": []},
            ])

            summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertTrue(summary["recommended_actions"])
            labels = {row["label"] for row in summary["recommended_actions"]}
            self.assertIn("进入主题综合", labels)
            self.assertEqual(summary["recommended_actions"][0]["sample_titles"], ["条目一"])
            self.assertEqual(summary["recommended_actions"][0]["item_ids"], ["item-1"])
            self.assertTrue(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_topic_synthesis")
            self.assertEqual(summary["recommended_actions"][0]["execution_label"], "立即生成主题综合候选")
            self.assertEqual(summary["recommended_actions"][0]["execution_params"]["item_ids"], ["item-1"])
            self.assertEqual(summary["recommended_actions"][0]["execution_params"]["projected_action"], "build_topic_synthesis")
            self.assertEqual(summary["recommended_actions"][0]["score_range"]["max"], 0.7)
            self.assertTrue(summary["top_projected_items"])
            self.assertEqual(summary["top_projected_items"][0]["title"], "条目一")
            self.assertEqual(summary["top_projected_items"][0]["projected_action_label"], "进入主题综合")

    def test_rewrite_recommendations_split_by_execution_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            briefs_file = Path(tmp) / "generation" / "generation_briefs.jsonl"
            drafts_file = Path(tmp) / "generation" / "drafts.jsonl"
            geo_file = Path(tmp) / "generation" / "geo_variants.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 4, "decision_counts": {"rewrite": 4}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-brief", "title": "提纲阶段", "source_name": "来源A", "source_id": "source-a", "score": 0.4, "tags": [], "last_feedback_event": "adjust_generation_template"},
                {"id": "item-draft", "title": "草稿阶段", "source_name": "来源B", "source_id": "source-b", "score": 0.3, "tags": [], "last_feedback_event": "adjust_generation_template"},
                {"id": "item-geo", "title": "GEO 阶段", "source_name": "来源C", "source_id": "source-c", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-brief", "source_item_id": "item-brief", "status": "approved", "projected_action": "prepare_rewrite_brief"},
                {"id": "knowledge:item-draft", "source_item_id": "item-draft", "status": "approved", "projected_action": "prepare_rewrite_brief"},
                {"id": "knowledge:item-geo", "source_item_id": "item-geo", "status": "approved", "projected_action": "prepare_rewrite_brief"},
            ])
            write_jsonl(briefs_file, [
                {"id": "brief:knowledge:item-draft", "knowledge_card_id": "knowledge:item-draft", "status": "approved"},
                {"id": "brief:knowledge:item-geo", "knowledge_card_id": "knowledge:item-geo", "status": "approved"},
            ])
            write_jsonl(drafts_file, [
                {"id": "draft:brief:knowledge:item-geo", "brief_id": "brief:knowledge:item-geo", "status": "approved"},
            ])
            write_jsonl(geo_file, [])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            rewrite_actions = [row for row in summary["recommended_actions"] if row["action"] == "prepare_rewrite_brief"]
            self.assertEqual({row["action_key"] for row in rewrite_actions}, {
                "prepare_rewrite_brief:build_generation_briefs",
                "prepare_rewrite_brief:build_generation_draft",
                "prepare_rewrite_brief:build_geo_variants",
            })
            by_key = {row["action_key"]: row for row in rewrite_actions}
            self.assertEqual(by_key["prepare_rewrite_brief:build_generation_briefs"]["action_key"], "prepare_rewrite_brief:build_generation_briefs")
            self.assertEqual(by_key["prepare_rewrite_brief:build_generation_draft"]["item_ids"], ["item-draft"])
            self.assertEqual(by_key["prepare_rewrite_brief:build_geo_variants"]["item_ids"], ["item-geo"])
            self.assertEqual(by_key["prepare_rewrite_brief:build_generation_draft"]["execution_params"]["brief_ids"], ["brief:knowledge:item-draft"])
            self.assertEqual(by_key["prepare_rewrite_brief:build_geo_variants"]["execution_params"]["draft_ids"], ["draft:brief:knowledge:item-geo"])

        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            briefs_file = Path(tmp) / "generation" / "generation_briefs.jsonl"
            drafts_file = Path(tmp) / "generation" / "drafts.jsonl"
            geo_file = Path(tmp) / "generation" / "geo_variants.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "approved", "projected_action": "prepare_rewrite_brief"},
            ])
            write_jsonl(briefs_file, [
                {"id": "brief:knowledge:item-1", "knowledge_card_id": "knowledge:item-1", "status": "approved"},
            ])
            write_jsonl(drafts_file, [])
            write_jsonl(geo_file, [])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            action = summary["recommended_actions"][0]
            self.assertTrue(action["actionable"])
            self.assertEqual(action["execution_kind"], "build_generation_draft")
            self.assertEqual(action["execution_label"], "立即生成草稿")
            self.assertEqual(action["execution_params"]["brief_ids"], ["brief:knowledge:item-1"])
            self.assertEqual(action["ready_count"], 1)

        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            briefs_file = Path(tmp) / "generation" / "generation_briefs.jsonl"
            drafts_file = Path(tmp) / "generation" / "drafts.jsonl"
            geo_file = Path(tmp) / "generation" / "geo_variants.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "approved", "projected_action": "prepare_rewrite_brief"},
            ])
            write_jsonl(briefs_file, [
                {"id": "brief:knowledge:item-1", "knowledge_card_id": "knowledge:item-1", "status": "approved"},
            ])
            write_jsonl(drafts_file, [
                {"id": "draft:brief:knowledge:item-1", "brief_id": "brief:knowledge:item-1", "status": "approved"},
            ])
            write_jsonl(geo_file, [])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            action = summary["recommended_actions"][0]
            self.assertTrue(action["actionable"])
            self.assertEqual(action["execution_kind"], "build_geo_variants")
            self.assertEqual(action["execution_label"], "立即生成 GEO 变体")
            self.assertEqual(action["execution_params"]["draft_ids"], ["draft:brief:knowledge:item-1"])
            self.assertEqual(action["ready_count"], 1)

    def test_recommended_action_blocks_pending_draft_and_geo_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            briefs_file = Path(tmp) / "generation" / "generation_briefs.jsonl"
            drafts_file = Path(tmp) / "generation" / "drafts.jsonl"
            review_file = Path(tmp) / "runs" / "run-draft" / "review_packets.json"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批草稿条目", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "approved", "projected_action": "prepare_rewrite_brief"},
            ])
            write_jsonl(briefs_file, [
                {"id": "brief:knowledge:item-1", "knowledge_card_id": "knowledge:item-1", "status": "approved"},
            ])
            write_jsonl(drafts_file, [
                {"id": "draft:brief:knowledge:item-1", "brief_id": "brief:knowledge:item-1", "status": "candidate"},
            ])
            write_jsonl(review_file, [
                {"packet_id": "packet-draft-1", "kind": "draft_review", "status": "open", "candidate_payload": {"draft_id": "draft:brief:knowledge:item-1", "title": "草稿一"}},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            action = summary["recommended_actions"][0]
            self.assertFalse(action["actionable"])
            self.assertEqual(action["pending_approval_count"], 1)
            self.assertEqual(action["pending_approval_packet_ids"], ["packet-draft-1"])
            self.assertEqual(action["blocked_reason_breakdown"], [{"reason": "待审批草稿", "count": 1}])
            self.assertEqual(action["execution_blocked_reason"], "当前动作已有待审批草稿，先在人工闸门中批准后再继续。")

        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            briefs_file = Path(tmp) / "generation" / "generation_briefs.jsonl"
            drafts_file = Path(tmp) / "generation" / "drafts.jsonl"
            geo_file = Path(tmp) / "generation" / "geo_variants.jsonl"
            review_file = Path(tmp) / "runs" / "run-geo" / "review_packets.json"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批 GEO 条目", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "approved", "projected_action": "prepare_rewrite_brief"},
            ])
            write_jsonl(briefs_file, [
                {"id": "brief:knowledge:item-1", "knowledge_card_id": "knowledge:item-1", "status": "approved"},
            ])
            write_jsonl(drafts_file, [
                {"id": "draft:brief:knowledge:item-1", "brief_id": "brief:knowledge:item-1", "status": "approved"},
            ])
            write_jsonl(geo_file, [
                {"id": "geo:draft:brief:knowledge:item-1", "draft_id": "draft:brief:knowledge:item-1", "status": "candidate"},
            ])
            write_jsonl(review_file, [
                {"packet_id": "packet-geo-1", "kind": "geo_review", "status": "open", "candidate_payload": {"draft_id": "draft:brief:knowledge:item-1", "geo_id": "geo:draft:brief:knowledge:item-1"}},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            action = summary["recommended_actions"][0]
            self.assertFalse(action["actionable"])
            self.assertEqual(action["pending_approval_count"], 1)
            self.assertEqual(action["pending_approval_packet_ids"], ["packet-geo-1"])
            self.assertEqual(action["blocked_reason_breakdown"], [{"reason": "待审批 GEO", "count": 1}])
            self.assertEqual(action["execution_blocked_reason"], "当前动作已有待审批 GEO，先在人工闸门中批准后再继续。")

    def test_recommended_action_uses_real_knowledge_card_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "approved", "projected_action": "prepare_rewrite_brief"},
                {"id": "knowledge:item-1-old", "source_item_id": "item-1", "status": "rejected", "projected_action": "prepare_rewrite_brief"},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_generation_briefs")
            self.assertEqual(summary["recommended_actions"][0]["execution_blocked_reason"], "")
            self.assertEqual(summary["recommended_actions"][0]["precondition_statuses"], ["approved", "applied"])
            self.assertTrue(summary["recommended_actions"][0]["precondition_passed"])
            self.assertEqual(summary["recommended_actions"][0]["ready_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["blocked_count"], 0)
            self.assertEqual(summary["recommended_actions"][0]["blocked_sample_titles"], [])
            self.assertEqual(summary["recommended_actions"][0]["execution_params"]["knowledge_card_ids"], ["knowledge:item-1"])
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "cards.jsonl"
            topics_file = Path(tmp) / "topics.jsonl"
            content_file = Path(tmp) / "content_items.jsonl"
            briefs_file = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "title": "已入库卡片", "source_item_id": "item-1", "summary": "a", "sources": [], "status": "applied", "projected_score": 0.7, "feedback_projection_delta": 0.7, "projected_action": "build_knowledge_candidate", "projected_action_label": "进入知识候选", "projected_action_reason": "AI"},
            ])
            write_jsonl(topics_file, [])
            write_jsonl(content_file, [])

            with patch.object(generation_pipeline, "CARDS_INDEX_FILE", cards_file), patch.object(generation_pipeline, "TOPICS_INDEX_FILE", topics_file), patch.object(generation_pipeline, "CONTENT_ITEMS_FILE", content_file), patch.object(generation_pipeline, "BRIEFS_FILE", briefs_file):
                result = generation_pipeline.build_generation_briefs(limit=10)

            briefs = read_jsonl(briefs_file)
            self.assertEqual(result.created, 1)
            self.assertEqual(briefs[0]["knowledge_card_id"], "knowledge:1")


    def test_knowledge_candidate_action_blocks_pending_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            review_file = Path(tmp) / "runs" / "run-1" / "review_packets.json"
            write_jsonl(projection_path, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.6, "dominant_decision": "adopted", "total_feedback": 4, "decision_counts": {"adopted": 4}},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批知识条目", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": ["AI"]},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "candidate"},
            ])
            write_jsonl(review_file, [
                {"packet_id": "packet-knowledge-1", "kind": "knowledge_candidates_review", "status": "open", "candidate_payload": {"candidate_card_ids": ["knowledge:item-1"], "sample_titles": ["待审批知识条目"], "candidates": 1}},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_knowledge_candidates")
            self.assertFalse(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_card_ids"], ["knowledge:item-1"])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_packet_ids"], ["packet-knowledge-1"])
            self.assertEqual(summary["recommended_actions"][0]["execution_blocked_reason"], "当前动作已有待审批知识候选，先在人工闸门中批准后再继续。")

    def test_knowledge_candidate_action_blocks_applied_knowledge(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            write_jsonl(projection_path, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.6, "dominant_decision": "adopted", "total_feedback": 4, "decision_counts": {"adopted": 4}},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "已入库知识条目", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": ["AI"], "last_feedback_event": "raise_item_score"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "applied"},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            knowledge_action = next(row for row in summary["recommended_actions"] if row["action"] == "build_knowledge_candidate")
            self.assertEqual(knowledge_action["execution_kind"], "build_knowledge_candidates")
            self.assertFalse(knowledge_action["actionable"])
            self.assertEqual(knowledge_action["ready_count"], 0)
            self.assertEqual(knowledge_action["blocked_count"], 1)
            self.assertEqual(knowledge_action["execution_blocked_reason"], "当前动作对应条目已存在知识沉淀，无需重复生成知识候选。")
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertFalse(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_generation_briefs")
            self.assertEqual(summary["recommended_actions"][0]["execution_blocked_reason"], "当前动作缺少可用知识卡片，先生成并批准知识候选。")
            self.assertEqual(summary["recommended_actions"][0]["ready_count"], 0)
            self.assertEqual(summary["recommended_actions"][0]["blocked_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["blocked_item_ids"], ["item-1"])
            self.assertEqual(summary["recommended_actions"][0]["blocked_sample_titles"], ["条目一"])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_count"], 0)
            self.assertEqual(summary["recommended_actions"][0]["missing_candidate_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["missing_candidate_sample_titles"], ["条目一"])
            self.assertTrue(summary["recommended_actions"][0]["fallback_actionable"])
            self.assertEqual(summary["recommended_actions"][0]["fallback_execution_kind"], "build_knowledge_candidates")
            self.assertEqual(summary["recommended_actions"][0]["fallback_execution_label"], "先生成知识候选")
            self.assertEqual(summary["recommended_actions"][0]["fallback_execution_params"]["item_ids"], ["item-1"])
            self.assertEqual(summary["recommended_actions"][0]["execution_params"]["knowledge_card_ids"], [])

    def test_recommended_action_blocks_pending_generation_brief_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            briefs_file = Path(tmp) / "generation" / "generation_briefs.jsonl"
            review_file = Path(tmp) / "runs" / "run-brief" / "review_packets.json"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批提纲条目", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "approved", "projected_action": "prepare_rewrite_brief"},
            ])
            write_jsonl(briefs_file, [
                {"id": "brief:knowledge:item-1", "knowledge_card_id": "knowledge:item-1", "status": "candidate"},
            ])
            write_jsonl(review_file, [
                {"packet_id": "packet-brief-1", "kind": "generation_briefs_review", "status": "open", "candidate_payload": {"brief_ids": ["brief:knowledge:item-1"], "sample_titles": ["待审批提纲条目"], "created": 1}},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            action = summary["recommended_actions"][0]
            self.assertEqual(action["execution_kind"], "build_generation_briefs")
            self.assertFalse(action["actionable"])
            self.assertEqual(action["ready_count"], 0)
            self.assertEqual(action["pending_approval_count"], 1)
            self.assertEqual(action["pending_approval_item_ids"], ["item-1"])
            self.assertEqual(action["pending_approval_packet_ids"], ["packet-brief-1"])
            self.assertEqual(action["pending_approval_sample_titles"], ["待审批提纲条目"])
            self.assertEqual(action["blocked_reason_breakdown"], [{"reason": "待审批写作提纲", "count": 1}])
            self.assertEqual(action["execution_blocked_reason"], "当前动作已有待审批写作提纲，先在人工闸门中批准后再继续。")

        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批条目", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
                {"id": "item-2", "title": "待生成条目", "source_name": "来源B", "source_id": "source-b", "score": 0.1, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1-real", "source_item_id": "item-1", "status": "candidate", "projected_action": "prepare_rewrite_brief"},
            ])
            review_file = Path(tmp) / "runs" / "run-1" / "review_packets.json"
            write_jsonl(review_file, [
                {"packet_id": "packet-1", "kind": "knowledge_candidates_review", "status": "open", "candidate_payload": {"candidate_card_ids": ["knowledge:item-1-real"]}},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertFalse(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["blocked_item_ids"], ["item-1", "item-2"])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_item_ids"], ["item-1"])
            self.assertEqual(summary["recommended_actions"][0]["missing_candidate_item_ids"], ["item-2"])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_card_ids"], ["knowledge:item-1-real"])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_packet_ids"], ["packet-1"])
            self.assertEqual(summary["recommended_actions"][0]["pending_approval_sample_titles"], ["待审批条目"])
            self.assertEqual(summary["recommended_actions"][0]["missing_candidate_count"], 1)
            self.assertEqual(summary["recommended_actions"][0]["missing_candidate_sample_titles"], ["待生成条目"])
            self.assertEqual(summary["recommended_actions"][0]["fallback_execution_params"]["item_ids"], ["item-2"])

    def test_recommended_action_collects_mixed_pending_packets_for_briefs(self):
        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            cards_file = Path(tmp) / "cards.jsonl"
            briefs_file = Path(tmp) / "generation" / "generation_briefs.jsonl"
            review_file = Path(tmp) / "runs" / "run-mixed" / "review_packets.json"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "adjust_generation_template", "dominant_decision": "rewrite", "total_feedback": 2, "decision_counts": {"rewrite": 2}, "strategy_hint": "adjust_generation_template"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "待审批知识条目", "source_name": "来源A", "source_id": "source-a", "score": 0.2, "tags": [], "last_feedback_event": "adjust_generation_template"},
                {"id": "item-2", "title": "待审批提纲条目", "source_name": "来源B", "source_id": "source-b", "score": 0.1, "tags": [], "last_feedback_event": "adjust_generation_template"},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:item-1", "source_item_id": "item-1", "status": "candidate", "projected_action": "prepare_rewrite_brief"},
                {"id": "knowledge:item-2", "source_item_id": "item-2", "status": "approved", "projected_action": "prepare_rewrite_brief"},
            ])
            write_jsonl(briefs_file, [
                {"id": "brief:knowledge:item-2", "knowledge_card_id": "knowledge:item-2", "status": "candidate"},
            ])
            write_jsonl(review_file, [
                {"packet_id": "packet-knowledge-1", "kind": "knowledge_candidates_review", "status": "open", "candidate_payload": {"candidate_card_ids": ["knowledge:item-1"]}},
                {"packet_id": "packet-brief-2", "kind": "generation_briefs_review", "status": "open", "candidate_payload": {"brief_ids": ["brief:knowledge:item-2"]}},
            ])

            with patch.object(feedback_projection, "KNOWLEDGE_CARDS_FILE", cards_file), patch.object(feedback_projection, "DATA_DIR", Path(tmp)):
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            action = summary["recommended_actions"][0]
            self.assertFalse(action["actionable"])
            self.assertEqual(action["pending_approval_count"], 2)
            self.assertEqual(action["pending_approval_item_ids"], ["item-1", "item-2"])
            self.assertEqual(action["pending_approval_label"], "待审批生成结果")
            self.assertEqual(action["blocked_reason_breakdown"], [
                {"reason": "待审批写作提纲", "count": 1},
                {"reason": "待审批知识候选", "count": 1},
            ])

    def test_build_generation_briefs_can_filter_by_knowledge_card_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "cards.jsonl"
            topics_file = Path(tmp) / "topics.jsonl"
            content_file = Path(tmp) / "content_items.jsonl"
            briefs_file = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "title": "卡片一", "source_item_id": "item-1", "summary": "a", "sources": [], "status": "approved", "projected_score": 0.8, "feedback_projection_delta": 0.8, "projected_action": "build_knowledge_candidate", "projected_action_label": "进入知识候选", "projected_action_reason": "AI"},
                {"id": "knowledge:2", "title": "卡片二", "source_item_id": "item-2", "summary": "b", "sources": [], "status": "approved", "projected_score": 0.6, "feedback_projection_delta": 0.6, "projected_action": "prepare_rewrite_brief", "projected_action_label": "准备改写 brief", "projected_action_reason": "adjust_generation_template"},
            ])
            write_jsonl(topics_file, [])
            write_jsonl(content_file, [])

            with patch.object(generation_pipeline, "CARDS_INDEX_FILE", cards_file), patch.object(generation_pipeline, "TOPICS_INDEX_FILE", topics_file), patch.object(generation_pipeline, "CONTENT_ITEMS_FILE", content_file), patch.object(generation_pipeline, "BRIEFS_FILE", briefs_file):
                result = generation_pipeline.build_generation_briefs(limit=10, knowledge_card_ids=["knowledge:2"])

            briefs = read_jsonl(briefs_file)
            self.assertEqual(result.created, 1)
            self.assertEqual(briefs[0]["knowledge_card_id"], "knowledge:2")

        with tempfile.TemporaryDirectory() as tmp:
            projection_path = Path(tmp) / "feedback_projection.jsonl"
            content_items_path = Path(tmp) / "content_items.jsonl"
            write_jsonl(projection_path, [
                {"scope": "action", "key": "raise_item_score", "dominant_decision": "adopted", "total_feedback": 3, "decision_counts": {"adopted": 3}, "strategy_hint": "raise_priority"},
            ])
            write_jsonl(content_items_path, [
                {"id": "item-1", "title": "条目一", "source_name": "来源A", "source_id": "source-a", "score": 0.1, "tags": [], "last_feedback_event": "raise_item_score"},
            ])

            summary = feedback_projection.summarize_feedback_projection(projection_path=projection_path, content_items_path=content_items_path)

            self.assertEqual(summary["recommended_actions"][0]["action"], "build_knowledge_candidate")
            self.assertEqual(summary["recommended_actions"][0]["count"], 1)
            self.assertTrue(summary["recommended_actions"][0]["actionable"])
            self.assertEqual(summary["recommended_actions"][0]["execution_kind"], "build_knowledge_candidates")
            self.assertEqual(summary["recommended_actions"][0]["execution_label"], "立即生成知识候选")
            self.assertEqual(summary["recommended_actions"][0]["execution_params"]["item_ids"], ["item-1"])
            self.assertEqual(summary["recommended_actions"][0]["execution_params"]["projected_action"], "build_knowledge_candidate")
            self.assertEqual(summary["recommended_actions"][0]["sample_ids"], ["item-1"])
            self.assertEqual(summary["recommended_actions"][0]["top_score"], 0.1)
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "cards.jsonl"
            topics_file = Path(tmp) / "topics.jsonl"
            content_file = Path(tmp) / "content_items.jsonl"
            briefs_file = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "title": "低优先", "source_item_id": "item-1", "summary": "a", "sources": [], "status": "approved", "projected_score": 0.2, "feedback_projection_delta": 0.2, "projected_action": "keep_observing"},
                {"id": "knowledge:2", "title": "高优先", "source_item_id": "item-2", "summary": "b", "sources": [], "status": "approved", "projected_score": 0.9, "feedback_projection_delta": 0.9, "projected_action": "build_knowledge_candidate", "projected_action_label": "进入知识候选", "projected_action_reason": "AI"},
            ])
            write_jsonl(topics_file, [])
            write_jsonl(content_file, [])

            with patch.object(generation_pipeline, "CARDS_INDEX_FILE", cards_file), patch.object(generation_pipeline, "TOPICS_INDEX_FILE", topics_file), patch.object(generation_pipeline, "CONTENT_ITEMS_FILE", content_file), patch.object(generation_pipeline, "BRIEFS_FILE", briefs_file):
                result = generation_pipeline.build_generation_briefs(limit=2)

            briefs = read_jsonl(briefs_file)
            self.assertEqual(result.brief_ids[0], "brief:knowledge:2")
            self.assertEqual(briefs[0]["title"], "高优先")
            self.assertEqual(briefs[0]["projected_score"], 0.9)
            self.assertEqual(briefs[0]["projected_action_label"], "进入知识候选")


if __name__ == "__main__":
    unittest.main()
