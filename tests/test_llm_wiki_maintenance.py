from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


class LLMWikiMaintenanceTests(unittest.TestCase):
    def test_apply_reviewed_topic_with_multiple_source_items_links_all_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "kind": "concept", "title": "概念一", "tags": ["AI"], "sources": ["source-a"], "source_item_id": "item-1", "wiki_path": "wiki/concepts/概念一.md", "status": "applied"},
                {"id": "knowledge:2", "kind": "concept", "title": "概念二", "tags": ["AI"], "sources": ["source-b"], "source_item_id": "item-2", "wiki_path": "wiki/concepts/概念二.md", "status": "applied"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:AI", "title": "AI", "source_item_id": "item-1", "source_item_ids": ["item-1", "item-2"], "sources": ["source-a", "source-b"], "wiki_path": "wiki/synthesis/AI.md", "status": "approved"},
            ])

            with patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                export_sources.apply_reviewed_knowledge_candidates(export_root=root, topic_ids=["topic:AI"])

            topic_text = (root / "wiki" / "synthesis" / "AI.md").read_text(encoding="utf-8")
            self.assertIn("[[概念一]]", topic_text)
            self.assertIn("[[概念二]]", topic_text)

    def test_apply_reviewed_knowledge_updates_navigation_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(cards_file, [{
                "id": "knowledge:1",
                "kind": "concept",
                "title": "测试概念",
                "tags": ["测试"],
                "sources": ["source-a"],
                "source_item_id": "item-1",
                "wiki_path": "wiki/concepts/测试概念.md",
                "status": "approved",
            }])
            write_jsonl(topics_file, [{
                "id": "topic:测试",
                "title": "测试",
                "source_item_id": "item-1",
                "sources": ["source-a"],
                "wiki_path": "wiki/synthesis/测试.md",
                "status": "approved",
            }])

            with patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.apply_reviewed_knowledge_candidates(export_root=root, trace={"run_id": "run-1", "task_id": "task-1", "packet_id": "packet-1"})

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(cards[0]["status"], "applied")
            self.assertEqual(topics[0]["status"], "applied")
            self.assertEqual(cards[0]["applied_run_id"], "run-1")
            self.assertEqual(cards[0]["applied_task_id"], "task-1")
            self.assertEqual(cards[0]["applied_packet_id"], "packet-1")
            self.assertEqual(topics[0]["applied_run_id"], "run-1")
            self.assertEqual(topics[0]["applied_task_id"], "task-1")
            self.assertEqual(topics[0]["applied_packet_id"], "packet-1")
            index_text = (root / "wiki" / "index.md").read_text(encoding="utf-8")
            overview_text = (root / "wiki" / "overview.md").read_text(encoding="utf-8")
            query_text = (root / "wiki" / "queries" / "content-questions.md").read_text(encoding="utf-8")
            concept_text = (root / "wiki" / "concepts" / "测试概念.md").read_text(encoding="utf-8")
            topic_text = (root / "wiki" / "synthesis" / "测试.md").read_text(encoding="utf-8")
            log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
            self.assertIn("[[overview]]", index_text)
            self.assertIn("[[测试概念]]", index_text)
            self.assertIn("[[测试]]", index_text)
            self.assertIn("概念页：1", overview_text)
            self.assertIn("主题综合页：1", overview_text)
            self.assertIn("哪些知识卡片缺少原始来源？", query_text)
            self.assertIn("related:", concept_text)
            self.assertIn("[[测试]]", concept_text)
            self.assertIn("## 来源", concept_text)
            self.assertIn("- source-a", concept_text)
            self.assertIn("## 来源", topic_text)
            self.assertIn("- source-a", topic_text)
            self.assertIn("[[测试概念]]", topic_text)
            self.assertIn("card_titles=['测试概念']", log_text)
            self.assertIn("run_id=run-1", log_text)
            self.assertIn("task_id=task-1", log_text)
            self.assertIn("packet_id=packet-1", log_text)
    def test_apply_reviewed_knowledge_can_limit_to_selected_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "kind": "concept", "title": "概念一", "tags": ["测试"], "sources": ["source-a"], "source_item_id": "item-1", "wiki_path": "wiki/concepts/概念一.md", "status": "approved"},
                {"id": "knowledge:2", "kind": "concept", "title": "概念二", "tags": ["测试"], "sources": ["source-b"], "source_item_id": "item-2", "wiki_path": "wiki/concepts/概念二.md", "status": "approved"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:一", "title": "主题一", "source_item_id": "item-1", "sources": ["source-a"], "wiki_path": "wiki/synthesis/主题一.md", "status": "approved"},
                {"id": "topic:二", "title": "主题二", "source_item_id": "item-2", "sources": ["source-b"], "wiki_path": "wiki/synthesis/主题二.md", "status": "approved"},
            ])

            with patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.apply_reviewed_knowledge_candidates(export_root=root, card_ids=["knowledge:2"], topic_ids=["topic:二"])

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(cards[0]["status"], "approved")
            self.assertEqual(cards[1]["status"], "applied")
            self.assertEqual(topics[0]["status"], "approved")
            self.assertEqual(topics[1]["status"], "applied")
            self.assertEqual(result["requested_ids"], {"cards": ["knowledge:2"], "topics": ["topic:二"]})
            self.assertEqual(result["accepted_ids"], {"cards": ["knowledge:2"], "topics": ["topic:二"]})
            self.assertEqual(result["rejected_ids"], {"cards": [], "topics": []})
            self.assertFalse((root / "wiki" / "concepts" / "概念一.md").exists())
            self.assertTrue((root / "wiki" / "concepts" / "概念二.md").exists())

    def test_update_topic_only_status_does_not_update_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "status": "candidate"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:1", "status": "candidate"},
            ])

            with patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.update_knowledge_candidate_status("approved", topic_ids=["topic:1"])

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(result["cards"], 0)
            self.assertEqual(result["topics"], 1)
            self.assertEqual(cards[0]["status"], "candidate")
            self.assertEqual(topics[0]["status"], "approved")

    def test_apply_reviewed_topic_only_does_not_apply_cards(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "kind": "concept", "title": "概念一", "tags": ["测试"], "sources": ["source-a"], "source_item_id": "item-1", "wiki_path": "wiki/concepts/概念一.md", "status": "approved"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:一", "title": "主题一", "source_item_id": "item-1", "sources": ["source-a"], "wiki_path": "wiki/synthesis/主题一.md", "status": "approved"},
            ])

            with patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.apply_reviewed_knowledge_candidates(export_root=root, topic_ids=["topic:一"], trace={"run_id": "run-topic-only", "task_id": "task-topic-only"})

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(result["written_cards"], 0)
            self.assertEqual(result["written_topics"], 1)
            self.assertEqual(result["requested_ids"], {"cards": [], "topics": ["topic:一"]})
            self.assertEqual(result["accepted_ids"], {"cards": [], "topics": ["topic:一"]})
            self.assertEqual(result["rejected_ids"], {"cards": [], "topics": []})
            self.assertEqual(cards[0]["status"], "approved")
            self.assertNotIn("applied_run_id", cards[0])
            self.assertEqual(topics[0]["status"], "applied")
            self.assertEqual(topics[0]["applied_run_id"], "run-topic-only")
            self.assertEqual(topics[0]["applied_task_id"], "task-topic-only")
            self.assertFalse((root / "wiki" / "concepts" / "概念一.md").exists())
            self.assertTrue((root / "wiki" / "synthesis" / "主题一.md").exists())

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(content_file, [
                {"id": "item-new", "title": "新增条目", "source_name": "来源A", "source_id": "source-a", "human_decision": "adopted", "tags": ["AI"], "references": ["source-a"], "score": 0.0, "summary": "new"},
            ])
            write_jsonl(projection_file, [
                {"scope": "tag", "key": "AI", "priority_delta": 0.6, "dominant_decision": "adopted", "total_feedback": 3, "decision_counts": {"adopted": 3}},
            ])
            write_jsonl(cards_file, [
                {"id": "knowledge:existing", "kind": "concept", "title": "已入库概念", "tags": ["历史"], "sources": ["source-old"], "source_item_id": "item-old", "wiki_path": "wiki/concepts/已入库概念.md", "status": "applied"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:历史", "title": "历史", "source_item_id": "item-old", "sources": ["source-old"], "wiki_path": "wiki/synthesis/历史.md", "status": "applied"},
            ])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_knowledge_candidates(export_root=root, limit=10, trace={"run_id": "run-candidate", "task_id": "task-candidate"})

            cards = read_jsonl(cards_file)
            topics = read_jsonl(topics_file)
            self.assertEqual(result.candidates, 1)
            self.assertEqual(result.source_run_id, "run-candidate")
            self.assertEqual(result.source_task_id, "task-candidate")
            self.assertEqual({row["id"] for row in cards}, {"knowledge:existing", "knowledge:item-new"})
            self.assertEqual({row["id"] for row in topics}, {"topic:历史"})
            status_by_card = {row["id"]: row["status"] for row in cards}
            status_by_topic = {row["id"]: row["status"] for row in topics}
            self.assertEqual(status_by_card["knowledge:existing"], "applied")
            candidate_card = next(row for row in cards if row["id"] == "knowledge:item-new")
            self.assertEqual(candidate_card["source_run_id"], "run-candidate")
            self.assertEqual(candidate_card["source_task_id"], "task-candidate")
            log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
            self.assertIn("知识候选生成：cards=1, topics=0", log_text)
            self.assertIn("run_id=run-candidate", log_text)
            self.assertIn("task_id=task-candidate", log_text)

    def test_build_topic_synthesis_candidates_persists_trace_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"
            content_file = Path(tmp) / "content_items.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(content_file, [
                {"id": "item-topic-1", "title": "主题条目一", "source_name": "来源A", "source_id": "source-a", "human_decision": "dig_deeper", "tags": ["AI"], "references": ["source-a"], "score": 0.1, "summary": "topic-1", "last_feedback_event": "raise_topic_priority"},
                {"id": "item-topic-2", "title": "主题条目二", "source_name": "来源B", "source_id": "source-b", "human_decision": "dig_deeper", "tags": ["AI"], "references": ["source-b"], "score": 0.2, "summary": "topic-2", "last_feedback_event": "raise_topic_priority"},
            ])
            write_jsonl(projection_file, [
                {"scope": "action", "key": "raise_topic_priority", "dominant_decision": "dig_deeper", "total_feedback": 2, "decision_counts": {"dig_deeper": 2}, "strategy_hint": "raise_topic_priority"},
            ])
            write_jsonl(cards_file, [])
            write_jsonl(topics_file, [])

            with patch.object(export_sources, "CONTENT_ITEMS_FILE", content_file), patch.object(export_sources, "FEEDBACK_PROJECTION_FILE", projection_file), patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.build_topic_synthesis_candidates(export_root=root, limit=10, trace={"run_id": "run-topic", "task_id": "task-topic"})

            topics = read_jsonl(topics_file)
            self.assertEqual(result.synthesis, 1)
            self.assertEqual(result.source_run_id, "run-topic")
            self.assertEqual(result.source_task_id, "task-topic")
            self.assertEqual(len(topics), 1)
            self.assertEqual(topics[0]["source_run_id"], "run-topic")
            self.assertEqual(topics[0]["source_task_id"], "task-topic")
            self.assertEqual(set(topics[0]["source_item_ids"]), {"item-topic-1", "item-topic-2"})
            log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
            self.assertIn("主题综合候选生成：topics=1", log_text)
            self.assertIn("run_id=run-topic", log_text)
            self.assertIn("task_id=task-topic", log_text)

    def test_apply_reviewed_knowledge_reports_rejected_requested_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"
            cards_file = Path(tmp) / "knowledge_index" / "cards.jsonl"
            topics_file = Path(tmp) / "knowledge_index" / "topics.jsonl"
            write_jsonl(cards_file, [
                {"id": "knowledge:1", "kind": "concept", "title": "概念一", "tags": ["测试"], "sources": ["source-a"], "source_item_id": "item-1", "wiki_path": "wiki/concepts/概念一.md", "status": "approved"},
            ])
            write_jsonl(topics_file, [
                {"id": "topic:1", "title": "主题一", "source_item_id": "item-1", "sources": ["source-a"], "wiki_path": "wiki/synthesis/主题一.md", "status": "candidate"},
            ])

            with patch.object(export_sources, "CARDS_INDEX_FILE", cards_file), patch.object(export_sources, "TOPICS_INDEX_FILE", topics_file):
                result = export_sources.apply_reviewed_knowledge_candidates(export_root=root, card_ids=["knowledge:missing", "knowledge:1"], topic_ids=["topic:1", "topic:missing"])

            self.assertEqual(result["requested_ids"], {"cards": ["knowledge:missing", "knowledge:1"], "topics": ["topic:1", "topic:missing"]})
            self.assertEqual(result["accepted_ids"], {"cards": ["knowledge:1"], "topics": []})
            self.assertEqual(result["rejected_ids"], {"cards": ["knowledge:missing"], "topics": ["topic:1", "topic:missing"]})
            self.assertEqual(result["rejected_reasons"], {
                "cards": {"knowledge:missing": "未找到对应记录"},
                "topics": {
                    "topic:1": "仍待审批",
                    "topic:missing": "未找到对应记录",
                },
            })
            log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
            self.assertIn("知识入库：cards=1, topics=0", log_text)
            self.assertIn("rejected_cards=['knowledge:missing']", log_text)
            self.assertIn("rejected_topics=['topic:1', 'topic:missing']", log_text)
            self.assertIn("rejected_card_reasons={'knowledge:missing': '未找到对应记录'}", log_text)
            self.assertIn("'topic:1': '仍待审批'", log_text)
            self.assertIn("'topic:missing': '未找到对应记录'", log_text)

    def test_export_llm_wiki_sources_writes_log_with_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "llm_wiki"

            class DummyDataManager:
                def __init__(self):
                    self.name2fakeid = {"测试号": "fakeid-1"}
                    self.message_info = {
                        "测试号": {
                            "blogs": [{
                                "id": "article-1",
                                "title": "测试文章",
                                "digest": "摘要",
                                "link": "https://example.com/a",
                                "cover": "",
                                "create_time": "2026-05-16 10:00:00",
                                "is_deleted": False,
                            }]
                        }
                    }
                    self.message_detail_text = {"article-1": "正文内容"}

                def reload(self, _key: str):
                    return None

            dummy_data_manager = DummyDataManager()

            with patch("src.utils.data_manager.data_manager", dummy_data_manager):
                result = export_sources.export_llm_wiki_sources(export_root=root, trace={"run_id": "run-export", "task_id": "task-export"})

            self.assertEqual(result.exported, 1)
            log_text = (root / "wiki" / "log.md").read_text(encoding="utf-8")
            self.assertIn("原始素材导出：exported=1, skipped=0, accounts=1", log_text)
            self.assertIn("run_id=run-export", log_text)
            self.assertIn("task_id=task-export", log_text)
