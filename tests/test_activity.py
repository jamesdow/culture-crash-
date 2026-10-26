from types import SimpleNamespace as NS

from culture_crash.activity import AgentState, Tracker


def ev(type_, **kw):
    return NS(type=type_, **kw)


def test_tracker_follows_stream():
    t = Tracker(AgentState(id="a1", label="TikTok scout", stage="scan", started_at=0, last_event_at=0))
    t.on_event(ev("content_block_start", content_block=NS(type="thinking")))
    t.on_event(ev("content_block_delta", delta=NS(type="thinking_delta", thinking="Looking for comment pile-ons")))
    assert t.s.status == "thinking" and "pile-ons" in t.s.thought
    t.on_event(ev("content_block_start", content_block=NS(type="server_tool_use", input={})))
    t.on_event(ev("content_block_delta", delta=NS(type="input_json_delta", partial_json='{"query": "is it weird')))
    t.on_event(ev("content_block_delta", delta=NS(type="input_json_delta", partial_json=' that tiktok"}')))
    t.on_event(ev("content_block_stop"))
    assert t.s.status == "searching" and t.s.searches == 1 and t.s.queries == ["is it weird that tiktok"]
    t.on_event(ev("content_block_start", content_block=NS(type="web_search_tool_result", content=[1, 2, 3])))
    assert t.s.status == "reading" and t.s.sources == 3
    t.on_event(ev("content_block_start", content_block=NS(type="server_tool_use", input={"query": "up front"})))
    t.on_event(ev("content_block_stop"))
    assert t.s.queries[-1] == "up front"
    t.on_event(ev("content_block_start", content_block=NS(type="text")))
    t.on_event(ev("content_block_delta", delta=NS(type="text_delta", text="notes")))
    assert t.s.status == "writing" and t.s.out_chars == 5


def test_new_step_clears_stale_search_and_thought():
    t = Tracker(AgentState(id="a1", label="TikTok scout", stage="scan", started_at=0, last_event_at=0))
    t.status("searching", "Searching tiktok.com")
    t.s.last_query, t.s.thought = "asking chatgpt before replying", "old thought"
    t.status("searching")  # same step: keep
    assert t.s.last_query
    t.status("thinking", "Turning notes from 68 sources into evidence")
    assert t.s.last_query == "" and t.s.thought == "" and t.s.searches == 0
