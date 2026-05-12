#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.llm_wiki_bridge import export_llm_wiki_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Export WeChat OA articles as llm_wiki raw sources.")
    parser.add_argument(
        "--export-root",
        default=None,
        help="Target llm_wiki project root. Defaults to data/llm_wiki/wechat_oa.",
    )
    args = parser.parse_args()

    result = export_llm_wiki_sources(Path(args.export_root) if args.export_root else None)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
