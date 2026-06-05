import os
import requests
from datetime import datetime, timedelta
from typing import Optional


GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


def _get(endpoint: str, params: dict) -> dict:
    resp = requests.get(f"{GRAPH_API_BASE}/{endpoint}", params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_ig_user_id(access_token: str) -> str:
    data = _get("me/accounts", {"access_token": access_token, "fields": "instagram_business_account"})
    for page in data.get("data", []):
        ig = page.get("instagram_business_account")
        if ig:
            return ig["id"]
    raise ValueError("找不到连接的 Instagram Business 账号，请确认已将 IG 连接到 Facebook Page。")


def fetch_account_insights(ig_user_id: str, access_token: str) -> dict:
    metrics = "impressions,reach,profile_views,follower_count"
    data = _get(
        f"{ig_user_id}/insights",
        {
            "access_token": access_token,
            "metric": metrics,
            "period": "day",
            "since": int((datetime.now() - timedelta(days=30)).timestamp()),
            "until": int(datetime.now().timestamp()),
        },
    )
    return data.get("data", [])


def fetch_media(ig_user_id: str, access_token: str, limit: int = 50) -> list[dict]:
    fields = (
        "id,caption,media_type,timestamp,like_count,comments_count,"
        "media_url,permalink,thumbnail_url"
    )
    data = _get(
        f"{ig_user_id}/media",
        {"access_token": access_token, "fields": fields, "limit": limit},
    )
    return data.get("data", [])


def fetch_carousel_children(media_id: str, access_token: str) -> list[dict]:
    data = _get(
        f"{media_id}/children",
        {"access_token": access_token, "fields": "id,media_type,media_url"},
    )
    return data.get("data", [])


def fetch_all(access_token: str) -> dict:
    ig_user_id = os.environ.get("IG_USER_ID") or get_ig_user_id(access_token)
    media = fetch_media(ig_user_id, access_token)

    posts = [m for m in media if m.get("media_type") in ("IMAGE", "CAROUSEL_ALBUM")]
    reels = [m for m in media if m.get("media_type") == "VIDEO"]

    for post in posts:
        if post.get("media_type") == "CAROUSEL_ALBUM":
            post["children"] = fetch_carousel_children(post["id"], access_token)

    return {
        "fetched_at": datetime.utcnow().isoformat(),
        "ig_user_id": ig_user_id,
        "posts": posts,
        "reels": reels,
        "total_media": len(media),
    }
