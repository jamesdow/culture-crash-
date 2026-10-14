"""YouTube comment sections, the place people write "I didn't know there was a
word for this" under someone else's video.

Routes:
1. YouTube Data API v3, if YOUTUBE_API_KEY is set (a free key from Google Cloud).
2. yt-dlp, with no key: searches recent videos and reads their top comments.
If both fail, the pipeline uses Claude web search restricted to youtube.com.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from .base import HarvestSpec, Post, Unavailable, check_status, gather, http_client, safe_get

VIDEO_QUERIES = [
    "things nobody tells you about adult life",
    "why does nobody talk about this",
    "I quit doing this and",
    "my weird routine that actually works",
    "is it just me or",
    "honest vlog I'm tired",
]


def _queries(spec: HarvestSpec) -> list[str]:
    if spec.focus:
        return [f"{spec.focus} {q}" for q in ("nobody talks about", "is it just me", "honest", "my system for")] + [spec.focus]
    return VIDEO_QUERIES


class YouTubeDataAPI:
    name = "youtube-data-api"
    base = "https://www.googleapis.com/youtube/v3"

    def ready(self) -> bool:
        return bool(os.getenv("YOUTUBE_API_KEY"))

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        key, http = os.environ["YOUTUBE_API_KEY"], http_client()
        after = datetime.fromtimestamp(spec.cutoff, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        videos: dict[str, str] = {}
        for q in _queries(spec):
            resp = safe_get(http, f"{self.base}/search", {"part": "snippet", "q": q, "type": "video", "order": "relevance",
                                                         "publishedAfter": after, "maxResults": 5, "key": key})
            check_status(resp)
            for item in resp.json().get("items", []):
                vid = item.get("id", {}).get("videoId")
                if vid:
                    videos[vid] = item.get("snippet", {}).get("title", "")

        def comments(vid: str, title: str) -> list[Post]:
            resp = safe_get(http, f"{self.base}/commentThreads", {"part": "snippet", "videoId": vid, "maxResults": 40,
                                                                 "order": "relevance", "textFormat": "plainText", "key": key})
            if resp.status_code == 403:  # comments disabled on this video
                return []
            check_status(resp)
            out = []
            for item in resp.json().get("items", []):
                c = item.get("snippet", {}).get("topLevelComment", {}).get("snippet", {})
                text = c.get("textDisplay") or c.get("textOriginal") or ""
                cid = item.get("id", "")
                ts = c.get("publishedAt")
                out.append(Post(platform="youtube", url=f"https://www.youtube.com/watch?v={vid}&lc={cid}", text=text[:800],
                                context=f"comment on: {title}", engagement=int(c.get("likeCount") or 0),
                                created_utc=datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp() if ts else 0.0))
            return out

        return gather([lambda v=v, t=t: comments(v, t) for v, t in list(videos.items())[:20]])


class YtDlp:
    name = "yt-dlp"

    def ready(self) -> bool:
        try:
            import yt_dlp  # noqa: F401
        except ImportError:
            return False
        return True

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        import yt_dlp

        base_opts = {"quiet": True, "no_warnings": True, "skip_download": True, "socket_timeout": 20, "noplaylist": True,
                     "ignore_no_formats_error": True}  # we only want comments; never fail on video formats
        ids: dict[str, str] = {}
        with yt_dlp.YoutubeDL({**base_opts, "extract_flat": True}) as ydl:
            for q in _queries(spec)[:4]:
                try:
                    res = ydl.extract_info(f"ytsearchdate6:{q}", download=False) or {}
                except Exception as e:
                    if not ids:
                        raise Unavailable(f"search failed: {str(e)[:120]}") from e
                    break
                for entry in res.get("entries") or []:
                    if entry and entry.get("id"):
                        ids[entry["id"]] = entry.get("title", "")

        posts: list[Post] = []
        opts = {**base_opts, "getcomments": True,
                "extractor_args": {"youtube": {"max_comments": ["40", "40", "0", "0"], "comment_sort": ["top"]}}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            for vid, title in list(ids.items())[:10]:
                try:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False) or {}
                except Exception:
                    if not posts:
                        continue
                    break
                for c in info.get("comments") or []:
                    posts.append(Post(platform="youtube", url=f"https://www.youtube.com/watch?v={vid}&lc={c.get('id', '')}",
                                      text=(c.get("text") or "")[:800], context=f"comment on: {info.get('title') or title}",
                                      engagement=int(c.get("like_count") or 0), created_utc=float(c.get("timestamp") or 0)))
        if not posts:
            raise Unavailable("no comments retrieved")
        return posts


def youtube_routes() -> list:
    return [YouTubeDataAPI(), YtDlp()]
