import json
import tempfile
import unittest
from pathlib import Path

from scripts.fetch_bilibili_ai_subtitles import (
    bvids_from_source,
    build_yt_dlp_command,
    fetch_bilibili_ai_subtitles,
)


class BilibiliSubtitlePipelineTests(unittest.TestCase):
    def test_bvids_from_source_keeps_order_and_dedupes(self):
        source = {
            "options": {
                "bvids": [
                    "BV1first",
                    {"bvid": "BV2second", "title": "二"},
                    "BV1first",
                    {"title": "missing"},
                ]
            }
        }

        self.assertEqual(bvids_from_source(source), ["BV1first", "BV2second"])

    def test_build_yt_dlp_command_uses_subtitle_only_chrome_flow(self):
        command = build_yt_dlp_command(
            yt_dlp_command=["yt-dlp"],
            batch_file=Path("/tmp/urls.txt"),
            subtitle_dir=Path("/tmp/subs"),
            cookies_from_browser="chrome:Default",
            sub_lang="ai-zh",
            sub_format="srt",
        )

        self.assertIn("--cookies-from-browser", command)
        self.assertIn("chrome:Default", command)
        self.assertIn("--skip-download", command)
        self.assertIn("--write-subs", command)
        self.assertIn("--write-auto-subs", command)
        self.assertIn("ai-zh", command)
        self.assertIn("%(id)s.%(ext)s", command)

    def test_dry_run_writes_url_batch_file_without_download_or_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            config_path = tmp_path / "external_sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "sources": [
                            {
                                "id": "bilibili-space-test",
                                "options": {"bvids": ["BV1alpha", "BV2beta"]},
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            result = fetch_bilibili_ai_subtitles(
                source_id="bilibili-space-test",
                config_path=config_path,
                subtitle_dir=tmp_path / "subs",
                yt_dlp_command=["yt-dlp"],
                dry_run=True,
            )

            batch_file = Path(result["url_batch_file"])
            self.assertTrue(result["download_skipped"])
            self.assertEqual(result["expected"], 2)
            self.assertEqual(result["subtitle_files"], 0)
            self.assertEqual(result["import_result"], None)
            self.assertEqual(
                batch_file.read_text(encoding="utf-8").splitlines(),
                [
                    "https://www.bilibili.com/video/BV1alpha/",
                    "https://www.bilibili.com/video/BV2beta/",
                ],
            )


if __name__ == "__main__":
    unittest.main()
