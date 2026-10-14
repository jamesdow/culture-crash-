from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

from .models import Run, RunConfig
from .store import RunStore


def _config(a: argparse.Namespace) -> RunConfig:
    return RunConfig(
        focus=a.focus, brand=a.brand, market=a.market, recency_days=a.days,
        use_web=not a.no_web, use_reddit=not a.no_reddit,
        subreddits=[s.strip().removeprefix("r/") for s in a.subreddits.split(",") if s.strip()] if a.subreddits else [],
        max_spaces=a.max_spaces, shortlist=a.shortlist, band=a.band,
        seeds_per_space=a.seeds, cards_per_space=a.cards, seed=a.seed, model=a.model, effort=a.effort,
    )


def cmd_run(a: argparse.Namespace) -> int:
    from .llm import ClaudeLLM
    from .pipeline import Engine
    from .report import render

    store = RunStore(a.runs)
    cfg = _config(a)
    run = Run(id=store.new_id(), config=cfg)
    store.save(run)
    print(f"run {run.id}  (stored in {store.path(run.id)})", flush=True)

    printed = 0
    done = threading.Event()

    def tail() -> None:
        nonlocal printed
        while not done.is_set():
            time.sleep(0.5)
            while printed < len(run.progress):
                ev = run.progress[printed]
                print(f"  [{ev.stage:8}] {ev.message}", flush=True)
                printed += 1

    t = threading.Thread(target=tail, daemon=True)
    t.start()
    Engine(ClaudeLLM(model=cfg.model, effort=cfg.effort), store).run(run)
    done.set()
    t.join()
    for ev in run.progress[printed:]:
        print(f"  [{ev.stage:8}] {ev.message}")
    md = Path(a.runs) / f"{run.id}.md"
    md.write_text(render(run), encoding="utf-8")
    print(f"\nreport: {md}")
    if run.status == "error":
        print(f"error: {run.error}", file=sys.stderr)
        return 1
    print("Next: judge each shortlisted space with `culture-crash verdict` or in the web UI (`culture-crash serve`).")
    return 0


def cmd_serve(a: argparse.Namespace) -> int:
    import uvicorn

    from .server import create_app

    print(f"Culture Crash on http://{a.host}:{a.port}")
    uvicorn.run(create_app(a.runs), host=a.host, port=a.port, log_level="warning")
    return 0


def cmd_demo(a: argparse.Namespace) -> int:
    from .demo import build_demo_run
    from .report import render

    store = RunStore(a.runs)
    run = build_demo_run(store.new_id())
    store.save(run)
    md = Path(a.runs) / f"{run.id}.md"
    md.write_text(render(run), encoding="utf-8")
    print(f"demo run {run.id} written to {store.path(run.id)} and {md}")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    for r in RunStore(a.runs).list():
        n = sum(1 for s in r.spaces if s.shortlisted)
        print(f"{r.id}  {r.status:7} {'DEMO ' if r.demo else ''}focus={r.config.focus or 'open'} brand={r.config.brand or '-'} shortlisted={n}")
    return 0


def cmd_verdict(a: argparse.Namespace) -> int:
    store = RunStore(a.runs)
    run = store.set_verdict(a.run_id, a.space_id, a.status, a.note or "", a.by or "")
    sp = run.space(a.space_id)
    print(f"{sp.working_name}: {sp.verdict.status}")
    return 0


def cmd_export(a: argparse.Namespace) -> int:
    from .report import render

    text = render(RunStore(a.runs).load(a.run_id), brief_only=a.brief)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
        print(f"wrote {a.out}")
    else:
        print(text)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="culture-crash", description="Find pre-trends and collide them with far latent concepts.")
    p.add_argument("--runs", default="runs", help="directory where runs are stored (default: ./runs)")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the engine end to end")
    r.add_argument("--focus", help="territory to scan near, e.g. 'friendship after 30' or 'food at work'")
    r.add_argument("--brand", help="optional brand lens; shapes only the value exchange")
    r.add_argument("--market", default="UK and US")
    r.add_argument("--days", type=int, default=90, help="recency window in days")
    r.add_argument("--no-web", action="store_true")
    r.add_argument("--no-reddit", action="store_true")
    r.add_argument("--subreddits", help="comma-separated list; defaults to a broad everyday-life set")
    r.add_argument("--max-spaces", type=int, default=8)
    r.add_argument("--shortlist", type=int, default=4)
    r.add_argument("--band", type=float, default=5.5, help="both axes must clear this (0-10)")
    r.add_argument("--seeds", type=int, default=4, help="far domains drawn per space")
    r.add_argument("--cards", type=int, default=3, help="collision cards kept per space")
    r.add_argument("--seed", type=int, help="random seed for far-domain draws")
    r.add_argument("--model", default="claude-opus-5-5")
    r.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    r.set_defaults(fn=cmd_run)

    s = sub.add_parser("serve", help="open the web UI")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    s.set_defaults(fn=cmd_serve)

    sub.add_parser("demo", help="write an illustrative offline run to explore the UI").set_defaults(fn=cmd_demo)
    sub.add_parser("list", help="list runs").set_defaults(fn=cmd_list)

    v = sub.add_parser("verdict", help="record the human conscience verdict for a space")
    v.add_argument("run_id")
    v.add_argument("space_id")
    v.add_argument("status", choices=["gives", "takes", "unsure", "pending"])
    v.add_argument("--note")
    v.add_argument("--by")
    v.set_defaults(fn=cmd_verdict)

    e = sub.add_parser("export", help="export a run as markdown")
    e.add_argument("run_id")
    e.add_argument("--brief", action="store_true", help="only spaces an operator has cleared as 'gives'")
    e.add_argument("--out")
    e.set_defaults(fn=cmd_export)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
