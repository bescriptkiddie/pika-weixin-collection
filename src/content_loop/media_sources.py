from __future__ import annotations

import html
import base64
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .store import (
    DATA_DIR,
    content_hash,
    now_local_iso,
    safe_slug,
    summary_from_text,
)

MEDIA_CACHE_DIR = DATA_DIR / "media_cache"
DEFAULT_EXPORT_ROOT = DATA_DIR / "llm_wiki" / "wechat_oa"
RAW_BILIBILI_ROOT = Path("raw") / "sources" / "bilibili"
RAW_PODCAST_ROOT = Path("raw") / "sources" / "podcast"
_LOCAL_ENV_LOADED = False


class MediaSourceImportError(RuntimeError):
    pass


def extract_bilibili_bvid(url: str) -> str:
    match = re.search(r"\b(BV[0-9A-Za-z]+)\b", url)
    if not match:
        raise MediaSourceImportError(f"无法从 URL 解析 B 站 BV 号：{url}")
    return match.group(1)


def extract_bilibili_mid(url: str) -> str:
    clean_url = str(url or "").strip()
    if re.fullmatch(r"\d{4,}", clean_url):
        return clean_url
    match = re.search(r"(?:^|//)space\.bilibili\.com/(\d{4,})(?:[/?#]|$)", clean_url)
    if match:
        return match.group(1)
    parsed = urlparse(clean_url)
    path_match = re.match(r"^/(\d{4,})(?:/|$)", parsed.path)
    if parsed.netloc.lower().endswith("bilibili.com") and path_match:
        return path_match.group(1)
    raise MediaSourceImportError(f"无法从 URL 解析 B 站 UP 主 mid：{url}")


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Accept": "application/json,text/plain,*/*",
        }
    )
    session.trust_env = False
    return session


def _get_json(session: requests.Session, url: str, *, headers: dict[str, str] | None = None) -> Any:
    response = session.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("code") not in (0, None):
        raise MediaSourceImportError(f"B 站 API 返回错误：{payload.get('message') or payload.get('code')}")
    return payload


def _get_text(session: requests.Session, url: str, *, headers: dict[str, str] | None = None) -> str:
    response = session.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.text


def _bilibili_cookie_header() -> str:
    cookie = _first_env("BILIBILI_COOKIE", "BILI_COOKIE")
    if cookie:
        return cookie
    sessdata = _first_env("BILIBILI_SESSDATA")
    return f"SESSDATA={sessdata}" if sessdata else ""


def _timestamp_to_iso(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")


def _pubdate_to_iso(value: str) -> str:
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).astimezone().isoformat(timespec="seconds")
    except (TypeError, ValueError, IndexError, OverflowError):
        return value


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "", text or "")
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _frontmatter_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _format_segments(segments: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = float(segment.get("start") or 0)
        end = float(segment.get("end") or 0)
        lines.append(f"[{start:07.2f}-{end:07.2f}] {text}")
    return "\n".join(lines)


def _download_file(
    session: requests.Session,
    url: str,
    dest: Path,
    *,
    headers: dict[str, str] | None = None,
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    request_headers = {"Accept": "*/*", **(headers or {})}
    with session.get(url, headers=request_headers, timeout=120, stream=True) as response:
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False, dir=str(dest.parent), suffix=".part") as tmp:
            tmp_path = Path(tmp.name)
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    tmp.write(chunk)
    tmp_path.replace(dest)
    return dest


def _audio_extension(url: str, fallback: str = ".audio") -> str:
    path = urlparse(url).path
    suffix = Path(path).suffix
    if suffix and len(suffix) <= 8:
        return suffix
    return fallback


def _first_env(*names: str) -> str:
    _load_local_env()
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _load_local_env() -> None:
    global _LOCAL_ENV_LOADED
    if _LOCAL_ENV_LOADED:
        return
    _LOCAL_ENV_LOADED = True
    env_path = DATA_DIR.parent / ".env.local"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _xiaomi_api_key(options: dict[str, Any]) -> str:
    _load_local_env()
    explicit = str(options.get("api_key") or options.get("xiaomi_api_key") or "").strip()
    if explicit:
        return explicit
    key_list = _first_env("XIAOMI_API_KEYS")
    if key_list:
        return next((part.strip() for part in re.split(r"[,;\s]+", key_list) if part.strip()), "")
    return _first_env("XIAOMI_API_KEY", "CONTENT_LOOP_LLM_API_KEY")


def _audio_format(path: Path) -> str:
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"m4s", "m4a", "mp4"}:
        return "mp4"
    if suffix in {"mp3", "mpeg"}:
        return "mp3"
    if suffix in {"wav", "wave"}:
        return "wav"
    if suffix in {"ogg", "oga"}:
        return "ogg"
    return suffix or "mp4"


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or "").strip())
            else:
                parts.append(str(part).strip())
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


def _post_chat_completion(
    *,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    response = requests.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=180,
    )
    if response.status_code >= 400:
        raise MediaSourceImportError(f"小米 Omni ASR 请求失败：HTTP {response.status_code} {response.text[:500]}")
    data = response.json()
    if isinstance(data, dict) and data.get("error"):
        raise MediaSourceImportError(f"小米 Omni ASR 返回错误：{data['error']}")
    return data


def _transcribe_with_xiaomi_omni(audio_path: Path, options: dict[str, Any]) -> dict[str, Any]:
    base_url = str(
        options.get("base_url")
        or options.get("xiaomi_base_url")
        or _first_env("XIAOMI_BASE_URL", "CONTENT_LOOP_LLM_BASE_URL")
        or "https://token-plan-sgp.xiaomimimo.com/v1"
    ).strip()
    api_key = _xiaomi_api_key(options)
    if not api_key:
        raise MediaSourceImportError("缺少小米 API key。请在 .env.local 设置 XIAOMI_API_KEY 或 CONTENT_LOOP_LLM_API_KEY。")

    model = str(options.get("asr_model") or _first_env("WECHATOA_ASR_MODEL", "XIAOMI_OMNI_MODEL") or "mimo-v2-omni")
    prompt = str(
        options.get("asr_prompt")
        or "请把这段音频完整转写成中文文本。保留关键名词、股票/公司/技术词，自动加标点。只输出转写正文。"
    )
    audio_bytes = audio_path.read_bytes()
    max_bytes = int(options.get("max_audio_bytes") or os.getenv("WECHATOA_ASR_MAX_AUDIO_BYTES") or 18_000_000)
    if len(audio_bytes) > max_bytes:
        raise MediaSourceImportError(f"音频过大：{len(audio_bytes)} bytes，当前上限 {max_bytes} bytes")

    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    audio_format = str(options.get("audio_format") or _audio_format(audio_path))
    max_tokens = int(options.get("max_completion_tokens") or options.get("max_tokens") or 4096)

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": audio_format}},
                ],
            }
        ],
        "temperature": 0,
        "max_completion_tokens": max_tokens,
    }
    try:
        data = _post_chat_completion(base_url=base_url, api_key=api_key, payload=payload)
    except MediaSourceImportError as first_error:
        payload["messages"][0]["content"][1] = {
            "type": "audio_url",
            "audio_url": {"url": f"data:audio/{audio_format};base64,{audio_b64}"},
        }
        try:
            data = _post_chat_completion(base_url=base_url, api_key=api_key, payload=payload)
        except MediaSourceImportError as second_error:
            raise MediaSourceImportError(f"{first_error}; fallback audio_url 也失败：{second_error}") from second_error

    choices = data.get("choices") if isinstance(data, dict) else []
    message = choices[0].get("message", {}) if choices and isinstance(choices[0], dict) else {}
    text = _message_content_text(message.get("content")).strip()
    return {
        "provider": "xiaomi_omni",
        "model": model,
        "language": str(options.get("language") or "auto"),
        "duration": 0,
        "segments": [{"start": 0, "end": 0, "text": text}] if text else [],
        "text": text,
    }


def transcribe_audio_file(audio_path: str | Path, options: dict[str, Any] | None = None) -> dict[str, Any]:
    options = options or {}
    provider = str(options.get("asr_provider") or os.getenv("WECHATOA_ASR_PROVIDER") or "xiaomi_omni").strip()
    provider = provider.lower().replace("-", "_")
    path = Path(audio_path)

    if provider in {"", "none", "disabled", "off"}:
        return {"provider": provider or "disabled", "model": "", "language": "", "duration": 0, "segments": [], "text": ""}
    if provider in {"xiaomi_omni", "mimo_omni", "openai_audio_chat", "cloud_omni"}:
        return _transcribe_with_xiaomi_omni(path, options)
    raise MediaSourceImportError(f"未知 ASR provider：{provider}")


def _bilibili_headers(bvid: str) -> dict[str, str]:
    return {"Referer": f"https://www.bilibili.com/video/{bvid}/", "Origin": "https://www.bilibili.com"}


def _bilibili_space_headers(mid: str) -> dict[str, str]:
    headers = {
        "Accept": "application/json,text/plain,*/*",
        "Referer": f"https://space.bilibili.com/{mid}/video",
        "Origin": "https://space.bilibili.com",
    }
    cookie = _bilibili_cookie_header()
    if cookie:
        headers["Cookie"] = cookie
    return headers


def _fetch_bilibili_api(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> dict[str, Any]:
    response = session.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, dict) and payload.get("code") not in (0, None):
        raise MediaSourceImportError(f"B 站 API 返回错误：{payload.get('message') or payload.get('code')}")
    if not isinstance(payload, dict):
        raise MediaSourceImportError("B 站 API 返回了非 JSON 对象")
    return payload


def _fetch_bilibili_space_total(session: requests.Session, mid: str) -> int:
    payload = _fetch_bilibili_api(
        session,
        "https://api.bilibili.com/x/space/navnum",
        params={"mid": mid},
        headers=_bilibili_space_headers(mid),
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    try:
        return int(data.get("video") or 0)
    except (TypeError, ValueError):
        return 0


def _normalize_bilibili_archive(
    archive: dict[str, Any],
    *,
    mid: str,
    fetch_mode: str,
    series_id: str = "",
    series_name: str = "",
) -> dict[str, Any] | None:
    bvid = str(archive.get("bvid") or "").strip()
    if not bvid:
        return None
    title = str(archive.get("title") or bvid).strip()
    return {
        "bvid": bvid,
        "title": title,
        "url": f"https://www.bilibili.com/video/{bvid}/",
        "pubdate": archive.get("pubdate") or archive.get("created") or archive.get("ctime"),
        "duration": archive.get("duration"),
        "cover": archive.get("pic") or archive.get("cover") or "",
        "desc": archive.get("desc") or "",
        "mid": mid,
        "series_id": series_id,
        "series_name": series_name,
        "fetch_mode": fetch_mode,
    }


def _dedupe_bilibili_archives(archives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_bvid: dict[str, dict[str, Any]] = {}
    for archive in archives:
        bvid = str(archive.get("bvid") or "").strip()
        if not bvid:
            continue
        previous = by_bvid.get(bvid, {})
        by_bvid[bvid] = {**previous, **archive}
    return sorted(
        by_bvid.values(),
        key=lambda item: int(item.get("pubdate") or 0) if str(item.get("pubdate") or "").isdigit() else 0,
        reverse=True,
    )


def _preloaded_bilibili_archives(source: dict[str, Any], mid: str) -> list[dict[str, Any]]:
    options = source.get("options") if isinstance(source.get("options"), dict) else {}
    raw_items = options.get("bvids") or options.get("video_bvids") or []
    if not isinstance(raw_items, list):
        return []
    archives: list[dict[str, Any]] = []
    for raw_item in raw_items:
        if isinstance(raw_item, str):
            archive = {"bvid": raw_item}
        elif isinstance(raw_item, dict):
            archive = raw_item
        else:
            continue
        normalized = _normalize_bilibili_archive(
            archive,
            mid=mid,
            fetch_mode="preloaded_bvids",
            series_id=str(archive.get("series_id") or "") if isinstance(archive, dict) else "",
            series_name=str(archive.get("series_name") or "") if isinstance(archive, dict) else "",
        )
        if normalized:
            archives.append(normalized)
    return _dedupe_bilibili_archives(archives)


def _fetch_bilibili_space_arc_archives(
    session: requests.Session,
    mid: str,
    *,
    max_items: int,
) -> tuple[list[dict[str, Any]], int]:
    archives: list[dict[str, Any]] = []
    total = 0
    page = 1
    page_size = min(max(max_items, 1), 50)
    while len(archives) < max_items:
        payload = _fetch_bilibili_api(
            session,
            "https://api.bilibili.com/x/space/arc/search",
            params={
                "mid": mid,
                "ps": page_size,
                "pn": page,
                "order": "pubdate",
                "jsonp": "jsonp",
            },
            headers=_bilibili_space_headers(mid),
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        page_info = data.get("page") if isinstance(data.get("page"), dict) else {}
        try:
            total = int(page_info.get("count") or total or 0)
        except (TypeError, ValueError):
            total = 0
        archive_list = data.get("list", {}).get("vlist") if isinstance(data.get("list"), dict) else []
        if not isinstance(archive_list, list) or not archive_list:
            break
        for archive in archive_list:
            if not isinstance(archive, dict):
                continue
            normalized = _normalize_bilibili_archive(archive, mid=mid, fetch_mode="space_arc_search")
            if normalized:
                archives.append(normalized)
        if total and len(archives) >= total:
            break
        page += 1
    return archives[:max_items], total


def _fetch_bilibili_series_archives(
    session: requests.Session,
    mid: str,
    *,
    series_id: str,
    series_name: str,
    max_items: int,
) -> list[dict[str, Any]]:
    archives: list[dict[str, Any]] = []
    page = 1
    page_size = min(max(max_items, 1), 100)
    total = 0
    while len(archives) < max_items:
        payload = _fetch_bilibili_api(
            session,
            "https://api.bilibili.com/x/series/archives",
            params={
                "mid": mid,
                "series_id": series_id,
                "pn": page,
                "ps": page_size,
                "only_normal": "true",
                "sort": "desc",
            },
            headers=_bilibili_space_headers(mid),
        )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        page_info = data.get("page") if isinstance(data.get("page"), dict) else {}
        try:
            total = int(page_info.get("total") or total or 0)
        except (TypeError, ValueError):
            total = 0
        archive_list = data.get("archives") if isinstance(data.get("archives"), list) else []
        if not archive_list:
            break
        for archive in archive_list:
            if not isinstance(archive, dict):
                continue
            normalized = _normalize_bilibili_archive(
                archive,
                mid=mid,
                fetch_mode="space_series_archives",
                series_id=series_id,
                series_name=series_name,
            )
            if normalized:
                archives.append(normalized)
        if total and len(archives) >= total:
            break
        page += 1
    return archives[:max_items]


def _fetch_bilibili_space_series_archives(
    session: requests.Session,
    mid: str,
    *,
    max_items: int,
) -> list[dict[str, Any]]:
    archives: list[dict[str, Any]] = []
    seen_series: set[str] = set()
    payload = _fetch_bilibili_api(
        session,
        "https://api.bilibili.com/x/polymer/web-space/home/seasons_series",
        params={"mid": mid, "page_num": 1, "page_size": 20},
        headers=_bilibili_space_headers(mid),
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    items_lists = data.get("items_lists") if isinstance(data.get("items_lists"), dict) else {}
    for bucket_name in ("series_list", "seasons_list"):
        bucket = items_lists.get(bucket_name)
        if not isinstance(bucket, list):
            continue
        for series in bucket:
            if not isinstance(series, dict):
                continue
            meta = series.get("meta") if isinstance(series.get("meta"), dict) else {}
            series_id = str(meta.get("series_id") or meta.get("season_id") or "").strip()
            if not series_id or series_id in seen_series:
                continue
            seen_series.add(series_id)
            series_name = str(meta.get("name") or "").strip()
            inline_archives = series.get("archives") if isinstance(series.get("archives"), list) else []
            for archive in inline_archives:
                if not isinstance(archive, dict):
                    continue
                normalized = _normalize_bilibili_archive(
                    archive,
                    mid=mid,
                    fetch_mode="space_series_inline",
                    series_id=series_id,
                    series_name=series_name,
                )
                if normalized:
                    archives.append(normalized)
            try:
                series_total = int(meta.get("total") or 0)
            except (TypeError, ValueError):
                series_total = 0
            if series_total and len([item for item in archives if item.get("series_id") == series_id]) < series_total:
                archives.extend(
                    _fetch_bilibili_series_archives(
                        session,
                        mid,
                        series_id=series_id,
                        series_name=series_name,
                        max_items=max_items,
                    )
                )
            if len(_dedupe_bilibili_archives(archives)) >= max_items:
                return _dedupe_bilibili_archives(archives)[:max_items]
    return _dedupe_bilibili_archives(archives)[:max_items]


def list_bilibili_space_videos(
    source: dict[str, Any],
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    session = session or _session()
    url = source.get("url") or ""
    mid = extract_bilibili_mid(url)
    options = source.get("options") if isinstance(source.get("options"), dict) else {}
    max_items = max(1, int(options.get("max_items") or 100))
    errors: list[str] = []
    fetch_modes: list[str] = []
    total = 0
    archives: list[dict[str, Any]] = []

    try:
        total = _fetch_bilibili_space_total(session, mid)
    except Exception as exc:  # noqa: BLE001 - keep partial sync visible
        errors.append(f"空间视频总数读取失败：{exc}")

    preloaded_archives = _preloaded_bilibili_archives(source, mid)
    if preloaded_archives:
        fetch_modes.append("preloaded_bvids")
        archives.extend(preloaded_archives)

    expected_total = min(max_items, total or len(preloaded_archives) or max_items)
    if len(_dedupe_bilibili_archives(archives)) < expected_total:
        try:
            arc_archives, arc_total = _fetch_bilibili_space_arc_archives(session, mid, max_items=max_items)
            if arc_total:
                total = arc_total
            if arc_archives:
                fetch_modes.append("space_arc_search")
                archives.extend(arc_archives)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"空间视频列表接口受限：{exc}")

    expected_total = min(max_items, total or len(preloaded_archives) or max_items)
    if len(_dedupe_bilibili_archives(archives)) < expected_total:
        try:
            series_archives = _fetch_bilibili_space_series_archives(session, mid, max_items=max_items)
            if series_archives:
                fetch_modes.append("space_series_archives")
                archives.extend(series_archives)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"合集/列表兜底读取失败：{exc}")

    archives = _dedupe_bilibili_archives(archives)[:max_items]
    if total and len(archives) < min(total, max_items):
        errors.append(
            f"当前公开接口只发现 {len(archives)}/{min(total, max_items)} 个视频；完整列表需要登录态 Cookie 或通过 B 站验证码后再同步。"
        )

    return {
        "mid": mid,
        "space_video_total": total,
        "archives": archives,
        "archives_discovered": len(archives),
        "fetch_modes": fetch_modes or ["none"],
        "errors": errors,
        "max_items": max_items,
    }


def _fetch_bilibili_metadata(session: requests.Session, bvid: str) -> dict[str, Any]:
    payload = _get_json(
        session,
        f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
        headers=_bilibili_headers(bvid),
    )
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise MediaSourceImportError(f"无法获取 B 站视频信息：{bvid}")
    pages = data.get("pages") if isinstance(data.get("pages"), list) else []
    cid = data.get("cid") or (pages[0].get("cid") if pages and isinstance(pages[0], dict) else "")
    if not cid:
        raise MediaSourceImportError(f"无法获取 B 站视频 cid：{bvid}")
    data["cid"] = cid
    return data


def _fetch_bilibili_subtitles(session: requests.Session, metadata: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str, str]:
    bvid = str(metadata.get("bvid") or "")
    cid = str(metadata.get("cid") or "")
    aid = str(metadata.get("aid") or "")
    payload = _get_json(
        session,
        f"https://api.bilibili.com/x/player/v2?aid={aid}&cid={cid}",
        headers=_bilibili_headers(bvid),
    )
    data = payload.get("data") if isinstance(payload, dict) else {}
    subtitle = data.get("subtitle") if isinstance(data, dict) else {}
    subtitles = subtitle.get("subtitles") if isinstance(subtitle, dict) else []
    if not isinstance(subtitles, list) or not subtitles:
        return "", [], "", ""

    first = next((item for item in subtitles if isinstance(item, dict) and item.get("subtitle_url")), None)
    if not first:
        return "", [], "", ""
    subtitle_url = str(first["subtitle_url"])
    if subtitle_url.startswith("//"):
        subtitle_url = "https:" + subtitle_url
    raw_text = _get_text(session, subtitle_url, headers=_bilibili_headers(bvid))
    raw = json.loads(raw_text)
    body = raw.get("body") if isinstance(raw, dict) else []
    segments = [
        {"start": item.get("from", 0), "end": item.get("to", 0), "text": str(item.get("content") or "").strip()}
        for item in body
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    return "\n".join(segment["text"] for segment in segments), segments, subtitle_url, json.dumps(raw, ensure_ascii=False, indent=2)


def _normalize_bilibili_xml_text(raw_xml: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", raw_xml):
        return raw_xml
    if not re.search(r"[ÃÂäåæçèéï]", raw_xml):
        return raw_xml
    try:
        repaired = raw_xml.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return raw_xml
    return repaired if re.search(r"[\u4e00-\u9fff]", repaired) else raw_xml


def _parse_bilibili_danmaku(raw_xml: str, *, bvid: str) -> tuple[str, list[dict[str, Any]]]:
    raw_xml = _normalize_bilibili_xml_text(raw_xml)
    try:
        root = ET.fromstring(raw_xml)
    except ET.ParseError as exc:
        raise MediaSourceImportError(f"弹幕 XML 解析失败：{bvid} {exc}") from exc
    segments: list[dict[str, Any]] = []
    for node in root.findall("d"):
        text = html.unescape(node.text or "").strip()
        text = re.sub(r"[\r\n\u2028\u2029]+", " ", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", "", text).strip()
        if not text:
            continue
        raw_start = (node.attrib.get("p") or "0").split(",", 1)[0]
        try:
            start = float(raw_start)
        except ValueError:
            start = 0.0
        segments.append({"start": start, "end": start, "text": text})
    segments.sort(key=lambda item: float(item.get("start") or 0))
    return "\n".join(segment["text"] for segment in segments), segments


def _fetch_bilibili_danmaku(session: requests.Session, metadata: dict[str, Any]) -> tuple[str, list[dict[str, Any]], str, str]:
    bvid = str(metadata.get("bvid") or "")
    cid = str(metadata.get("cid") or "")
    if not cid:
        return "", [], "", ""
    danmaku_url = f"https://api.bilibili.com/x/v1/dm/list.so?oid={cid}"
    response = session.get(
        danmaku_url,
        headers={**_bilibili_headers(bvid), "Accept": "application/xml,text/xml,*/*"},
        timeout=30,
    )
    response.raise_for_status()
    raw_xml = response.content.decode("utf-8", errors="replace")
    danmaku_text, segments = _parse_bilibili_danmaku(raw_xml, bvid=bvid)
    return danmaku_text, segments, danmaku_url, raw_xml


def _download_bilibili_audio(session: requests.Session, metadata: dict[str, Any]) -> Path:
    bvid = str(metadata.get("bvid") or "")
    cid = str(metadata.get("cid") or "")
    payload = _get_json(
        session,
        f"https://api.bilibili.com/x/player/playurl?bvid={bvid}&cid={cid}&fnval=16&fourk=1",
        headers=_bilibili_headers(bvid),
    )
    data = payload.get("data") if isinstance(payload, dict) else {}
    dash = data.get("dash") if isinstance(data, dict) else {}
    audio_list = dash.get("audio") if isinstance(dash, dict) else []
    if not isinstance(audio_list, list) or not audio_list:
        raise MediaSourceImportError(f"未找到 B 站音频流：{bvid}")
    audio = audio_list[0]
    audio_url = str(audio.get("baseUrl") or audio.get("base_url") or "")
    if not audio_url:
        raise MediaSourceImportError(f"音频流 URL 为空：{bvid}")
    dest = MEDIA_CACHE_DIR / "bilibili" / bvid / f"audio{_audio_extension(audio_url, '.m4s')}"
    return _download_file(session, audio_url, dest, headers=_bilibili_headers(bvid))


def _media_raw_markdown(item: dict[str, Any], source: dict[str, Any]) -> str:
    source_type = item["source_type"]
    frontmatter = [
        "---",
        "type: source",
        f"source_type: {_frontmatter_value(source_type)}",
        f"source_id: {_frontmatter_value(source['id'])}",
        f"source_name: {_frontmatter_value(source.get('name') or source['id'])}",
        f"title: {_frontmatter_value(item['title'])}",
        f"url: {_frontmatter_value(item.get('url') or '')}",
        f"published_at: {_frontmatter_value(item.get('published_at') or '')}",
        f"fetched_at: {_frontmatter_value(item.get('fetched_at') or '')}",
        f"metadata: {_frontmatter_value(item.get('metadata') or {})}",
        "sources: []",
        "---",
        "",
        f"# {item['title']}",
        "",
        f"- 来源：{item.get('source_name') or source.get('name') or source['id']}",
        f"- URL：{item.get('url') or ''}",
        f"- 抓取时间：{item.get('fetched_at') or ''}",
        "",
    ]
    if item.get("summary"):
        frontmatter.extend(["## 摘要", "", str(item["summary"]), ""])
    frontmatter.extend(["## 文本", "", str(item.get("content_markdown") or ""), ""])
    return "\n".join(frontmatter)


def _write_media_raw_snapshot(
    source: dict[str, Any],
    item: dict[str, Any],
    export_root: Path,
    raw_root: Path,
) -> str:
    source_dir = export_root / raw_root / safe_slug(source["id"], "source")
    source_dir.mkdir(parents=True, exist_ok=True)
    title = safe_slug(str(item.get("title") or item.get("id") or "media"), "media", 72)
    dest = source_dir / f"{title}.md"
    dest.write_text(_media_raw_markdown(item, source), encoding="utf-8")
    return str(dest.relative_to(export_root))


def _write_bilibili_text_resource(
    source: dict[str, Any],
    *,
    title: str,
    bvid: str,
    suffix: str,
    content: str,
    export_root: Path,
) -> str:
    dest = _bilibili_text_resource_path(source, title=title, bvid=bvid, suffix=suffix, export_root=export_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")
    return str(dest.relative_to(export_root))


def _bilibili_text_resource_path(
    source: dict[str, Any],
    *,
    title: str,
    bvid: str,
    suffix: str,
    export_root: Path,
) -> Path:
    source_dir = export_root / RAW_BILIBILI_ROOT / safe_slug(source["id"], "source") / "subtitles"
    filename = f"{safe_slug(f'{title}-{bvid}', 'subtitle', 96)}{suffix}"
    return source_dir / filename


def _read_bilibili_text_resource(
    source: dict[str, Any],
    *,
    title: str,
    bvid: str,
    suffix: str,
    export_root: Path,
) -> tuple[str, str]:
    dest = _bilibili_text_resource_path(source, title=title, bvid=bvid, suffix=suffix, export_root=export_root)
    if not dest.exists():
        return "", ""
    return str(dest.relative_to(export_root)), dest.read_text(encoding="utf-8")


def _build_media_item(
    *,
    item_id: str,
    source: dict[str, Any],
    source_type: str,
    source_name_prefix: str,
    title: str,
    url: str,
    author: str,
    published_at: str,
    fetched_at: str,
    content_markdown: str,
    metadata: dict[str, Any],
    raw_source_file: str = "",
) -> dict[str, Any]:
    item_hash = content_hash(title, url, content_markdown)
    references = [{"type": "url", "url": url}, {"type": source_type, "source_id": source["id"], "url": url}]
    if raw_source_file:
        references.append({"type": "source_snapshot", "path": raw_source_file})
    return {
        "id": item_id,
        "source_type": source_type,
        "source_id": source["id"],
        "source_name": f"{source_name_prefix} / {source.get('name') or source['id']}",
        "title": title,
        "url": url,
        "author": author,
        "published_at": published_at,
        "fetched_at": fetched_at,
        "summary": summary_from_text(content_markdown),
        "tags": source.get("options", {}).get("tags", []),
        "score": source.get("options", {}).get("initial_score", 0.0),
        "content_hash": item_hash,
        "dedupe_key": f"{source_type}:{item_hash[:16]}",
        "status": "candidate",
        "content_markdown": content_markdown,
        "references": references,
        "human_decision": "candidate",
        "feedback_notes": [],
        "metadata": {
            **metadata,
            "origin": source_type,
            "connector_type": source_type,
            "source_config_id": source["id"],
            "human_reason": source.get("human_reason") or "",
            **({"raw_source_file": raw_source_file} if raw_source_file else {}),
        },
    }


def sync_bilibili_video_source(
    source: dict[str, Any],
    *,
    session: requests.Session | None = None,
    export_root: str | Path = DEFAULT_EXPORT_ROOT,
) -> dict[str, Any]:
    session = session or _session()
    url = source.get("url") or ""
    bvid = extract_bilibili_bvid(url)
    fetched_at = now_local_iso()
    options = source.get("options") if isinstance(source.get("options"), dict) else {}
    metadata = _fetch_bilibili_metadata(session, bvid)
    title = str(metadata.get("title") or bvid)
    owner = metadata.get("owner") if isinstance(metadata.get("owner"), dict) else {}
    published_at = _timestamp_to_iso(metadata.get("pubdate"))
    video_url = f"https://www.bilibili.com/video/{bvid}/"

    export_root_path = Path(export_root)
    download_subtitles = bool(options.get("download_subtitles", True))
    transcript, segments, subtitle_url, raw_subtitle_text = _fetch_bilibili_subtitles(session, metadata)
    transcript_source = "official_subtitle" if transcript else ""
    asr_result: dict[str, Any] | None = None
    audio_path = ""
    raw_subtitle_file = ""
    danmaku_text = ""
    danmaku_segments: list[dict[str, Any]] = []
    danmaku_url = ""
    danmaku_file = ""
    errors: list[str] = []

    if raw_subtitle_text and download_subtitles:
        raw_subtitle_file = _write_bilibili_text_resource(
            source,
            title=title,
            bvid=bvid,
            suffix=".subtitle.json",
            content=raw_subtitle_text,
            export_root=export_root_path,
        )

    if not transcript and bool(options.get("transcribe", True)):
        try:
            audio = _download_bilibili_audio(session, metadata)
            audio_path = str(audio)
            asr_result = transcribe_audio_file(audio, options)
            transcript = str(asr_result.get("text") or "").strip()
            segments = asr_result.get("segments") if isinstance(asr_result.get("segments"), list) else []
            transcript_source = str(asr_result.get("provider") or "asr")
        except Exception as exc:  # noqa: BLE001 - keep source result visible
            errors.append(f"ASR 转写失败：{exc}")

    if not transcript and download_subtitles:
        try:
            danmaku_file, raw_danmaku_xml = _read_bilibili_text_resource(
                source,
                title=title,
                bvid=bvid,
                suffix=".danmaku.xml",
                export_root=export_root_path,
            )
            if raw_danmaku_xml:
                normalized_danmaku_xml = _normalize_bilibili_xml_text(raw_danmaku_xml)
                if normalized_danmaku_xml != raw_danmaku_xml:
                    raw_danmaku_xml = normalized_danmaku_xml
                    danmaku_file = _write_bilibili_text_resource(
                        source,
                        title=title,
                        bvid=bvid,
                        suffix=".danmaku.xml",
                        content=raw_danmaku_xml,
                        export_root=export_root_path,
                    )
                danmaku_text, danmaku_segments = _parse_bilibili_danmaku(raw_danmaku_xml, bvid=bvid)
                danmaku_url = f"https://api.bilibili.com/x/v1/dm/list.so?oid={metadata.get('cid') or ''}"
            else:
                danmaku_text, danmaku_segments, danmaku_url, raw_danmaku_xml = _fetch_bilibili_danmaku(session, metadata)
                danmaku_file = _write_bilibili_text_resource(
                    source,
                    title=title,
                    bvid=bvid,
                    suffix=".danmaku.xml",
                    content=raw_danmaku_xml,
                    export_root=export_root_path,
                )
        except Exception as exc:  # noqa: BLE001 - keep source result visible
            errors.append(f"弹幕资源下载失败：{exc}")

    text_source_label = transcript_source or ("danmaku" if danmaku_text else "")
    content_parts = [
        f"# {title}",
        "",
        f"- UP主：{owner.get('name') or ''}",
        f"- 发布时间：{published_at}",
        f"- 视频链接：{video_url}",
        f"- 文本来源：{text_source_label or '未取得字幕/转写'}",
        "",
    ]
    if raw_subtitle_file:
        content_parts.extend([f"- 字幕资源：{raw_subtitle_file}"])
    if danmaku_file:
        content_parts.extend([f"- 弹幕资源：{danmaku_file}"])
    if raw_subtitle_file or danmaku_file:
        content_parts.append("")
    if transcript:
        content_parts.extend(["## 转写文本", "", transcript, ""])
    if transcript and segments:
        content_parts.extend(["## 时间线文本", "", _format_segments(segments), ""])
    if not transcript and danmaku_text:
        content_parts.extend(["## 弹幕文本（非口播字幕）", "", danmaku_text, ""])
    if not transcript and danmaku_segments:
        content_parts.extend(["## 弹幕时间线", "", _format_segments(danmaku_segments), ""])
    if metadata.get("desc"):
        content_parts.extend(["## 简介", "", str(metadata.get("desc") or "").strip(), ""])
    content_markdown = "\n".join(content_parts).strip()

    item = _build_media_item(
        item_id=f"bilibili_video:{bvid}",
        source=source,
        source_type="bilibili_video",
        source_name_prefix="B站",
        title=title,
        url=video_url,
        author=str(owner.get("name") or ""),
        published_at=published_at,
        fetched_at=fetched_at,
        content_markdown=content_markdown,
        metadata={
            "bvid": bvid,
            "aid": metadata.get("aid"),
            "cid": metadata.get("cid"),
            "duration": metadata.get("duration"),
            "cover": metadata.get("pic") or "",
            "subtitle_url": subtitle_url,
            "transcript_source": transcript_source,
            "raw_subtitle_file": raw_subtitle_file,
            "danmaku_url": danmaku_url,
            "danmaku_file": danmaku_file,
            "danmaku_count": len(danmaku_segments),
            "subtitle_resource_type": "official_subtitle" if raw_subtitle_file else ("danmaku" if danmaku_file else ""),
            "asr": {k: v for k, v in (asr_result or {}).items() if k not in {"segments", "text"}},
            "audio_path": audio_path,
        },
    )
    if raw_subtitle_file:
        item["references"].append({"type": "subtitle_resource", "path": raw_subtitle_file})
    if danmaku_file:
        item["references"].append({"type": "danmaku_resource", "path": danmaku_file})
    raw_source_file = ""
    if bool(options.get("snapshot_raw_sources", False)):
        raw_source_file = _write_media_raw_snapshot(source, item, export_root_path, RAW_BILIBILI_ROOT)
        item["references"].append({"type": "source_snapshot", "path": raw_source_file})
        item["metadata"]["raw_source_file"] = raw_source_file

    return {
        "source_id": source["id"],
        "source_type": source["type"],
        "items_fetched": 1,
        "raw_items": 1,
        "content_items": [item],
        "errors": errors,
        "fetch_mode": "bilibili_api",
        "transcript_source": transcript_source,
        "snapshot_raw_sources": bool(options.get("snapshot_raw_sources", False)),
        "raw_sources_dir": str(Path(export_root) / RAW_BILIBILI_ROOT / safe_slug(source["id"], "source"))
        if bool(options.get("snapshot_raw_sources", False))
        else "",
    }


def sync_bilibili_space_source(
    source: dict[str, Any],
    *,
    session: requests.Session | None = None,
    export_root: str | Path = DEFAULT_EXPORT_ROOT,
) -> dict[str, Any]:
    session = session or _session()
    options = source.get("options") if isinstance(source.get("options"), dict) else {}
    listing = list_bilibili_space_videos(source, session=session)
    mid = str(listing.get("mid") or extract_bilibili_mid(source.get("url") or ""))
    archives = listing.get("archives") if isinstance(listing.get("archives"), list) else []
    errors = list(listing.get("errors") or [])
    content_items: list[dict[str, Any]] = []
    synced_bvids: list[str] = []

    for archive in archives:
        if not isinstance(archive, dict):
            continue
        bvid = str(archive.get("bvid") or "").strip()
        if not bvid:
            continue
        video_source = {
            **source,
            "type": "bilibili_video",
            "url": f"https://www.bilibili.com/video/{bvid}/",
            "options": options,
        }
        try:
            result = sync_bilibili_video_source(video_source, session=session, export_root=export_root)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{bvid} 同步失败：{exc}")
            continue
        errors.extend(result.get("errors") or [])
        items = result.get("content_items") if isinstance(result.get("content_items"), list) else []
        for item in items:
            item["source_id"] = source["id"]
            item["source_name"] = f"B站 / {source.get('name') or source['id']}"
            item["tags"] = options.get("tags", item.get("tags", []))
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            item["metadata"] = {
                **metadata,
                "space_mid": mid,
                "space_url": f"https://space.bilibili.com/{mid}/video",
                "space_source_id": source["id"],
                "space_source_type": source.get("type") or "bilibili_space",
                "space_list_fetch_mode": archive.get("fetch_mode") or "",
                "space_series_id": archive.get("series_id") or "",
                "space_series_name": archive.get("series_name") or "",
            }
            for reference in item.get("references") or []:
                if isinstance(reference, dict) and reference.get("type") == "bilibili_video":
                    reference["source_id"] = source["id"]
            content_items.append(item)
            synced_bvids.append(str(item.get("metadata", {}).get("bvid") or bvid))

    snapshot_enabled = bool(options.get("snapshot_raw_sources", False))
    return {
        "source_id": source["id"],
        "source_type": source.get("type") or "bilibili_space",
        "items_fetched": len(content_items),
        "raw_items": len(archives),
        "content_items": content_items,
        "errors": errors,
        "fetch_mode": ",".join(listing.get("fetch_modes") or []) or "bilibili_space",
        "space_mid": mid,
        "space_video_total": listing.get("space_video_total") or 0,
        "archives_discovered": listing.get("archives_discovered") or len(archives),
        "synced_bvids": synced_bvids,
        "snapshot_raw_sources": snapshot_enabled,
        "raw_sources_dir": str(Path(export_root) / RAW_BILIBILI_ROOT / safe_slug(source["id"], "source"))
        if snapshot_enabled
        else "",
    }


def _xml_text(element: ET.Element | None, default: str = "") -> str:
    if element is None or element.text is None:
        return default
    return element.text.strip()


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if child.tag.rsplit("}", 1)[-1].lower() == name.lower():
            return child
    return None


def _find_children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in element if child.tag.rsplit("}", 1)[-1].lower() == name.lower()]


def _podcast_enclosure_url(item: ET.Element) -> str:
    for enclosure in _find_children(item, "enclosure"):
        url = enclosure.attrib.get("url")
        if url:
            return url
    for child in item.iter():
        local_name = child.tag.rsplit("}", 1)[-1].lower()
        if local_name == "content" and child.attrib.get("url"):
            medium = child.attrib.get("medium", "")
            mime = child.attrib.get("type", "")
            if medium == "audio" or mime.startswith("audio/"):
                return child.attrib["url"]
    return ""


def _podcast_episode_id(source_id: str, item: ET.Element, title: str, link: str) -> str:
    guid = _xml_text(_find_child(item, "guid"))
    raw_id = guid or link or title
    return f"podcast_episode:{safe_slug(source_id, 'podcast')}:{content_hash(raw_id)[:16]}"


def sync_podcast_feed_source(
    source: dict[str, Any],
    *,
    session: requests.Session | None = None,
    export_root: str | Path = DEFAULT_EXPORT_ROOT,
) -> dict[str, Any]:
    session = session or _session()
    options = source.get("options") if isinstance(source.get("options"), dict) else {}
    max_items = int(options.get("max_items", 3))
    transcribe = bool(options.get("transcribe", False))
    fetched_at = now_local_iso()
    feed_url = source.get("url") or ""
    xml_text = _get_text(session, feed_url, headers={"Accept": "application/rss+xml,application/xml,text/xml,*/*"})
    root = ET.fromstring(xml_text)
    channel = root.find("channel") or root
    feed_title = _xml_text(_find_child(channel, "title"), source.get("name") or source["id"])
    feed_author = _xml_text(_find_child(channel, "author")) or _xml_text(_find_child(channel, "creator"))
    episodes = _find_children(channel, "item")[: max(1, max_items)]

    content_items: list[dict[str, Any]] = []
    errors: list[str] = []
    for episode in episodes:
        title = _xml_text(_find_child(episode, "title"), "未命名播客")
        link = _xml_text(_find_child(episode, "link"), feed_url)
        published_at = _pubdate_to_iso(_xml_text(_find_child(episode, "pubDate")))
        description = _strip_html(_xml_text(_find_child(episode, "description")))
        audio_url = _podcast_enclosure_url(episode)
        author = _xml_text(_find_child(episode, "author")) or feed_author
        transcript = ""
        transcript_source = ""
        audio_path = ""
        asr_result: dict[str, Any] | None = None

        if transcribe and audio_url:
            try:
                dest = (
                    MEDIA_CACHE_DIR
                    / "podcast"
                    / safe_slug(source["id"], "podcast")
                    / f"{safe_slug(title, 'episode', 64)}{_audio_extension(audio_url)}"
                )
                audio = _download_file(session, audio_url, dest)
                audio_path = str(audio)
                asr_result = transcribe_audio_file(audio, options)
                transcript = str(asr_result.get("text") or "").strip()
                transcript_source = str(asr_result.get("provider") or "asr") if transcript else ""
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{title} ASR 转写失败：{exc}")

        content_parts = [
            f"# {title}",
            "",
            f"- 播客：{feed_title}",
            f"- 作者：{author}",
            f"- 发布时间：{published_at}",
            f"- 原始链接：{link}",
            f"- 音频链接：{audio_url}",
            "",
        ]
        if description:
            content_parts.extend(["## 节目简介", "", description, ""])
        if transcript:
            content_parts.extend(["## 转写文本", "", transcript, ""])
        content_markdown = "\n".join(content_parts).strip()
        item = _build_media_item(
            item_id=_podcast_episode_id(source["id"], episode, title, link),
            source=source,
            source_type="podcast_episode",
            source_name_prefix="播客",
            title=title,
            url=link,
            author=author,
            published_at=published_at,
            fetched_at=fetched_at,
            content_markdown=content_markdown,
            metadata={
                "feed_url": feed_url,
                "feed_title": feed_title,
                "audio_url": audio_url,
                "transcript_source": transcript_source,
                "asr": {k: v for k, v in (asr_result or {}).items() if k not in {"segments", "text"}},
                "audio_path": audio_path,
            },
        )
        if bool(options.get("snapshot_raw_sources", False)):
            raw_source_file = _write_media_raw_snapshot(source, item, Path(export_root), RAW_PODCAST_ROOT)
            item["references"].append({"type": "source_snapshot", "path": raw_source_file})
            item["metadata"]["raw_source_file"] = raw_source_file
        content_items.append(item)

    return {
        "source_id": source["id"],
        "source_type": source["type"],
        "items_fetched": len(content_items),
        "raw_items": len(content_items),
        "content_items": content_items,
        "errors": errors,
        "fetch_mode": "podcast_rss",
        "snapshot_raw_sources": bool(options.get("snapshot_raw_sources", False)),
        "raw_sources_dir": str(Path(export_root) / RAW_PODCAST_ROOT / safe_slug(source["id"], "source"))
        if bool(options.get("snapshot_raw_sources", False))
        else "",
    }
