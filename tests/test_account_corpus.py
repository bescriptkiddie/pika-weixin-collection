from __future__ import annotations

from src.content_loop.store import build_wechat_account_corpus


def test_account_corpus_is_filtered_bounded_and_reports_coverage() -> None:
    body = "有效正文" * 200
    message_info = {
        "甲公众号": {
            "blogs": [
                {"id": "a1", "title": "第一篇", "create_time": "2026-08-25", "link": "https://example.com/a1"},
                {"id": "a2", "title": "第二篇", "create_time": "2026-08-26", "link": "https://example.com/a2"},
            ]
        },
        "乙公众号": {"blogs": [{"id": "b1", "title": "不应出现", "create_time": "2026-08-26"}]},
    }
    result = build_wechat_account_corpus(
        "甲公众号",
        limit=1,
        message_info=message_info,
        detail_texts={"a1": body, "a2": "短文", "b1": body},
    )

    assert result["account"] == "甲公众号"
    assert [article["id"] for article in result["articles"]] == ["wechat_article:a2"]
    assert result["coverage"] == {
        "total_articles": 2,
        "returned_articles": 1,
        "with_content": 2,
        "substantial_articles": 1,
        "date_from": "2026-08-25",
        "date_to": "2026-08-26",
    }
