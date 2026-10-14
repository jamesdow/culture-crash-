"""Harvester parsing and fallback behaviour, against mocked HTTP."""

from __future__ import annotations

import httpx
import pytest

from culture_crash.harvest import HarvestSpec, Post, Unavailable, platform_of, run_chain
from culture_crash.harvest import reddit as R
from culture_crash.harvest import social as S
from culture_crash.harvest import youtube as Y
from culture_crash.harvest.base import gather

NOW = __import__("time").time()

RSS = f"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
 <entry>
  <category term="AskUK" label="r/AskUK"/>
  <content type="html">&lt;p&gt;I set reminders to text my best friend and feel weird about it&lt;/p&gt;</content>
  <link href="https://www.reddit.com/r/AskUK/comments/abc/is_it_weird/"/>
  <updated>{__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()}</updated>
  <title>Is it weird that I schedule my friends?</title>
 </entry>
</feed>"""


def mock_client(monkeypatch, module, handler):
    monkeypatch.setattr(module, "http_client", lambda timeout=20.0: httpx.Client(transport=httpx.MockTransport(handler)))


def spec(**kw):
    return HarvestSpec(focus=None, recency_days=30, subreddits=["AskUK"], **kw)


def test_reddit_rss_parses_atom(monkeypatch):
    mock_client(monkeypatch, R, lambda req: httpx.Response(200, content=RSS.encode()))
    posts = R.RedditRSS().harvest(spec(tells=["is it weird that"]))
    assert posts[0].url == "https://www.reddit.com/r/AskUK/comments/abc/is_it_weird/"
    assert posts[0].context == "r/AskUK" and "reminders" in posts[0].text and "<p>" not in posts[0].text


def test_reddit_json_blocked_raises(monkeypatch):
    mock_client(monkeypatch, R, lambda req: httpx.Response(403))
    with pytest.raises(Unavailable):
        R.RedditJSON().harvest(spec())


def test_archives_parse(monkeypatch):
    item = {"title": "Does anyone else hide that they're learning to swim at 35?", "selftext": "body",
            "permalink": "/r/AskUK/comments/z/x/", "subreddit": "AskUK", "score": 5, "num_comments": 9, "created_utc": NOW}
    mock_client(monkeypatch, R, lambda req: httpx.Response(200, json={"data": [item, {**item, "over_18": True}]}))
    for route in (R.ArcticShift(), R.PullPush()):
        posts = route.harvest(spec(tells=["does anyone else"]))
        assert posts and all(p.url == "https://www.reddit.com/r/AskUK/comments/z/x/" for p in posts)
        assert posts[0].engagement == 5 + 18


def test_chain_falls_through_and_keeps_partial(monkeypatch):
    calls = iter([[Post("reddit", "u1", "a long enough text for the filter")], Unavailable("429")])

    def thunk():
        v = next(calls)
        if isinstance(v, Exception):
            raise v
        return v

    assert len(gather([thunk, thunk])) == 1  # 429 after a success keeps what we had

    class Bad:
        name = "bad"
        def ready(self): return True
        def harvest(self, s): raise Unavailable("HTTP 403")

    class Off:
        name = "off"
        def ready(self): return False
        def harvest(self, s): raise AssertionError

    class Good:
        name = "good"
        def ready(self): return True
        def harvest(self, s): return [Post("reddit", f"u{i}", "a long enough text for the filter", created_utc=NOW) for i in range(10)]

    res = run_chain([Bad(), Off(), Good()], spec())
    assert res.route == "good" and len(res.posts) == 10
    assert res.attempts[0] == "bad: HTTP 403" and "skipped" in res.attempts[1]
    with pytest.raises(Unavailable):
        run_chain([Bad(), Off()], spec())


def test_youtube_data_api(monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "k")

    def handler(req):
        if req.url.path.endswith("/search"):
            return httpx.Response(200, json={"items": [{"id": {"videoId": "v1"}, "snippet": {"title": "Things nobody tells you"}}]})
        return httpx.Response(200, json={"items": [{"id": "c1", "snippet": {"topLevelComment": {"snippet": {
            "textDisplay": "I didn't know there was a word for this", "likeCount": 40, "publishedAt": "2026-10-01T10:00:00Z"}}}}]})

    monkeypatch.setattr(Y, "http_client", lambda timeout=20.0: httpx.Client(transport=httpx.MockTransport(handler)))
    posts = Y.YouTubeDataAPI().harvest(spec())
    assert posts[0].url == "https://www.youtube.com/watch?v=v1&lc=c1" and posts[0].engagement == 40
    assert posts[0].context == "comment on: Things nobody tells you"
    monkeypatch.delenv("YOUTUBE_API_KEY")
    assert not Y.YouTubeDataAPI().ready()


def test_apify_tiktok(monkeypatch):
    monkeypatch.setenv("APIFY_TOKEN", "t")

    def fake_post(url, params=None, json=None, timeout=None):
        if "comments" in url:
            return httpx.Response(201, json=[{"text": "not me doing this at 2am", "videoWebUrl": "https://www.tiktok.com/@a/video/1", "diggCount": 3}],
                                  request=httpx.Request("POST", url))
        return httpx.Response(201, json=[{"text": "my friendship spreadsheet", "webVideoUrl": "https://www.tiktok.com/@a/video/1",
                                          "hashtags": [{"name": "adulting"}], "commentCount": 10, "createTimeISO": "2026-10-01T00:00:00Z"}],
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(S.httpx, "post", fake_post)
    posts = S.ApifyTikTok().harvest(spec())
    assert posts[0].text == "my friendship spreadsheet #adulting"
    assert any(p.context == "comment on a TikTok" for p in posts)


def test_platform_of():
    assert platform_of("https://www.tiktok.com/@x/video/1") == "tiktok"
    assert platform_of("https://youtu.be/abc") == "youtube"
    assert platform_of("https://old.reddit.com/r/x") == "reddit"
    assert platform_of("https://www.instagram.com/p/x") == "instagram"
    assert platform_of("https://news.example/x") == "web"
