from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.content_loop.media_sources import _media_raw_markdown
from src.content_loop.store import DATA_DIR, content_hash, read_json, read_jsonl, summary_from_text, write_jsonl


EXPORT_ROOT = DATA_DIR / "llm_wiki" / "wechat_oa"
DEFAULT_SOURCE_ID = "bilibili-space-3546669224298959"
TRANSCRIPT_SOURCE = "bilibili_ai_subtitle"


def parse_srt(raw: str) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", raw.replace("\r\n", "\n").replace("\r", "\n").strip()):
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if not lines:
            continue
        if re.fullmatch(r"\d+", lines[0]):
            lines = lines[1:]
        if not lines or "-->" not in lines[0]:
            continue
        start, end = [part.strip() for part in lines[0].split("-->", 1)]
        text = " ".join(lines[1:]).strip()
        text = re.sub(r"\s+", " ", text)
        if text:
            segments.append({"start": start, "end": end, "text": text})
    return segments


def compact_transcript(segments: list[dict[str, str]]) -> str:
    lines: list[str] = []
    previous = ""
    for segment in segments:
        text = segment["text"].strip()
        if not text or text == previous:
            continue
        lines.append(text)
        previous = text
    return "\n".join(lines)


def format_timeline(segments: list[dict[str, str]]) -> str:
    return "\n".join(f"- [{segment['start']} -> {segment['end']}] {segment['text']}" for segment in segments)


def transcript_markdown(item: dict[str, Any], raw_subtitle_file: str, transcript: str, segments: list[dict[str, str]]) -> str:
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    parts = [
        f"# {item.get('title') or item.get('id')}",
        "",
        f"- UP主：{item.get('author') or '米来哆哆'}",
        f"- 发布时间：{item.get('published_at') or ''}",
        f"- 视频链接：{item.get('url') or ''}",
        f"- BVID：{metadata.get('bvid') or ''}",
        f"- AID：{metadata.get('aid') or ''}",
        f"- CID：{metadata.get('cid') or ''}",
        f"- 时长：{metadata.get('duration') or ''} 秒",
        f"- 文本来源：{TRANSCRIPT_SOURCE}",
        "- 状态：已取得 B 站登录态可见的 AI 中文字幕（ai-zh）。",
        "- 说明：本文档不包含弹幕内容。",
        f"- 字幕原始文件：{raw_subtitle_file}",
        "",
        "## 转写文本",
        "",
        transcript,
        "",
        "## 时间线文本",
        "",
        format_timeline(segments),
        "",
    ]
    return "\n".join(parts).strip() + "\n"


def content_markdown(item: dict[str, Any], raw_subtitle_file: str, transcript_markdown_file: str, transcript: str, segments: list[dict[str, str]]) -> str:
    return "\n".join(
        [
            f"# {item.get('title') or item.get('id')}",
            "",
            f"- UP主：{item.get('author') or '米来哆哆'}",
            f"- 发布时间：{item.get('published_at') or ''}",
            f"- 视频链接：{item.get('url') or ''}",
            f"- 文本来源：{TRANSCRIPT_SOURCE}",
            "",
            f"- 字幕资源：{raw_subtitle_file}",
            f"- Markdown 文本资源：{transcript_markdown_file}",
            "",
            "## 转写文本",
            "",
            transcript,
            "",
            "## 时间线文本",
            "",
            format_timeline(segments),
            "",
        ]
    ).strip()


def ensure_reference(item: dict[str, Any], reference: dict[str, str]) -> None:
    references = item.setdefault("references", [])
    if not isinstance(references, list):
        item["references"] = references = []
    key = (reference.get("type"), reference.get("path") or reference.get("url"), reference.get("source_id"))
    for existing in references:
        if not isinstance(existing, dict):
            continue
        existing_key = (existing.get("type"), existing.get("path") or existing.get("url"), existing.get("source_id"))
        if existing_key == key:
            return
    insert_at = next((index for index, existing in enumerate(references) if existing.get("type") == "transcript_markdown"), len(references))
    references.insert(insert_at, reference)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--subtitle-dir", default="/tmp/pika-bilibili-subs")
    parser.add_argument("--source-id", default=DEFAULT_SOURCE_ID)
    args = parser.parse_args()

    subtitle_dir = Path(args.subtitle_dir)
    source_config = next(
        source
        for source in read_json(DATA_DIR / "external_sources.json", {}).get("sources", [])
        if source.get("id") == args.source_id
    )
    items = read_jsonl(DATA_DIR / "content_items.jsonl")
    by_bvid = {
        item.get("metadata", {}).get("bvid"): item
        for item in items
        if isinstance(item.get("metadata"), dict) and item.get("source_id") == args.source_id
    }

    imported = 0
    missing: list[str] = []
    for source_srt in sorted(subtitle_dir.glob("*.ai-zh.srt")):
        bvid = source_srt.name.split(".", 1)[0]
        item = by_bvid.get(bvid)
        if not item:
            missing.append(bvid)
            continue
        metadata = item.setdefault("metadata", {})
        transcript_rel = metadata.get("transcript_markdown_file")
        if not transcript_rel:
            missing.append(bvid)
            continue

        raw_subtitle_rel = str(transcript_rel).removesuffix(".transcript.md") + ".subtitle.srt"
        transcript_path = EXPORT_ROOT / transcript_rel
        raw_subtitle_path = EXPORT_ROOT / raw_subtitle_rel
        raw_subtitle_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_srt, raw_subtitle_path)

        segments = parse_srt(raw_subtitle_path.read_text(encoding="utf-8"))
        transcript = compact_transcript(segments)
        transcript_path.write_text(transcript_markdown(item, raw_subtitle_rel, transcript, segments), encoding="utf-8")

        metadata.update(
            {
                "raw_subtitle_file": raw_subtitle_rel,
                "subtitle_language": "ai-zh",
                "subtitle_format": "srt",
                "subtitle_fetch_mode": "yt-dlp_cookies_from_browser",
                "subtitle_segments_count": len(segments),
                "subtitle_resource_type": TRANSCRIPT_SOURCE,
                "transcript_resource_type": TRANSCRIPT_SOURCE,
                "transcript_source": TRANSCRIPT_SOURCE,
            }
        )
        updated_content = content_markdown(item, raw_subtitle_rel, transcript_rel, transcript, segments)
        item["content_markdown"] = updated_content
        item["summary"] = summary_from_text(updated_content)
        item["content_hash"] = content_hash(str(item.get("title") or ""), str(item.get("url") or ""), updated_content)
        item["dedupe_key"] = f"{item.get('source_type') or 'bilibili_video'}:{item['content_hash'][:16]}"
        ensure_reference(item, {"type": "subtitle_resource", "path": raw_subtitle_rel})
        ensure_reference(item, {"type": "transcript_markdown", "path": transcript_rel})

        raw_source_rel = metadata.get("raw_source_file")
        if raw_source_rel:
            raw_source_path = EXPORT_ROOT / raw_source_rel
            raw_source_path.write_text(_media_raw_markdown(item, source_config), encoding="utf-8")
        imported += 1

    write_jsonl(DATA_DIR / "content_items.jsonl", items)
    print(json.dumps({"imported": imported, "missing": missing}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
