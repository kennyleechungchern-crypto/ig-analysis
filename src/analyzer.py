import base64
import io
import json
import os
import subprocess
import tempfile
import anthropic
import requests as http_requests
from PIL import Image

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("  [whisper] loading model (first run may download ~150 MB)...")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        print("  [whisper] model ready")
    return _whisper_model


def _bytes_to_base64(data: bytes) -> str | None:
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"  [warn] failed to encode image: {e}")
        return None


def _image_to_base64(url: str) -> str | None:
    try:
        resp = http_requests.get(url, timeout=15)
        resp.raise_for_status()
        return _bytes_to_base64(resp.content)
    except Exception as e:
        print(f"  [warn] failed to load image: {e}")
        return None


def _analyze_reel(url: str) -> dict:
    """Download a Reel, extract hook/ending frames and transcribe audio with Whisper.

    Returns {'frames': [base64, ...], 'transcript': str | None}
    Frames: index 0 = hook (5%), index 1 = ending (90%)
    """
    result = {"frames": [], "transcript": None}
    try:
        resp = http_requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "reel.mp4")
            audio_path = os.path.join(tmpdir, "audio.wav")

            downloaded = 0
            max_bytes = 50 * 1024 * 1024
            with open(video_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= max_bytes:
                        print(f"  [warn] video >{max_bytes // 1024 // 1024}MB, capped")
                        break

            # Get duration
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    video_path,
                ],
                capture_output=True, text=True, timeout=15,
            )
            duration = float(probe.stdout.strip())

            # Extract hook frame (5%) and ending frame (90%)
            for i, pct in enumerate([0.05, 0.90]):
                ts = max(0.5, duration * pct)
                frame_path = os.path.join(tmpdir, f"frame{i}.jpg")
                subprocess.run(
                    [
                        "ffmpeg", "-ss", str(ts), "-i", video_path,
                        "-frames:v", "1", "-q:v", "2", frame_path, "-y",
                    ],
                    capture_output=True, timeout=15,
                )
                if os.path.exists(frame_path):
                    with open(frame_path, "rb") as fh:
                        b64 = _bytes_to_base64(fh.read())
                    if b64:
                        result["frames"].append(b64)

            # Extract audio and transcribe with Whisper
            ffmpeg_audio = subprocess.run(
                [
                    "ffmpeg", "-i", video_path,
                    "-vn", "-ar", "16000", "-ac", "1", "-f", "wav",
                    audio_path, "-y",
                ],
                capture_output=True, timeout=60,
            )
            if ffmpeg_audio.returncode == 0 and os.path.exists(audio_path):
                try:
                    model = _get_whisper_model()
                    segments, _ = model.transcribe(audio_path, beam_size=5)
                    transcript = " ".join(seg.text.strip() for seg in segments)
                    result["transcript"] = transcript.strip() or None
                except Exception as e:
                    print(f"  [warn] whisper transcription failed: {e}")

    except Exception as e:
        print(f"  [warn] reel analysis failed: {e}")

    return result


ANALYSIS_PROMPT = """你是一位专业的社交媒体分析师。以下是某 Instagram 账号所有内容的完整数据，请进行全面分析并给出可操作的建议。

数据如下（reels_summary 中已包含每支 Reel 的完整口播文字稿）：
{data_json}

注意：
- 所有 Reels 的口播文字稿已包含在上方 JSON 的 transcript 字段中，请基于全部文字稿进行分析。
- Top 10 Reels 的关键帧（开头钩子 / 结尾 CTA）已附在此消息中，供视觉参考。
- Carousel 贴文的图片已附上，请结合视觉内容分析。

请分析以下维度，用繁体中文输出：

## 1. 整体表现摘要
- 总帖子数、Reels 数
- 平均互动率（Engagement Rate = (likes + comments) / 帖子数，对比行业均值 1-3%）
- 整体趋势评估（近期是上升还是下滑？）

## 2. Posts 分析
- 表现最好的前 3 篇及原因
- 表现最差的前 3 篇及原因
- 最佳发布时间段

## 2a. Carousel 视觉内容分析
- 高互动 Carousel 的排版风格、字体、配色规律
- 封面图（第一张）的钩子设计
- 内容结构（起承转合）是否清晰

## 3. Reels 全量数据分析
- 34 支 Reels 整体互动率分布（高 / 中 / 低区间各多少支）
- 播放量与 likes 的相关性
- 哪个时期的内容表现最好？

## 3a. 口播内容深度分析（基于所有 Reels 完整文字稿）
请系统性分析所有 Reels 的口播内容，重点提炼：

**开头钩子模式分析**
- 盘点所有 Reels 使用了哪几类开头技巧（痛点、悬念、反直觉、数字冲击、故事开场等）
- 各类型开头对应的平均互动率是多少？哪种最有效？
- 列出表现最好的 3 个开头原句，分析为什么有效

**内容结构规律**
- 高互动 Reels（likes > 100）的内容结构有何共同点？
- 低互动 Reels 常见的结构问题是什么？
- 最有效的内容结构模板是什么？

**话题与主题分析**
- 哪类话题持续高互动？哪类话题反应冷淡？
- 受众最感兴趣的核心关键词是什么？

**CTA 设计分析**
- 高互动 Reels 的结尾 CTA 是什么？有没有规律？
- 给出 3 个可直接复用的高效 CTA 句式

**高互动内容公式提炼**
- 综合以上分析，提炼出 2-3 个「可直接复用的爆款公式」
  格式：[开头句式] + [内容结构] + [CTA] = [预期效果]

## 4. 内容主题洞察
- 你的账号核心定位是否清晰？受众画像推测
- 哪类内容与定位最匹配且互动最高？

## 5. 可行的改进建议（Top 5）
- 具体、量化、可立即执行的行动项目

## 6. 下周内容计划建议（5 个）
- 每个主题附上：话题 + 建议发布时间 + 开头第一句话（直接可用）
"""


def analyze(data: dict) -> str:
    client = anthropic.Anthropic()
    all_reels = data.get("reels", [])

    # ── Step 1: Transcribe ALL Reels + extract frames ─────────────────────────
    print(f"  [whisper] analyzing all {len(all_reels)} reels...")
    for reel in all_reels:
        date_str = (reel.get("timestamp") or "")[:10]
        result = _analyze_reel(reel.get("media_url", ""))
        reel["_transcript"] = result["transcript"]
        reel["_frames"] = result["frames"]
        if result["transcript"]:
            print(f"  [whisper] {date_str}: {len(result['transcript'])} chars transcribed")
        else:
            print(f"  [whisper] {date_str}: no transcript (music/silent/failed)")

    # ── Step 2: Build compact with ALL transcripts ────────────────────────────
    compact = {
        "fetched_at": data["fetched_at"],
        "posts_summary": [
            {
                "caption": (p.get("caption") or "")[:120],
                "timestamp": p.get("timestamp"),
                "media_type": p.get("media_type"),
                "like_count": p.get("like_count", 0),
                "comments_count": p.get("comments_count", 0),
                "reach": p.get("reach", 0),
                "saved": p.get("saved", 0),
                "carousel_slides": len(p.get("children", [])) if p.get("media_type") == "CAROUSEL_ALBUM" else None,
            }
            for p in data.get("posts", [])
        ],
        "reels_summary": [
            {
                "caption": (r.get("caption") or "")[:120],
                "timestamp": r.get("timestamp"),
                "like_count": r.get("like_count", 0),
                "comments_count": r.get("comments_count", 0),
                "video_views": r.get("video_views", 0),
                "plays": r.get("plays", 0),
                "reach": r.get("reach", 0),
                "transcript": r.get("_transcript"),
            }
            for r in all_reels
        ],
        "total_posts": len(data.get("posts", [])),
        "total_reels": len(all_reels),
    }

    content = [
        {
            "type": "text",
            "text": ANALYSIS_PROMPT.format(data_json=json.dumps(compact, ensure_ascii=False, indent=2)),
        }
    ]

    # ── Carousel visual analysis (top 5, up to 6 IMAGE slides each) ──────────
    carousels = sorted(
        [p for p in data.get("posts", []) if p.get("media_type") == "CAROUSEL_ALBUM" and p.get("children")],
        key=lambda p: p.get("like_count", 0),
        reverse=True,
    )[:5]

    for post in carousels:
        children = [c for c in post.get("children", []) if c.get("media_type") == "IMAGE"][:6]
        if not children:
            continue
        date_str = (post.get("timestamp") or "")[:10]
        likes = post.get("like_count", 0)
        image_blocks = []
        for child in children:
            url = child.get("media_url")
            if not url:
                continue
            b64 = _image_to_base64(url)
            if b64:
                image_blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                })
        if not image_blocks:
            continue
        content.append({
            "type": "text",
            "text": f"\n--- Carousel {date_str}（{likes} 讚，{len(image_blocks)} 张图）---",
        })
        content.extend(image_blocks)
        print(f"  [vision] carousel {date_str}: {len(image_blocks)} images attached")

    # ── Reel frames: Top 10 by likes (transcripts already in compact JSON) ────
    top_reels = sorted(all_reels, key=lambda r: r.get("like_count", 0), reverse=True)[:10]

    reel_blocks = []
    for reel in top_reels:
        date_str = (reel.get("timestamp") or "")[:10]
        likes = reel.get("like_count", 0)
        frames = reel.get("_frames", [])

        if not frames:
            thumb = _image_to_base64(reel.get("thumbnail_url", ""))
            if thumb:
                frames = [thumb]
                print(f"  [vision] reel {date_str}: using thumbnail fallback")

        if not frames:
            continue

        reel_blocks.append({
            "type": "text",
            "text": f"\n--- Reel {date_str}（{likes} 讚）---",
        })
        frame_labels = ["开头钩子", "结尾 CTA"]
        for j, b64 in enumerate(frames):
            label = frame_labels[j] if j < len(frame_labels) else f"帧{j+1}"
            reel_blocks.append({"type": "text", "text": f"[{label}]"})
            reel_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            })

    if reel_blocks:
        content.append({
            "type": "text",
            "text": "\n\n=== Top 10 Reels 关键帧（所有 Reels 完整文字稿已在上方 JSON 中）===",
        })
        content.extend(reel_blocks)

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system="你是专业的社交媒体策略顾问，擅长 Instagram 数据分析，输出繁体中文报告。",
        messages=[{"role": "user", "content": content}],
    )
    return message.content[0].text
