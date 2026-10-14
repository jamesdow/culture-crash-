"""Direct Reddit harvesting for raw, unfiltered language.

Uses app-only OAuth if REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET are set (more
reliable), otherwise Reddit's public JSON. If Reddit can't be reached the
pipeline falls back to web search restricted to reddit.com.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass

import httpx

USER_AGENT = "culture-crash/0.1 (cultural research engine)"

DEFAULT_SUBREDDITS = [
    "NoStupidQuestions", "confession", "TrueOffMyChest", "DoesAnybodyElse", "Adulting",
    "CasualConversation", "selfimprovement", "LifeProTips", "mildlyinfuriating", "simpleliving",
    "AskUK", "AskWomenOver30", "AskMenOver30", "antiwork", "BuyItForLife",
]

# Phrases that tend to surface language lagging behind need.
TELL_QUERIES = [
    '"is there a word for"',
    '"is it weird that"',
    '"does anyone else"',
    '"don\'t judge me"',
    '"my janky system"',
    '"I stopped" "and I don\'t know why"',
]


@dataclass
class RedditPost:
    title: str
    body: str
    url: str
    subreddit: str
    score: int
    created_utc: float


class RedditUnavailable(RuntimeError):
    pass


class RedditClient:
    def __init__(self, timeout: float = 20.0):
        self.http = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        self.base = "https://www.reddit.com"
        cid, secret = os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET")
        if cid and secret:
            resp = self.http.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(cid, secret),
                data={"grant_type": "client_credentials"},
            )
            if resp.status_code == 200 and "access_token" in resp.json():
                self.http.headers["Authorization"] = f"Bearer {resp.json()['access_token']}"
                self.base = "https://oauth.reddit.com"

    def _get(self, path: str, params: dict) -> list[RedditPost]:
        try:
            resp = self.http.get(f"{self.base}{path}", params={**params, "raw_json": 1})
        except httpx.HTTPError as e:
            raise RedditUnavailable(str(e)) from e
        if resp.status_code in (401, 403, 429) or resp.status_code >= 500:
            raise RedditUnavailable(f"HTTP {resp.status_code} from Reddit")
        resp.raise_for_status()
        posts = []
        for child in resp.json().get("data", {}).get("children", []):
            d = child.get("data", {})
            if d.get("over_18") or d.get("stickied"):
                continue
            posts.append(
                RedditPost(
                    title=d.get("title", ""),
                    body=(d.get("selftext") or "")[:1200],
                    url="https://www.reddit.com" + d.get("permalink", ""),
                    subreddit=d.get("subreddit", ""),
                    score=int(d.get("score", 0)),
                    created_utc=float(d.get("created_utc", 0)),
                )
            )
        return posts

    def harvest(self, subreddits: list[str], recency_days: int, focus: str | None, per_source: int = 15) -> list[RedditPost]:
        window = "week" if recency_days <= 7 else "month" if recency_days <= 31 else "year"
        cutoff = time.time() - recency_days * 86400
        seen: dict[str, RedditPost] = {}

        def add(posts: list[RedditPost]) -> None:
            for p in posts:
                if p.created_utc >= cutoff and p.url not in seen and (p.body or len(p.title) > 40):
                    seen[p.url] = p

        for sub in subreddits:
            add(self._get(f"/r/{sub}/top.json", {"t": window, "limit": per_source}))
        for q in TELL_QUERIES:
            query = f"{q} {focus}" if focus else q
            add(self._get("/search.json", {"q": query, "sort": "top", "t": window, "limit": per_source}))
        return sorted(seen.values(), key=lambda p: p.score, reverse=True)
