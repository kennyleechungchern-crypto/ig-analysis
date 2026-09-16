"""Shared helpers for the 泰欣老师 → Kenny 口播稿 pipeline."""
import json
import os
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
TRANSCRIPT_DIR = HERE / "transcripts"
SCRIPT_DIR = HERE / "scripts"
PROMPT_DIR = HERE / "prompts"
CACHE_DIR = Path(os.environ.get("TAIXIN_CACHE_DIR", HERE / ".cache"))

VIDEOS_JSON = DATA_DIR / "videos.json"
TRANSCRIPTS_JSONL = DATA_DIR / "transcripts.jsonl"


def load_videos() -> list[dict]:
    if not VIDEOS_JSON.exists():
        return []
    return json.loads(VIDEOS_JSON.read_text(encoding="utf-8"))


def load_transcripts() -> dict[str, dict]:
    """Return {video_id: record} for every transcript already produced."""
    out: dict[str, dict] = {}
    if TRANSCRIPTS_JSONL.exists():
        for line in TRANSCRIPTS_JSONL.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                out[rec["id"]] = rec
    return out


def append_transcript(rec: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with TRANSCRIPTS_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def ffmpeg_path() -> str:
    """Prefer a system ffmpeg; fall back to the static binary shipped with imageio-ffmpeg."""
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def ytdlp_base_args(cookies: str | None = None) -> list[str]:
    """Common yt-dlp flags. Set TAIXIN_POT_SERVER (e.g. http://127.0.0.1:4416) when a
    bgutil PO-token server is running; pass a Netscape cookies.txt for IG or for
    cloud IPs that YouTube challenges."""
    args = ["yt-dlp", "--no-warnings", "--ffmpeg-location", ffmpeg_path()]
    if cookies:
        args += ["--cookies", cookies]
    pot = os.environ.get("TAIXIN_POT_SERVER")
    if pot:
        args += ["--extractor-args", f"youtubepot-bgutilhttp:base_url={pot}"]
    return args


def short_date(entry: dict) -> str:
    """yt-dlp flat entries rarely carry dates; the channel titles its shorts with the
    upload date (e.g. 2026年9月14日), so use that when nothing better exists."""
    ts = entry.get("upload_date")
    if ts:
        return f"{ts[:4]}-{ts[4:6]}-{ts[6:]}"
    return ""
