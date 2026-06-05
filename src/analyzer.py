import base64
import io
import json
import anthropic
import requests as http_requests
from PIL import Image


def _image_to_base64(url: str) -> str | None:
    try:
        resp = http_requests.get(url, timeout=15)
        resp.raise_for_status()
        img = Image.open(io.BytesIO(resp.content))
        if img.mode != "RGB":
            img = img.convert("RGB")
        img.thumbnail((1024, 1024))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.standard_b64encode(buf.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"  [warn] failed to load image: {e}")
        return None


ANALYSIS_PROMPT = """你是一位专业的社交媒体分析师。以下是某 Instagram 账号近期的数据，请进行全面分析并给出可操作的建议。

数据如下：
{data_json}

注意：Carousel 贴文的每张图片已附在此消息中（标注了对应贴文的发布日期与按讚数），请结合图片视觉内容进行分析。

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
            b64_data = _image_to_base64(url)
            if b64_data:
                image_blocks.append({
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64_data},
                })
        if not image_blocks:
            continue
        content.append({
            "type": "text",
            "text": f"\n--- Carousel {date_str}（{likes} 讚，{len(image_blocks)} 张图）---",
        })
        content.extend(image_blocks)
        print(f"  [vision] carousel {date_str}: {len(image_blocks)} images attached")

    message = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=4096,
        system="你是专业的社交媒体策略顾问，擅长 Instagram 数据分析，输出繁体中文报告。",
        messages=[{"role": "user", "content": content}],
    )
    return message.content[0].text
