from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.utils.data_manager import data_manager

DEFAULT_EXPORT_ROOT = Path(__file__).parent.parent.parent / "data" / "llm_wiki" / "wechat_oa"


@dataclass
class LLMWikiExportResult:
    export_root: str
    raw_sources_dir: str
    exported: int
    skipped: int
    accounts: int


def _yaml_value(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _safe_filename(text: str, fallback: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", " ", text).strip()
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = fallback
    return name[:80].rstrip(". ")


def _detail_to_markdown(detail: Any, digest: str) -> str:
    if isinstance(detail, list):
        parts = [str(part).strip() for part in detail if str(part).strip()]
    elif isinstance(detail, str) and detail.strip():
        parts = [detail.strip()]
    else:
        parts = [digest.strip()] if digest.strip() else []

    if not parts:
        return "_正文缓存为空，等待下一次采集补全。_"
    return "\n\n".join(parts)


def _write_project_scaffold(root: Path) -> None:
    (root / "raw" / "sources" / "wechat").mkdir(parents=True, exist_ok=True)
    (root / "wiki").mkdir(parents=True, exist_ok=True)
    (root / ".llm-wiki").mkdir(parents=True, exist_ok=True)

    purpose = root / "purpose.md"
    if not purpose.exists():
        purpose.write_text(
            "\n".join(
                [
                    "# 公众号知识库目标",
                    "",
                    "把持续采集的微信公众号文章沉淀为可检索、可关联、可追溯的个人知识库。",
                    "",
                    "重点关注：文章主题、作者观点、产品/技术/市场实体、跨公众号共识与分歧、长期趋势。",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    schema = root / "schema.md"
    if not schema.exists():
        schema.write_text(
            "\n".join(
                [
                    "# Wiki Schema",
                    "",
                    "- `wiki/sources/`: 单篇公众号文章的来源摘要。",
                    "- `wiki/entities/`: 人物、公司、产品、项目、模型、公众号作者。",
                    "- `wiki/concepts/`: 技术概念、市场主题、创作方法、投资/职业观点。",
                    "- `wiki/synthesis/`: 跨文章综合、周期性观察和主题复盘。",
                    "",
                    "所有页面必须保留 `sources` 字段，指向 `raw/sources/wechat/...` 下的原始文章 Markdown。",
                    "",
                ]
            ),
            encoding="utf-8",
        )

    index = root / "wiki" / "index.md"
    if not index.exists():
        index.write_text("# Index\n\n- [[overview]]\n", encoding="utf-8")

    overview = root / "wiki" / "overview.md"
    if not overview.exists():
        overview.write_text(
            "---\ntype: synthesis\ntitle: 公众号知识库概览\ntags: []\nrelated: []\nsources: []\n---\n\n# 公众号知识库概览\n\n等待摄入后生成。\n",
            encoding="utf-8",
        )

    log = root / "wiki" / "log.md"
    if not log.exists():
        log.write_text("# Log\n", encoding="utf-8")


def _article_markdown(account: str, article: dict[str, Any], detail: Any) -> str:
    title = str(article.get("title") or "未命名文章").strip()
    digest = str(article.get("digest") or "").strip()
    tags = article.get("tags") if isinstance(article.get("tags"), list) else []
    body = _detail_to_markdown(detail, digest)

    frontmatter = [
        "---",
        "type: source",
        "source_type: wechat_article",
        f"title: {_yaml_value(title)}",
        f"account: {_yaml_value(account)}",
        f"article_id: {_yaml_value(article.get('id') or '')}",
        f"url: {_yaml_value(article.get('link') or '')}",
        f"published_at: {_yaml_value(article.get('create_time') or '')}",
        f"digest: {_yaml_value(digest)}",
        f"tags: {_yaml_value(tags)}",
        "origin: wechat-official-account",
        "sources: []",
        "---",
        "",
    ]
    meta = [
        f"# {title}",
        "",
        f"- 公众号：{account}",
        f"- 发布时间：{article.get('create_time') or ''}",
        f"- 原文链接：{article.get('link') or ''}",
        "",
    ]
    if digest:
        meta.extend(["## 摘要", "", digest, ""])
    meta.extend(["## 正文", "", body, ""])
    return "\n".join(frontmatter + meta)


def export_llm_wiki_sources(export_root: str | Path | None = DEFAULT_EXPORT_ROOT) -> LLMWikiExportResult:
    root = Path(export_root) if export_root is not None else DEFAULT_EXPORT_ROOT
    _write_project_scaffold(root)

    data_manager.reload("name2fakeid")
    data_manager.reload("message_info")
    data_manager.reload("message_detail_text")

    tracked_accounts = set(data_manager.name2fakeid.keys())
    exported = 0
    skipped = 0
    accounts_seen = 0
    raw_root = root / "raw" / "sources" / "wechat"

    for account, account_data in data_manager.message_info.items():
        if tracked_accounts and account not in tracked_accounts:
            continue
        blogs = account_data.get("blogs", []) if isinstance(account_data, dict) else []
        if not blogs:
            continue
        accounts_seen += 1
        account_dir = raw_root / _safe_filename(account, "account")
        account_dir.mkdir(parents=True, exist_ok=True)

        for article in blogs:
            if not isinstance(article, dict) or article.get("is_deleted"):
                skipped += 1
                continue
            article_id = str(article.get("id") or "")
            if not article_id:
                skipped += 1
                continue
            date = str(article.get("create_time") or "unknown").split(" ")[0]
            title = _safe_filename(str(article.get("title") or ""), "untitled")
            suffix = _safe_filename(article_id, "article")[-24:]
            dest = account_dir / f"{date}-{title}-{suffix}.md"
            detail = data_manager.message_detail_text.get(article_id)
            dest.write_text(_article_markdown(account, article, detail), encoding="utf-8")
            exported += 1

    return LLMWikiExportResult(
        export_root=str(root),
        raw_sources_dir=str(raw_root),
        exported=exported,
        skipped=skipped,
        accounts=accounts_seen,
    )
