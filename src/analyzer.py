import base64
import io
import json
import os
import subprocess
import tempfile
import anthropic
import requests as http_requests
from PIL import Image


def _bytes_to_base64(data: bytes) -> str | None:
    """Convert raw image bytes to base64-encoded JPEG via Pillow."""
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
    """Download an image URL and return base64-encoded JPEG."""
    try:
        resp = http_requests.get(url, timeout=15)
        resp.raise_for_status()
        return _bytes_to_base64(resp.content)
    except Exception as e:
        print(f"  [warn] failed to load image: {e}")
        return None


def _video_to_frames(url: str, n_frames: int = 3) -> list[str]:
    """Download a Reel video and extract n_frames evenly-spaced frames as base64 JPEG.

    Frames are sampled at 10%, 50%, 90% of the video duration so we capture
    the hook, body, and ending of the content.  Falls back to [] on any error
    so the caller can gracefully degrade to thumbnail_url.
    """
    try:
        resp = http_requests.get(url, timeout=60, stream=True)
        resp.raise_for_status()

        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "reel.mp4")

            # Download with a 50 MB cap to avoid huge files
            downloaded = 0
            max_bytes = 50 * 1024 * 1024
            with open(video_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if downloaded >= max_bytes:
                        print(f"  [warn] video >{max_bytes // 1024 // 1024}MB, capped download")
                        break

            # Get duration via ffprobe
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

            # Extract frames at 10%, 50%, 90%
            percentages = [0.1, 0.5, 0.9][:n_frames]
            frames = []
            for i, pct in enumerate(percentages):
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
                        frames.append(b64)

            return frames

    except Exception as e:
        print(f"  [warn] failed to extract video frames: {e}")
        return []


ANALYSIS_PROMPT = """你是一位专业的社交媒体分析师。以下是某 Instagram 账号近期的数据，请进行全面分析并给出可操作的建议。

数据如下：
{data_json}

注意：
- Carousel 贴文的每张图片已附在此消息中（标注了对应贴文的发布日期与按讚数），请结合图片视觉内容进行分析。
- Top 5 Reels 的实际视频帧（开头 / 中间 / 结尾各一帧）也已附上，请分析视频内容、画面构图与钩子设计。

请分析以下维度，用繁体中文输出：

## 1. 整体表现摘要
- 总帖子数、Reels 数
- 平均互动率（Engagement Rate = (likes + comments) / 帖子数，对比行业均值 1-3%）
- 整体趋势评估

## 2. Posts 分析
- 表现最好的前 3 篇及原因
- 表现最差的前 3 篇及原因
- 最佳发布时间段

## 2a. Carousel 视觉内容分析
- 高互动 Carousel 的排版风格、字体、配色规律
- 封面图（第一张）的钩子设计
- 内容结构（起承转合）是否清晰

## 3. Reels 分析
- 播放量与互动率对比
- 表现最好的 Reels 及成功因素
- Reels 相比 Posts 的表现差异

## 3a. Reels 视频内容分析
- 开头帧的钩子：画面构图、文字叠加、人物表情/动作
- 中段内容节奏：信息密度、场景切换规律
- 结尾帧的行动呼吁（CTA）设计
- 高互动 vs 低互动 Reels 的视频内容差异

## 4. 内容主题洞察
- 哪类内容最受欢迎
- 受众互动偏好

## 5. 可行的改进建议（Top 5）
- 具体、量化、可立即执行的行动项目

## 6. 下周内容计划建议
- 推荐 3-5 个内容主题及发布时间
"""


def analyze(data: dict) -> str:
    client = anthropic.Anthropic()

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
            }
            for r in data.get("reels", [])
        ],
        "total_posts": len(data.get("posts", [])),
        "total_reels": len(data.get("reels", [])),
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

    # ── Reels video frame analysis (top 5, 3 frames each) ───────────────────
    top_reels = sorted(
        data.get("reels", []),
        key=lambda r: r.get("like_count", 0),
        reverse=True,
    )[:5]

    reel_blocks = []
    for reel in top_reels:
        date_str = (reel.get("timestamp") or "")[:10]
        likes = reel.get("like_count", 0)

        frames = _video_to_frames(reel.get("media_url", ""), n_frames=3)

        if not frames:
            # Fallback: use thumbnail_url if video extraction failed
            thumb = _image_to_base64(reel.get("thumbnail_url", ""))
            if thumb:
                frames = [thumb]
                print(f"  [vision] reel {date_str}: video failed, using thumbnail fallback")

        if not frames:
            continue

        reel_blocks.append({
            "type": "text",
            "text": f"\n--- Reel {date_str}（{likes} 讚，{len(frames)} 帧：开头/中间/结尾）---",
        })
        for b64 in frames:
            reel_blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            })
        print(f"  [vision] reel {date_str}: {len(frames)} frames extracted")

    if reel_blocks:
        content.append({
            "type": "text",
            "text": "\n\n=== 以下为 Top 5 Reels 视频帧（开头 / 中间 / 结尾）===",
        })
        content.extend(reel_blocks)

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system="你是专业的社交媒体策略顾问，擅长 Instagram 数据分析，输出繁体中文报告。",
        messages=[{"role": "user", "content": content}],
    )
    return message.content[0].text
