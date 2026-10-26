"""Thin Claude layer: two verbs the pipeline needs.

* ``research`` - an open-ended, web-searching call. Returns the prose notes
  plus every source the search tool actually retrieved.
* ``structured`` - a JSON-schema-constrained call that returns a validated
  pydantic object.

Citation integrity rests on the split: structured calls never invent URLs,
they point at numbered sources (S1, S2...) that ``research`` really fetched,
and the pipeline drops anything that points elsewhere.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

import anthropic
import httpx2
from pydantic import BaseModel

from . import activity
from .models import Source

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEB_SEARCH_TOOL = "web_search_20260209"
MAX_PAUSE_RESUMES = 5
# Generous overall, but a stream that goes silent for 5 minutes is treated as dropped.
STREAM_TIMEOUT = httpx2.Timeout(900.0, connect=30.0, read=300.0)
FINAL_ANSWER_RULE = (
    "\n\nImportant: do all of your searching first. Then write your complete notes, with "
    "citations, in your final answer. Anything you write between searches is discarded."
)


class EngineError(RuntimeError):
    pass


@dataclass
class Research:
    text: str
    sources: list[Source] = field(default_factory=list)
    cited_excerpts: list[tuple[str, str]] = field(default_factory=list)  # (url, cited_text)


class LLM(Protocol):
    def research(self, system: str, prompt: str, max_searches: int = 6, allowed_domains: list[str] | None = None) -> Research: ...

    def structured(self, system: str, prompt: str, schema: type[T], effort: str | None = None) -> T: ...


class ClaudeLLM:
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "medium", client: anthropic.Anthropic | None = None):
        self.model = model
        self.effort = effort
        self.client = client or make_client()

    def preflight(self) -> None:
        """Fail fast, before any scraping, if credentials or the model are wrong."""
        try:
            self.client.models.retrieve(self.model)
        except anthropic.BadRequestError as e:
            if "workspace" in str(e).lower():
                raise EngineError(
                    "This API key isn't tied to a workspace. Either create a key inside a workspace "
                    "(Console > Settings > Workspaces > pick one > API keys), or set ANTHROPIC_WORKSPACE_ID "
                    "to your workspace ID (it starts with wrkspc_)."
                ) from e
            raise EngineError(f"The API rejected the startup check: {e}") from e
        except anthropic.NotFoundError as e:
            raise EngineError(f"Model {self.model!r} isn't available to this account.") from e
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError) as e:
            raise EngineError(
                f"Anthropic rejected the API key (HTTP {e.status_code}: {_api_message(e)}). "
                "Check ANTHROPIC_API_KEY, and restart `culture-crash serve` after changing it."
            ) from e
        except anthropic.APIConnectionError as e:
            raise EngineError("Couldn't reach the Anthropic API. Check your network.") from e
        except TypeError as e:  # the SDK found no credentials at all
            raise EngineError("No Anthropic credentials found. Set ANTHROPIC_API_KEY (or run `ant auth login`).") from e

    def _stream(self, **kwargs):
        """One streamed call. Thinking summaries are streamed so the connection never sits
        silent for minutes while the model works; one retry if the stream still drops."""
        for attempt in range(2):
            try:
                with self.client.with_options(timeout=STREAM_TIMEOUT).beta.messages.stream(
                    model=self.model,
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                    thinking={"type": "adaptive", "display": "summarized"},
                    **kwargs,
                ) as stream:
                    tracker = activity.current.get()
                    for event in stream:  # feed the live progress panel
                        if tracker:
                            tracker.on_event(event)
                    return stream.get_final_message()
            except (anthropic.APITimeoutError, anthropic.APIConnectionError, httpx2.TimeoutException, httpx2.TransportError) as e:
                if attempt == 1:
                    raise EngineError(f"Claude call timed out twice ({type(e).__name__}). Resume the run to retry from here.") from e
                # Second try: think less, so the call is shorter.
                cfg = dict(kwargs.get("output_config") or {})
                cfg["effort"] = {"max": "high", "xhigh": "high", "high": "medium"}.get(cfg.get("effort", ""), "low")
                kwargs["output_config"] = cfg
        raise AssertionError("unreachable")

    def research(self, system: str, prompt: str, max_searches: int = 6, allowed_domains: list[str] | None = None) -> Research:
        user = {"role": "user", "content": prompt}
        messages: list[dict] = [user]
        tool: dict = {"type": WEB_SEARCH_TOOL, "name": "web_search", "max_uses": max_searches}
        if allowed_domains:
            tool["allowed_domains"] = allowed_domains
        tools = [tool]
        texts: list[str] = []
        sources: dict[str, Source] = {}
        excerpts: list[tuple[str, str]] = []

        for _ in range(MAX_PAUSE_RESUMES + 1):
            msg = self._stream(
                max_tokens=32000,
                system=system + FINAL_ANSWER_RULE,
                messages=messages,
                tools=tools,
                output_config={"effort": "medium"},
            )
            if msg.stop_reason == "refusal":
                raise EngineError(f"Model declined a research step ({_refusal_category(msg)}).")
            for block in msg.content:
                if block.type == "web_search_tool_result":
                    # Success is a list of results; an error is a single object.
                    if isinstance(block.content, list):
                        for r in block.content:
                            url = getattr(r, "url", None)
                            if url and url not in sources:
                                sources[url] = Source(url=url, title=getattr(r, "title", "") or "", date=getattr(r, "page_age", None))
                elif block.type == "text":
                    texts.append(block.text)
                    for c in getattr(block, "citations", None) or []:
                        url = getattr(c, "url", None)
                        if url:
                            excerpts.append((url, getattr(c, "cited_text", "") or ""))
                            if url not in sources:
                                sources[url] = Source(url=url, title=getattr(c, "title", "") or "")
            if msg.stop_reason != "pause_turn":
                break
            # Server-side search loop hit its iteration cap: resend and it resumes.
            messages = [user, {"role": "assistant", "content": msg.content}]

        text = "".join(texts).strip()
        if len(text) < 200 and excerpts:  # notes went missing; fall back to what the citations quote
            text = (text + "\n\n" + "\n".join(f"- {t} ({u})" for u, t in excerpts if t)).strip()
        return Research(text=text, sources=list(sources.values()), cited_excerpts=excerpts)

    def structured(self, system: str, prompt: str, schema: type[T], effort: str | None = None) -> T:
        msg = self._stream(
            max_tokens=32000,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": effort or self.effort},
            output_format=schema,
        )
        if msg.stop_reason == "refusal":
            raise EngineError(f"Model declined a structuring step ({_refusal_category(msg)}).")
        if msg.stop_reason == "max_tokens":
            raise EngineError("Structured output was cut off at max_tokens.")
        text = next((b.text for b in msg.content if b.type == "text"), None)
        if text is None:
            raise EngineError("Structured call returned no text block.")
        return schema.model_validate_json(text)


def _api_message(e: anthropic.APIStatusError) -> str:
    body = e.body if isinstance(e.body, dict) else {}
    return (body.get("error") or {}).get("message") or e.message


def make_client() -> anthropic.Anthropic:
    """Standard client. Keys that aren't scoped to a workspace need the workspace named on
    every request, which ANTHROPIC_WORKSPACE_ID supplies."""
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
    headers = {"anthropic-workspace-id": workspace} if workspace else None
    return anthropic.Anthropic(max_retries=4, default_headers=headers)


def _refusal_category(msg) -> str:
    details = getattr(msg, "stop_details", None)
    return getattr(details, "category", None) or "no category"
