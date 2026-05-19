from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api
from src.execution import store
from src.execution.models import ExecutionRun, ReviewPacket
from src.execution.orchestrator import execute_sync_action
from src.execution.review import build_review_packet


class ExecutionRejectedStateTests(unittest.TestCase):
    def test_rejected_review_marks_run_rejected(self):
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
                run = store.read_run(run_id)

            self.assertIsNotNone(resolved)
            self.assertEqual(resolved["status"], "rejected")
            self.assertEqual(run["status"], "rejected")
            self.assertEqual(run["failure_state"]["code"], "review_rejected")

    def test_append_execution_outcome_logs_rejected_status(self):
        emitted: list[tuple[str, str, dict | None]] = []

        def capture_log(log_type: str, message: str, details: dict | None = None):
            emitted.append((log_type, message, details))

        with patch.object(api, "_append_log", capture_log):
            api._append_execution_outcome(
                {"run_id": "run-1", "status": "rejected"},
                "人工闸门拒绝：packet-1",
                {"packet_id": "packet-1"},
            )

        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0][0], api.LOG_EXECUTION_RUN_REJECTED)
        self.assertEqual(emitted[0][1], "人工闸门拒绝：packet-1")
        self.assertEqual(emitted[0][2], {"run_id": "run-1", "execution_status": "rejected", "packet_id": "packet-1"})


if __name__ == "__main__":
    unittest.main()
