#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.content_loop import ai_enrich_content_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Use configured LLM to summarize and classify content_items.jsonl.")
    parser.add_argument("--limit", type=int, default=30, help="Max items to process in this run.")
    parser.add_argument("--all", action="store_true", help="Process all matching items instead of only missing AI summaries.")
    parser.add_argument("--tag", default=None, help="Only process items containing this tag.")
    parser.add_argument("--source-type", default=None, help="Only process this source_type.")
    parser.add_argument("--max-chars", type=int, default=3200, help="Max chars sent to the model per item.")
    args = parser.parse_args()

    result = ai_enrich_content_items(
        limit=args.limit,
        only_missing=not args.all,
        tag=args.tag,
        source_type=args.source_type,
        max_chars=args.max_chars,
    )
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
