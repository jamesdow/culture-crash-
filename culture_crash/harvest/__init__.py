"""Platform harvesters. Every platform degrades to Claude web search on its own domain."""

from __future__ import annotations

from .base import TELLS, ChainResult, HarvestSpec, Post, Unavailable, run_chain
from .reddit import DEFAULT_SUBREDDITS, reddit_routes
from .social import ApifyInstagram, ApifyTikTok
from .youtube import youtube_routes

PLATFORMS = ("web", "reddit", "tiktok", "instagram", "youtube")

DOMAINS = {
    "reddit": ["reddit.com"],
    "tiktok": ["tiktok.com"],
    "instagram": ["instagram.com"],
    "youtube": ["youtube.com"],
}


def routes_for(platform: str) -> list:
    return {
        "reddit": reddit_routes,
        "youtube": youtube_routes,
        "tiktok": lambda: [ApifyTikTok()],
        "instagram": lambda: [ApifyInstagram()],
    }[platform]()


def platform_of(url: str) -> str:
    u = url.lower()
    for p, doms in DOMAINS.items():
        if any(d in u for d in doms):
            return p
    if "youtu.be" in u:
        return "youtube"
    return "web"


__all__ = ["PLATFORMS", "DOMAINS", "TELLS", "DEFAULT_SUBREDDITS", "ChainResult", "HarvestSpec", "Post",
           "Unavailable", "platform_of", "routes_for", "run_chain"]
