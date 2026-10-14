from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from .models import Run, RunConfig, VerdictStatus
from .report import render
from .store import RunStore

STATIC = Path(__file__).parent / "static"


class VerdictIn(BaseModel):
    status: VerdictStatus
    note: str = ""
    by: str = ""


def create_app(runs_dir: str = "runs") -> FastAPI:
    store = RunStore(runs_dir)
    live: dict[str, Run] = {}  # in-flight runs, served from memory while they execute
    app = FastAPI(title="Culture Crash")

    def get(run_id: str) -> Run:
        if run_id in live:
            return live[run_id]
        try:
            return store.load(run_id)
        except (FileNotFoundError, ValueError):
            raise HTTPException(404, "run not found")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/runs")
    def list_runs():
        return [
            {"id": r.id, "status": r.status, "demo": r.demo, "created_at": r.created_at,
             "focus": r.config.focus, "brand": r.config.brand,
             "shortlisted": sum(1 for s in r.spaces if s.shortlisted)}
            for r in store.list()
        ]

    @app.post("/api/runs")
    def start_run(cfg: RunConfig):
        from .llm import ClaudeLLM
        from .pipeline import Engine

        run = Run(id=store.new_id(), config=cfg)
        store.save(run)
        live[run.id] = run

        def work() -> None:
            try:
                Engine(ClaudeLLM(model=cfg.model, effort=cfg.effort), store).run(run)
            except Exception as e:  # e.g. missing credentials when the client is built
                run.status, run.error = "error", f"{type(e).__name__}: {e}"
                store.log(run, "error", run.error)
            finally:
                live.pop(run.id, None)

        threading.Thread(target=work, daemon=True).start()
        return {"id": run.id}

    @app.post("/api/demo")
    def demo():
        from .demo import build_demo_run

        run = build_demo_run(store.new_id())
        store.save(run)
        return {"id": run.id}

    @app.get("/api/runs/{run_id}")
    def read_run(run_id: str):
        return get(run_id)

    @app.post("/api/runs/{run_id}/spaces/{space_id}/verdict")
    def verdict(run_id: str, space_id: str, v: VerdictIn):
        if run_id in live:
            raise HTTPException(409, "run still in progress")
        try:
            store.set_verdict(run_id, space_id, v.status, v.note, v.by)
        except KeyError:
            raise HTTPException(404, "space not found")
        return {"ok": True}

    @app.get("/api/runs/{run_id}/export.md", response_class=PlainTextResponse)
    def export(run_id: str, brief: bool = False):
        return PlainTextResponse(render(get(run_id), brief_only=brief), media_type="text/markdown")

    return app
