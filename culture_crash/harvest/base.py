"""Shared shapes for platform harvesters.

Each platform has a chain of routes, tried in order. Routes that need a key are
skipped when the key isn't set. If every direct route fails, the pipeline falls
back to Claude's web search restricted to that platform's domain, which needs
no keys at all.
"""

from __future__ import annotations

import html
import re
import time
from dataclasses import dataclass, field
from typing import Protocol

import httpx

USER_AGENT = "Mozilla/5.0 (compatible; culture-crash/0.2; cultural research)"

# Phrases that tend to surface language lagging behind need. Shared by every platform.
TELLS = [
    "is there a word for",
    "is it weird that",
    "does anyone else",
    "don't judge me",
    "I feel so seen",
    "nobody talks about",
    "my janky system",
    "I stopped and I don't know why",
]


class Unavailable(RuntimeError):
    """A route couldn't be used (blocked, rate-limited, missing key or library)."""


@dataclass
class Post:
    platform: str
    url: str
    text: str
    title: str = ""
    context: str = ""  # e.g. "comment on: <video title>" or "r/AskUK"
    created_utc: float = 0.0
    engagement: int = 0


@dataclass
class HarvestSpec:
    focus: str | None
    recency_days: int
    subreddits: list[str] = field(default_factory=list)
    tells: list[str] = field(default_factory=lambda: list(TELLS))
    limit: int = 60

    @property
    def cutoff(self) -> float:
        return time.time() - self.recency_days * 86400

    def queries(self, n: int | None = None) -> list[str]:
        qs = [f"{t} {self.focus}" if self.focus else t for t in self.tells]
        return qs[:n] if n else qs


class Route(Protocol):
    name: str

    def ready(self) -> bool: ...

    def harvest(self, spec: HarvestSpec) -> list[Post]: ...


@dataclass
class ChainResult:
    posts: list[Post]
    route: str
    attempts: list[str]


def run_chain(routes: list[Route], spec: HarvestSpec, min_posts: int = 8) -> ChainResult:
    """Try each ready route until one yields enough posts. Raises Unavailable if none do."""
    attempts: list[str] = []
    best: tuple[list[Post], str] | None = None
    for r in routes:
        if not r.ready():
            attempts.append(f"{r.name}: skipped (not configured)")
            continue
        try:
            posts = dedupe(r.harvest(spec), spec)
        except Unavailable as e:
            attempts.append(f"{r.name}: {e}")
            continue
        except Exception as e:  # a broken route should never sink the run
            attempts.append(f"{r.name}: {type(e).__name__}: {e}")
            continue
        attempts.append(f"{r.name}: {len(posts)} posts")
        if len(posts) >= min_posts:
            return ChainResult(posts[: spec.limit], r.name, attempts)
        if posts and (best is None or len(posts) > len(best[0])):
            best = (posts, r.name)
    if best:
        return ChainResult(best[0][: spec.limit], best[1], attempts)
    raise Unavailable("; ".join(attempts) or "no routes")


def dedupe(posts: list[Post], spec: HarvestSpec) -> list[Post]:
    seen: dict[str, Post] = {}
    for p in posts:
        if p.created_utc and p.created_utc < spec.cutoff:
            continue
        if len((p.title + p.text).strip()) < 25:
            continue
        key = p.url + "|" + p.text[:80]
        if key not in seen:
            seen[key] = p
    return sorted(seen.values(), key=lambda p: p.engagement, reverse=True)


def strip_html(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def gather(calls) -> list[Post]:
    """Run request thunks in order. Stop at the first failure, but keep what came
    back before it (a 429 halfway through is still a useful harvest)."""
    posts: list[Post] = []
    for call in calls:
        try:
            posts.extend(call())
        except Unavailable:
            if not posts:
                raise
            break
    return posts


def http_client(timeout: float = 20.0) -> httpx.Client:
    return httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)


def safe_get(http: httpx.Client, url: str, params: dict) -> httpx.Response:
    try:
        return http.get(url, params=params)
    except httpx.HTTPError as e:
        raise Unavailable(f"{type(e).__name__}") from e


def check_status(resp: httpx.Response) -> None:
    if resp.status_code != 200:
        raise Unavailable(f"HTTP {resp.status_code}")
