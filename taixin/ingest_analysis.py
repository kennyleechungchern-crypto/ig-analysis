#!/usr/bin/env python3
"""Step 2b · 把 Higgsfield video_analysis 的结果（英文分段转写）落成逐字稿文件。

云端环境抓不到 YouTube 音频时的替代路：在 Claude Code 里用 Higgsfield MCP 的
video_analysis_create(youtube_url) 拿到 scenes（每段的 audio 是英文转写），把 JSON 存到
data/analyses/<video_id>.json，再跑本脚本：

  python ingest_analysis.py            # 处理 data/analyses 下所有还没落地的
  python ingest_analysis.py --force
"""
import argparse
import json
import re
from datetime import datetime

from common import DATA_DIR, TRANSCRIPT_DIR, append_transcript, load_transcripts, load_videos

ANALYSES_DIR = DATA_DIR / "analyses"


def _ts(s: str) -> float:
    m, sec = s.split(":")
    return int(m) * 60 + int(sec)


def to_record(video_id: str, analysis: dict, video: dict) -> dict:
    segs = []
    for sc in analysis.get("scenes") or []:
        text = (sc.get("audio") or "").strip()
        if text:
            segs.append({"start": _ts(sc["timestamp_start"]), "end": _ts(sc["timestamp_end"]),
                         "text": text, "label": sc.get("label", "")})
    full = " ".join(s["text"] for s in segs)
    return {**video, "id": video_id, "transcript": full, "segments": segs,
            "model": "higgsfield-video-analysis (English rendering of the speech)",
            "duration": video.get("duration") or (segs[-1]["end"] if segs else None),
            "transcribed_at": datetime.now().isoformat(timespec="seconds")}


def write_markdown(rec: dict) -> None:
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# {rec.get('title') or rec['id']}", "",
        f"- 来源: {rec['url']}",
        f"- 频道: @{rec.get('channel', '')}  ·  播放: {rec.get('views', 0)}  ·  时长: 约 {rec.get('duration')}s",
        f"- 转写方式: Higgsfield 视频分析（口播内容的英文转述，非中文逐字）· {datetime.now():%Y-%m-%d}",
        "", "## 口播内容（英文转述）", "", rec["transcript"], "", "## 分段", "",
    ]
    for s in rec["segments"]:
        lines.append(f"- [{s['start']:>4.0f}s–{s['end']:>4.0f}s] ({s['label']}) {s['text']}")
    (TRANSCRIPT_DIR / f"{rec['id']}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    by_id = {v["id"]: v for v in load_videos()}
    done = load_transcripts()
    n = 0
    for p in sorted(ANALYSES_DIR.glob("*.json")):
        vid = p.stem
        if vid in done and not args.force:
            continue
        analysis = json.loads(p.read_text(encoding="utf-8"))
        if analysis.get("status") != "completed":
            continue
        video = by_id.get(vid) or {"id": vid, "url": f"https://www.youtube.com/watch?v={vid}", "views": 0}
        rec = to_record(vid, analysis, video)
        write_markdown(rec)
        append_transcript(rec)
        n += 1
        print(f"✅ {vid} · {video.get('title', '')[:30]} · {len(rec['segments'])} 段")
    print(f"落地 {n} 条")


if __name__ == "__main__":
    main()
