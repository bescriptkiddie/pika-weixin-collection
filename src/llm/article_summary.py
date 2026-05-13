"""
爬取后为新文章生成中文摘要：优先提炼正文核心信息，输出适合在信息流中直接展示的短摘要。
"""

from __future__ import annotations

from typing import Any

from src.llm.article_tagging import _body_excerpt
from src.llm.model_client import chat_qwen35_27b, qwen_endpoint_configured

MAX_SUMMARY_CHARS = 120

_SYSTEM_PROMPT = f"""你是微信公众号文章的摘要助手。请根据标题、原始摘要与正文片段，生成一段适合信息流展示的中文摘要。

规则：
- 只输出摘要正文，不要加标题、引号、编号、前缀或解释。
- 控制在 {MAX_SUMMARY_CHARS} 个中文字符内，尽量 60～100 字。
- 优先提炼文章核心观点、结论、方法或事件进展，避免空泛套话。
- 若原始摘要已经足够清楚，可压缩重写，但不要机械复述。
- 若正文片段明显是广告、营销、引流或商务合作内容，要如实点明其推广性质。"""


def _clean_summary(content: str) -> str:
    s = (content or "").strip()
    s = s.replace("\r", " ").replace("\n", " ")
    while "  " in s:
        s = s.replace("  ", " ")
    if len(s) > MAX_SUMMARY_CHARS:
        s = s[:MAX_SUMMARY_CHARS].rstrip("，,、；;：:。.!！？? ")
    return s


def summarize_article(article: dict[str, Any], data_manager: Any) -> str:
    """
    为单篇文章生成摘要。未配置 LLM endpoint 时返回空字符串。

    :param article: message_info 中 blogs 的一项（含 id/title/digest）
    :param data_manager: JsonFileManager 单例，用于读取 message_detail_text
    """
    if not qwen_endpoint_configured():
        return ""

    aid = article.get("id") or ""
    title = (article.get("title") or "").strip()
    digest = (article.get("digest") or "").strip()
    detail = None
    if aid and hasattr(data_manager, "message_detail_text"):
        detail = data_manager.message_detail_text.get(aid)
    excerpt = _body_excerpt(detail)

    user = f"""标题：{title}
原始摘要：{digest}
正文片段（可能不完整或为空）：
{excerpt}
"""
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user},
    ]
    try:
        raw = chat_qwen35_27b(messages)
        return _clean_summary(raw)
    except Exception as e:
        print(f"[summary] LLM 调用失败 article_id={aid!r}: {e}")
        return ""
