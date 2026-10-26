"""`culture-crash doctor`: is a stall Claude thinking, or the network holding the stream back?

It makes one streamed call and times every line that arrives, including the
server's keep-alive pings. If pings arrive steadily, the connection is healthy
and long silences are Claude working. If everything arrives in bursts after
long gaps, something between this computer and the API (often a work VPN or
proxy) is buffering the stream, and long calls will time out.
"""

from __future__ import annotations

import time

from .llm import ClaudeLLM, EngineError

PROMPT = (
    "Think it through carefully before answering. List twelve everyday behaviours that people are "
    "slightly embarrassed about, and for each give one sentence on the unmet need underneath it."
)


def run_doctor(model: str = "claude-opus-5-5") -> int:
    llm = ClaudeLLM(model=model)
    print("1/2  Checking credentials...", flush=True)
    try:
        llm.preflight()
    except EngineError as e:
        print(f"     FAILED: {e}")
        return 1
    print("     OK")

    print("2/2  Timing a streamed call (about a minute)...", flush=True)
    t0 = time.monotonic()
    arrivals: list[tuple[float, str]] = []
    try:
        with llm.client.with_options(timeout=300.0).messages.with_streaming_response.create(
            model=model,
            max_tokens=8000,
            stream=True,
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": "medium"},
            messages=[{"role": "user", "content": PROMPT}],
        ) as resp:
            for line in resp.iter_lines():
                if line.startswith("event:"):
                    arrivals.append((time.monotonic() - t0, line[6:].strip()))
    except Exception as e:
        print(f"     The test call failed after {time.monotonic() - t0:.0f}s: {type(e).__name__}: {e}")
        print("     If this was a timeout, your connection is likely holding the stream back (see below).")
        _advice_buffered()
        return 1

    total = time.monotonic() - t0
    if not arrivals:
        print("     No events arrived at all.")
        return 1
    times = [t for t, _ in arrivals]
    gaps = [b - a for a, b in zip([0.0] + times, times)]
    pings = sum(1 for _, k in arrivals if k == "ping")
    first, worst = times[0], max(gaps)
    # Share of all events that arrived in the last 2 seconds: high means it was held back and released at once.
    burst = sum(1 for t in times if t > total - 2) / len(times)
    print(f"     {len(arrivals)} events in {total:.0f}s · first after {first:.1f}s · longest silence {worst:.1f}s · {pings} keep-alive pings")

    if worst > 45 or (total > 20 and burst > 0.8):
        _advice_buffered()
        return 1
    print("\nStreaming is healthy. Long quiet spells during a run are Claude thinking, not your connection.")
    return 0


def _advice_buffered() -> None:
    print(
        "\nYour connection seems to be holding the stream back and releasing it in bursts.\n"
        "This is usually a work VPN, proxy or security tool inspecting web traffic, and it causes\n"
        "the long silences and timeouts during runs. Try: disconnect from the VPN (or use a\n"
        "non-work network) and run `culture-crash doctor` again. If that fixes it, ask IT to allow\n"
        "streaming to api.anthropic.com."
    )
