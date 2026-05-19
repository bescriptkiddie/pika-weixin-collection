from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api
from src.content_loop import generation_pipeline, geo_pipeline
from src.execution import store
from src.execution.models import ExecutionRun, ExecutionTask, ReviewPacket
from src.execution.orchestrator import execute_sync_action
from src.execution.review import build_review_packet


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


class GenerationPipelineTests(unittest.TestCase):
    def test_build_draft_from_brief_returns_result_and_writes_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "generation_briefs.jsonl"
            draft_path = Path(tmp) / "drafts.jsonl"
            write_jsonl(brief_path, [{
                "id": "brief:card-1",
                "title": "测试 Brief",
                "topic": "测试主题",
                "summary": "测试摘要",
                "sources": ["source-a"],
                "status": "approved",
            }])

            with patch.object(generation_pipeline, "BRIEFS_FILE", brief_path), patch.object(generation_pipeline, "DRAFTS_FILE", draft_path):
                result = generation_pipeline.build_draft_from_brief("brief:card-1", trace={"run_id": "run-draft", "task_id": "task-draft"})

            self.assertEqual(result.created, 1)
            self.assertEqual(result.draft_id, "draft:brief:card-1")
            self.assertEqual(result.title, "测试 Brief")
            self.assertEqual(result.topic, "测试主题")
            self.assertEqual(result.sample_titles, ["测试 Brief"])
            self.assertEqual(result.summary, "测试摘要")
            self.assertEqual(result.source_run_id, "run-draft")
            self.assertEqual(result.source_task_id, "task-draft")
            drafts = read_jsonl(draft_path)
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]["id"], "draft:brief:card-1")
            self.assertEqual(drafts[0]["status"], "candidate")
            self.assertEqual(drafts[0]["source_run_id"], "run-draft")
            self.assertEqual(drafts[0]["source_task_id"], "task-draft")

    def test_build_draft_from_brief_requires_approved_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "generation_briefs.jsonl"
            draft_path = Path(tmp) / "drafts.jsonl"
            write_jsonl(brief_path, [{
                "id": "brief:card-1",
                "title": "测试 Brief",
                "topic": "测试主题",
                "summary": "测试摘要",
                "sources": ["source-a"],
                "status": "candidate",
            }])

            with patch.object(generation_pipeline, "BRIEFS_FILE", brief_path), patch.object(generation_pipeline, "DRAFTS_FILE", draft_path):
                with self.assertRaisesRegex(RuntimeError, "写作提纲尚未批准"):
                    generation_pipeline.build_draft_from_brief("brief:card-1")

    def test_build_draft_from_brief_preserves_existing_approved_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "generation_briefs.jsonl"
            draft_path = Path(tmp) / "drafts.jsonl"
            write_jsonl(brief_path, [{
                "id": "brief:card-1",
                "title": "测试 Brief",
                "topic": "测试主题",
                "summary": "测试摘要",
                "sources": ["source-a"],
                "status": "approved",
            }])
            write_jsonl(draft_path, [{
                "id": "draft:brief:card-1",
                "brief_id": "brief:card-1",
                "title": "旧标题",
                "topic": "旧主题",
                "content": "旧内容",
                "sources": ["source-old"],
                "status": "approved",
                "source_run_id": "locked-run",
                "source_task_id": "locked-task",
                "applied_run_id": "approved-run",
                "applied_task_id": "approved-task",
                "applied_packet_id": "approved-packet",
            }])

            with patch.object(generation_pipeline, "BRIEFS_FILE", brief_path), patch.object(generation_pipeline, "DRAFTS_FILE", draft_path):
                result = generation_pipeline.build_draft_from_brief("brief:card-1", trace={"run_id": "new-run", "task_id": "new-task"})

            drafts = read_jsonl(draft_path)
            self.assertEqual(drafts[0]["status"], "approved")
            self.assertEqual(drafts[0]["source_run_id"], "locked-run")
            self.assertEqual(drafts[0]["source_task_id"], "locked-task")
            self.assertEqual(drafts[0]["applied_run_id"], "approved-run")
            self.assertEqual(drafts[0]["applied_task_id"], "approved-task")
            self.assertEqual(drafts[0]["applied_packet_id"], "approved-packet")
            self.assertEqual(result.source_run_id, "locked-run")
            self.assertEqual(result.source_task_id, "locked-task")

        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "generation_briefs.jsonl"
            draft_path = Path(tmp) / "drafts.jsonl"
            write_jsonl(brief_path, [{
                "id": "brief:card-1",
                "title": "新标题",
                "topic": "新主题",
                "summary": "新摘要",
                "sources": ["source-a"],
                "status": "approved",
            }])
            write_jsonl(draft_path, [{
                "id": "draft:brief:card-1",
                "brief_id": "brief:card-1",
                "title": "旧标题",
                "topic": "旧主题",
                "content": "旧内容",
                "sources": ["source-old"],
                "status": "candidate",
            }])

            with patch.object(generation_pipeline, "BRIEFS_FILE", brief_path), patch.object(generation_pipeline, "DRAFTS_FILE", draft_path):
                result = generation_pipeline.build_draft_from_brief("brief:card-1")

            drafts = read_jsonl(draft_path)
            self.assertEqual(result.created, 1)
            self.assertEqual(len(drafts), 1)
            self.assertEqual(drafts[0]["id"], "draft:brief:card-1")
            self.assertEqual(drafts[0]["title"], "新标题")
            self.assertIn("新摘要", drafts[0]["content"])

    def test_build_draft_from_brief_reopens_rejected_status_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "generation_briefs.jsonl"
            draft_path = Path(tmp) / "drafts.jsonl"
            write_jsonl(brief_path, [{
                "id": "brief:card-1",
                "title": "测试 Brief",
                "topic": "测试主题",
                "summary": "测试摘要",
                "sources": ["source-a"],
                "status": "approved",
            }])
            write_jsonl(draft_path, [{
                "id": "draft:brief:card-1",
                "brief_id": "brief:card-1",
                "title": "旧标题",
                "topic": "旧主题",
                "content": "旧内容",
                "sources": ["source-old"],
                "status": "rejected",
            }])

            with patch.object(generation_pipeline, "BRIEFS_FILE", brief_path), patch.object(generation_pipeline, "DRAFTS_FILE", draft_path):
                generation_pipeline.build_draft_from_brief("brief:card-1")

            drafts = read_jsonl(draft_path)
            self.assertEqual(drafts[0]["status"], "candidate")

    def test_update_generation_status_maps_edited_to_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            brief_path = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(brief_path, [
                {"id": "brief:1", "status": "candidate"},
                {"id": "brief:2", "status": "candidate"},
            ])

            with patch.object(generation_pipeline, "BRIEFS_FILE", brief_path):
                result = generation_pipeline.update_generation_status("brief", "brief:1", "edited")

            self.assertEqual(result["status"], "approved")
            rows = read_jsonl(brief_path)
            status_by_id = {row["id"]: row["status"] for row in rows}
            self.assertEqual(status_by_id["brief:1"], "approved")
            self.assertEqual(status_by_id["brief:2"], "candidate")

    def test_build_generation_briefs_preserves_existing_approved_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "cards.jsonl"
            topics_file = Path(tmp) / "topics.jsonl"
            content_file = Path(tmp) / "content_items.jsonl"
            briefs_file = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(cards_file, [{
                "id": "knowledge:1",
                "title": "卡片一",
                "source_item_id": "item-1",
                "summary": "新摘要",
                "sources": ["source-a"],
                "status": "approved",
                "projected_score": 0.8,
                "feedback_projection_delta": 0.8,
                "projected_action": "build_knowledge_candidate",
                "projected_action_label": "进入知识候选",
                "projected_action_reason": "AI",
            }])
            write_jsonl(topics_file, [{"source_item_id": "item-1", "title": "主题一"}])
            write_jsonl(content_file, [])
            write_jsonl(briefs_file, [{
                "id": "brief:knowledge:1",
                "title": "旧标题",
                "topic": "旧主题",
                "summary": "旧摘要",
                "status": "approved",
                "source_run_id": "locked-brief-run",
                "source_task_id": "locked-brief-task",
                "applied_run_id": "approved-brief-run",
                "applied_task_id": "approved-brief-task",
                "applied_packet_id": "approved-brief-packet",
            }])

            with patch.object(generation_pipeline, "CARDS_INDEX_FILE", cards_file), patch.object(generation_pipeline, "TOPICS_INDEX_FILE", topics_file), patch.object(generation_pipeline, "CONTENT_ITEMS_FILE", content_file), patch.object(generation_pipeline, "BRIEFS_FILE", briefs_file):
                generation_pipeline.build_generation_briefs(limit=10, trace={"run_id": "new-brief-run", "task_id": "new-brief-task"})

            briefs = read_jsonl(briefs_file)
            self.assertEqual(briefs[0]["status"], "approved")
            self.assertEqual(briefs[0]["source_run_id"], "locked-brief-run")
            self.assertEqual(briefs[0]["source_task_id"], "locked-brief-task")
            self.assertEqual(briefs[0]["applied_run_id"], "approved-brief-run")
            self.assertEqual(briefs[0]["applied_task_id"], "approved-brief-task")
            self.assertEqual(briefs[0]["applied_packet_id"], "approved-brief-packet")

    def test_build_generation_briefs_reopens_rejected_status_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "cards.jsonl"
            topics_file = Path(tmp) / "topics.jsonl"
            content_file = Path(tmp) / "content_items.jsonl"
            briefs_file = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(cards_file, [{
                "id": "knowledge:1",
                "title": "卡片一",
                "source_item_id": "item-1",
                "summary": "新摘要",
                "sources": ["source-a"],
                "status": "approved",
                "projected_score": 0.8,
                "feedback_projection_delta": 0.8,
                "projected_action": "build_knowledge_candidate",
                "projected_action_label": "进入知识候选",
                "projected_action_reason": "AI",
            }])
            write_jsonl(topics_file, [{"source_item_id": "item-1", "title": "主题一"}])
            write_jsonl(content_file, [])
            write_jsonl(briefs_file, [{
                "id": "brief:knowledge:1",
                "title": "旧标题",
                "topic": "旧主题",
                "summary": "旧摘要",
                "status": "rejected",
            }])

            with patch.object(generation_pipeline, "CARDS_INDEX_FILE", cards_file), patch.object(generation_pipeline, "TOPICS_INDEX_FILE", topics_file), patch.object(generation_pipeline, "CONTENT_ITEMS_FILE", content_file), patch.object(generation_pipeline, "BRIEFS_FILE", briefs_file):
                generation_pipeline.build_generation_briefs(limit=10)

            briefs = read_jsonl(briefs_file)
            self.assertEqual(briefs[0]["status"], "candidate")

    def test_build_generation_briefs_upserts_existing_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            cards_file = Path(tmp) / "cards.jsonl"
            topics_file = Path(tmp) / "topics.jsonl"
            content_file = Path(tmp) / "content_items.jsonl"
            briefs_file = Path(tmp) / "generation_briefs.jsonl"
            write_jsonl(cards_file, [{
                "id": "knowledge:1",
                "title": "卡片一",
                "source_item_id": "item-1",
                "summary": "新摘要",
                "sources": ["source-a"],
                "status": "approved",
                "projected_score": 0.8,
                "feedback_projection_delta": 0.8,
                "projected_action": "build_knowledge_candidate",
                "projected_action_label": "进入知识候选",
                "projected_action_reason": "AI",
            }])
            write_jsonl(topics_file, [{"source_item_id": "item-1", "title": "主题一"}])
            write_jsonl(content_file, [])
            write_jsonl(briefs_file, [{
                "id": "brief:knowledge:1",
                "title": "旧标题",
                "topic": "旧主题",
                "summary": "旧摘要",
                "status": "candidate",
            }])

            with patch.object(generation_pipeline, "CARDS_INDEX_FILE", cards_file), patch.object(generation_pipeline, "TOPICS_INDEX_FILE", topics_file), patch.object(generation_pipeline, "CONTENT_ITEMS_FILE", content_file), patch.object(generation_pipeline, "BRIEFS_FILE", briefs_file):
                result = generation_pipeline.build_generation_briefs(limit=10, trace={"run_id": "run-brief", "task_id": "task-brief"})

            briefs = read_jsonl(briefs_file)
            self.assertEqual(result.created, 1)
            self.assertEqual(len(briefs), 1)
            self.assertEqual(briefs[0]["id"], "brief:knowledge:1")
            self.assertEqual(briefs[0]["title"], "卡片一")
            self.assertEqual(briefs[0]["summary"], "新摘要")
            self.assertEqual(briefs[0]["topic"], "主题一")
            self.assertEqual(briefs[0]["source_run_id"], "run-brief")
            self.assertEqual(briefs[0]["source_task_id"], "task-brief")


class GeoPipelineTests(unittest.TestCase):
    def test_build_geo_variants_returns_result_and_update_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = Path(tmp) / "drafts.jsonl"
            geo_path = Path(tmp) / "geo_variants.jsonl"
            write_jsonl(draft_path, [{
                "id": "draft:1",
                "title": "测试 Draft",
                "topic": "测试主题",
                "sources": ["source-a", "source-b"],
                "status": "approved",
            }])

            with patch.object(geo_pipeline, "DRAFTS_FILE", draft_path), patch.object(geo_pipeline, "GEO_FILE", geo_path):
                result = geo_pipeline.build_geo_variants("draft:1", trace={"run_id": "run-geo", "task_id": "task-geo"})
                status_result = geo_pipeline.update_geo_variant_status("draft:1", "edited", trace={"run_id": "run-geo-apply", "task_id": "task-geo-apply", "packet_id": "packet-geo"})

            self.assertEqual(result.created, 1)
            self.assertEqual(result.geo_id, "geo:draft:1")
            self.assertEqual(result.title, "测试 Draft")
            self.assertEqual(result.topic, "测试主题")
            self.assertEqual(result.sample_titles[0], "测试 Draft")
            self.assertEqual(result.qa_count, 2)
            self.assertEqual(result.faq_count, 2)
            self.assertEqual(result.source_run_id, "run-geo")
            self.assertEqual(result.source_task_id, "task-geo")
            self.assertEqual(status_result["status"], "approved")
            variants = read_jsonl(geo_path)
            self.assertEqual(len(variants), 1)
            self.assertEqual(variants[0]["status"], "approved")
            self.assertEqual(variants[0]["source_run_id"], "run-geo")
            self.assertEqual(variants[0]["source_task_id"], "task-geo")
            self.assertEqual(variants[0]["applied_run_id"], "run-geo-apply")
            self.assertEqual(variants[0]["applied_task_id"], "task-geo-apply")
            self.assertEqual(variants[0]["applied_packet_id"], "packet-geo")

    def test_build_geo_variants_requires_approved_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = Path(tmp) / "drafts.jsonl"
            geo_path = Path(tmp) / "geo_variants.jsonl"
            write_jsonl(draft_path, [{
                "id": "draft:1",
                "title": "测试 Draft",
                "topic": "测试主题",
                "sources": ["source-a", "source-b"],
                "status": "candidate",
            }])

            with patch.object(geo_pipeline, "DRAFTS_FILE", draft_path), patch.object(geo_pipeline, "GEO_FILE", geo_path):
                with self.assertRaisesRegex(RuntimeError, "草稿尚未批准"):
                    geo_pipeline.build_geo_variants("draft:1")

    def test_build_geo_variants_preserves_existing_approved_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = Path(tmp) / "drafts.jsonl"
            geo_path = Path(tmp) / "geo_variants.jsonl"
            write_jsonl(draft_path, [{
                "id": "draft:1",
                "title": "测试 Draft",
                "topic": "测试主题",
                "sources": ["source-a", "source-b"],
                "status": "approved",
            }])
            write_jsonl(geo_path, [{
                "id": "geo:draft:1",
                "draft_id": "draft:1",
                "title": "旧 Draft",
                "topic": "旧主题",
                "qa_summary": [],
                "faq": [],
                "status": "approved",
                "source_run_id": "locked-geo-run",
                "source_task_id": "locked-geo-task",
                "applied_run_id": "approved-geo-run",
                "applied_task_id": "approved-geo-task",
                "applied_packet_id": "approved-geo-packet",
            }])

            with patch.object(geo_pipeline, "DRAFTS_FILE", draft_path), patch.object(geo_pipeline, "GEO_FILE", geo_path):
                result = geo_pipeline.build_geo_variants("draft:1", trace={"run_id": "new-geo-run", "task_id": "new-geo-task"})

            variants = read_jsonl(geo_path)
            self.assertEqual(variants[0]["status"], "approved")
            self.assertEqual(variants[0]["source_run_id"], "locked-geo-run")
            self.assertEqual(variants[0]["source_task_id"], "locked-geo-task")
            self.assertEqual(variants[0]["applied_run_id"], "approved-geo-run")
            self.assertEqual(variants[0]["applied_task_id"], "approved-geo-task")
            self.assertEqual(variants[0]["applied_packet_id"], "approved-geo-packet")
            self.assertEqual(result.source_run_id, "locked-geo-run")
            self.assertEqual(result.source_task_id, "locked-geo-task")

    def test_build_geo_variants_reopens_rejected_status_on_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = Path(tmp) / "drafts.jsonl"
            geo_path = Path(tmp) / "geo_variants.jsonl"
            write_jsonl(draft_path, [{
                "id": "draft:1",
                "title": "测试 Draft",
                "topic": "测试主题",
                "sources": ["source-a", "source-b"],
                "status": "approved",
            }])
            write_jsonl(geo_path, [{
                "id": "geo:draft:1",
                "draft_id": "draft:1",
                "title": "旧 Draft",
                "topic": "旧主题",
                "qa_summary": [],
                "faq": [],
                "status": "rejected",
            }])

            with patch.object(geo_pipeline, "DRAFTS_FILE", draft_path), patch.object(geo_pipeline, "GEO_FILE", geo_path):
                geo_pipeline.build_geo_variants("draft:1")

            variants = read_jsonl(geo_path)
            self.assertEqual(variants[0]["status"], "candidate")

    def test_build_geo_variants_upserts_existing_variant(self):
        with tempfile.TemporaryDirectory() as tmp:
            draft_path = Path(tmp) / "drafts.jsonl"
            geo_path = Path(tmp) / "geo_variants.jsonl"
            write_jsonl(draft_path, [{
                "id": "draft:1",
                "title": "新 Draft",
                "topic": "新主题",
                "sources": ["source-a"],
                "status": "approved",
            }])
            write_jsonl(geo_path, [{
                "id": "geo:draft:1",
                "draft_id": "draft:1",
                "title": "旧 Draft",
                "topic": "旧主题",
                "qa_summary": [],
                "faq": [],
                "status": "candidate",
            }])

            with patch.object(geo_pipeline, "DRAFTS_FILE", draft_path), patch.object(geo_pipeline, "GEO_FILE", geo_path):
                result = geo_pipeline.build_geo_variants("draft:1")

            variants = read_jsonl(geo_path)
            self.assertEqual(result.created, 1)
            self.assertEqual(len(variants), 1)
            self.assertEqual(variants[0]["id"], "geo:draft:1")
            self.assertEqual(variants[0]["title"], "新 Draft")
            self.assertEqual(variants[0]["topic"], "新主题")
            self.assertEqual(len(variants[0]["qa_summary"]), 2)


class GenerationApiTests(unittest.TestCase):
    def test_build_generation_draft_api_returns_404_for_missing_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.build_draft_from_brief", side_effect=RuntimeError("brief 不存在")):
                with self.assertRaises(api.HTTPException) as ctx:
                    api.build_generation_draft_api("brief:1")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("brief 不存在", str(ctx.exception.detail))

    def test_build_generation_draft_api_returns_409_for_unapproved_brief(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.build_draft_from_brief", side_effect=RuntimeError("写作提纲尚未批准，不能生成草稿")):
                with self.assertRaises(api.HTTPException) as ctx:
                    api.build_generation_draft_api("brief:1")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("写作提纲尚未批准", str(ctx.exception.detail))

    def test_build_generation_draft_api_skips_review_packet_for_approved_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.content_loop.build_draft_from_brief", return_value=type("DraftResult", (), {"__dict__": {"draft_id": "draft:1", "brief_id": "brief:1", "created": 1, "drafts_file": "drafts.jsonl", "title": "草稿一", "topic": "主题一", "sample_titles": ["草稿一"], "summary": "摘要", "status": "approved", "review_required": False}})()):
                result = api.build_generation_draft_api("brief:1")

        self.assertIsNone(result["review_packet"])
        self.assertEqual(result["run"]["status"], "completed")

    def test_build_geo_variants_api_returns_404_for_missing_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.build_geo_variants", side_effect=RuntimeError("draft 不存在")):
                with self.assertRaises(api.HTTPException) as ctx:
                    api.build_geo_variants_api("draft:1")

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("draft 不存在", str(ctx.exception.detail))

    def test_build_geo_variants_api_returns_409_for_unapproved_draft(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.build_geo_variants", side_effect=RuntimeError("草稿尚未批准，不能生成 GEO 变体")):
                with self.assertRaises(api.HTTPException) as ctx:
                    api.build_geo_variants_api("draft:1")

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("草稿尚未批准", str(ctx.exception.detail))

    def test_build_geo_variants_api_skips_review_packet_for_approved_rerun(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.content_loop.build_geo_variants", return_value=type("GeoResult", (), {"__dict__": {"geo_id": "geo:draft:1", "draft_id": "draft:1", "created": 1, "geo_file": "geo.jsonl", "title": "GEO 一", "topic": "主题一", "sample_titles": ["GEO 一"], "qa_count": 2, "faq_count": 2, "status": "approved", "review_required": False}})()):
                result = api.build_geo_variants_api("draft:1")

        self.assertIsNone(result["review_packet"])
        self.assertEqual(result["run"]["status"], "completed")


class ExecutionReviewTests(unittest.TestCase):
    def test_execute_sync_action_marks_task_waiting_human_until_review_resolved(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir):
                execution = execute_sync_action(
                    intent="build_draft",
                    task_kind="build_draft",
                    context={"brief_id": "brief:1"},
                    artifact_type="draft",
                    action=lambda: {"draft_id": "draft:1"},
                    summarize=lambda payload: f"生成草稿：{payload['draft_id']}",
                    build_review=lambda payload: build_review_packet(
                        kind="draft_review",
                        run_id="",
                        task_id="",
                        reason="等待人工确认",
                        candidate_payload=payload,
                        suggested_action="review_draft",
                    ),
                )
                run_id = execution["run"]["run_id"]
                packet_id = execution["review_packet"]["packet_id"]
                tasks_before = store.read_tasks(run_id)

                resolved = store.resolve_review_packet(run_id, packet_id, status="approved")
                tasks_after = store.read_tasks(run_id)
                run = store.read_run(run_id)

            self.assertEqual(execution["run"]["status"], "action_required")
            self.assertEqual(execution["task"]["status"], "waiting_human")
            self.assertEqual(tasks_before[-1]["status"], "waiting_human")
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved["status"], "approved")
            self.assertEqual(tasks_after[-1]["status"], "approved")
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "completed")

    def test_resolve_review_packet_updates_task_by_packet_task_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir):
                run = ExecutionRun(
                    run_id="run-multi-task",
                    intent="build_briefs",
                    status="action_required",
                    trigger="user",
                    started_at="2026-05-14T10:00:00+08:00",
                    summary="待审批",
                )
                store.write_run(run)
                store.write_tasks("run-multi-task", [
                    ExecutionTask(task_id="task-a", run_id="run-multi-task", kind="build_generation_briefs", status="waiting_human"),
                    ExecutionTask(task_id="task-b", run_id="run-multi-task", kind="log_flush", status="running"),
                ])
                store.write_review_packets("run-multi-task", [
                    ReviewPacket(packet_id="packet-a", run_id="run-multi-task", task_id="task-a", kind="generation_briefs_review", reason="等待人工确认"),
                ])

                resolved = store.resolve_review_packet("run-multi-task", "packet-a", status="approved")
                tasks_after = store.read_tasks("run-multi-task")

            self.assertIsNotNone(resolved)
            task_by_id = {task["task_id"]: task for task in tasks_after}
            self.assertEqual(task_by_id["task-a"]["status"], "approved")
            self.assertEqual(task_by_id["task-b"]["status"], "running")

    def test_resolve_review_packet_can_defer_source_run_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir):
                execution = execute_sync_action(
                    intent="build_draft",
                    task_kind="build_draft",
                    context={"brief_id": "brief:1"},
                    artifact_type="draft",
                    action=lambda: {"draft_id": "draft:1"},
                    summarize=lambda payload: f"生成草稿：{payload['draft_id']}",
                    build_review=lambda payload: build_review_packet(
                        kind="draft_review",
                        run_id="",
                        task_id="",
                        reason="等待人工确认",
                        candidate_payload=payload,
                        suggested_action="review_draft",
                    ),
                )
                run_id = execution["run"]["run_id"]
                packet_id = execution["review_packet"]["packet_id"]

                resolved = store.resolve_review_packet(run_id, packet_id, status="approved", finalize_run=False)
                run = store.read_run(run_id)
                tasks_after = store.read_tasks(run_id)

            self.assertIsNotNone(resolved)
            self.assertEqual(resolved["status"], "approved")
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "running")
            self.assertEqual(run["finished_at"], "")
            self.assertEqual(tasks_after[-1]["status"], "approved")

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir):
                execution = execute_sync_action(
                    intent="build_draft",
                    task_kind="build_draft",
                    context={"brief_id": "brief:1"},
                    artifact_type="draft",
                    action=lambda: {"draft_id": "draft:1"},
                    summarize=lambda payload: f"生成草稿：{payload['draft_id']}",
                    build_review=lambda payload: build_review_packet(
                        kind="draft_review",
                        run_id="",
                        task_id="",
                        reason="等待人工确认",
                        candidate_payload=payload,
                        suggested_action="review_draft",
                    ),
                )
                run_id = execution["run"]["run_id"]
                packet_id = execution["review_packet"]["packet_id"]

                resolved = store.resolve_review_packet(run_id, packet_id, status="rejected")
                tasks_after = store.read_tasks(run_id)
                run = store.read_run(run_id)

            self.assertIsNotNone(resolved)
            self.assertEqual(resolved["status"], "rejected")
            self.assertEqual(tasks_after[-1]["status"], "rejected")
            self.assertIsNotNone(run)
            self.assertEqual(run["status"], "rejected")
            self.assertEqual(run["failure_state"]["code"], "review_rejected")


if __name__ == "__main__":
    unittest.main()
