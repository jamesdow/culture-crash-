"""Reddit without an API key.

Routes, in order:
1. Reddit JSON: www, then old.reddit. Uses app-only OAuth if REDDIT_CLIENT_ID /
   REDDIT_CLIENT_SECRET happen to be set. It usually works from a home connection
   and is often blocked from cloud servers.
2. Reddit RSS feeds. These are less aggressively rate-limited than JSON.
3. Arctic Shift, a public research archive of Reddit (no key).
4. PullPush, a public Pushshift successor (no key).
If all fail, the pipeline uses Claude web search restricted to reddit.com.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from datetime import datetime

from .base import HarvestSpec, Post, Unavailable, check_status, http_client, safe_get, gather, strip_html

DEFAULT_SUBREDDITS = [
    "NoStupidQuestions", "confession", "TrueOffMyChest", "DoesAnybodyElse", "Adulting",
    "CasualConversation", "selfimprovement", "LifeProTips", "mildlyinfuriating", "simpleliving",
    "AskUK", "AskWomenOver30", "AskMenOver30", "antiwork", "BuyItForLife",
]

ATOM = "{http://www.w3.org/2005/Atom}"


def _window(days: int) -> str:
    return "week" if days <= 7 else "month" if days <= 31 else "year"


def _post_from_json(d: dict) -> Post | None:
    if d.get("over_18") or d.get("stickied"):
        return None
    permalink = d.get("permalink") or ""
    url = permalink if permalink.startswith("http") else "https://www.reddit.com" + permalink
    return Post(
        platform="reddit", url=url, title=d.get("title", "") or "", text=(d.get("selftext") or "")[:1200],
        context=f"r/{d.get('subreddit', '')}", created_utc=float(d.get("created_utc") or 0),
        engagement=int(d.get("score") or 0) + 2 * int(d.get("num_comments") or 0),
    )


class RedditJSON:
    def __init__(self, host: str = "https://www.reddit.com", name: str = "reddit-json"):
        self.host, self.name = host, name

    def ready(self) -> bool:
        return True

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        http, base = http_client(), self.host
        cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
        if cid and secret:
            tok = http.post("https://www.reddit.com/api/v1/access_token", auth=(cid, secret), data={"grant_type": "client_credentials"})
            if tok.status_code == 200 and "access_token" in tok.json():
                http.headers["Authorization"] = f"Bearer {tok.json()['access_token']}"
                base = "https://oauth.reddit.com"
        t = _window(spec.recency_days)

        def get(path: str, params: dict) -> list[Post]:
            resp = safe_get(http, base + path, {**params, "raw_json": 1})
            check_status(resp)
            return [p for c in resp.json().get("data", {}).get("children", []) if (p := _post_from_json(c.get("data", {})))]

        calls = [lambda s=sub: get(f"/r/{s}/top.json", {"t": t, "limit": 15}) for sub in spec.subreddits]
        calls += [lambda q=q: get("/search.json", {"q": q, "sort": "top", "t": t, "limit": 15}) for q in spec.queries()]
        return gather(calls)


class RedditRSS:
    name = "reddit-rss"

    def ready(self) -> bool:
        return True

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        http, t = http_client(), _window(spec.recency_days)

        def feed(url: str, params: dict) -> list[Post]:
            posts: list[Post] = []
            resp = safe_get(http, url, params)
            check_status(resp)
            try:
                root = ET.fromstring(resp.content)
            except ET.ParseError as e:
                raise Unavailable(f"bad feed: {e}") from e
            for e in root.findall(f"{ATOM}entry"):
                link = e.find(f"{ATOM}link")
                cat = e.find(f"{ATOM}category")
                upd = (e.findtext(f"{ATOM}updated") or e.findtext(f"{ATOM}published") or "").strip()
                try:
                    ts = datetime.fromisoformat(upd.replace("Z", "+00:00")).timestamp() if upd else 0.0
                except ValueError:
                    ts = 0.0
                posts.append(Post(
                    platform="reddit", url=link.get("href", "") if link is not None else "",
                    title=e.findtext(f"{ATOM}title") or "", text=strip_html(e.findtext(f"{ATOM}content") or "")[:1200],
                    context=f"r/{cat.get('term')}" if cat is not None else "", created_utc=ts,
                ))
            return posts

        calls = [lambda s=sub: feed(f"https://www.reddit.com/r/{s}/top/.rss", {"t": t, "limit": 25}) for sub in spec.subreddits]
        calls += [lambda q=q: feed("https://www.reddit.com/search.rss", {"q": q, "sort": "top", "t": t, "limit": 25}) for q in spec.queries()]
        return gather(calls)


class ArcticShift:
    name = "arctic-shift"
    base = "https://arctic-shift.photon-reddit.com/api/posts/search"

    def ready(self) -> bool:
        return True

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        http, after = http_client(30.0), datetime.fromtimestamp(spec.cutoff).strftime("%Y-%m-%d")

        def get(params: dict) -> list[Post]:
            resp = safe_get(http, self.base, {**params, "after": after, "limit": 50, "sort": "desc"})
            check_status(resp)
            return [p for d in resp.json().get("data") or [] if (p := _post_from_json(d))]

        posts = gather([lambda s=sub: get({"subreddit": s}) for sub in spec.subreddits])
        for q in spec.tells:  # title search; tolerated if the archive rejects it
            try:
                posts += get({"title": q})
            except Unavailable:
                break
        return posts


class PullPush:
    name = "pullpush"
    base = "https://api.pullpush.io/reddit/search/submission/"

    def ready(self) -> bool:
        return True

    def harvest(self, spec: HarvestSpec) -> list[Post]:
        http, after = http_client(30.0), int(spec.cutoff)

        def get(params: dict) -> list[Post]:
            resp = safe_get(http, self.base, {**params, "after": after, "size": 50, "sort_type": "score", "sort": "desc"})
            check_status(resp)
            return [p for d in resp.json().get("data") or [] if (p := _post_from_json(d))]

        calls = [lambda s=sub: get({"subreddit": s}) for sub in spec.subreddits]
        calls += [lambda q=q: get({"q": f'"{q}"'}) for q in spec.queries()]
        return gather(calls)


def reddit_routes() -> list:
    return [RedditJSON(), RedditJSON("https://old.reddit.com", "old-reddit-json"), RedditRSS(), ArcticShift(), PullPush()]
