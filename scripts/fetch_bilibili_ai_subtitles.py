from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.import_bilibili_srt_subtitles import DEFAULT_SOURCE_ID, import_bilibili_srt_subtitles


DEFAULT_CONFIG = ROOT / "data" / "external_sources.json"
DEFAULT_SUBTITLE_DIR = Path("/tmp/pika-bilibili-subs")
DEFAULT_COOKIES_FROM_BROWSER = "chrome:Default"
DEFAULT_SUB_LANG = "ai-zh"
DEFAULT_SUB_FORMAT = "srt"
DEFAULT_YT_DLP_COMMAND = ["uvx", "--from", "yt-dlp", "yt-dlp"]


def load_bilibili_source(config_path: str | Path, source_id: str) -> dict[str, Any]:
    config_path = Path(config_path)
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    sources = payload.get("sources") if isinstance(payload, dict) else []
    if not isinstance(sources, list):
        raise ValueError(f"{config_path} does not contain a sources list")
    for source in sources:
        if isinstance(source, dict) and source.get("id") == source_id:
            return source
    raise ValueError(f"source_id not found in {config_path}: {source_id}")


def bvids_from_source(source: dict[str, Any]) -> list[str]:
    options = source.get("options") if isinstance(source.get("options"), dict) else {}
    raw_items = options.get("bvids") or options.get("video_bvids") or []
    if not isinstance(raw_items, list):
        return []

    bvids: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            bvid = raw_item.strip()
        elif isinstance(raw_item, dict):
            bvid = str(raw_item.get("bvid") or "").strip()
        else:
            continue
        if bvid and bvid not in seen:
            bvids.append(bvid)
            seen.add(bvid)
    return bvids


def bilibili_video_urls(bvids: list[str]) -> list[str]:
    return [f"https://www.bilibili.com/video/{bvid}/" for bvid in bvids]


def write_url_batch_file(subtitle_dir: Path, source_id: str, bvids: list[str]) -> Path:
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    batch_file = subtitle_dir / f"{source_id}.urls.txt"
    batch_file.write_text("\n".join(bilibili_video_urls(bvids)) + "\n", encoding="utf-8")
    return batch_file


def build_yt_dlp_command(
    *,
    yt_dlp_command: list[str],
    batch_file: Path,
    subtitle_dir: Path,
    cookies_from_browser: str,
    sub_lang: str,
    sub_format: str,
) -> list[str]:
    return [
        *yt_dlp_command,
        "--cookies-from-browser",
        cookies_from_browser,
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        sub_lang,
        "--sub-format",
        sub_format,
        "--ignore-errors",
        "--paths",
        str(subtitle_dir),
        "-o",
        "%(id)s.%(ext)s",
        "-a",
        str(batch_file),
    ]


def subtitle_files_for_bvids(subtitle_dir: Path, bvids: list[str], *, sub_lang: str, sub_format: str) -> dict[str, Path]:
    files: dict[str, Path] = {}
    for bvid in bvids:
        path = subtitle_dir / f"{bvid}.{sub_lang}.{sub_format}"
        if path.exists():
            files[bvid] = path
    return files


def fetch_bilibili_ai_subtitles(
    *,
    source_id: str = DEFAULT_SOURCE_ID,
    config_path: str | Path = DEFAULT_CONFIG,
    subtitle_dir: str | Path = DEFAULT_SUBTITLE_DIR,
    cookies_from_browser: str = DEFAULT_COOKIES_FROM_BROWSER,
    sub_lang: str = DEFAULT_SUB_LANG,
    sub_format: str = DEFAULT_SUB_FORMAT,
    yt_dlp_command: list[str] | None = None,
    import_after_download: bool = True,
    import_only: bool = False,
    refresh_raw_sources: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    subtitle_dir = Path(subtitle_dir)
    source = load_bilibili_source(config_path, source_id)
    bvids = bvids_from_source(source)
    if not bvids:
        raise ValueError(f"no bvids configured for source: {source_id}")

    batch_file = write_url_batch_file(subtitle_dir, source_id, bvids)
    command = build_yt_dlp_command(
        yt_dlp_command=yt_dlp_command or DEFAULT_YT_DLP_COMMAND,
        batch_file=batch_file,
        subtitle_dir=subtitle_dir,
        cookies_from_browser=cookies_from_browser,
        sub_lang=sub_lang,
        sub_format=sub_format,
    )

    if not dry_run and not import_only:
        subprocess.run(command, cwd=ROOT, check=True)

    subtitle_files = subtitle_files_for_bvids(subtitle_dir, bvids, sub_lang=sub_lang, sub_format=sub_format)
    missing = [bvid for bvid in bvids if bvid not in subtitle_files]
    import_result: dict[str, Any] | None = None
    if import_after_download and not dry_run:
        import_result = import_bilibili_srt_subtitles(
            subtitle_dir,
            source_id=source_id,
            refresh_raw_sources=refresh_raw_sources,
        )

    return {
        "source_id": source_id,
        "expected": len(bvids),
        "subtitle_files": len(subtitle_files),
        "missing": missing,
        "subtitle_dir": str(subtitle_dir),
        "url_batch_file": str(batch_file),
        "command": command,
        "download_skipped": dry_run or import_only,
        "import_result": import_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Bilibili AI subtitles with Chrome login state and import them as Markdown.")
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--subtitle-dir", default=str(DEFAULT_SUBTITLE_DIR))
    parser.add_argument("--cookies-from-browser", default=DEFAULT_COOKIES_FROM_BROWSER)
    parser.add_argument("--sub-lang", default=DEFAULT_SUB_LANG)
    parser.add_argument("--sub-format", default=DEFAULT_SUB_FORMAT)
    parser.add_argument("--yt-dlp-bin", default="", help="Use an installed yt-dlp binary instead of uvx --from yt-dlp yt-dlp.")
    parser.add_argument("--import-only", action="store_true", help="Import existing subtitle files without calling yt-dlp.")
    parser.add_argument("--no-import", action="store_true", help="Download subtitle files but do not write Markdown/content metadata.")
    parser.add_argument("--refresh-raw-sources", action="store_true", help="Also rewrite existing raw source snapshot Markdown files.")
    parser.add_argument("--dry-run", action="store_true", help="Write the URL batch file and print the yt-dlp command without running it.")
    args = parser.parse_args()

    yt_dlp_command = [args.yt_dlp_bin] if args.yt_dlp_bin else DEFAULT_YT_DLP_COMMAND
    result = fetch_bilibili_ai_subtitles(
        source_id=args.source_id,
        config_path=args.config,
        subtitle_dir=args.subtitle_dir,
        cookies_from_browser=args.cookies_from_browser,
        sub_lang=args.sub_lang,
        sub_format=args.sub_format,
        yt_dlp_command=yt_dlp_command,
        import_after_download=not args.no_import,
        import_only=args.import_only,
        refresh_raw_sources=args.refresh_raw_sources,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
