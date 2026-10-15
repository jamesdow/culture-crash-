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
from pydantic import BaseModel

from .models import Source

T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
WEB_SEARCH_TOOL = "web_search_20260209"
MAX_PAUSE_RESUMES = 5


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
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high", client: anthropic.Anthropic | None = None):
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
            raise EngineError("Anthropic credentials were rejected. Check ANTHROPIC_API_KEY.") from e
        except anthropic.APIConnectionError as e:
            raise EngineError("Couldn't reach the Anthropic API. Check your network.") from e
        except TypeError as e:  # the SDK found no credentials at all
            raise EngineError("No Anthropic credentials found. Set ANTHROPIC_API_KEY (or run `ant auth login`).") from e

    def _stream(self, **kwargs):
        with self.client.beta.messages.stream(
            model=self.model,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            **kwargs,
        ) as stream:
            return stream.get_final_message()

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
                system=system,
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

        return Research(text="".join(texts).strip(), sources=list(sources.values()), cited_excerpts=excerpts)

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


def make_client() -> anthropic.Anthropic:
    """Standard client. Keys that aren't scoped to a workspace need the workspace named on
    every request, which ANTHROPIC_WORKSPACE_ID supplies."""
    workspace = os.getenv("ANTHROPIC_WORKSPACE_ID", "").strip()
    headers = {"anthropic-workspace-id": workspace} if workspace else None
    return anthropic.Anthropic(max_retries=4, default_headers=headers)


def _refusal_category(msg) -> str:
    details = getattr(msg, "stop_details", None)
    return getattr(details, "category", None) or "no category"
