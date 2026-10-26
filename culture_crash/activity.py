"""Live view of what each agent is doing, for the progress panel.

The pipeline opens an agent around each unit of work (a platform scout, a scorer,
a diver). Claude calls made inside it report their stream events here: thinking,
searching (with the query), writing. The web UI polls the in-memory run, so this
is visible while it happens without writing the run file on every token.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal, Optional

from pydantic import BaseModel

AgentStatus = Literal["starting", "harvesting", "thinking", "searching", "reading", "writing", "done", "failed"]


class AgentState(BaseModel):
    id: str
    label: str
    stage: str
    space_id: str = ""
    status: AgentStatus = "starting"
    step: str = ""
    started_at: float
    last_event_at: float
    ended_at: Optional[float] = None
    searches: int = 0
    last_query: str = ""
    queries: list[str] = []  # the full search trail, so a person can retrace it
    sources: int = 0
    out_chars: int = 0
    thought: str = ""
    error: str = ""


class Tracker:
    def __init__(self, state: AgentState):
        self.s = state
        self._json = ""

    def _touch(self) -> None:
        self.s.last_event_at = time.time()

    def status(self, status: AgentStatus, step: str | None = None) -> None:
        self.s.status = status
        if step is not None and step != self.s.step:
            # a new step: the previous step's search and thinking would only mislead
            self.s.step, self.s.last_query, self.s.thought = step, "", ""
        self._touch()

    def on_event(self, event) -> None:
        """Consume one raw streaming event from the Claude API."""
        t = getattr(event, "type", "")
        if t == "content_block_start":
            kind = getattr(event.content_block, "type", "")
            if kind == "thinking":
                self.status("thinking")
            elif kind == "server_tool_use":
                self.s.searches += 1
                self._json = ""
                q = (getattr(event.content_block, "input", None) or {}).get("query") if isinstance(getattr(event.content_block, "input", None), dict) else None
                if q:  # some streams send the query up front rather than as deltas
                    self._json = json.dumps({"query": q})
                self.status("searching")
            elif kind == "web_search_tool_result":
                content = getattr(event.content_block, "content", None)
                if isinstance(content, list):
                    self.s.sources += len(content)
                self.status("reading")
            elif kind == "text":
                self.status("writing")
        elif t == "content_block_delta":
            d = event.delta
            dt = getattr(d, "type", "")
            if dt == "thinking_delta":
                self.s.thought = (self.s.thought + (d.thinking or ""))[-280:]
            elif dt == "text_delta":
                self.s.out_chars += len(d.text or "")
            elif dt == "input_json_delta":
                self._json += d.partial_json or ""
            self._touch()
        elif t == "content_block_stop" and self._json:
            try:
                q = json.loads(self._json).get("query")
                if q:
                    self.s.last_query = str(q)[:160]
                    if len(self.s.queries) < 40:
                        self.s.queries = self.s.queries + [self.s.last_query]
            except (ValueError, AttributeError):
                pass
            self._json = ""
            self._touch()


current: ContextVar[Optional[Tracker]] = ContextVar("current_agent", default=None)


@contextmanager
def agent(store, run, label: str, stage: str, space_id: str = "") -> Iterator[Tracker]:
    now = time.time()
    with store._lock:
        state = AgentState(id=f"a{len(run.agents) + 1}", label=label, stage=stage, space_id=space_id,
                           started_at=now, last_event_at=now)
        run.agents.append(state)
    tracker = Tracker(state)
    token = current.set(tracker)
    try:
        yield tracker
        state.status = "done"
    except Exception as e:
        state.status, state.error = "failed", f"{type(e).__name__}: {e}"[:300]
        raise
    finally:
        state.ended_at = time.time()
        current.reset(token)
