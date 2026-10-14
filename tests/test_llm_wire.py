"""Exercise the real ClaudeLLM against a mocked HTTP transport replaying SSE streams.

Checks the request shape (model, fallbacks, web search tool, JSON schema) and
that search results, citations, pause_turn and structured JSON are parsed.
"""

from __future__ import annotations

import json

import anthropic
import httpx2

from culture_crash.llm import ClaudeLLM
from culture_crash.schemas import SignalExtraction


def sse(events: list[dict]) -> bytes:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def message(blocks: list[dict], stop_reason: str) -> list[dict]:
    ev = [{"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                                                  "content": [], "stop_reason": None, "stop_sequence": None,
                                                  "usage": {"input_tokens": 1, "output_tokens": 1}}}]
    for i, b in enumerate(blocks):
        if b["type"] == "text":
            ev.append({"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": "", "citations": []}})
            ev.append({"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": b["text"]}})
            for c in b.get("citations", []):
                ev.append({"type": "content_block_delta", "index": i, "delta": {"type": "citations_delta", "citation": c}})
        else:
            ev.append({"type": "content_block_start", "index": i, "content_block": b})
        ev.append({"type": "content_block_stop", "index": i})
    ev.append({"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": 5}})
    ev.append({"type": "message_stop"})
    return ev


def make_llm(responses: list[bytes], seen: list[dict]) -> ClaudeLLM:
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=responses[len(seen) - 1])

    client = anthropic.Anthropic(api_key="test", http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    return ClaudeLLM(client=client)


def test_research_collects_sources_and_resumes_pause_turn():
    search = {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "is there a word for"}}
    result = {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1", "content": [
        {"type": "web_search_result", "url": "https://www.reddit.com/r/x/1", "title": "Is there a word for...", "encrypted_content": "e", "page_age": "2 days ago"}]}
    first = sse(message([search, result], "pause_turn"))
    cite = {"type": "web_search_result_location", "url": "https://forum.example/2", "title": "Forum", "cited_text": "my janky system", "encrypted_index": "x"}
    second = sse(message([{"type": "text", "text": "Finding one.", "citations": [cite]}], "end_turn"))
    seen: list[dict] = []
    r = make_llm([first, second], seen).research("sys", "find things", max_searches=3)

    req = seen[0]
    assert req["model"] == "claude-opus-5-5" and req["fallbacks"] == "default"
    assert req["tools"][0]["type"] == "web_search_20260209" and req["tools"][0]["max_uses"] == 3
    assert len(seen) == 2 and seen[1]["messages"][-1]["role"] == "assistant"  # resumed after pause_turn
    assert [s.url for s in r.sources] == ["https://www.reddit.com/r/x/1", "https://forum.example/2"]
    assert r.cited_excerpts == [("https://forum.example/2", "my janky system")]
    assert r.text == "Finding one."


def test_structured_sends_schema_and_parses():
    payload = {"signals": [{"kind": "shame", "observation": "o", "verbatim": "v", "emotional_weight": 4, "source_ref": "S1"}]}
    seen: list[dict] = []
    out = make_llm([sse(message([{"type": "text", "text": json.dumps(payload)}], "end_turn"))], seen).structured(
        "sys", "extract", SignalExtraction, effort="medium")
    req = seen[0]
    assert req["output_config"]["effort"] == "medium"
    assert req["output_config"]["format"]["type"] == "json_schema"
    assert out.signals[0].kind == "shame"
