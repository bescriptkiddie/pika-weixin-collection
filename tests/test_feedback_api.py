from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import api
from src.content_loop import feedback_projection


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


class FeedbackApiTests(unittest.TestCase):
    def test_content_loop_overview_endpoint_returns_store_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            feedback_file = Path(tmp) / "feedback_events.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            sources_file = Path(tmp) / "external_sources.json"
            write_jsonl(content_file, [{
                "id": "item-1",
                "source_type": "wechat_article",
                "human_decision": "adopted",
                "tags": ["AI"],
                "ai_summary": "summary",
            }])
            write_jsonl(feedback_file, [{"item_id": "item-1", "event": "raise_item_score"}])
            write_jsonl(projection_file, [{"scope": "tag", "key": "AI"}])
            sources_file.write_text(json.dumps({"sources": [{"id": "rss-a", "type": "rss", "name": "RSS A", "enabled": True}]}, ensure_ascii=False), encoding="utf-8")

            with patch("src.content_loop.store.CONTENT_ITEMS_FILE", content_file), patch("src.content_loop.store.FEEDBACK_EVENTS_FILE", feedback_file), patch("src.content_loop.store.FEEDBACK_PROJECTION_FILE", projection_file), patch("src.content_loop.store.EXTERNAL_SOURCES_FILE", sources_file), patch("src.content_loop.store.EXTERNAL_SOURCES_EXAMPLE_FILE", Path(tmp) / "missing.json"), patch("src.content_loop.store.DATA_DIR", Path(tmp)):
                result = api.content_loop_overview()

            self.assertEqual(result["content_items"], 1)
            self.assertEqual(result["feedback_events"], 1)
            self.assertEqual(result["feedback_projection_rules"], 1)
            self.assertEqual(result["enabled_external_sources"], 1)
            self.assertEqual(result["source_types"], {"wechat_article": 1})

    def test_content_loop_feedback_writes_event_and_updates_projection_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_file = Path(tmp) / "content_items.jsonl"
            feedback_file = Path(tmp) / "feedback_events.jsonl"
            projection_file = Path(tmp) / "feedback_projection.jsonl"
            write_jsonl(content_file, [{
                "id": "item-1",
                "title": "测试条目",
                "source_id": "source-a",
                "source_name": "来源A",
                "tags": ["AI"],
                "score": 0.0,
                "human_decision": "candidate",
                "feedback_notes": [],
                "content_markdown": "内容",
            }])
            body = api.FeedbackEventRequest(
                item_id="item-1",
                event="raise_item_score",
                human_decision="adopted",
                feedback_note="保留",
                suggested_action="raise_item_score",
            )

            with patch.object(api, "_append_log", lambda *args, **kwargs: None), patch("src.content_loop.store.CONTENT_ITEMS_FILE", content_file), patch("src.content_loop.store.FEEDBACK_EVENTS_FILE", feedback_file), patch("src.content_loop.store.FEEDBACK_PROJECTION_FILE", projection_file), patch.object(feedback_projection, "CONTENT_ITEMS_FILE", content_file), patch.object(feedback_projection, "FEEDBACK_EVENTS_FILE", feedback_file), patch.object(feedback_projection, "FEEDBACK_PROJECTION_FILE", projection_file):
                result = api.content_loop_feedback(body)
                summary = feedback_projection.summarize_feedback_projection(projection_path=projection_file, content_items_path=content_file)

            self.assertTrue(result["item_found"])
            events = read_jsonl(feedback_file)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["item_id"], "item-1")
            self.assertEqual(events[0]["human_decision"], "adopted")
            items = read_jsonl(content_file)
            self.assertEqual(items[0]["human_decision"], "adopted")
            self.assertEqual(items[0]["last_feedback_event"], "raise_item_score")
            self.assertEqual(items[0]["feedback_notes"], ["保留"])
            self.assertTrue(projection_file.exists())
            projection_rows = read_jsonl(projection_file)
            self.assertGreaterEqual(len(projection_rows), 1)
            recommended = next(row for row in summary["recommended_actions"] if row["action"] == "build_knowledge_candidate")
            self.assertEqual(recommended["count"], 1)
            self.assertEqual(recommended["execution_kind"], "build_knowledge_candidates")


if __name__ == "__main__":
    unittest.main()
