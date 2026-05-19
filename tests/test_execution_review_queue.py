from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.execution import store
from src.execution.models import ExecutionRun, ReviewPacket


class ExecutionReviewQueueTests(unittest.TestCase):
    def test_list_open_review_packets_aggregates_across_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with patch.object(store, "RUNS_DIR", runs_dir):
                run_a = ExecutionRun(run_id="run-a", intent="build_knowledge", status="action_required", trigger="user", started_at="2026-05-14T10:00:00+08:00", summary="知识候选待确认")
                run_b = ExecutionRun(run_id="run-b", intent="build_briefs", status="action_required", trigger="user", started_at="2026-05-14T11:00:00+08:00", summary="写作提纲待确认")
                run_c = ExecutionRun(run_id="run-c", intent="build_draft", status="action_required", trigger="user", started_at="2026-05-14T12:00:00+08:00", summary="草稿待确认")
                store.write_run(run_a)
                store.write_run(run_b)
                store.write_run(run_c)
                store.write_review_packets("run-a", [ReviewPacket(packet_id="packet-a", run_id="run-a", task_id="task-a", kind="knowledge_candidates_review", reason="知识候选待确认", candidate_payload={"candidates": 2, "synthesis": 1, "sample_titles": ["条目A", "条目B"], "candidate_card_ids": ["knowledge:1", "knowledge:2"], "candidate_topic_ids": ["topic:1"], "source_run_id": "run-knowledge", "source_task_id": "task-knowledge"})])
                store.write_review_packets("run-b", [
                    ReviewPacket(packet_id="packet-b", run_id="run-b", task_id="task-b", kind="generation_briefs_review", reason="写作提纲待确认", candidate_payload={"created": 2, "total_candidates": 5, "sample_titles": ["Brief A", "Brief B"], "brief_ids": ["brief:1", "brief:2"], "source_run_id": "run-brief", "source_task_id": "task-brief"}),
                ])
                store.write_review_packets("run-c", [
                    ReviewPacket(packet_id="packet-c", run_id="run-c", task_id="task-c", kind="draft_review", reason="草稿待确认", candidate_payload={"draft_id": "draft:1", "title": "草稿一", "source_run_id": "run-draft", "source_task_id": "task-draft"}),
                ])
                store.write_review_packets("run-d", [
                    ReviewPacket(packet_id="packet-d", run_id="run-d", task_id="task-d", kind="topic_synthesis_review", reason="主题综合待确认", candidate_payload={"candidates": 0, "synthesis": 2, "sample_titles": ["主题A", "主题B"], "candidate_topic_ids": ["topic:1", "topic:2"], "source_run_id": "run-topic", "source_task_id": "task-topic"}),
                ])
                store.write_review_packets("run-e", [
                    ReviewPacket(packet_id="packet-e", run_id="run-e", task_id="task-e", kind="geo_review", reason="GEO 待确认", candidate_payload={"geo_id": "geo:draft:1", "draft_id": "draft:1", "topic": "主题一", "qa_count": 2, "faq_count": 2, "source_run_id": "run-geo", "source_task_id": "task-geo", "applied_run_id": "run-geo-apply", "applied_task_id": "task-geo-apply", "applied_packet_id": "packet-geo"}),
                ])

                packets = store.list_open_review_packets()

            self.assertEqual(len(packets), 5)
            packets_by_id = {packet["packet_id"]: packet for packet in packets}
            self.assertEqual(packets_by_id["packet-d"]["preview"]["label"], "主题综合候选")
            self.assertEqual(packets_by_id["packet-d"]["preview"]["summary"], "主题 2 条")
            self.assertEqual(packets_by_id["packet-d"]["preview"]["details"]["topic_only"], True)
            self.assertEqual(packets_by_id["packet-d"]["follow_up"], {"action": "apply_reviewed_knowledge", "label": "批准并写入主题综合"})
            self.assertEqual(packets_by_id["packet-c"]["follow_up"], {"action": "build_geo_variants", "target_id": "draft:1", "label": "批准并生成 GEO 变体"})
            self.assertEqual(packets_by_id["packet-b"]["follow_up"], {"action": "build_generation_draft", "target_id": "brief:1", "target_ids": ["brief:1", "brief:2"], "count": 2, "label": "批准并生成 2 个草稿"})
            self.assertEqual(packets_by_id["packet-a"]["follow_up"], {"action": "apply_reviewed_knowledge", "label": "批准并入库"})
            self.assertEqual(packets_by_id["packet-b"]["preview"]["details"]["source_run_id"], "run-brief")
            self.assertEqual(packets_by_id["packet-b"]["preview"]["details"]["source_task_id"], "task-brief")
            self.assertEqual(packets_by_id["packet-c"]["preview"]["details"]["source_run_id"], "run-draft")
            self.assertEqual(packets_by_id["packet-c"]["preview"]["details"]["source_task_id"], "task-draft")
            self.assertEqual(packets_by_id["packet-a"]["preview"]["details"]["candidates"], 2)
            self.assertEqual(packets_by_id["packet-a"]["preview"]["details"]["card_ids"], ["knowledge:1", "knowledge:2"])


if __name__ == "__main__":
    unittest.main()
