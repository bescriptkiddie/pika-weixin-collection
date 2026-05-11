#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.content_loop import sync_external_sources


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync configured external source connectors into content_items.jsonl.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="External source config path. Defaults to data/external_sources.json, with example fallback.",
    )
    parser.add_argument(
        "--export-root",
        default=None,
        help="Optional raw snapshot root when a source sets options.snapshot_raw_sources=true.",
    )
    parser.add_argument(
        "--content-items",
        default=None,
        help="Target content pool JSONL path. Defaults to data/content_items.jsonl.",
    )
    parser.add_argument(
        "--no-example-fallback",
        action="store_true",
        help="Do not import from data/external_sources.example.json when data/external_sources.json is missing.",
    )
    args = parser.parse_args()

    result = sync_external_sources(
        config_path=Path(args.config) if args.config else None,
        export_root=Path(args.export_root) if args.export_root else None,
        content_items_path=Path(args.content_items) if args.content_items else None,
        use_example=not args.no_example_fallback,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
