"""M3 - OpenCV analysis.

Input:  the M2 output (enhanced frames + registration matrices).
Steps:  per-frame detection -> group frames into views of the same scene
        -> per view: warp to reference, optical-flow motion, persistence maps,
           Kalman-tracked drains, per-drain obstruction, risk + confidence
        -> evidence images.
Views:  registered frames form one view (compared over time). Photos that do
        not register to it show a different scene and are analysed one by one,
        so a photo of another street never leaks into this drain's score.
Output: analysis.json + evidence/ images in `out_dir`. Top-level metrics,
        drains, risk and evidence describe the highest-risk view.
"""
import json
import os
import time

import cv2
import numpy as np

from . import detection, evidence, geometry, registration, temporal
from .tracking import DrainTracker

PERSISTENT = 0.6     # seen in >= 60% of aligned frames
TRANSIENT = 0.15


def _bbox_to_reference(bbox, matrix):
    x, y, w, h = bbox
    corners = np.float32([[x, y], [x + w, y], [x, y + h], [x + w, y + h]]).reshape(-1, 1, 2)
    pts = cv2.transform(corners, np.float32(matrix)).reshape(-1, 2)
    x0, y0 = pts.min(axis=0)
    x1, y1 = pts.max(axis=0)
    return [int(x0), int(y0), int(x1 - x0), int(y1 - y0)]


def _regions(mask, pers, moving, area_px, kind):
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    out = []
    for i in range(1, n):
        size = int(stats[i, cv2.CC_STAT_AREA])
        if size < 0.002 * area_px:
            continue
        sel = labels == i
        out.append({
            "type": kind,
            "bbox": [int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                     int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])],
            "coverage_pct": round(100.0 * size / area_px, 2),
            "persistence": round(float(pers[sel].mean()), 2),
            "motion": round(float(moving[sel].mean()), 2),
        })
    return sorted(out, key=lambda r: -r["coverage_pct"])[:8]


def _ring(shape, bbox, margin):
    """Mask of the band `margin` px wide around a box (box itself excluded)."""
    H, W = shape
    x, y, w, h = bbox
    ring = np.zeros((H, W), bool)
    ring[max(0, y - margin):min(H, y + h + margin), max(0, x - margin):min(W, x + w + margin)] = True
    ring[max(0, y):min(H, y + h), max(0, x):min(W, x + w)] = False
    return ring


def _drain_condition(bbox, pers_water, pers_debris):
    """Condition of one drain from what is on it, at its edge, and around it.

    on the grate    debris / water inside the box            -> obstruction
    at the edge     water in a thin band touching the grate  -> water backing up at the inlet
    around it       debris within half a drain-size          -> material that will wash in
                    water within one drain-size              -> pooling nearby
    """
    H, W = pers_water.shape
    x, y, w, h = bbox
    x, y = max(0, x), max(0, y)
    size = max(1.0, float(np.sqrt(w * h)))
    inside = (slice(y, min(H, y + h)), slice(x, min(W, x + w)))
    blocked = (pers_debris[inside] >= 0.5) | (pers_water[inside] >= 0.5)
    obstruction = 100.0 * float(blocked.mean()) if blocked.size else 0.0

    def share(mask, ring):
        return 100.0 * float(mask[ring].mean()) if ring.any() else 0.0

    edge_wet = share(pers_water >= 0.5, _ring((H, W), (x, y, w, h), max(6, int(0.08 * size))))
    debris_around = share(pers_debris >= 0.5, _ring((H, W), (x, y, w, h), int(0.5 * size)))
    water_around = share(pers_water >= 0.5, _ring((H, W), (x, y, w, h), int(size)))

    if obstruction >= 40 or edge_wet >= 30:
        status = "blockage_suspected"          # covered, or water backing up all round the inlet
    elif obstruction >= 15:
        status = "partial_obstruction"         # material lying on the grate
    elif debris_around >= 10:
        status = "debris_at_inlet"             # will wash onto the grate in the next rain
    elif water_around >= 10:
        status = "clear_water_nearby"          # grate clear and edge dry: water pools beside it
    else:
        status = "clear"
    return {"obstruction_pct": round(obstruction, 1), "edge_wet_pct": round(edge_wet, 1),
            "debris_around_pct": round(debris_around, 1), "water_around_pct": round(water_around, 1),
            "status": status}


def _risk_level(score: float) -> str:
    if score >= 70:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def _group_views(frames: list[dict], photos: bool) -> list[list[int]]:
    """Registered frames form one view; for photo sets every unregistered photo is its own view."""
    aligned = [i for i, f in enumerate(frames) if f["alignment"]["ok"]]
    views = [aligned]
    if photos:
        views += [[i] for i, f in enumerate(frames) if not f["alignment"]["ok"]]
    return views


def _analyze_view(frames, images, detections, members, ref_pos):
    """Measure one view. Multi-frame views are compared in the reference frame's coordinates."""
    ref_img = images[ref_pos]
    H, W = ref_img.shape[:2]
    ground_ref = detection.ground_mask((H, W))
    temporal_ok = len(members) >= 2

    if temporal_ok:
        persistence = temporal.Persistence((H, W))
        tracker = DrainTracker(gate_px=0.08 * W)
        prev_gray = prev_valid = None
        for i in members:
            f, det = frames[i], detections[i]
            M = f["alignment"]["matrix"]
            valid = registration.warp(np.full(images[i].shape[:2], 255, np.uint8), M, (W, H), nearest=True) > 0
            water = registration.warp(det["water"].astype(np.uint8), M, (W, H), nearest=True) > 0
            debris = registration.warp(det["debris"].astype(np.uint8), M, (W, H), nearest=True) > 0
            gray = registration.warp(det["gray"], M, (W, H))
            moving = np.zeros((H, W), bool)
            if prev_gray is not None:
                moving = temporal.motion_mask(prev_gray, gray) & valid & prev_valid
            persistence.add(valid, water, debris, moving)
            prev_gray, prev_valid = gray, valid
            tracker.update([{**d, "bbox": _bbox_to_reference(d["bbox"], M)} for d in det["drains"]], f["index"])
        maps = persistence.maps()
        pers_w, pers_d, moving = maps["water"], maps["debris"], maps["moving"]
        area = maps["covered"] & ground_ref
        min_hits = max(2, int(np.ceil(0.3 * len(members))))
        candidates = [(t["bbox"], t["hits"] / len(members), t["score"], t["kind"])
                      for t in tracker.confirmed(min_hits)]
    else:
        # One view only: persistence over time cannot be measured.
        det = detections[ref_pos]
        pers_w = det["water"].astype(np.float32)
        pers_d = det["debris"].astype(np.float32)
        moving = np.zeros((H, W), np.float32)
        area = ground_ref
        candidates = [(d["bbox"], 1.0, d["score"], d["kind"]) for d in det["drains"]]

    area_px = float(area.sum()) or 1.0
    persistent_w = (pers_w >= PERSISTENT) & area
    persistent_d = (pers_d >= PERSISTENT) & area

    drains = []
    for k, (bbox, seen, score, kind) in enumerate(candidates[:5], start=1):
        drains.append({"drain_id": f"D{k}", "kind": kind, "bbox": [int(v) for v in bbox],
                       "seen_in_frames_pct": round(100 * seen), "detector_score": round(score, 3),
                       **_drain_condition(bbox, pers_w, pers_d)})

    water_pct = 100.0 * float(persistent_w.sum()) / area_px
    debris_pct = 100.0 * float(persistent_d.sum()) / area_px
    seen = (pers_w > TRANSIENT) | (pers_d > TRANSIENT)
    if temporal_ok:
        mean_persistence = float(np.maximum(pers_w, pers_d)[seen].mean()) if seen.any() else 0.0
    else:
        mean_persistence = 0.5 if seen.any() else 0.0      # unknown -> neutral
    transient_water = 100.0 * float(((pers_w > TRANSIENT) & (pers_w < PERSISTENT) & area).sum()) / area_px
    max_obstruction = max((d["obstruction_pct"] for d in drains), default=None)
    standing = bool(moving[persistent_w].mean() < 0.2) if (temporal_ok and persistent_w.any()) else None

    water_term = min(water_pct / 25.0, 1.0)
    debris_term = min(debris_pct / 10.0, 1.0)
    obstruction_term = max_obstruction / 100.0 if max_obstruction is not None else 0.5 * water_term
    score = 100.0 * (0.35 * water_term + 0.25 * debris_term + 0.20 * mean_persistence + 0.20 * obstruction_term)

    water_location = geometry.water_drain_relation(persistent_w, drains, max_obstruction, water_pct)

    view_frames = [frames[i] for i in members]
    good_frames = 1.0 - sum(1 for f in view_frames if {"blurry", "low_light"} & set(f["quality"]["issues"])) / len(view_frames)
    confidence = (0.35 * good_frames + 0.30 * (1.0 if temporal_ok else 0.3)
                  + 0.15 * min(len(view_frames) / 10.0, 1.0) + 0.20 * (1.0 if drains else 0.0))

    result = {
        "frames": [frames[i]["index"] for i in members],
        "reference_index": frames[ref_pos]["index"],
        "temporal_analysis": temporal_ok,
        "metrics": {
            "persistent_water_pct": round(water_pct, 2),
            "transient_water_pct": round(transient_water, 2),
            "persistent_debris_pct": round(debris_pct, 2),
            "mean_persistence": round(mean_persistence, 2),
            "max_drain_obstruction_pct": max_obstruction,
            "standing_water": standing,
        },
        "drains": drains,
        "water_location": water_location,
        "findings": (_regions(persistent_w, pers_w, moving, area_px, "water")
                     + _regions(persistent_d, pers_d, moving, area_px, "debris")),
        "risk": {"score": round(score, 1), "level": _risk_level(score), "confidence": round(confidence, 2),
                 "components": {"water": round(35 * water_term, 1), "debris": round(25 * debris_term, 1),
                                "persistence": round(20 * mean_persistence, 1),
                                "obstruction": round(20 * obstruction_term, 1)}},
    }
    return result, (ref_img, pers_w, pers_d, persistent_w)


def run(pre_dir: str, out_dir: str, progress=None) -> dict:
    def report(message, fraction):
        if progress:
            progress(message, fraction)

    t0 = time.perf_counter()
    with open(os.path.join(pre_dir, "preprocess.json"), encoding="utf-8") as fh:
        pre = json.load(fh)
    frames = pre["frames"]
    photos = pre["source"]["kind"] == "images"
    ref_index = pre["summary"]["reference_index"]

    # 1. Detect in every frame ---------------------------------------------
    images, detections, per_frame = [], [], []
    for n, f in enumerate(frames):
        report(f"Detecting drain, water and debris in frame {n + 1} of {len(frames)}", 0.05 + 0.65 * n / len(frames))
        img = cv2.imread(os.path.join(pre_dir, f["enhanced"]))
        det = detection.detect(img)
        images.append(img)
        detections.append(det)
        ground_px = float(det["ground"].sum()) or 1.0
        per_frame.append({"index": f["index"], "t": f["t"], "aligned": f["alignment"]["ok"],
                          "source_file": f.get("source_file"),
                          "water_pct": round(100.0 * float(det["water"].sum()) / ground_px, 2),
                          "debris_pct": round(100.0 * float(det["debris"].sum()) / ground_px, 2),
                          "drains": len(det["drains"])})

    # 2. Analyse each view -------------------------------------------------
    report("Comparing frames over time", 0.75)
    views, arrays = [], []
    for members in _group_views(frames, photos):
        ref_pos = next((i for i in members if frames[i]["index"] == ref_index), members[0])
        view, arr = _analyze_view(frames, images, detections, members, ref_pos)
        names = [frames[i].get("source_file") for i in members]
        if len(members) == 1:
            view["label"] = names[0] or f"Frame {frames[members[0]]['index']}"
        else:
            view["label"] = f"{len(members)} aligned {'photos' if photos else 'frames'}"
        view["view_id"] = len(views) + 1
        views.append(view)
        arrays.append(arr)
    primary = max(range(len(views)), key=lambda k: views[k]["risk"]["score"])

    # 3. Evidence ------------------------------------------------------------
    report("Drawing evidence images", 0.9)
    ev_dir = os.path.join(out_dir, "evidence")
    os.makedirs(ev_dir, exist_ok=True)
    blurred = 0
    pos_of = {f["index"]: i for i, f in enumerate(frames)}
    for view, (ref_img, pers_w, pers_d, persistent_w) in zip(views, arrays):
        prefix = f"v{view['view_id']}_"
        members = [pos_of[idx] for idx in view["frames"]]
        picks = evidence.select_frames([per_frame[i] for i in members],
                                       [frames[i]["quality"]["sharpness"] for i in members])
        ev = {"frames": []}
        for p in picks:
            i = members[p]
            f, det, r = frames[i], detections[i], per_frame[i]
            name = f"{prefix}frame_{f['index']:05d}.jpg"
            caption = (f"t={f['t']}s  water {r['water_pct']}%  debris {r['debris_pct']}%" if not photos
                       else f"{f.get('source_file') or 'photo'}  water {r['water_pct']}%  debris {r['debris_pct']}%")
            blurred += evidence.save(os.path.join(ev_dir, name),
                                     evidence.annotate(images[i], det["water"], det["debris"], det["drains"], caption))
            ev["frames"].append({"index": f["index"], "t": f["t"], "path": f"evidence/{name}"})
        if view["temporal_analysis"]:
            blurred += evidence.save(os.path.join(ev_dir, f"{prefix}heatmap.jpg"),
                                     evidence.heatmap(ref_img, pers_w, pers_d, view["drains"]))
            ev["heatmap"] = f"evidence/{prefix}heatmap.jpg"
        if "line" in view["water_location"]:
            blurred += evidence.save(os.path.join(ev_dir, f"{prefix}water_location.jpg"),
                                     geometry.draw_relation(ref_img, persistent_w, view["drains"], view["water_location"]))
            ev["water_location"] = f"evidence/{prefix}water_location.jpg"
        blurred += evidence.save(os.path.join(ev_dir, f"{prefix}reference.jpg"), ref_img)
        ev["reference"] = f"evidence/{prefix}reference.jpg"
        view["evidence"] = ev

    cv2.imwrite(os.path.join(ev_dir, "timeline.png"), evidence.timeline(per_frame))

    top = views[primary]
    result = {
        "opencv_version": cv2.__version__,
        "frames_analyzed": len(frames),
        "scene": {"consistent": len(views) == 1, "views": len(views), "primary_view": top["view_id"]},
        "views": views,
        # Headline result = the highest-risk view.
        "reference_index": top["reference_index"],
        "frames_registered": len(top["frames"]) if top["temporal_analysis"] else 1,
        "temporal_analysis": top["temporal_analysis"],
        "metrics": top["metrics"],
        "drains": top["drains"],
        "water_location": top["water_location"],
        "findings": top["findings"],
        "risk": top["risk"],
        "per_frame": per_frame,
        "evidence": {**top["evidence"], "timeline": "evidence/timeline.png", "privacy_regions_blurred": blurred},
        "timings_s": {"total": round(time.perf_counter() - t0, 2)},
    }
    with open(os.path.join(out_dir, "analysis.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    report("Analysis complete", 1.0)
    return result
