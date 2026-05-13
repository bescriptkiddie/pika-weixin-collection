from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .media_sources import extract_bilibili_bvid, _fetch_bilibili_metadata, _session
from .store import DATA_DIR, EXTERNAL_SOURCES_FILE, content_hash, read_json, safe_slug


class SourceConfigError(RuntimeError):
    pass


def infer_source_type(url: str, requested_type: str = "auto") -> str:
    normalized = requested_type.strip().lower() if requested_type else "auto"
    if normalized in {"bilibili_video", "podcast_feed"}:
        return normalized
    if normalized not in {"", "auto"}:
        raise SourceConfigError(f"不支持的信源类型：{requested_type}")

    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    if "bilibili.com" in host or extractable_bvid(url):
        return "bilibili_video"
    if path.endswith((".xml", ".rss", ".atom")):
        return "podcast_feed"
    raise SourceConfigError("无法自动识别链接类型，请选择 B 站视频或播客 RSS")


def extractable_bvid(url: str) -> bool:
    try:
        extract_bilibili_bvid(url)
    except Exception:
        return False
    return True


def _load_config(path: Path) -> dict[str, Any]:
    raw = read_json(path, {"sources": []})
    if isinstance(raw, list):
        return {"sources": raw}
    if not isinstance(raw, dict):
        return {"sources": []}
    sources = raw.get("sources")
    if not isinstance(sources, list):
        raw["sources"] = []
    return raw


def _write_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _default_tags(source_type: str) -> list[str]:
    if source_type == "bilibili_video":
        return ["B站", "视频转写"]
    if source_type == "podcast_feed":
        return ["播客", "外部源"]
    return ["外部源"]


def _bilibili_source(
    *,
    url: str,
    name: str,
    human_reason: str,
    transcribe: bool,
    tags: list[str] | None,
    enabled: bool,
) -> dict[str, Any]:
    bvid = extract_bilibili_bvid(url)
    metadata = _fetch_bilibili_metadata(_session(), bvid)
    title = str(metadata.get("title") or bvid)
    owner = metadata.get("owner") if isinstance(metadata.get("owner"), dict) else {}
    owner_name = str(owner.get("name") or "").strip()
    source_name = name.strip() or (f"{owner_name}：{title}" if owner_name else title)
    return {
        "id": f"bilibili-{bvid.lower()}",
        "type": "bilibili_video",
        "name": source_name,
        "url": f"https://www.bilibili.com/video/{bvid}/",
        "enabled": enabled,
        "human_reason": human_reason.strip() or "B 站视频转成可读文本，进入统一内容池做摘要、标签和复盘。",
        "options": {
            "transcribe": transcribe,
            "asr_provider": "xiaomi_omni",
            "asr_model": "mimo-v2-omni",
            "max_completion_tokens": 12000,
            "language": "zh",
            "snapshot_raw_sources": True,
            "tags": tags or _default_tags("bilibili_video"),
            "initial_score": 0.7,
        },
    }


def _podcast_source(
    *,
    url: str,
    name: str,
    human_reason: str,
    transcribe: bool,
    tags: list[str] | None,
    enabled: bool,
) -> dict[str, Any]:
    parsed = urlparse(url)
    label = name.strip() or parsed.netloc or "播客 RSS"
    return {
        "id": f"podcast-{safe_slug(label, 'rss', 36).lower()}-{content_hash(url)[:8]}",
        "type": "podcast_feed",
        "name": label,
        "url": url,
        "enabled": enabled,
        "human_reason": human_reason.strip() or "播客 RSS 进入统一内容池，需要全文时开启音频转写。",
        "options": {
            "max_items": 3,
            "transcribe": transcribe,
            "asr_provider": "xiaomi_omni",
            "asr_model": "mimo-v2-omni",
            "max_completion_tokens": 12000,
            "language": "zh",
            "snapshot_raw_sources": True,
            "tags": tags or _default_tags("podcast_feed"),
            "initial_score": 0.55,
        },
    }


def build_media_source_config(
    *,
    url: str,
    source_type: str = "auto",
    name: str = "",
    human_reason: str = "",
    transcribe: bool = True,
    tags: list[str] | None = None,
    enabled: bool = True,
) -> dict[str, Any]:
    clean_url = url.strip()
    if not clean_url:
        raise SourceConfigError("url 不能为空")
    resolved_type = infer_source_type(clean_url, source_type)
    if resolved_type == "bilibili_video":
        return _bilibili_source(
            url=clean_url,
            name=name,
            human_reason=human_reason,
            transcribe=transcribe,
            tags=tags,
            enabled=enabled,
        )
    if resolved_type == "podcast_feed":
        return _podcast_source(
            url=clean_url,
            name=name,
            human_reason=human_reason,
            transcribe=transcribe,
            tags=tags,
            enabled=enabled,
        )
    raise SourceConfigError(f"不支持的信源类型：{resolved_type}")


def upsert_media_source_config(
    *,
    url: str,
    source_type: str = "auto",
    name: str = "",
    human_reason: str = "",
    transcribe: bool = True,
    tags: list[str] | None = None,
    enabled: bool = True,
    config_path: str | Path = EXTERNAL_SOURCES_FILE,
) -> dict[str, Any]:
    path = Path(config_path)
    config = _load_config(path)
    source = build_media_source_config(
        url=url,
        source_type=source_type,
        name=name,
        human_reason=human_reason,
        transcribe=transcribe,
        tags=tags,
        enabled=enabled,
    )
    sources = [item for item in config.get("sources", []) if isinstance(item, dict)]
    replaced = False
    for index, current in enumerate(sources):
        if current.get("id") == source["id"] or current.get("url") == source["url"]:
            current_options = current.get("options") if isinstance(current.get("options"), dict) else {}
            merged = {**current, **source}
            if current.get("url") == source["url"] and current.get("id") != source["id"]:
                merged["id"] = current.get("id") or source["id"]
            if not name.strip() and current.get("name"):
                merged["name"] = current["name"]
            if not human_reason.strip() and current.get("human_reason"):
                merged["human_reason"] = current["human_reason"]
            merged_options = {**source["options"], **current_options}
            merged_options["transcribe"] = source["options"]["transcribe"]
            if tags is not None:
                merged_options["tags"] = source["options"]["tags"]
            merged["options"] = merged_options
            sources[index] = merged
            source = merged
            replaced = True
            break
    if not replaced:
        sources.append(source)
    config["sources"] = sources
    _write_config(path, config)
    return {
        "config_path": str(path),
        "source": source,
        "created": not replaced,
        "updated": replaced,
        "sources_total": len(sources),
        "data_dir": str(DATA_DIR),
    }
