#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
将已爬取的公众号文章导出为本地 Markdown 文件。

用法：
    uv run python scripts/export_markdown.py                    # 导出到 data/markdown/
    uv run python scripts/export_markdown.py /path/to/output    # 导出到指定目录

文件结构：
    output_dir/
        记忆承载/
            2026-04-02-文章标题.md
            2026-04-03-另一篇文章.md
        另一个公众号/
            ...
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 清除代理，避免请求走代理超时
for _k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
    os.environ.pop(_k, None)
os.environ["NO_PROXY"] = "127.0.0.1,localhost"

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# 确保 src 模块可被 import
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sanitize_filename(name: str, max_len: int = 80) -> str:
    """清理文件名中的非法字符。"""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '', name)
    name = name.strip('. ')
    return name[:max_len] if len(name) > max_len else name


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_article_text(article_id: str, link: str, detail_text_cache: dict) -> list[str] | None:
    """
    获取文章正文段落列表。
    优先从缓存读取，缓存中没有则从链接实时拉取。
    """
    cached = detail_text_cache.get(article_id)
    if cached is not None:
        if isinstance(cached, list):
            return cached
        # 缓存的是错误信息字符串，尝试重新拉取
        if cached in ('已删除', '请求错误'):
            print(f"  缓存为 '{cached}'，尝试重新拉取: {article_id}")
        else:
            return None

    # 实时拉取
    print(f"  正在拉取正文: {article_id}")
    try:
        from src.utils.helpers import url2text
        result = url2text(link)
        if isinstance(result, list):
            return result
        print(f"  拉取失败: {result}")
    except Exception as e:
        print(f"  拉取异常: {e}")
    return None


def _path_matches_article(filepath: Path, link: str, article_id: str) -> bool:
    """判断已存在的 Markdown 是否对应同一篇文章。"""
    try:
        content = filepath.read_text(encoding='utf-8', errors='ignore')[:1000]
    except OSError:
        return False
    return (
        (link and f'source: "{link}"' in content)
        or (article_id and f'id: "{article_id}"' in content)
    )


def resolve_output_path(account_dir: Path, base_stem: str, article_id: str, link: str) -> tuple[Path, bool]:
    """
    生成不会覆盖其它文章的输出路径。

    若同一天出现同名文章，原始文件名会冲突；此时追加 article_id 后缀。
    返回值第二项表示目标文件是否已存在且对应同一篇文章，可直接跳过。
    """
    filepath = account_dir / f"{base_stem}.md"
    if not filepath.exists():
        return filepath, False
    if _path_matches_article(filepath, link, article_id):
        return filepath, True

    suffix = sanitize_filename(article_id, max_len=40) or "duplicate"
    dedup_path = account_dir / f"{base_stem}-{suffix}.md"
    if not dedup_path.exists():
        return dedup_path, False
    if _path_matches_article(dedup_path, link, article_id):
        return dedup_path, True

    i = 2
    while True:
        candidate = account_dir / f"{base_stem}-{suffix}-{i}.md"
        if not candidate.exists():
            return candidate, False
        if _path_matches_article(candidate, link, article_id):
            return candidate, True
        i += 1


def build_markdown(article_id: str, title: str, author: str, create_time: str, link: str,
                   digest: str, paragraphs: list[str] | None) -> str:
    """组装 Markdown 内容（含 frontmatter）。"""
    tags_line = ""
    frontmatter = f"""---
title: "{title}"
author: "{author}"
date: "{create_time}"
source: "{link}"
id: "{article_id}"
---

"""
    body_parts = []
    if digest:
        body_parts.append(f"> {digest}\n")

    if paragraphs:
        body_parts.append("\n\n".join(paragraphs))
    else:
        body_parts.append("（正文获取失败）")

    return frontmatter + "\n\n".join(body_parts) + "\n"


def export(output_dir: Path) -> None:
    message_info = load_json(DATA_DIR / "message_info.json")
    detail_text_cache = load_json(DATA_DIR / "message_detail_text.json")

    if not message_info:
        print("message_info.json 为空，没有文章可导出。")
        return

    total_exported = 0
    total_skipped = 0

    for account_name, account_data in message_info.items():
        blogs = account_data.get("blogs", [])
        if not blogs:
            print(f"\n[{account_name}] 无文章，跳过。")
            continue

        account_dir = output_dir / sanitize_filename(account_name)
        account_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[{account_name}] {len(blogs)} 篇文章 → {account_dir}")

        for article in blogs:
            article_id = article["id"]
            title = article.get("title", "untitled")
            create_time = article.get("create_time", "")
            link = article.get("link", "")
            digest = article.get("digest", "")
            is_deleted = article.get("is_deleted", False)

            if is_deleted:
                total_skipped += 1
                continue

            # 文件名：日期-标题.md
            date_prefix = create_time.split(" ")[0] if create_time else "unknown-date"
            base_stem = sanitize_filename(f"{date_prefix}-{title}")
            filepath, already_exported = resolve_output_path(account_dir, base_stem, article_id, link)
            filename = filepath.name

            # 跳过已导出的（幂等）
            if already_exported:
                total_exported += 1
                continue

            paragraphs = get_article_text(article_id, link, detail_text_cache)
            md_content = build_markdown(article_id, title, account_name, create_time, link, digest, paragraphs)

            filepath.write_text(md_content, encoding='utf-8')
            total_exported += 1
            print(f"  ✓ {filename}")

    print(f"\n导出完成: {total_exported} 篇, 跳过(已删除): {total_skipped} 篇")
    print(f"输出目录: {output_dir}")


def main() -> None:
    if len(sys.argv) > 1:
        output_dir = Path(sys.argv[1])
    else:
        output_dir = DATA_DIR / "markdown"

    output_dir = output_dir.resolve()
    print(f"开始导出文章到: {output_dir}")
    export(output_dir)


if __name__ == "__main__":
    main()
