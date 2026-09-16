#!/usr/bin/env python3
"""Step 1 · 列出泰欣老师所有短视频 → data/videos.json（按播放量排序）

用法:
  python list_videos.py                 # 抓 sources.json 里所有 YouTube 频道
  python list_videos.py --cookies c.txt # 有 cookies 时同时抓 Instagram reels
"""
import argparse
import json
import subprocess
import sys

from common import DATA_DIR, HERE, VIDEOS_JSON, ytdlp_base_args


def flat_playlist(url: str, cookies: str | None) -> list[dict]:
    cmd = ytdlp_base_args(cookies) + ["--flat-playlist", "-J", url]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not proc.stdout.strip():
        print(f"  [warn] 抓不到 {url}: {proc.stderr.strip()[-300:]}", file=sys.stderr)
        return []
    data = json.loads(proc.stdout)
    return data.get("entries") or []


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cookies", help="Netscape cookies.txt（抓 IG 必须）")
    args = ap.parse_args()

    sources = json.loads((HERE / "sources.json").read_text(encoding="utf-8"))
    seen: dict[str, dict] = {}

    for ch in sources["youtube"]:
        for tab in ch["tabs"]:
            url = f"https://www.youtube.com/@{ch['handle']}/{tab}"
            print(f"📡 {url}")
            for e in flat_playlist(url, args.cookies):
                vid = e.get("id")
                if not vid or vid in seen:
                    continue
                seen[vid] = {
                    "id": vid,
                    "platform": "youtube",
                    "channel": ch["handle"],
                    "tab": tab,
                    "title": e.get("title") or "",
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "views": e.get("view_count") or 0,
                    "duration": e.get("duration"),
                }
            print(f"   累计 {len(seen)} 条")

    if args.cookies:
        for ig in sources.get("instagram", []):
            url = f"https://www.instagram.com/{ig['handle']}/reels/"
            print(f"📡 {url}")
            for e in flat_playlist(url, args.cookies):
                vid = e.get("id")
                if not vid or vid in seen:
                    continue
                seen[vid] = {
                    "id": vid,
                    "platform": "instagram",
                    "channel": ig["handle"],
                    "tab": "reels",
                    "title": e.get("title") or "",
                    "url": e.get("url") or e.get("webpage_url") or "",
                    "views": e.get("view_count") or 0,
                    "duration": e.get("duration"),
                }

    videos = sorted(seen.values(), key=lambda v: -(v["views"] or 0))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    VIDEOS_JSON.write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 共 {len(videos)} 条 → {VIDEOS_JSON}")


if __name__ == "__main__":
    main()
