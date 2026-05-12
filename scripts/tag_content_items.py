#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.content_loop import apply_tags_to_content_items


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply local topic tags to data/content_items.jsonl.")
    parser.add_argument(
        "--taxonomy",
        default=None,
        help="Tag taxonomy JSON path. Defaults to data/tag_taxonomy.json, with example fallback.",
    )
    parser.add_argument(
        "--content-items",
        default=None,
        help="Content items JSONL path. Defaults to data/content_items.jsonl.",
    )
    args = parser.parse_args()

    kwargs = {}
    if args.content_items:
        kwargs["content_items_path"] = Path(args.content_items)
    if args.taxonomy:
        kwargs["taxonomy_path"] = Path(args.taxonomy)
    result = apply_tags_to_content_items(**kwargs)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
