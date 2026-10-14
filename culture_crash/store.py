from __future__ import annotations

import secrets
import threading
from datetime import datetime
from pathlib import Path

from .models import ProgressEvent, Run, Verdict, VerdictStatus, now_iso


class RunStore:
    """Runs live as one JSON file each, so they can be diffed, shared and re-opened."""

    def __init__(self, root: str | Path = "runs"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def new_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S-") + secrets.token_hex(2)

    def path(self, run_id: str) -> Path:
        if not run_id.replace("-", "").isalnum():
            raise ValueError("bad run id")
        return self.root / f"{run_id}.json"

    def save(self, run: Run) -> None:
        with self._lock:
            tmp = self.path(run.id).with_suffix(".json.tmp")
            tmp.write_text(run.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(self.path(run.id))

    def load(self, run_id: str) -> Run:
        with self._lock:
            return Run.model_validate_json(self.path(run_id).read_text(encoding="utf-8"))

    def list(self) -> list[Run]:
        runs = []
        for p in sorted(self.root.glob("*.json"), reverse=True):
            try:
                runs.append(Run.model_validate_json(p.read_text(encoding="utf-8")))
            except Exception:
                continue
        return runs

    def log(self, run: Run, stage: str, message: str) -> None:
        with self._lock:
            run.stage = stage
            run.progress.append(ProgressEvent(at=now_iso(), stage=stage, message=message))
            self.save(run)

    def set_route(self, run: Run, platform: str, route: str) -> None:
        with self._lock:  # scan jobs run in threads; never mutate the run mid-save
            run.routes[platform] = route

    def set_verdict(self, run_id: str, space_id: str, status: VerdictStatus, note: str = "", by: str = "") -> Run:
        """The only way a verdict is ever written: by a person, through here."""
        with self._lock:
            run = self.load(run_id)
            space = run.space(space_id)
            if space is None:
                raise KeyError(space_id)
            space.verdict = Verdict(status=status, note=note, by=by, at=now_iso())
            self.save(run)
            return run
