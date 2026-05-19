from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from .store import (
    CONTENT_ITEMS_FILE,
    DATA_DIR,
    content_hash,
    load_external_source_configs,
    now_local_iso,
    read_jsonl,
    safe_slug,
    summary_from_text,
    upsert_content_items,
    write_jsonl,
)
from .media_sources import sync_bilibili_space_source, sync_bilibili_video_source, sync_podcast_feed_source

DEFAULT_EXPORT_ROOT = DATA_DIR / "llm_wiki" / "wechat_oa"
RAW_GITHUB_ROOT = Path("raw") / "sources" / "github"


class ExternalSourceImportError(RuntimeError):
    pass


def parse_github_repo_url(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"github.com", "www.github.com"}:
        raise ExternalSourceImportError(f"不是 GitHub 仓库 URL：{url}")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise ExternalSourceImportError(f"无法解析 GitHub owner/repo：{url}")
    repo = parts[1].removesuffix(".git")
    return parts[0], repo


def _github_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "User-Agent": "pika-weixin-content-loop",
        }
    )
    token = __import__("os").environ.get("GITHUB_TOKEN", "").strip()
    if token:
        session.headers["Authorization"] = f"Bearer {token}"
    return session


def _get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Any:
    response = session.get(url, params=params, timeout=20)
    if response.status_code == 404:
        raise FileNotFoundError(url)
    response.raise_for_status()
    return response.json()


def _get_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=20)
    response.raise_for_status()
    return response.text


def _frontmatter_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _raw_source_markdown(item: dict[str, Any], source: dict[str, Any]) -> str:
    frontmatter = [
        "---",
        "type: source",
        "source_type: github_repo",
        f"source_id: {_frontmatter_value(source['id'])}",
        f"source_name: {_frontmatter_value(source.get('name') or source['id'])}",
        f"title: {_frontmatter_value(item['title'])}",
        f"url: {_frontmatter_value(item.get('url') or '')}",
        f"published_at: {_frontmatter_value(item.get('published_at') or '')}",
        f"fetched_at: {_frontmatter_value(item.get('fetched_at') or '')}",
        f"human_reason: {_frontmatter_value(source.get('human_reason') or '')}",
        f"metadata: {_frontmatter_value(item.get('metadata') or {})}",
        "sources: []",
        "---",
        "",
        f"# {item['title']}",
        "",
        f"- 来源：GitHub / {source.get('name') or source['id']}",
        f"- URL：{item.get('url') or ''}",
        f"- 抓取时间：{item.get('fetched_at') or ''}",
        "",
    ]
    if item.get("digest"):
        frontmatter.extend(["## 摘要", "", str(item["digest"]), ""])
    frontmatter.extend(["## 内容", "", str(item.get("content_markdown") or ""), ""])
    return "\n".join(frontmatter)


def _raw_filename(item: dict[str, Any]) -> str:
    kind = item.get("metadata", {}).get("kind") or "item"
    title = safe_slug(str(item.get("title") or item.get("id") or "item"), "item", 72)
    for suffix in (".md", ".mdx", ".txt"):
        if title.lower().endswith(suffix):
            title = title[: -len(suffix)]
            break
    return f"{kind}-{title}.md"


def _github_content_items(
    source: dict[str, Any],
    items: list[dict[str, Any]],
    *,
    raw_source_paths: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    raw_source_paths = raw_source_paths or {}
    content_items: list[dict[str, Any]] = []
    for item in items:
        item_hash = content_hash(item["title"], item.get("digest", ""), item.get("content_markdown", ""))
        metadata = item.get("metadata") or {}
        references = [
            {"type": "url", "url": item.get("url") or ""},
            {
                "type": "github_repo",
                "source_id": source["id"],
                "repo_url": source.get("url") or "",
                "kind": metadata.get("kind") or "",
                "path": metadata.get("path") or "",
                "tag": metadata.get("tag") or "",
                "fetch_mode": "github_api",
            },
        ]
        raw_path = raw_source_paths.get(item["id"])
        if raw_path:
            references.append({"type": "source_snapshot", "path": raw_path})

        content_items.append(
            {
                "id": item["id"],
                "source_type": "github_repo",
                "source_id": source["id"],
                "source_name": f"GitHub / {source.get('name') or source['id']}",
                "title": item["title"],
                "url": item.get("url") or "",
                "author": item.get("author") or "",
                "published_at": item.get("published_at") or "",
                "fetched_at": item.get("fetched_at") or "",
                "summary": item.get("digest") or summary_from_text(item.get("content_markdown") or ""),
                "tags": source.get("options", {}).get("tags", []),
                "score": source.get("options", {}).get("initial_score", 0.0),
                "content_hash": item_hash,
                "dedupe_key": f"github_repo:{item_hash[:16]}",
                "status": "candidate",
                "content_markdown": item.get("content_markdown") or "",
                "references": references,
                "human_decision": "candidate",
                "feedback_notes": [],
                "metadata": {
                    **metadata,
                    "origin": "github",
                    "connector_type": "github_repo",
                    "fetch_mode": "github_api",
                    "source_config_id": source["id"],
                    "human_reason": source.get("human_reason") or "",
                    **({"raw_source_file": raw_path} if raw_path else {}),
                },
            }
        )
    return content_items


def _write_raw_source_snapshots(
    source: dict[str, Any],
    items: list[dict[str, Any]],
    export_root: Path,
) -> dict[str, str]:
    source_dir = export_root / RAW_GITHUB_ROOT / safe_slug(source["id"], "source")
    source_dir.mkdir(parents=True, exist_ok=True)

    raw_source_paths: dict[str, str] = {}
    for item in items:
        dest = source_dir / _raw_filename(item)
        dest.write_text(_raw_source_markdown(item, source), encoding="utf-8")
        rel_dest = str(dest.relative_to(export_root))
        raw_source_paths[item["id"]] = rel_dest
    return raw_source_paths


def normalize_github_connector_references(
    source: dict[str, Any],
    *,
    content_items_path: str | Path = CONTENT_ITEMS_FILE,
) -> dict[str, Any]:
    """Migrate old GitHub raw-file references to connector references in the content pool."""
    path = Path(content_items_path)
    rows = read_jsonl(path)
    normalized = 0

    for item in rows:
        if item.get("source_type") != "github_repo" or item.get("source_id") != source.get("id"):
            continue
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        github_ref = {
            "type": "github_repo",
            "source_id": source["id"],
            "repo_url": source.get("url") or "",
            "kind": metadata.get("kind") or "",
            "path": metadata.get("path") or "",
            "tag": metadata.get("tag") or "",
            "fetch_mode": "github_api",
        }
        refs = item.get("references") if isinstance(item.get("references"), list) else []
        next_refs = [ref for ref in refs if isinstance(ref, dict) and ref.get("type") != "llm_wiki_raw_source"]
        if not any(isinstance(ref, dict) and ref.get("type") == "github_repo" for ref in next_refs):
            insert_at = 1 if next_refs and next_refs[0].get("type") == "url" else len(next_refs)
            next_refs.insert(insert_at, github_ref)

        next_metadata = {
            **metadata,
            "origin": "github",
            "connector_type": "github_repo",
            "fetch_mode": "github_api",
            "source_config_id": source["id"],
            "human_reason": source.get("human_reason") or metadata.get("human_reason") or "",
        }
        next_metadata.pop("raw_source_file", None)

        if next_refs != refs or next_metadata != metadata:
            item["references"] = next_refs
            item["metadata"] = next_metadata
            normalized += 1

    if normalized:
        write_jsonl(path, rows)

    return {"source_id": source.get("id"), "references_normalized": normalized}


def _readme_item(
    session: requests.Session,
    *,
    owner: str,
    repo: str,
    source: dict[str, Any],
    fetched_at: str,
) -> dict[str, Any]:
    payload = _get_json(session, f"https://api.github.com/repos/{owner}/{repo}/readme")
    text = _get_text(session, payload["download_url"])
    return {
        "id": f"github_repo:{source['id']}:readme",
        "title": f"{source.get('name') or repo} README",
        "url": payload.get("html_url") or f"https://github.com/{owner}/{repo}",
        "author": owner,
        "published_at": "",
        "fetched_at": fetched_at,
        "digest": summary_from_text(text),
        "content_markdown": text,
        "metadata": {"kind": "readme", "path": payload.get("path") or "README.md"},
    }


def _docs_items(
    session: requests.Session,
    *,
    owner: str,
    repo: str,
    branch: str,
    source: dict[str, Any],
    fetched_at: str,
) -> list[dict[str, Any]]:
    options = source.get("options", {})
    doc_paths = options.get("docs_paths") if isinstance(options.get("docs_paths"), list) else ["docs"]
    max_docs = int(options.get("max_docs", 20))
    items: list[dict[str, Any]] = []

    def visit(path: str) -> None:
        if len(items) >= max_docs:
            return
        try:
            payload = _get_json(
                session,
                f"https://api.github.com/repos/{owner}/{repo}/contents/{path.strip('/')}",
                {"ref": branch},
            )
        except FileNotFoundError:
            return
        entries = payload if isinstance(payload, list) else [payload]
        for entry in entries:
            if len(items) >= max_docs or not isinstance(entry, dict):
                return
            entry_type = entry.get("type")
            entry_path = str(entry.get("path") or "")
            if entry_type == "dir":
                visit(entry_path)
            elif entry_type == "file" and re.search(r"\.(md|mdx|txt)$", entry_path, re.I):
                download_url = entry.get("download_url")
                if not download_url:
                    continue
                text = _get_text(session, download_url)
                file_id = safe_slug(entry_path, "doc", 120)
                items.append(
                    {
                        "id": f"github_repo:{source['id']}:doc:{file_id}",
                        "title": f"{source.get('name') or repo} / {entry_path}",
                        "url": entry.get("html_url") or f"https://github.com/{owner}/{repo}/blob/{branch}/{entry_path}",
                        "author": owner,
                        "published_at": "",
                        "fetched_at": fetched_at,
                        "digest": summary_from_text(text),
                        "content_markdown": text,
                        "metadata": {"kind": "doc", "path": entry_path},
                    }
                )

    for doc_path in doc_paths:
        visit(str(doc_path))
    return items


def _release_items(
    session: requests.Session,
    *,
    owner: str,
    repo: str,
    source: dict[str, Any],
    fetched_at: str,
) -> list[dict[str, Any]]:
    options = source.get("options", {})
    max_releases = int(options.get("max_releases", 10))
    payload = _get_json(
        session,
        f"https://api.github.com/repos/{owner}/{repo}/releases",
        {"per_page": max(1, min(max_releases, 100))},
    )
    if not isinstance(payload, list):
        return []

    items: list[dict[str, Any]] = []
    for release in payload[:max_releases]:
        if not isinstance(release, dict):
            continue
        tag = str(release.get("tag_name") or release.get("id") or "release")
        name = str(release.get("name") or tag)
        body = str(release.get("body") or "")
        content = "\n".join(
            [
                f"# {name}",
                "",
                f"- Tag: {tag}",
                f"- Published: {release.get('published_at') or ''}",
                "",
                body or "_没有 release note。_",
            ]
        )
        items.append(
            {
                "id": f"github_repo:{source['id']}:release:{safe_slug(tag, 'release')}",
                "title": f"{source.get('name') or repo} release {tag}",
                "url": release.get("html_url") or f"https://github.com/{owner}/{repo}/releases/tag/{tag}",
                "author": release.get("author", {}).get("login") or owner,
                "published_at": release.get("published_at") or "",
                "fetched_at": fetched_at,
                "digest": summary_from_text(body or name),
                "content_markdown": content,
                "metadata": {"kind": "release", "tag": tag, "draft": bool(release.get("draft"))},
            }
        )
    return items


def sync_github_repo_source(
    source: dict[str, Any],
    *,
    session: requests.Session | None = None,
    export_root: str | Path = DEFAULT_EXPORT_ROOT,
) -> dict[str, Any]:
    owner, repo = parse_github_repo_url(source.get("url") or "")
    session = session or _github_session()
    fetched_at = now_local_iso()
    repo_meta = _get_json(session, f"https://api.github.com/repos/{owner}/{repo}")
    branch = str(source.get("options", {}).get("branch") or repo_meta.get("default_branch") or "main")
    include_raw = source.get("options", {}).get("include", ["README", "docs", "releases"])
    include = {str(part).lower() for part in include_raw if str(part).strip()}
    snapshot_raw_sources = bool(source.get("options", {}).get("snapshot_raw_sources", False))

    raw_items: list[dict[str, Any]] = []
    errors: list[str] = []

    if "readme" in include:
        try:
            raw_items.append(_readme_item(session, owner=owner, repo=repo, source=source, fetched_at=fetched_at))
        except Exception as exc:  # noqa: BLE001 - keep importing other parts
            errors.append(f"README 导入失败：{exc}")

    if "docs" in include:
        try:
            raw_items.extend(_docs_items(session, owner=owner, repo=repo, branch=branch, source=source, fetched_at=fetched_at))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"docs 导入失败：{exc}")

    if "releases" in include:
        try:
            raw_items.extend(_release_items(session, owner=owner, repo=repo, source=source, fetched_at=fetched_at))
        except Exception as exc:  # noqa: BLE001
            errors.append(f"releases 导入失败：{exc}")

    raw_source_paths: dict[str, str] = {}
    if snapshot_raw_sources:
        raw_source_paths = _write_raw_source_snapshots(source, raw_items, Path(export_root))
    content_items = _github_content_items(source, raw_items, raw_source_paths=raw_source_paths)
    return {
        "source_id": source["id"],
        "source_type": source["type"],
        "items_fetched": len(raw_items),
        "raw_items": len(raw_items),
        "content_items": content_items,
        "errors": errors,
        "fetch_mode": "github_api",
        "snapshot_raw_sources": snapshot_raw_sources,
        "raw_sources_dir": str(Path(export_root) / RAW_GITHUB_ROOT / safe_slug(source["id"], "source"))
        if snapshot_raw_sources
        else "",
    }


def sync_external_sources(
    *,
    config_path: str | Path | None = None,
    export_root: str | Path | None = DEFAULT_EXPORT_ROOT,
    content_items_path: str | Path | None = None,
    use_example: bool = True,
    source_ids: list[str] | None = None,
) -> dict[str, Any]:
    export_root = export_root or DEFAULT_EXPORT_ROOT
    configs = load_external_source_configs(config_path, allow_example=use_example)
    all_sources = configs["sources"]
    selected_source_ids = {str(source_id) for source_id in (source_ids or []) if str(source_id).strip()}
    sources = [
        source for source in all_sources
        if not selected_source_ids or str(source.get("id")) in selected_source_ids
    ]
    imported_items: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    reference_results: list[dict[str, Any]] = []
    errors: list[str] = []
    skipped = 0
    content_pool_path = content_items_path or (DATA_DIR / "content_items.jsonl")

    for source in sources:
        if not source.get("enabled", True):
            skipped += 1
            continue
        source_type = source.get("type")
        try:
            if source_type == "github_repo":
                result = sync_github_repo_source(source, export_root=export_root)
            elif source_type == "bilibili_space":
                result = sync_bilibili_space_source(source, export_root=export_root)
            elif source_type == "bilibili_video":
                result = sync_bilibili_video_source(source, export_root=export_root)
            elif source_type == "podcast_feed":
                result = sync_podcast_feed_source(source, export_root=export_root)
            else:
                skipped += 1
                errors.append(f"暂不支持来源类型 {source_type}：{source.get('id')}")
                continue
            imported_items.extend(result.pop("content_items"))
            source_results.append(result)
            errors.extend(result.get("errors") or [])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source.get('id')} 同步失败：{exc}")
        if source_type == "github_repo":
            reference_results.append(
                normalize_github_connector_references(source, content_items_path=content_pool_path)
            )

    if imported_items:
        upsert_result = upsert_content_items(imported_items, path=content_pool_path)
        for source in sources:
            if source.get("enabled", True) and source.get("type") == "github_repo":
                reference_results.append(
                    normalize_github_connector_references(source, content_items_path=content_pool_path)
                )
    else:
        upsert_result = {
            "content_items_file": str(content_pool_path),
            "inserted": 0,
            "updated": 0,
            "total": len(read_jsonl(Path(content_pool_path))),
        }
    return {
        "config_path": configs["path"],
        "using_example_config": configs["using_example"],
        "export_root": str(export_root),
        "sources_total": len(all_sources),
        "sources_selected": len(sources),
        "sources_synced": len(source_results),
        "sources_imported": len(source_results),
        "sources_skipped": skipped,
        "items_synced": len(imported_items),
        "items_imported": len(imported_items),
        "content_pool": upsert_result,
        "fetch_mode": "source_connectors",
        "raw_sources_root": str(Path(export_root) / "raw" / "sources"),
        "reference_results": reference_results,
        "references_normalized": sum(int(item.get("references_normalized") or 0) for item in reference_results),
        "source_results": source_results,
        "errors": errors,
    }


def import_github_repo_source(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Backward-compatible alias. External repos are synced as live source connectors."""
    return sync_github_repo_source(*args, **kwargs)


def import_external_sources(*args: Any, **kwargs: Any) -> dict[str, Any]:
    """Backward-compatible alias. Use sync_external_sources for new code."""
    return sync_external_sources(*args, **kwargs)
