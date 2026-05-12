import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from src.content_loop.external_sources import (
    normalize_github_connector_references,
    parse_github_repo_url,
    sync_github_repo_source,
)
from src.content_loop.media_sources import (
    extract_bilibili_bvid,
    sync_bilibili_video_source,
    sync_podcast_feed_source,
    transcribe_audio_file,
)
from src.content_loop.source_configs import infer_source_type, upsert_media_source_config
from src.content_loop.store import (
    build_wechat_content_items,
    list_content_items,
    record_feedback_event,
    upsert_content_items,
)
from src.content_loop.tagging import apply_tags_to_content_items, get_tagging_overview
from src.content_loop.ai_enrichment import ai_enrich_content_items


class ContentLoopStoreTests(unittest.TestCase):
    def test_build_wechat_content_items_normalizes_article(self):
        message_info = {
            "测试号": {
                "blogs": [
                    {
                        "id": "2247-1-1776000000",
                        "title": "一篇文章",
                        "digest": "这是一段摘要",
                        "link": "https://example.com/a",
                        "cover": "https://example.com/c.jpg",
                        "create_time": "2026-04-12 10:20",
                        "is_deleted": False,
                        "tags": ["AI", "内容"],
                    }
                ]
            }
        }
        detail_texts = {"2247-1-1776000000": ["第一段", "第二段"]}

        items = build_wechat_content_items(message_info, detail_texts)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], "wechat_article:2247-1-1776000000")
        self.assertEqual(item["source_type"], "wechat_article")
        self.assertEqual(item["source_id"], "测试号")
        self.assertIn("第二段", item["content_markdown"])
        self.assertEqual(item["human_decision"], "candidate")

    def test_upsert_preserves_human_feedback_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_path = Path(tmp) / "content_items.jsonl"
            feedback_path = Path(tmp) / "feedback_events.jsonl"
            item = {
                "id": "wechat_article:1",
                "source_type": "wechat_article",
                "source_id": "a",
                "source_name": "A",
                "title": "old",
                "published_at": "2026-01-01",
                "content_markdown": "正文",
                "human_decision": "candidate",
                "feedback_notes": [],
            }
            upsert_content_items([item], path=content_path)
            record_feedback_event(
                item_id="wechat_article:1",
                event="content_pool_reviewed",
                human_decision="adopted",
                feedback_note="值得写",
                content_items_path=content_path,
                feedback_events_path=feedback_path,
            )
            newer = {**item, "title": "new", "human_decision": "candidate", "feedback_notes": []}
            upsert_content_items([newer], path=content_path)

            rows = list_content_items(path=content_path, include_content=True)
            self.assertEqual(rows[0]["title"], "new")
            self.assertEqual(rows[0]["human_decision"], "adopted")
            self.assertEqual(rows[0]["feedback_notes"], ["值得写"])


class ExternalSourceTests(unittest.TestCase):
    def test_parse_github_repo_url(self):
        self.assertEqual(
            parse_github_repo_url("https://github.com/Thysrael/Horizon.git"),
            ("Thysrael", "Horizon"),
        )

    def test_github_source_sync_builds_connector_reference_without_snapshot(self):
        class FakeResponse:
            def __init__(self, payload=None, text=""):
                self._payload = payload
                self.text = text
                self.status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeSession:
            def get(self, url, params=None, timeout=20):
                if url == "https://api.github.com/repos/acme/Horizon":
                    return FakeResponse({"default_branch": "main"})
                if url == "https://api.github.com/repos/acme/Horizon/readme":
                    return FakeResponse(
                        {
                            "download_url": "https://raw.example/readme.md",
                            "html_url": "https://github.com/acme/Horizon/blob/main/README.md",
                            "path": "README.md",
                        }
                    )
                if url == "https://raw.example/readme.md":
                    return FakeResponse(text="# Horizon\n\nAI news source workflow.")
                raise AssertionError(f"unexpected url: {url}")

        result = sync_github_repo_source(
            {
                "id": "horizon",
                "type": "github_repo",
                "name": "Horizon",
                "url": "https://github.com/acme/Horizon",
                "options": {"include": ["README"], "tags": ["外部源"], "snapshot_raw_sources": False},
            },
            session=FakeSession(),
        )

        self.assertEqual(result["items_fetched"], 1)
        self.assertFalse(result["snapshot_raw_sources"])
        item = result["content_items"][0]
        self.assertEqual(item["source_type"], "github_repo")
        self.assertEqual(item["metadata"]["fetch_mode"], "github_api")
        self.assertIn({"type": "github_repo", "source_id": "horizon", "repo_url": "https://github.com/acme/Horizon", "kind": "readme", "path": "README.md", "tag": "", "fetch_mode": "github_api"}, item["references"])
        self.assertNotIn("raw_source_file", item["metadata"])

    def test_normalize_github_connector_references_removes_raw_source_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            content_path = Path(tmp) / "content_items.jsonl"
            upsert_content_items(
                [
                    {
                        "id": "github_repo:horizon:readme",
                        "source_type": "github_repo",
                        "source_id": "horizon",
                        "source_name": "GitHub / Horizon",
                        "title": "Horizon README",
                        "url": "https://github.com/acme/Horizon/blob/main/README.md",
                        "published_at": "",
                        "content_markdown": "# Horizon",
                        "references": [
                            {"type": "url", "url": "https://github.com/acme/Horizon/blob/main/README.md"},
                            {"type": "llm_wiki_raw_source", "path": "raw/sources/github/horizon/readme.md"},
                        ],
                        "metadata": {"kind": "readme", "path": "README.md", "raw_source_file": "raw/sources/github/horizon/readme.md"},
                    }
                ],
                path=content_path,
            )

            result = normalize_github_connector_references(
                {"id": "horizon", "url": "https://github.com/acme/Horizon", "human_reason": "source"},
                content_items_path=content_path,
            )

            rows = list_content_items(path=content_path, include_content=True)
            refs = rows[0]["references"]
            self.assertEqual(result["references_normalized"], 1)
            self.assertFalse(any(ref.get("type") == "llm_wiki_raw_source" for ref in refs))
            self.assertTrue(any(ref.get("type") == "github_repo" for ref in refs))
            self.assertNotIn("raw_source_file", rows[0]["metadata"])


class MediaSourceTests(unittest.TestCase):
    def test_infer_media_source_type(self):
        self.assertEqual(
            infer_source_type("https://www.bilibili.com/video/BV1jb5767ECK/?spm_id_from=333"),
            "bilibili_video",
        )
        self.assertEqual(infer_source_type("https://example.com/podcast/feed.xml"), "podcast_feed")

    def test_upsert_media_source_config_writes_bilibili_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "external_sources.json"
            with patch(
                "src.content_loop.source_configs._fetch_bilibili_metadata",
                return_value={
                    "bvid": "BV1jb5767ECK",
                    "aid": 1,
                    "cid": 2,
                    "title": "题材里面重个股",
                    "owner": {"name": "米莱"},
                },
            ):
                result = upsert_media_source_config(
                    url="https://www.bilibili.com/video/BV1jb5767ECK/?spm_id_from=333",
                    name="",
                    config_path=config_path,
                )
                updated = upsert_media_source_config(
                    url="https://www.bilibili.com/video/BV1jb5767ECK/",
                    name="自定义标题",
                    transcribe=False,
                    config_path=config_path,
                )

        self.assertTrue(result["created"])
        self.assertFalse(updated["created"])
        self.assertTrue(updated["updated"])
        self.assertEqual(updated["sources_total"], 1)
        source = updated["source"]
        self.assertEqual(source["id"], "bilibili-bv1jb5767eck")
        self.assertEqual(source["type"], "bilibili_video")
        self.assertEqual(source["name"], "自定义标题")
        self.assertFalse(source["options"]["transcribe"])
        self.assertEqual(source["options"]["asr_provider"], "xiaomi_omni")
        self.assertEqual(source["options"]["max_completion_tokens"], 12000)

    def test_upsert_media_source_config_preserves_existing_source_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "external_sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "bilibili-custom",
                                "type": "bilibili_video",
                                "name": "已有名称",
                                "url": "https://www.bilibili.com/video/BV1jb5767ECK/",
                                "enabled": True,
                                "human_reason": "已有理由",
                                "options": {"tags": ["已有标签"], "initial_score": 0.8},
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            with patch(
                "src.content_loop.source_configs._fetch_bilibili_metadata",
                return_value={
                    "bvid": "BV1jb5767ECK",
                    "aid": 1,
                    "cid": 2,
                    "title": "题材里面重个股",
                    "owner": {"name": "米莱"},
                },
            ):
                result = upsert_media_source_config(
                    url="https://www.bilibili.com/video/BV1jb5767ECK/",
                    transcribe=False,
                    config_path=config_path,
                )

        source = result["source"]
        self.assertEqual(source["id"], "bilibili-custom")
        self.assertEqual(source["name"], "已有名称")
        self.assertEqual(source["human_reason"], "已有理由")
        self.assertEqual(source["options"]["tags"], ["已有标签"])
        self.assertFalse(source["options"]["transcribe"])

    def test_extract_bilibili_bvid(self):
        self.assertEqual(
            extract_bilibili_bvid("https://www.bilibili.com/video/BV1jb5767ECK/?spm_id_from=333"),
            "BV1jb5767ECK",
        )

    def test_bilibili_source_uses_official_subtitle_without_asr(self):
        class FakeResponse:
            def __init__(self, payload=None, text=""):
                self._payload = payload
                self.text = text
                self.status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        class FakeSession:
            def get(self, url, headers=None, timeout=30, **kwargs):
                if "x/web-interface/view" in url:
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "bvid": "BV1test",
                                "aid": 1,
                                "cid": 2,
                                "title": "测试视频",
                                "pubdate": 1778416536,
                                "duration": 60,
                                "pic": "https://example.com/cover.jpg",
                                "owner": {"name": "测试UP"},
                            },
                        }
                    )
                if "x/player/v2" in url:
                    return FakeResponse(
                        {
                            "code": 0,
                            "data": {
                                "subtitle": {
                                    "subtitles": [
                                        {"subtitle_url": "https://subtitle.example/subtitle.json"}
                                    ]
                                }
                            },
                        }
                    )
                if url == "https://subtitle.example/subtitle.json":
                    return FakeResponse(text=json.dumps({"body": [{"from": 1, "to": 3, "content": "第一句字幕"}]}))
                raise AssertionError(f"unexpected url: {url}")

        result = sync_bilibili_video_source(
            {
                "id": "test-video",
                "type": "bilibili_video",
                "name": "测试视频源",
                "url": "https://www.bilibili.com/video/BV1test/",
                "options": {"transcribe": True},
            },
            session=FakeSession(),
        )

        self.assertEqual(result["items_fetched"], 1)
        self.assertEqual(result["transcript_source"], "official_subtitle")
        item = result["content_items"][0]
        self.assertEqual(item["source_type"], "bilibili_video")
        self.assertIn("第一句字幕", item["content_markdown"])
        self.assertEqual(item["metadata"]["transcript_source"], "official_subtitle")

    def test_podcast_feed_source_imports_shownotes_without_audio_download(self):
        class FakeResponse:
            def __init__(self, text=""):
                self.text = text
                self.status_code = 200

            def raise_for_status(self):
                return None

        class FakeSession:
            def get(self, url, headers=None, timeout=30, **kwargs):
                self.last_url = url
                return FakeResponse(
                    """<?xml version="1.0"?>
                    <rss><channel>
                      <title>测试播客</title>
                      <item>
                        <title>第一期</title>
                        <link>https://example.com/ep1</link>
                        <pubDate>Sun, 10 May 2026 12:00:00 GMT</pubDate>
                        <description><![CDATA[<p>节目简介正文</p>]]></description>
                        <enclosure url="https://example.com/audio.mp3" type="audio/mpeg" />
                      </item>
                    </channel></rss>"""
                )

        result = sync_podcast_feed_source(
            {
                "id": "test-podcast",
                "type": "podcast_feed",
                "name": "测试播客",
                "url": "https://example.com/feed.xml",
                "options": {"max_items": 1, "transcribe": False},
            },
            session=FakeSession(),
        )

        self.assertEqual(result["items_fetched"], 1)
        item = result["content_items"][0]
        self.assertEqual(item["source_type"], "podcast_episode")
        self.assertIn("节目简介正文", item["content_markdown"])
        self.assertEqual(item["metadata"]["audio_url"], "https://example.com/audio.mp3")

    def test_xiaomi_omni_asr_uses_chat_audio_payload(self):
        class FakeResponse:
            status_code = 200

            def json(self):
                return {"choices": [{"message": {"content": "云端转写结果"}}]}

        captured = {}

        def fake_post(url, headers=None, json=None, timeout=180):
            captured["url"] = url
            captured["headers"] = headers
            captured["payload"] = json
            return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp:
            audio_path = Path(tmp) / "audio.mp4"
            audio_path.write_bytes(b"fake-audio")
            with patch.dict("os.environ", {"XIAOMI_API_KEY": "test-key"}, clear=False), patch(
                "src.content_loop.media_sources.requests.post",
                side_effect=fake_post,
            ):
                result = transcribe_audio_file(
                    audio_path,
                    {"asr_provider": "xiaomi_omni", "asr_model": "mimo-v2-omni"},
                )

        self.assertEqual(result["text"], "云端转写结果")
        self.assertTrue(captured["url"].endswith("/chat/completions"))
        self.assertEqual(captured["payload"]["model"], "mimo-v2-omni")
        content = captured["payload"]["messages"][0]["content"]
        self.assertEqual(content[1]["type"], "input_audio")
        self.assertIn("Bearer test-key", captured["headers"]["Authorization"])


class TaggingTests(unittest.TestCase):
    def test_apply_tags_uses_taxonomy_and_writes_topic_mentions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content_path = root / "content_items.jsonl"
            taxonomy_path = root / "tag_taxonomy.json"
            topic_path = root / "topic_tags.jsonl"
            taxonomy_path.write_text(
                json.dumps(
                    {
                        "max_tags_per_item": 3,
                        "min_score": 2,
                        "tags": [
                            {"name": "AI Agent", "keywords": ["Agent", "智能体"]},
                            {"name": "内容创作", "keywords": ["公众号", "写作"]},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            upsert_content_items(
                [
                    {
                        "id": "wechat_article:agent",
                        "source_type": "wechat_article",
                        "source_id": "测试号",
                        "source_name": "测试号",
                        "title": "AI Agent 写作工作流",
                        "summary": "用智能体生成公众号草稿",
                        "published_at": "2026-01-01",
                        "content_markdown": "Agent 负责整理素材，人来确认写作方向。",
                        "human_decision": "candidate",
                        "feedback_notes": [],
                    }
                ],
                path=content_path,
            )

            result = apply_tags_to_content_items(
                content_items_path=content_path,
                taxonomy_path=taxonomy_path,
                topic_tags_path=topic_path,
            )
            rows = list_content_items(path=content_path, include_content=True)
            overview = get_tagging_overview(
                content_items_path=content_path,
                taxonomy_path=taxonomy_path,
                topic_tags_path=topic_path,
            )

            self.assertEqual(result.tagged, 1)
            self.assertIn("AI Agent", rows[0]["tags"])
            self.assertIn("内容创作", rows[0]["tags"])
            self.assertEqual(overview["tag_counts"]["AI Agent"], 1)
            self.assertGreater(topic_path.stat().st_size, 0)


class AIEnrichmentTests(unittest.TestCase):
    def test_ai_enrich_writes_summary_and_ai_tags(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            content_path = root / "content_items.jsonl"
            taxonomy_path = root / "tag_taxonomy.json"
            taxonomy_path.write_text(
                json.dumps({"tags": [{"name": "AI Agent", "keywords": ["Agent"]}, {"name": "待分类", "keywords": []}]}),
                encoding="utf-8",
            )
            upsert_content_items(
                [
                    {
                        "id": "wechat_article:ai",
                        "source_type": "wechat_article",
                        "source_id": "测试号",
                        "source_name": "测试号",
                        "title": "AI Agent 工作流",
                        "summary": "旧摘要",
                        "published_at": "2026-01-01",
                        "content_markdown": "Agent 负责整理素材。",
                        "tags": [],
                        "human_decision": "candidate",
                    }
                ],
                path=content_path,
            )

            def fake_chat(_messages):
                return '{"summary":"这篇文章介绍 AI Agent 如何整理素材并辅助内容生产。","tags":["AI Agent"],"category":"技术分析","confidence":0.9,"why":"多次提到 Agent"}'

            import src.content_loop.ai_enrichment as ai_module

            old_chat = ai_module.chat_content_loop_llm
            old_status = ai_module.content_loop_llm_status
            try:
                ai_module.chat_content_loop_llm = fake_chat
                ai_module.content_loop_llm_status = lambda: {
                    "configured": True,
                    "model": "test-model",
                    "base_url": "http://test",
                    "has_api_key": True,
                    "timeout": 1,
                }
                result = ai_enrich_content_items(
                    limit=1,
                    content_items_path=content_path,
                    taxonomy_path=taxonomy_path,
                )
            finally:
                ai_module.chat_content_loop_llm = old_chat
                ai_module.content_loop_llm_status = old_status

            rows = list_content_items(path=content_path, include_content=True)
            self.assertEqual(result.processed, 1)
            self.assertEqual(rows[0]["ai_tags"], ["AI Agent"])
            self.assertIn("辅助内容生产", rows[0]["ai_summary"])
            self.assertEqual(rows[0]["ai_model"], "test-model")


if __name__ == "__main__":
    unittest.main()
