"""Runs the processing stages for an inspection in a background thread.

Stage status (pending / running / done / failed) is stored in inspection.json;
live progress messages are kept in memory and served by the status endpoint.
"""
import shutil
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor

from ..vision import preprocess
from . import storage

_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")
_lock = threading.Lock()
_running: set[str] = set()
_progress: dict[str, dict] = {}


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
    _progress[inspection_id] = {"stage": "preprocess", "message": "Queued", "fraction": 0.0}
    _executor.submit(_run, app, inspection_id)
    return True


def _run(app, inspection_id: str) -> None:
    with app.app_context():
        try:
            _preprocess(inspection_id)
            # M3 (analysis), M4 (vlm) and M5 (agent) plug in here.
        finally:
            with _lock:
                _running.discard(inspection_id)
            _progress.pop(inspection_id, None)


def _preprocess(inspection_id: str) -> None:
    record = storage.set_stage(inspection_id, "preprocess", "running")
    out_dir = storage.stage_dir(inspection_id, "preprocess")
    shutil.rmtree(out_dir, ignore_errors=True)      # clean re-run

    def report(message, fraction):
        _progress[inspection_id] = {"stage": "preprocess", "message": message, "fraction": round(fraction, 3)}

    try:
        preprocess.run(storage.media_paths(record), out_dir, progress=report)
    except Exception as e:
        traceback.print_exc()
        storage.set_stage(inspection_id, "preprocess", "failed", error=str(e))
        raise
    storage.set_stage(inspection_id, "preprocess", "done")
