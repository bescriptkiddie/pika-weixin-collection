import unittest
from unittest.mock import Mock, patch

from src.content_loop.media_sources import (
    MediaSourceImportError,
    extract_bilibili_mid,
    list_bilibili_space_videos,
    sync_bilibili_space_source,
)
from src.content_loop.source_configs import build_media_source_config, infer_source_type


class BilibiliSpaceConfigTests(unittest.TestCase):
    def test_extract_bilibili_mid_from_space_url(self):
        self.assertEqual(
            extract_bilibili_mid("https://space.bilibili.com/3546669224298959?spm_id_from=333.337.0.0"),
            "3546669224298959",
        )
        self.assertEqual(extract_bilibili_mid("3546669224298959"), "3546669224298959")

    def test_build_bilibili_space_config(self):
        url = "https://space.bilibili.com/3546669224298959/video"

        self.assertEqual(infer_source_type(url), "bilibili_space")
        source = build_media_source_config(url=url, name="米来哆哆", transcribe=False)

        self.assertEqual(source["id"], "bilibili-space-3546669224298959")
        self.assertEqual(source["type"], "bilibili_space")
        self.assertEqual(source["name"], "米来哆哆")
        self.assertFalse(source["options"]["transcribe"])
        self.assertEqual(source["options"]["max_items"], 100)


class BilibiliSpaceSyncTests(unittest.TestCase):
    def test_list_space_videos_preserves_partial_result_when_arc_search_is_blocked(self):
        source = {
            "id": "bilibili-space-3546669224298959",
            "type": "bilibili_space",
            "url": "https://space.bilibili.com/3546669224298959/video",
            "options": {"max_items": 100},
        }
        archives = [
            {"bvid": "BV1yhZtYBERt", "title": "主力抬轿", "pubdate": 1743501271},
            {"bvid": "BV1GWXHYHE72", "title": "涨停炸板", "pubdate": 1742632938},
        ]

        with patch("src.content_loop.media_sources._fetch_bilibili_space_total", return_value=48), patch(
            "src.content_loop.media_sources._fetch_bilibili_space_arc_archives",
            side_effect=MediaSourceImportError("请求过于频繁，请稍后再试"),
        ), patch("src.content_loop.media_sources._fetch_bilibili_space_series_archives", return_value=archives):
            result = list_bilibili_space_videos(source, session=Mock())

        self.assertEqual(result["space_video_total"], 48)
        self.assertEqual([item["bvid"] for item in result["archives"]], ["BV1yhZtYBERt", "BV1GWXHYHE72"])
        self.assertIn("space_series_archives", result["fetch_modes"])
        self.assertTrue(any("公开接口只发现 2/48 个视频" in error for error in result["errors"]))

    def test_sync_space_reuses_single_video_sync_with_parent_source_id(self):
        source = {
            "id": "bilibili-space-3546669224298959",
            "type": "bilibili_space",
            "name": "米来哆哆",
            "url": "https://space.bilibili.com/3546669224298959/video",
            "options": {"transcribe": False, "snapshot_raw_sources": False, "tags": ["B站", "投资复盘"]},
        }
        item = {
            "id": "bilibili_video:BV1yhZtYBERt",
            "source_id": "bilibili-space-3546669224298959",
            "source_name": "B站 / 米来哆哆",
            "tags": [],
            "metadata": {"bvid": "BV1yhZtYBERt"},
            "references": [{"type": "bilibili_video", "source_id": "old"}],
        }

        with patch("src.content_loop.media_sources.list_bilibili_space_videos", return_value={
            "mid": "3546669224298959",
            "space_video_total": 48,
            "archives": [{"bvid": "BV1yhZtYBERt", "series_name": "干货合集", "fetch_mode": "space_series_archives"}],
            "archives_discovered": 1,
            "fetch_modes": ["space_series_archives"],
            "errors": ["当前公开接口只发现 1/48 个视频"],
        }), patch("src.content_loop.media_sources.sync_bilibili_video_source", return_value={
            "content_items": [item],
            "errors": [],
        }) as sync_video:
            result = sync_bilibili_space_source(source, session=Mock())

        video_source = sync_video.call_args.args[0]
        self.assertEqual(video_source["type"], "bilibili_video")
        self.assertEqual(video_source["id"], source["id"])
        self.assertEqual(video_source["url"], "https://www.bilibili.com/video/BV1yhZtYBERt/")
        self.assertEqual(result["items_fetched"], 1)
        self.assertEqual(result["content_items"][0]["source_id"], source["id"])
        self.assertEqual(result["content_items"][0]["tags"], ["B站", "投资复盘"])
        self.assertEqual(result["content_items"][0]["metadata"]["space_mid"], "3546669224298959")
        self.assertEqual(result["content_items"][0]["references"][0]["source_id"], source["id"])


if __name__ == "__main__":
    unittest.main()
