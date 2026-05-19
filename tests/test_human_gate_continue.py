from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api
from src.execution import store
from src.execution.models import ExecutionRun, ReviewPacket


class HumanGateContinueTests(unittest.TestCase):
    def test_knowledge_review_continue_returns_execution_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.apply_reviewed_knowledge_candidates", return_value={"written_cards": 1, "written_topics": 1, "cards_index_file": "cards.jsonl", "topics_index_file": "topics.jsonl", "export_root": "tmp"}), patch("src.llm_wiki_bridge.update_knowledge_candidate_status", lambda status, **kwargs: {"status": status, **kwargs}):
                run = ExecutionRun(run_id="run-a", intent="build_knowledge", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="知识候选待确认")
                store.write_run(run)
                store.write_review_packets("run-a", [ReviewPacket(packet_id="packet-a", run_id="run-a", task_id="task-a", kind="knowledge_candidates_review", reason="知识候选待确认", candidate_payload={"candidates": 2, "synthesis": 1})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-a", "packet-a", body)

            self.assertIn("follow_up_result", result)
            self.assertEqual(result["follow_up_result"]["run"]["intent"], "apply_knowledge")
            self.assertEqual(result["follow_up_result"]["run"]["trigger"], "system")
            self.assertEqual(result["follow_up_result"]["result"]["written_cards"], 1)
            self.assertEqual(result["follow_up_result"]["result"]["written_topics"], 1)

    def test_knowledge_review_continue_accepts_edited_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.apply_reviewed_knowledge_candidates", return_value={"written_cards": 1, "written_topics": 1, "cards_index_file": "cards.jsonl", "topics_index_file": "topics.jsonl", "export_root": "tmp"}), patch("src.llm_wiki_bridge.update_knowledge_candidate_status", lambda status, **kwargs: {"status": status, **kwargs}):
                run = ExecutionRun(run_id="run-a-edit", intent="build_knowledge", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="知识候选待确认")
                store.write_run(run)
                store.write_review_packets("run-a-edit", [ReviewPacket(packet_id="packet-a-edit", run_id="run-a-edit", task_id="task-a", kind="knowledge_candidates_review", reason="知识候选待确认", candidate_payload={"candidates": 2, "synthesis": 1})])
                body = api.ReviewPacketResolveRequest(status="edited", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-a-edit", "packet-a-edit", body)

            self.assertEqual(result["status"], "edited")
            self.assertIn("follow_up_result", result)
            self.assertEqual(result["follow_up_result"]["run"]["intent"], "apply_knowledge")
            self.assertEqual(result["follow_up_result"]["result"]["written_cards"], 1)

    def test_brief_review_continue_keeps_draft_human_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.content_loop.update_generation_status", lambda *args, **kwargs: {"updated": 1}), patch("src.content_loop.build_draft_from_brief", return_value=type("DraftResult", (), {"__dict__": {"draft_id": "draft:brief:1", "brief_id": "brief:1", "created": 1, "drafts_file": "drafts.jsonl", "title": "草稿一", "topic": "主题一", "sample_titles": ["草稿一"], "summary": "摘要"}})()):
                run = ExecutionRun(run_id="run-b", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="写作提纲待确认")
                store.write_run(run)
                store.write_review_packets("run-b", [ReviewPacket(packet_id="packet-b", run_id="run-b", task_id="task-b", kind="generation_briefs_review", reason="写作提纲待确认", candidate_payload={"brief_ids": ["brief:1"]})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-b", "packet-b", body)

            self.assertIn("follow_up_result", result)
            self.assertEqual(result["follow_up_result"]["run"]["status"], "action_required")
            self.assertEqual(result["follow_up_result"]["review_packet"]["kind"], "draft_review")
            self.assertEqual(result["follow_up_result"]["result"]["draft_id"], "draft:brief:1")

    def test_brief_review_continue_runs_all_briefs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            build_calls: list[str] = []

            def fake_build_draft(brief_id: str, trace: dict | None = None):
                build_calls.append(brief_id)
                return type("DraftResult", (), {"__dict__": {"draft_id": f"draft:{brief_id}", "brief_id": brief_id, "created": 1, "drafts_file": "drafts.jsonl", "title": f"草稿 {brief_id}", "topic": f"主题 {brief_id}", "sample_titles": [f"草稿 {brief_id}"], "summary": f"摘要 {brief_id}"}})()

            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.content_loop.update_generation_status", lambda *args, **kwargs: {"updated": 1}), patch("src.content_loop.build_draft_from_brief", side_effect=fake_build_draft):
                run = ExecutionRun(run_id="run-c", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="写作提纲批量待确认")
                store.write_run(run)
                store.write_review_packets("run-c", [ReviewPacket(packet_id="packet-c", run_id="run-c", task_id="task-c", kind="generation_briefs_review", reason="写作提纲批量待确认", candidate_payload={"brief_ids": ["brief:1", "brief:2"]})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-c", "packet-c", body)
                source_run = store.read_run("run-c")

            self.assertEqual(build_calls, ["brief:1", "brief:2"])
            self.assertIn("follow_up_result", result)
            self.assertIn("follow_up_results", result)
            self.assertEqual(len(result["follow_up_results"]), 2)
            self.assertEqual(result["follow_up_results"][0]["result"]["draft_id"], "draft:brief:1")
            self.assertEqual(result["follow_up_results"][1]["result"]["draft_id"], "draft:brief:2")
            self.assertIsNotNone(source_run)
            self.assertEqual(source_run["status"], "completed")

    def test_brief_review_continue_captures_partial_follow_up_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            build_calls: list[str] = []

            def fake_build_draft(brief_id: str, trace: dict | None = None):
                build_calls.append(brief_id)
                if brief_id == "brief:2":
                    raise RuntimeError("brief:2 生成失败")
                return type("DraftResult", (), {"__dict__": {"draft_id": f"draft:{brief_id}", "brief_id": brief_id, "created": 1, "drafts_file": "drafts.jsonl", "title": f"草稿 {brief_id}", "topic": f"主题 {brief_id}", "sample_titles": [f"草稿 {brief_id}"], "summary": f"摘要 {brief_id}"}})()

            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.content_loop.update_generation_status", lambda *args, **kwargs: {"updated": 1}), patch("src.content_loop.build_draft_from_brief", side_effect=fake_build_draft):
                run = ExecutionRun(run_id="run-c-partial", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="写作提纲批量待确认")
                store.write_run(run)
                store.write_review_packets("run-c-partial", [ReviewPacket(packet_id="packet-c-partial", run_id="run-c-partial", task_id="task-c", kind="generation_briefs_review", reason="写作提纲批量待确认", candidate_payload={"brief_ids": ["brief:1", "brief:2"]})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-c-partial", "packet-c-partial", body)

            self.assertEqual(build_calls, ["brief:1", "brief:2"])
            self.assertIn("follow_up_result", result)
            self.assertIn("follow_up_results", result)
            self.assertIn("follow_up_errors", result)
            self.assertEqual(len(result["follow_up_results"]), 1)
            self.assertEqual(result["follow_up_results"][0]["result"]["draft_id"], "draft:brief:1")
            self.assertEqual(result["follow_up_errors"], [{"target_id": "brief:2", "error": "brief:2 生成失败"}])

    def test_brief_review_all_follow_up_failures_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"

            def fake_build_draft(brief_id: str, trace: dict | None = None):
                raise RuntimeError(f"{brief_id} 生成失败")

            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.update_generation_status", lambda *args, **kwargs: {"updated": 1}), patch("src.content_loop.build_draft_from_brief", side_effect=fake_build_draft):
                run = ExecutionRun(run_id="run-c-all-fail", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="写作提纲批量待确认")
                store.write_run(run)
                store.write_review_packets("run-c-all-fail", [ReviewPacket(packet_id="packet-c-all-fail", run_id="run-c-all-fail", task_id="task-c", kind="generation_briefs_review", reason="写作提纲批量待确认", candidate_payload={"brief_ids": ["brief:1", "brief:2"]})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-c-all-fail", "packet-c-all-fail", body)
                source_run = store.read_run("run-c-all-fail")

            self.assertNotIn("follow_up_result", result)
            self.assertNotIn("follow_up_results", result)
            self.assertEqual(result["follow_up_errors"], [
                {"target_id": "brief:1", "error": "brief:1 生成失败"},
                {"target_id": "brief:2", "error": "brief:2 生成失败"},
            ])
            self.assertIsNotNone(source_run)
            self.assertEqual(source_run["status"], "degraded")

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"

            def fake_build_draft(brief_id: str, trace: dict | None = None):
                if brief_id == "brief:2":
                    raise RuntimeError("brief:2 生成失败")
                return type("DraftResult", (), {"__dict__": {"draft_id": f"draft:{brief_id}", "brief_id": brief_id, "created": 1, "drafts_file": "drafts.jsonl", "title": f"草稿 {brief_id}", "topic": f"主题 {brief_id}", "sample_titles": [f"草稿 {brief_id}"], "summary": f"摘要 {brief_id}"}})()

            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.update_generation_status", lambda *args, **kwargs: {"updated": 1}), patch("src.content_loop.build_draft_from_brief", side_effect=fake_build_draft):
                run = ExecutionRun(run_id="run-c-degraded", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="写作提纲批量待确认")
                store.write_run(run)
                store.write_review_packets("run-c-degraded", [ReviewPacket(packet_id="packet-c-degraded", run_id="run-c-degraded", task_id="task-c", kind="generation_briefs_review", reason="写作提纲批量待确认", candidate_payload={"brief_ids": ["brief:1", "brief:2"]})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-c-degraded", "packet-c-degraded", body)
                source_run = store.read_run("run-c-degraded")

            self.assertIn("follow_up_errors", result)
            self.assertIsNotNone(source_run)
            self.assertEqual(source_run["status"], "degraded")
            self.assertEqual(source_run["failure_state"]["code"], "partial_follow_up_failure")

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            build_calls: list[str] = []

            def fake_build_draft(brief_id: str, trace: dict | None = None):
                build_calls.append(brief_id)
                return type("DraftResult", (), {"__dict__": {"draft_id": f"draft:{brief_id}", "brief_id": brief_id, "created": 1, "drafts_file": "drafts.jsonl", "title": f"草稿 {brief_id}", "topic": f"主题 {brief_id}", "sample_titles": [f"草稿 {brief_id}"], "summary": f"摘要 {brief_id}"}})()

            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.content_loop.update_generation_status", lambda *args, **kwargs: {"updated": 1}), patch("src.content_loop.build_draft_from_brief", side_effect=fake_build_draft):
                run = ExecutionRun(run_id="run-c-edit", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="写作提纲批量待确认")
                store.write_run(run)
                store.write_review_packets("run-c-edit", [ReviewPacket(packet_id="packet-c-edit", run_id="run-c-edit", task_id="task-c", kind="generation_briefs_review", reason="写作提纲批量待确认", candidate_payload={"brief_ids": ["brief:1", "brief:2"]})])
                body = api.ReviewPacketResolveRequest(status="edited", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-c-edit", "packet-c-edit", body)

            self.assertEqual(build_calls, ["brief:1", "brief:2"])
            self.assertEqual(result["status"], "edited")
            self.assertEqual(len(result["follow_up_results"]), 2)

    def test_edited_resolution_continues_follow_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.apply_reviewed_knowledge_candidates", return_value={"written_cards": 1, "written_topics": 1, "cards_index_file": "cards.jsonl", "topics_index_file": "topics.jsonl", "export_root": "tmp"}), patch("src.llm_wiki_bridge.update_knowledge_candidate_status", lambda status, **kwargs: {"status": status, **kwargs}):
                run = ExecutionRun(run_id="run-edited-ui", intent="build_knowledge", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="知识候选待确认")
                store.write_run(run)
                store.write_review_packets("run-edited-ui", [ReviewPacket(packet_id="packet-edited-ui", run_id="run-edited-ui", task_id="task-a", kind="knowledge_candidates_review", reason="知识候选待确认", candidate_payload={"candidates": 1, "synthesis": 0})])
                body = api.ReviewPacketResolveRequest(status="edited", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-edited-ui", "packet-edited-ui", body)

            self.assertEqual(result["status"], "edited")
            self.assertIn("follow_up_result", result)
            self.assertEqual(result["follow_up_result"]["run"]["intent"], "apply_knowledge")

    def test_edited_resolution_can_skip_follow_up(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.apply_reviewed_knowledge_candidates", return_value={"written_cards": 1, "written_topics": 1, "cards_index_file": "cards.jsonl", "topics_index_file": "topics.jsonl", "export_root": "tmp"}) as apply_mock, patch("src.llm_wiki_bridge.update_knowledge_candidate_status", lambda status, **kwargs: {"status": status, **kwargs}):
                run = ExecutionRun(run_id="run-edited-no-follow-up", intent="build_knowledge", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="知识候选待确认")
                store.write_run(run)
                store.write_review_packets("run-edited-no-follow-up", [ReviewPacket(packet_id="packet-edited-no-follow-up", run_id="run-edited-no-follow-up", task_id="task-a", kind="knowledge_candidates_review", reason="知识候选待确认", candidate_payload={"candidates": 1, "synthesis": 0})])
                body = api.ReviewPacketResolveRequest(status="edited", continue_after_resolve=False)

                result = api.resolve_execution_review_packet("run-edited-no-follow-up", "packet-edited-no-follow-up", body)

            self.assertEqual(result["status"], "edited")
            self.assertNotIn("follow_up_result", result)
            apply_mock.assert_not_called()

    def test_brief_review_partial_follow_up_failure_does_not_mark_source_completed_first(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"

            def fake_build_draft(brief_id: str, trace: dict | None = None):
                if brief_id == "brief:2":
                    raise RuntimeError("brief:2 生成失败")
                return type("DraftResult", (), {"__dict__": {"draft_id": f"draft:{brief_id}", "brief_id": brief_id, "created": 1, "drafts_file": "drafts.jsonl", "title": f"草稿 {brief_id}", "topic": f"主题 {brief_id}", "sample_titles": [f"草稿 {brief_id}"], "summary": f"摘要 {brief_id}"}})()

            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.update_generation_status", lambda *args, **kwargs: {"updated": 1}), patch("src.content_loop.build_draft_from_brief", side_effect=fake_build_draft):
                run = ExecutionRun(run_id="run-c-no-completed-gap", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="写作提纲批量待确认")
                store.write_run(run)
                store.write_review_packets("run-c-no-completed-gap", [ReviewPacket(packet_id="packet-c-no-completed-gap", run_id="run-c-no-completed-gap", task_id="task-c", kind="generation_briefs_review", reason="写作提纲批量待确认", candidate_payload={"brief_ids": ["brief:1", "brief:2"]})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                api.resolve_execution_review_packet("run-c-no-completed-gap", "packet-c-no-completed-gap", body)
                events = store.read_events("run-c-no-completed-gap", limit=20)
                source_run = store.read_run("run-c-no-completed-gap")

            self.assertIsNotNone(source_run)
            self.assertEqual(source_run["status"], "degraded")
            self.assertNotIn("run_completed", [entry.get("type") for entry in events])
            self.assertIn("run_degraded", [entry.get("type") for entry in events])

    def test_build_knowledge_candidates_api_keeps_topic_only_review_packet(self):
        with patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.build_knowledge_candidates", return_value=type("KnowledgeResult", (), {"__dict__": {"export_root": "tmp", "candidates": 0, "entities": 0, "concepts": 0, "synthesis": 1, "cards_index_file": "cards.jsonl", "topics_index_file": "topics.jsonl", "sample_titles": ["主题一"], "candidate_card_ids": [], "candidate_topic_ids": ["topic:AI"]}})()):
            result = api.build_wiki_knowledge_candidates(limit=5)

        self.assertEqual(result["run"]["intent"], "build_knowledge")
        self.assertIsNotNone(result["review_packet"])
        self.assertEqual(result["review_packet"]["kind"], "knowledge_candidates_review")
        self.assertEqual(result["review_packet"]["candidate_payload"]["candidate_topic_ids"], ["topic:AI"])

    def test_build_topic_synthesis_api_uses_dedicated_intent(self):
        with patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.build_topic_synthesis_candidates", return_value=type("TopicSynthesisResult", (), {"__dict__": {"export_root": "tmp", "synthesis": 2, "topics_index_file": "topics.jsonl", "sample_titles": ["主题一", "主题二"], "candidate_topic_ids": ["topic:1", "topic:2"]}})()):
            result = api.build_wiki_topic_synthesis(limit=5, item_ids="item-1,item-2")

        self.assertEqual(result["run"]["intent"], "build_topic_synthesis")
        self.assertEqual(result["task"]["kind"], "build_topic_synthesis")
        self.assertEqual(result["review_packet"]["candidate_payload"]["candidate_topic_ids"], ["topic:1", "topic:2"])
        self.assertEqual(result["result"]["synthesis"], 2)
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir), patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.apply_reviewed_knowledge_candidates", return_value={"written_cards": 0, "written_topics": 2, "cards_index_file": "cards.jsonl", "topics_index_file": "topics.jsonl", "export_root": "tmp"}) as apply_mock, patch("src.llm_wiki_bridge.update_knowledge_candidate_status", lambda status, **kwargs: {"status": status, **kwargs}):
                run = ExecutionRun(run_id="run-d", intent="build_topic_synthesis", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="主题综合待确认")
                store.write_run(run)
                store.write_review_packets("run-d", [ReviewPacket(packet_id="packet-d", run_id="run-d", task_id="task-d", kind="topic_synthesis_review", reason="主题综合待确认", candidate_payload={"candidate_topic_ids": ["topic:1", "topic:2"], "synthesis": 2})])
                body = api.ReviewPacketResolveRequest(status="approved", continue_after_resolve=True)

                result = api.resolve_execution_review_packet("run-d", "packet-d", body)

            _, kwargs = apply_mock.call_args
            self.assertEqual(kwargs["card_ids"], [])
            self.assertEqual(kwargs["topic_ids"], ["topic:1", "topic:2"])
            self.assertEqual(result["follow_up_result"]["run"]["summary"], "知识入库：写入 cards 0 条，topics 2 条，未写入 0 项")
            self.assertEqual(result["follow_up_result"]["result"]["written_cards"], 0)
            self.assertEqual(result["follow_up_result"]["result"]["written_topics"], 2)

    def test_apply_reviewed_wiki_knowledge_can_limit_to_selected_ids(self):
        with patch.object(api, "_append_log", lambda *args, **kwargs: None), patch.object(api, "_append_execution_outcome", lambda *args, **kwargs: None), patch("src.llm_wiki_bridge.apply_reviewed_knowledge_candidates", return_value={"written_cards": 1, "written_topics": 1, "cards_index_file": "cards.jsonl", "topics_index_file": "topics.jsonl", "export_root": "tmp", "requested_ids": {"cards": ["knowledge:1", "knowledge:2"], "topics": ["topic:1"]}, "accepted_ids": {"cards": ["knowledge:1"], "topics": ["topic:1"]}, "rejected_ids": {"cards": ["knowledge:2"], "topics": []}}) as apply_mock:
            result = api.apply_reviewed_wiki_knowledge(card_ids="knowledge:1,knowledge:2", topic_ids="topic:1")

        _, kwargs = apply_mock.call_args
        self.assertEqual(kwargs["card_ids"], ["knowledge:1", "knowledge:2"])
        self.assertEqual(kwargs["topic_ids"], ["topic:1"])
        self.assertEqual(result["run"]["context"]["card_ids"], ["knowledge:1", "knowledge:2"])
        self.assertEqual(result["run"]["context"]["topic_ids"], ["topic:1"])
        self.assertEqual(result["run"]["summary"], "知识入库：写入 cards 1 条，topics 1 条，未写入 1 项")
        self.assertEqual(result["result"]["accepted_ids"], {"cards": ["knowledge:1"], "topics": ["topic:1"]})
        self.assertEqual(result["result"]["rejected_ids"], {"cards": ["knowledge:2"], "topics": []})

