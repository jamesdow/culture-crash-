"""TikTok and Instagram.

Neither has an open API. The default route is Claude web search restricted to
tiktok.com / instagram.com, run by the pipeline, which needs no keys. If you set
APIFY_TOKEN, the engine first pulls captions (and TikTok comments) through
Apify's public-data scrapers, which is much richer. That is pay-per-result, a
few cents a run. Check the platforms' terms for your use.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

import httpx

from .base import HarvestSpec, Post, Unavailable, check_status

APIFY = "https://api.apify.com/v2/acts/{actor}/run-sync-get-dataset-items"

TIKTOK_SEARCHES = ["is it weird that", "nobody talks about", "POV you", "tell me without telling me", "my weird habit", "the way I"]
INSTAGRAM_HASHTAGS = ["thingsnobodytellsyou", "relatable", "adulting", "confession", "unpopularopinion", "softlife", "burnout"]


def _ts(v) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v:
        try:
            return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0
    return 0.0


def _run_actor(actor: str, payload: dict, timeout: float = 240.0) -> list[dict]:
    token = os.environ["APIFY_TOKEN"]
    try:
        resp = httpx.post(APIFY.format(actor=actor), params={"token": token}, json=payload, timeout=timeout)
    except httpx.HTTPError as e:
        raise Unavailable(type(e).__name__) from e
    if resp.status_code == 201:
        resp.status_code = 200
    check_status(resp)
    data = resp.json()
    if not isinstance(data, list):
        raise Unavailable("unexpected Apify response")
    return data


class ApifyTikTok:
    name = "apify-tiktok"

    def ready(self) -> bool:
        return bool(os.getenv("APIFY_TOKEN"))

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        searches = [f"{spec.focus} {q}" for q in TIKTOK_SEARCHES[:4]] if spec.focus else TIKTOK_SEARCHES
        items = _run_actor("clockworks~tiktok-scraper", {
            "searchQueries": searches, "resultsPerPage": 10,
            "shouldDownloadVideos": False, "shouldDownloadCovers": False, "shouldDownloadSubtitles": False,
        })
        posts = []
        for it in items:
            url = it.get("webVideoUrl") or it.get("url") or ""
            if not url:
                continue
            tags = " ".join("#" + (h.get("name") or "") for h in it.get("hashtags") or [] if isinstance(h, dict))
            posts.append(Post(platform="tiktok", url=url, text=f"{it.get('text') or ''} {tags}".strip()[:800],
                              context="TikTok caption", created_utc=_ts(it.get("createTimeISO") or it.get("createTime")),
                              engagement=int(it.get("commentCount") or 0) * 3 + int(it.get("diggCount") or 0) // 100))
        # Comments are where the confessions are: read the most-discussed videos.
        top = [p.url for p in sorted(posts, key=lambda p: p.engagement, reverse=True)[:6]]
        if top:
            try:
                for c in _run_actor("clockworks~tiktok-comments-scraper", {"postURLs": top, "commentsPerPost": 30}):
                    text = c.get("text") or ""
                    url = c.get("videoWebUrl") or c.get("postUrl") or ""
                    if text and url:
                        posts.append(Post(platform="tiktok", url=url, text=text[:600], context="comment on a TikTok",
                                          created_utc=_ts(c.get("createTimeISO") or c.get("createTime")),
                                          engagement=int(c.get("diggCount") or 0)))
            except Unavailable:
                pass  # captions alone are still useful
        return posts


class ApifyInstagram:
    name = "apify-instagram"

    def ready(self) -> bool:
        return bool(os.getenv("APIFY_TOKEN"))

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        tags = list(INSTAGRAM_HASHTAGS)
        if spec.focus:
            tags = [re.sub(r"[^a-z0-9]", "", spec.focus.lower())] + tags[:5]
        items = _run_actor("apify~instagram-hashtag-scraper", {"hashtags": tags, "resultsLimit": 15})
        posts = []
        for it in items:
            url = it.get("url") or ""
            if url:
                posts.append(Post(platform="instagram", url=url, text=(it.get("caption") or "")[:800],
                                  context="Instagram caption", created_utc=_ts(it.get("timestamp")),
                                  engagement=int(it.get("commentsCount") or 0) * 3 + int(it.get("likesCount") or 0) // 100))
        return posts
