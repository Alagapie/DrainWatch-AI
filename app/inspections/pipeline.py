"""Runs the processing stages for an inspection in a background thread.

Stage status (pending / running / done / failed) is stored in inspection.json;
live progress messages are kept in memory and served by the status endpoint.
"""
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from flask import current_app

from ..ai import agent, severity
from ..vision import analysis, preprocess
from . import storage

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")
_lock = threading.Lock()
_running: set[str] = set()
_progress: dict[str, dict] = {}

# Stages run in this order; each takes (inspection_id, record, out_dir, report).
STAGE_RUNNERS = [
    ("preprocess", lambda iid, rec, out, report: preprocess.run(storage.media_paths(rec), out, progress=report)),
    ("analysis", lambda iid, rec, out, report: analysis.run(storage.stage_dir(iid, "preprocess"), out, progress=report)),
    ("vlm", lambda iid, rec, out, report: severity.run(
        storage.stage_dir(iid, "analysis"), out, rec.get("notes"),
        current_app.config["AWS_REGION"], current_app.config["BEDROCK_MODEL_ID"], progress=report)),
    ("agent", lambda iid, rec, out, report: agent.run(
        iid, current_app.config["AWS_REGION"], current_app.config["BEDROCK_MODEL_ID"], progress=report)),
]


def is_running(inspection_id: str) -> bool:
    return inspection_id in _running


def progress(inspection_id: str) -> dict | None:
    return _progress.get(inspection_id)


def start(app, inspection_id: str) -> bool:
    """Queue processing. Returns False if this inspection is already being processed."""
    with _lock:
        if inspection_id in _running:
            return False
        _running.add(inspection_id)
    _progress[inspection_id] = {"stage": STAGE_RUNNERS[0][0], "message": "Queued", "fraction": 0.0}
    _executor.submit(_run, app, inspection_id)
    return True


def _run(app, inspection_id: str) -> None:
    with app.app_context():
        try:
            for stage, _ in STAGE_RUNNERS:              # later stages are stale once we re-run
                storage.set_stage(inspection_id, stage, "pending")
            for stage, runner in STAGE_RUNNERS:
                if not _run_stage(inspection_id, stage, runner):
                    break
        finally:
            with _lock:
                _running.discard(inspection_id)
            _progress.pop(inspection_id, None)


def _run_stage(inspection_id: str, stage: str, runner) -> bool:
    record = storage.set_stage(inspection_id, stage, "running")
    out_dir = storage.stage_dir(inspection_id, stage)
    shutil.rmtree(out_dir, ignore_errors=True)

    def report(message, fraction):
        _progress[inspection_id] = {"stage": stage, "message": message, "fraction": round(fraction, 3)}

    try:
        runner(inspection_id, record, out_dir, report)
    except Exception as e:
        traceback.print_exc()
        storage.set_stage(inspection_id, stage, "failed", error=str(e))
        return False
    storage.set_stage(inspection_id, stage, "done")
    return True
