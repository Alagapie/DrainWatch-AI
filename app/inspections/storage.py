"""File-based storage for inspections.

Each inspection lives in its own folder so later modules (OpenCV, VLM, agent,
review) can add their outputs next to the uploaded media:

    data/inspections/<inspection_id>/
        inspection.json     metadata + per-module status
        media/              uploaded video or photos
        preprocess/         M2 output: frames + preprocess.json
        analysis/           M3 output: evidence images + analysis.json
        vlm/                M4 output: vlm.json (Nova Pro severity assessment)
        agent/              M5 output: agent.json (recommendation + tool trace) + images from OpenCV tools
        audit.jsonl         M6: append-only log of every event (who, what, when)
"""
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone

from flask import current_app
from werkzeug.utils import secure_filename

STAGES = ["upload", "preprocess", "analysis", "vlm", "agent", "review"]

# inspection.json is updated by the pipeline thread and by web requests (reviews): serialise writes.
_write_lock = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class UploadError(ValueError):
    pass


def _root() -> str:
    return current_app.config["INSPECTIONS_DIR"]


def inspection_dir(inspection_id: str) -> str:
    return os.path.join(_root(), secure_filename(inspection_id))


def media_dir(inspection_id: str) -> str:
    return os.path.join(inspection_dir(inspection_id), "media")


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _new_id() -> str:
    return datetime.now(timezone.utc).strftime("insp-%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def classify_files(files) -> tuple[str, list]:
    """Return ("video" | "images", files) or raise UploadError."""
    cfg = current_app.config
    files = [f for f in files if f and f.filename]
    if not files:
        raise UploadError("Select a video or at least one photo.")

    videos = [f for f in files if _ext(f.filename) in cfg["VIDEO_EXTENSIONS"]]
    images = [f for f in files if _ext(f.filename) in cfg["IMAGE_EXTENSIONS"]]
    unsupported = [f.filename for f in files if f not in videos and f not in images]
    if unsupported:
        raise UploadError(f"Unsupported file type: {', '.join(unsupported)}")
    if videos and images:
        raise UploadError("Upload either one video or a set of photos, not both.")
    if len(videos) > 1:
        raise UploadError("Upload one video per inspection.")
    if len(images) > cfg["MAX_IMAGES"]:
        raise UploadError(f"Upload at most {cfg['MAX_IMAGES']} photos per inspection.")
    return ("video", videos) if videos else ("images", images)


def parse_site(form) -> dict:
    site_id = form.get("site_id", "").strip()
    lat_raw, lon_raw = form.get("lat", "").strip(), form.get("lon", "").strip()
    lat = lon = None
    if lat_raw or lon_raw:
        try:
            lat, lon = float(lat_raw), float(lon_raw)
        except ValueError:
            raise UploadError("Latitude and longitude must both be numbers.")
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise UploadError("Latitude must be -90..90 and longitude -180..180.")
    return {
        "site_id": site_id or None,
        "address": form.get("address", "").strip() or None,
        "lat": lat,
        "lon": lon,
    }


def create_inspection(files, form) -> dict:
    kind, files = classify_files(files)
    site = parse_site(form)

    inspection_id = _new_id()
    os.makedirs(media_dir(inspection_id))
    saved = []
    for i, f in enumerate(files):
        name = secure_filename(f.filename) or f"file_{i}.{_ext(f.filename)}"
        if name in saved:
            name = f"{i}_{name}"
        f.save(os.path.join(media_dir(inspection_id), name))
        saved.append(name)

    record = {
        "inspection_id": inspection_id,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reporter": form.get("reporter", "").strip() or None,
        "notes": form.get("notes", "").strip() or None,
        "site": site,
        "media": {"kind": kind, "files": saved},
        "status": {stage: "pending" for stage in STAGES},
    }
    record["status"]["upload"] = "done"
    save(record)
    audit(inspection_id, record["reporter"] or "Reporter", "Footage submitted",
          f"{len(saved)} {'video' if kind == 'video' else 'photo(s)'}" + (f" for site {site['site_id']}" if site["site_id"] else ""))
    return record


def save(record: dict) -> None:
    path = os.path.join(inspection_dir(record["inspection_id"]), "inspection.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2)
    for attempt in range(5):            # Windows refuses to replace a file another thread is reading
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.05 * (attempt + 1))
    os.replace(tmp, path)


def load(inspection_id: str) -> dict | None:
    path = os.path.join(inspection_dir(inspection_id), "inspection.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    status = record.setdefault("status", {})
    status.pop("opencv", None)          # stage name used before M2 existed
    for stage in STAGES:
        status.setdefault(stage, "pending")
    record.setdefault("errors", {})
    return record


def update(inspection_id: str, change) -> dict:
    """Load, apply `change(record)` and save, as one locked step."""
    with _write_lock:
        record = load(inspection_id)
        change(record)
        save(record)
        return record


def set_stage(inspection_id: str, stage: str, state: str, error: str | None = None) -> dict:
    def change(record):
        record["status"][stage] = state
        if error:
            record["errors"][stage] = error
        else:
            record["errors"].pop(stage, None)
    return update(inspection_id, change)


def audit(inspection_id: str, actor: str, event: str, detail: str = "") -> None:
    line = json.dumps({"at": now_iso(), "actor": actor, "event": event, "detail": detail})
    with _write_lock, open(os.path.join(inspection_dir(inspection_id), "audit.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def load_audit(inspection_id: str) -> list[dict]:
    path = os.path.join(inspection_dir(inspection_id), "audit.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def stage_dir(inspection_id: str, stage: str) -> str:
    return os.path.join(inspection_dir(inspection_id), stage)


def media_paths(record: dict) -> list[str]:
    return [os.path.join(media_dir(record["inspection_id"]), f) for f in record["media"]["files"]]


def load_result(inspection_id: str, stage: str) -> dict | None:
    path = os.path.join(stage_dir(inspection_id, stage), f"{stage}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_all() -> list[dict]:
    root = _root()
    records = [load(name) for name in os.listdir(root) if os.path.isdir(os.path.join(root, name))]
    return sorted((r for r in records if r), key=lambda r: r["created_at"], reverse=True)
