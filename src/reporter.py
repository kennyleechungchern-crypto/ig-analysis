import os
import requests
from datetime import datetime


NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": NOTION_VERSION,
    }


def _t(text: str, limit: int = 1990) -> str:
    return text[:limit] if len(text) > limit else text


def _markdown_to_blocks(text: str) -> list[dict]:
    blocks = []
    for line in text.split("\n"):
        if line.startswith("## "):
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {"rich_text": [{"type": "text", "text": {"content": _t(line[3:])}}]},
            })
        elif line.startswith("# "):
            blocks.append({
                "object": "block",
                "type": "heading_1",
                "heading_1": {"rich_text": [{"type": "text", "text": {"content": _t(line[2:])}}]},
            })
        elif line.startswith("- "):
            blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": _t(line[2:])}}]},
            })
        elif line.strip() == "":
            blocks.append({"object": "block", "type": "paragraph", "paragraph": {"rich_text": []}})
        else:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": [{"type": "text", "text": {"content": _t(line)}}]},
            })
    return blocks[:99]


def create_report_page(notion_token: str, parent_page_id: str, analysis: str, data: dict) -> str:
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    title = f"IG 每日分析报告 · {date_str}"

    summary_block = {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": [{"type": "text", "text": {"content": (
                f"📊 Posts: {len(data.get('posts', []))}  |  "
                f"🎬 Reels: {len(data.get('reels', []))}  |  "
                f"⏰ 抓取时间: {data.get('fetched_at', '')[:19]} UTC"
            )}}],
            "icon": {"type": "emoji", "emoji": "📈"},
        },
    }

    body_blocks = _markdown_to_blocks(analysis)

    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {
            "title": {"title": [{"type": "text", "text": {"content": title}}]}
        },
        "children": [summary_block] + body_blocks,
    }

    resp = requests.post(
        f"{NOTION_API_BASE}/pages",
        headers=_headers(notion_token),
        json=payload,
        timeout=30,
    )
    if not resp.ok:
        print(f"Notion error {resp.status_code}: {resp.text[:500]}")
    resp.raise_for_status()
    page = resp.json()
    return page["url"]
