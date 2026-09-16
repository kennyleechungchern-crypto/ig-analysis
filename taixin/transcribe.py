#!/usr/bin/env python3
"""Step 2 · 批量下载音频 + faster-whisper 逐字稿 → transcripts/<id>.md + data/transcripts.jsonl

用法:
  python transcribe.py --top 30            # 播放量前 30 条（已做过的自动跳过）
  python transcribe.py --ids abc123 def456 # 指定视频
  python transcribe.py --all               # 全部（453 条 CPU 上约 2 小时）
  python transcribe.py --top 30 --model medium --cookies cookies.txt

环境变量:
  TAIXIN_POT_SERVER  bgutil PO token 服务地址（云端 IP 抓 YouTube 必须，见 README）
  TAIXIN_CACHE_DIR   音频缓存目录（默认 taixin/.cache，已 gitignore）
"""
import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from common import (
    CACHE_DIR,
    TRANSCRIPT_DIR,
    append_transcript,
    load_transcripts,
    load_videos,
    ytdlp_base_args,
)

_model = None


def whisper(model_name: str):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel

        print(f"  [whisper] loading {model_name} …")
        _model = WhisperModel(model_name, device="cpu", compute_type="int8")
    return _model


def download_audio(video: dict, cookies: str | None) -> Path | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    out = CACHE_DIR / f"{video['id']}.wav"
    if out.exists() and out.stat().st_size > 10_000:
        return out
    cmd = ytdlp_base_args(cookies) + [
        "-q",
        "-f", "ba[ext=m4a]/ba/b",
        "-x", "--audio-format", "wav",
        "--postprocessor-args", "ffmpeg:-ar 16000 -ac 1",
        "-o", str(CACHE_DIR / f"{video['id']}.%(ext)s"),
        video["url"],
    ]
    for attempt in range(2):
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and out.exists() and out.stat().st_size > 10_000:
            return out
        time.sleep(3)
    print(f"  [warn] 下载失败 {video['id']}: {proc.stderr.strip()[-200:]}", file=sys.stderr)
    return None


def fetch_metadata(video: dict, cookies: str | None) -> dict:
    """Upload date + description + duration; flat listings do not carry them."""
    cmd = ytdlp_base_args(cookies) + [
        "--skip-download", "--print", "%(upload_date)s\t%(duration)s\t%(title)s", video["url"],
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    meta = {}
    if proc.returncode == 0 and proc.stdout.strip():
        parts = proc.stdout.strip().split("\t", 2)
        if len(parts) == 3:
            d, dur, title = parts
            if re.fullmatch(r"\d{8}", d):
                meta["date"] = f"{d[:4]}-{d[4:6]}-{d[6:]}"
            if dur not in ("NA", ""):
                meta["duration"] = float(dur)
            if title:
                meta["title"] = title
    return meta


def transcribe_file(path: Path, model_name: str) -> tuple[str, list[dict]]:
    model = whisper(model_name)
    segments, info = model.transcribe(
        str(path),
        language="zh",
        beam_size=5,
        vad_filter=True,
        initial_prompt="以下是一位台灣銷售講師的短影片口播，繁體中文，口語。",
    )
    segs = []
    for s in segments:
        text = s.text.strip()
        if text:
            segs.append({"start": round(s.start, 1), "end": round(s.end, 1), "text": text})
    full = "".join(s["text"] for s in segs)
    return full, segs


def write_markdown(video: dict, full: str, segs: list[dict]) -> Path:
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"{video['id']}.md"
    lines = [
        f"# {video.get('title') or video['id']}",
        "",
        f"- 来源: {video['url']}",
        f"- 频道: @{video.get('channel', '')}  ·  播放: {video.get('views', 0)}  ·  日期: {video.get('date', '?')}  ·  时长: {video.get('duration', '?')}s",
        f"- 转写: faster-whisper · {datetime.now():%Y-%m-%d}",
        "",
        "## 逐字稿",
        "",
        full,
        "",
        "## 时间轴",
        "",
    ]
    for s in segs:
        lines.append(f"- [{s['start']:>5.1f}–{s['end']:>5.1f}] {s['text']}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--top", type=int, help="按播放量取前 N 条")
    g.add_argument("--ids", nargs="+", help="指定视频 id")
    g.add_argument("--all", action="store_true")
    ap.add_argument("--model", default="small", help="faster-whisper 模型: base/small/medium/large-v3")
    ap.add_argument("--cookies")
    ap.add_argument("--force", action="store_true", help="已有逐字稿也重做")
    args = ap.parse_args()

    videos = load_videos()
    if not videos:
        sys.exit("先跑 python list_videos.py")
    by_id = {v["id"]: v for v in videos}
    if args.ids:
        targets = [by_id.get(i) or {"id": i, "url": f"https://www.youtube.com/watch?v={i}", "views": 0} for i in args.ids]
    elif args.top:
        targets = videos[: args.top]
    else:
        targets = videos

    done = load_transcripts()
    todo = [v for v in targets if args.force or v["id"] not in done]
    print(f"🎯 目标 {len(targets)} 条，待做 {len(todo)} 条（已完成 {len(targets) - len(todo)}）")

    ok = fail = 0
    for i, video in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {video['id']} · {video.get('title', '')[:30]} · views={video.get('views')}")
        video.update(fetch_metadata(video, args.cookies))
        audio = download_audio(video, args.cookies)
        if audio is None:
            fail += 1
            continue
        t0 = time.time()
        full, segs = transcribe_file(audio, args.model)
        if not full.strip():
            print("  [warn] 空转写，跳过", file=sys.stderr)
            fail += 1
            continue
        md = write_markdown(video, full, segs)
        append_transcript({**video, "transcript": full, "segments": segs, "model": args.model,
                           "transcribed_at": datetime.now().isoformat(timespec="seconds")})
        ok += 1
        print(f"  ✅ {len(full)} 字 · {time.time() - t0:.0f}s → {md.name}")

    print(f"\n完成 {ok} 条，失败 {fail} 条。逐字稿在 {TRANSCRIPT_DIR}")


if __name__ == "__main__":
    main()
