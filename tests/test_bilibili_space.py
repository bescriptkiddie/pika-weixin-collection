import unittest
from unittest.mock import Mock, patch

from src.content_loop.media_sources import (
    MediaSourceImportError,
    _decode_bilibili_danmaku_segments,
    _format_bilibili_danmaku_xml,
    _format_bilibili_transcript_markdown,
    extract_bilibili_mid,
    _normalize_bilibili_xml_text,
    _parse_bilibili_danmaku,
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
        self.assertTrue(source["options"]["download_subtitles"])
        self.assertTrue(source["options"]["write_transcript_markdown"])
        self.assertFalse(source["options"]["download_danmaku"])
        self.assertEqual(source["options"]["max_items"], 100)

    def test_parse_bilibili_danmaku_repairs_cached_mojibake(self):
        raw_xml = '<?xml version="1.0" encoding="UTF-8"?><i><d p="1.5,1,25,16777215,0,0,hash,id,0">两种可能性</d></i>'
        mojibake = raw_xml.encode("utf-8").decode("latin-1")

        repaired = _normalize_bilibili_xml_text(mojibake)
        text, segments = _parse_bilibili_danmaku(mojibake, bvid="BV1test")

        self.assertIn("两种可能性", repaired)
        self.assertEqual(text, "两种可能性")
        self.assertEqual(segments[0]["start"], 1.5)

    def test_decode_bilibili_segmented_danmaku_protobuf(self):
        def varint(value: int) -> bytes:
            output = bytearray()
            while value >= 0x80:
                output.append((value & 0x7F) | 0x80)
                value >>= 7
            output.append(value)
            return bytes(output)

        def field_varint(field: int, value: int) -> bytes:
            return varint(field << 3) + varint(value)

        def field_text(field: int, value: str) -> bytes:
            data = value.encode("utf-8")
            return varint((field << 3) | 2) + varint(len(data)) + data

        elem = b"".join(
            [
                field_varint(1, 123456789),
                field_varint(2, 12345),
                field_varint(3, 1),
                field_varint(4, 25),
                field_varint(5, 16777215),
                field_text(6, "abc123"),
                field_text(7, "完整分段弹幕"),
                field_varint(8, 1779193447),
                field_varint(9, 10),
                field_text(12, "123456789"),
            ]
        )
        raw = varint((1 << 3) | 2) + varint(len(elem)) + elem

        segments = _decode_bilibili_danmaku_segments(raw, bvid="BV1test")
        xml = _format_bilibili_danmaku_xml({"cid": 42}, segments, source="public-list.so+web-seg.so")

        self.assertEqual(segments[0]["text"], "完整分段弹幕")
        self.assertEqual(segments[0]["start"], 12.345)
        self.assertIn("<source>public-list.so+web-seg.so</source>", xml)
        self.assertIn("完整分段弹幕", xml)

    def test_format_transcript_markdown_excludes_danmaku(self):
        markdown, source = _format_bilibili_transcript_markdown(
            title="测试视频",
            owner_name="米来哆哆",
            published_at="2026-05-20T12:00:00+08:00",
            video_url="https://www.bilibili.com/video/BV1test/",
            bvid="BV1test",
            aid=123,
            cid=456,
            duration=789,
            transcript="",
            segments=[],
            transcript_source="",
            subtitle_url="",
            raw_subtitle_file="",
            description="视频简介",
            transcribe_enabled=False,
        )

        self.assertEqual(source, "pending_transcription")
        self.assertIn("本文档不包含弹幕内容", markdown)
        self.assertIn("暂无口播转写文本", markdown)
        self.assertNotIn("弹幕文本", markdown)


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
