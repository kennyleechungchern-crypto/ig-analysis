#!/usr/bin/env python3
"""
IG Daily Analysis – entry point.

Required environment variables:
  IG_ACCESS_TOKEN    – Instagram Graph API long-lived access token
  ANTHROPIC_API_KEY  – Claude API key
  NOTION_TOKEN       – Notion integration token
  NOTION_PAGE_ID     – Parent Notion page ID where reports will be created
"""

import json
import os
import sys
from pathlib import Path

from fetcher import fetch_all
from analyzer import analyze
from reporter import create_report_page


def _require(var: str) -> str:
    value = os.environ.get(var)
    if not value:
        print(f"[ERROR] 缺少环境变量: {var}")
        sys.exit(1)
    return value


def main():
    ig_token = _require("IG_ACCESS_TOKEN")
    notion_token = _require("NOTION_TOKEN")
    notion_page_id = _require("NOTION_PAGE_ID")
    # ANTHROPIC_API_KEY is picked up automatically by the anthropic SDK

    print("📥 正在抓取 Instagram 数据...")
    data = fetch_all(ig_token)
    print(f"   Posts: {len(data['posts'])}  |  Reels: {len(data['reels'])}")

    # Save raw data snapshot
    snapshot_dir = Path("data")
    snapshot_dir.mkdir(exist_ok=True)
    snapshot_path = snapshot_dir / f"{data['fetched_at'][:10]}.json"
    snapshot_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"   已保存原始数据 → {snapshot_path}")

    print("🤖 正在用 Claude 分析数据...")
    analysis = analyze(data)

    print("📝 正在将报告写入 Notion...")
    page_url = create_report_page(notion_token, notion_page_id, analysis, data)
    print(f"   ✅ 报告已创建：{page_url}")

    print("\n--- 分析摘要（前 500 字）---")
    print(analysis[:500])


if __name__ == "__main__":
    main()
