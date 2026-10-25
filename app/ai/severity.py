"""M4 - Severity check with a vision-language model (Amazon Nova Pro on Bedrock).

The model receives the clean reference image, the OpenCV-annotated evidence and
OpenCV's measurements. It rates severity, describes what it sees, and says where
it disagrees with OpenCV (e.g. floodwater OpenCV under-measured). It does not
create detections; OpenCV's numbers stay the measured evidence.
"""
import json
import os
import time

import cv2

from . import bedrock

SEVERITIES = ["low", "medium", "high", "critical"]
CAUSES = ["drain_blockage", "surface_depression", "drain_overloaded", "unclear"]
CREWS = ["drain_cleaning", "road_repair", "engineering_review", "none"]
MAX_IMAGES = 6

SYSTEM = """You are a drainage inspection assistant for a city maintenance team.
You review street-level images of drains together with measurements made by an OpenCV pipeline.
Be factual and cautious: describe only what is visible, never invent details, and say when you are unsure.
You do not dispatch anyone; a human supervisor reviews your assessment."""

PROMPT = """## Task
Assess how serious the drainage problem is in these images.

## Images (in order)
{legend}

Overlay colours in annotated images: BLUE = OpenCV water mask, RED = OpenCV debris mask, GREEN box = OpenCV drain detection.
OpenCV uses simple rules: it can miss rippled or muddy floodwater, mistake shadows or wet asphalt for water, and under-measure debris lying on a grate. Check its masks against what you actually see.

## OpenCV measurements
{measurements}

## Reporter's note
{notes}

## Severity scale (severity_score must fall in the band of the chosen severity)
- low (0-24): drain clear or only minor litter; no meaningful standing water
- medium (25-49): partial blockage or a moderate puddle; schedule a check
- high (50-74): drain clearly blocked or a large area of standing water; act soon
- critical (75-100): road or property flooding, or water blocking traffic/pedestrians; act now
Rule: if a vehicle is stuck or partly submerged, a road or path is impassable, or water is entering
buildings, the severity MUST be critical. Take the reporter's note into account (e.g. "road blocked"),
but rely on the images when they clearly contradict it.

## Is OpenCV's drain real?
First check every GREEN box: is it really a drain (grate, gully or kerb inlet)? OpenCV sometimes boxes
car grilles, windows, fences or shadows. Answer opencv_drain_is_real:
"yes" (at least one green box is a real drain), "no" (none of them are), "unsure", or "no_detection" (no green box).
drain_visible / drain_condition describe a real drain that YOU can see. If no real drain is visible,
set drain_visible to false and drain_condition to "not_visible", even if OpenCV drew a box.

## Probable cause (decides which crew is sent)
- drain_blockage: water backs up around the drain inlet, or debris/silt covers the grate -> drain cleaning
- surface_depression: water collects in a dip, pothole, sunken or broken paving, away from or beside a drain that looks clear -> road repair
- drain_overloaded: widespread flooding while drains look clear (heavy rain beyond capacity) -> engineering review
- unclear: the images do not show enough to tell
OpenCV's "water_location" measures where the water sits relative to the drain it detected
(e.g. cause_hint "surface_depression" when the grate edge is dry and the puddle lies beside it).
It is only valid if OpenCV's green drain box really is a drain; check that first, and ignore the hint if it is not.
Water covering a wide area (a road, car park or junction) is flooding: choose drain_overloaded unless a
blocked drain is clearly visible, even if one spot looks like a dip.
Look for surface damage yourself: potholes, cracks, sunken or missing paving, worn asphalt.

## Answer
Return ONLY one JSON object, no other text:
{{
  "scene_description": "1-2 sentences of what the images show",
  "opencv_drain_is_real": "yes" | "no" | "unsure" | "no_detection",
  "drain_visible": true | false,
  "drain_condition": "clear" | "partially_blocked" | "blocked" | "not_visible",
  "water_present": true | false,
  "water_extent": "none" | "small" | "moderate" | "large" | "flooding",
  "water_type": "none" | "puddle" | "standing" | "flowing" | "flood",
  "debris_present": true | false,
  "debris_types": ["leaves", "plastic", "silt", ...],
  "debris_on_drain": true | false,
  "hazards": ["short phrases, e.g. 'water across the carriageway'"],
  "probable_cause": "drain_blockage" | "surface_depression" | "drain_overloaded" | "unclear",
  "surface_damage": true | false,
  "surface_damage_description": "what damage is visible, or empty string",
  "recommended_crew": "drain_cleaning" | "road_repair" | "engineering_review" | "none",
  "cause_reasoning": "1-2 sentences: why this cause, citing the images and OpenCV's water_location",
  "severity": "low" | "medium" | "high" | "critical",
  "severity_score": 0-100,
  "confidence": 0.0-1.0,
  "agrees_with_opencv": true only if OpenCV's water/debris masks and drain boxes match what you see, else false,
  "opencv_corrections": ["specific places where the OpenCV masks, boxes or numbers look wrong"],
  "reasoning": "2-4 sentences explaining the severity, citing what you see and the measurements"
}}"""


def _pick_images(analysis_dir: str, ana: dict) -> list[tuple[str, str]]:
    """Clean reference + annotated evidence, primary view first, capped at MAX_IMAGES."""
    views = ana.get("views") or [{"label": "", "evidence": ana["evidence"], "risk": ana["risk"],
                                  "view_id": 1, "temporal_analysis": ana.get("temporal_analysis")}]
    primary = (ana.get("scene") or {}).get("primary_view", 1)
    views = sorted(views, key=lambda v: (v["view_id"] != primary, -v["risk"]["score"]))
    multi = len(views) > 1

    picks = []
    for v in views:
        ev, name = v["evidence"], (f" of {v['label']}" if multi else "")
        if ev.get("reference"):
            picks.append((ev["reference"], f"Original photo{name} (no overlay)"))
        if ev.get("heatmap"):
            picks.append((ev["heatmap"], f"OpenCV persistence heatmap{name} (red = present in most frames)"))
        if ev.get("water_location") and not multi:
            picks.append((ev["water_location"], "OpenCV water-vs-drain geometry (yellow arrow = nearest gap)"))
        for f in ev.get("frames", [])[: (1 if multi else 2)]:
            picks.append((f["path"], f"OpenCV-annotated frame{name}" + (f" at t={f['t']}s" if not multi and v.get("temporal_analysis") else "")))
    seen, out = set(), []
    for rel, label in picks:
        path = os.path.join(analysis_dir, rel)
        if rel not in seen and os.path.exists(path):
            seen.add(rel)
            out.append((path, label))
    return out[:MAX_IMAGES]


def _drain_closeups(analysis_dir: str, ana: dict, out_dir: str, max_drains: int = 2) -> list[tuple[str, str]]:
    """OpenCV crops of each detected drain box (with context), so the model can verify it is a drain."""
    ref_rel = (ana.get("evidence") or {}).get("reference")
    img = cv2.imread(os.path.join(analysis_dir, ref_rel)) if ref_rel else None
    if img is None:
        return []
    H, W = img.shape[:2]
    crops_dir = os.path.join(out_dir, "crops")
    os.makedirs(crops_dir, exist_ok=True)
    out = []
    for d in ana["drains"][:max_drains]:
        x, y, w, h = d["bbox"]
        m = int(0.6 * max(w, h))
        x0, y0, x1, y1 = max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m)
        crop = img[y0:y1, x0:x1].copy()
        cv2.rectangle(crop, (x - x0, y - y0), (x - x0 + w, y - y0 + h), (60, 210, 60), 2, cv2.LINE_AA)
        scale = 480 / max(crop.shape[:2])
        if scale > 1:
            crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        path = os.path.join(crops_dir, f"{d['drain_id']}.jpg")
        cv2.imwrite(path, crop, [cv2.IMWRITE_JPEG_QUALITY, 88])
        out.append((path, f"Close-up of OpenCV drain box {d['drain_id']} (green): is this really a drain?"))
    return out


def _measurements(ana: dict) -> str:
    keep = {
        "headline_view": next((v["label"] for v in ana.get("views", []) if v["view_id"] == ana.get("scene", {}).get("primary_view")), None),
        "time_comparison": ana.get("temporal_analysis"),
        "metrics": ana["metrics"],
        "drains": [{k: d.get(k) for k in ("drain_id", "kind", "obstruction_pct", "edge_wet_pct",
                                          "debris_around_pct", "water_around_pct", "status")} for d in ana["drains"]],
        "water_location": {k: v for k, v in (ana.get("water_location") or {}).items() if k != "line"},
        "opencv_risk": ana["risk"],
    }
    if ana.get("scene") and not ana["scene"]["consistent"]:
        keep["note"] = "The photos show different places; each was analysed separately."
        keep["views"] = [{"label": v["label"], "risk": v["risk"]["score"],
                          "water_pct": v["metrics"]["persistent_water_pct"],
                          "debris_pct": v["metrics"]["persistent_debris_pct"]} for v in ana["views"]]
    return json.dumps(keep, indent=1)


def _validate(raw: dict) -> dict:
    def pick(key, options, default):
        val = str(raw.get(key, default)).lower()
        return val if val in options else default

    try:
        score = float(raw.get("severity_score", 0))
    except (TypeError, ValueError):
        score = 0.0
    try:
        conf = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    score = max(0.0, min(100.0, score))
    severity = pick("severity", SEVERITIES, SEVERITIES[min(int(score // 25), 3)])
    low, high = {"low": (0, 24), "medium": (25, 49), "high": (50, 74), "critical": (75, 100)}[severity]
    score = max(low, min(high, score))                     # keep score inside the label's band
    drain_condition = pick("drain_condition", ["clear", "partially_blocked", "blocked", "not_visible"], "not_visible")
    as_list = lambda v: [str(x) for x in v] if isinstance(v, list) else ([str(v)] if v else [])  # noqa: E731
    return {
        "scene_description": str(raw.get("scene_description", "")),
        "opencv_drain_is_real": pick("opencv_drain_is_real", ["yes", "no", "unsure", "no_detection"], "unsure"),
        "drain_visible": bool(raw.get("drain_visible", False)) and drain_condition != "not_visible",
        "drain_condition": drain_condition,
        "water_present": bool(raw.get("water_present", False)),
        "water_extent": pick("water_extent", ["none", "small", "moderate", "large", "flooding"], "none"),
        "water_type": pick("water_type", ["none", "puddle", "standing", "flowing", "flood"], "none"),
        "debris_present": bool(raw.get("debris_present", False)),
        "debris_types": as_list(raw.get("debris_types")),
        "debris_on_drain": bool(raw.get("debris_on_drain", False)) and drain_condition != "not_visible",
        "hazards": as_list(raw.get("hazards")),
        "probable_cause": pick("probable_cause", CAUSES, "unclear"),
        "surface_damage": bool(raw.get("surface_damage", False)),
        "surface_damage_description": str(raw.get("surface_damage_description", "") or ""),
        "recommended_crew": pick("recommended_crew", CREWS, "none"),
        "cause_reasoning": str(raw.get("cause_reasoning", "")),
        "severity": severity,
        "severity_score": round(float(score), 1),
        "confidence": round(max(0.0, min(1.0, conf)), 2),
        "agrees_with_opencv": bool(raw.get("agrees_with_opencv", True)),
        "opencv_corrections": as_list(raw.get("opencv_corrections")),
        "reasoning": str(raw.get("reasoning", "")),
    }


def _cross_checks(a: dict, ana: dict) -> dict:
    """DrainWatch's own consistency checks between the model and OpenCV (not left to the model)."""
    cv_water = ana["metrics"]["persistent_water_pct"]
    band_gap = abs(SEVERITIES.index(a["severity"]) - SEVERITIES.index(ana["risk"]["level"]))
    has_drain_box = bool(ana["drains"])
    issues = []
    drain_false = has_drain_box and a["opencv_drain_is_real"] == "no"
    if drain_false:
        issues.append("OpenCV's drain detection is wrong here: the model sees no drain in the green box(es).")
    water_under = a["water_extent"] in ("large", "flooding") and cv_water < 15
    if water_under:
        issues.append(f"OpenCV under-measured the water: it found {cv_water}% of the ground, "
                      f"the model sees {a['water_extent']} water.")
    water_over = a["water_extent"] in ("none", "small") and cv_water >= 15
    if water_over:
        issues.append(f"OpenCV may have over-measured the water ({cv_water}% of the ground).")
    if band_gap >= 2:
        issues.append(f"Severity differs by {band_gap} bands ({ana['risk']['level']} vs {a['severity']}).")
    return {
        "opencv_drain_false_positive": drain_false,
        "opencv_water_underestimated": water_under,
        "opencv_water_overestimated": water_over,
        "band_gap": band_gap,
        "opencv_reliable": a["agrees_with_opencv"] and not issues,
        "issues": issues,
    }


def run(analysis_dir: str, out_dir: str, notes: str | None, region: str, model_id: str, progress=None) -> dict:
    def report(message, fraction):
        if progress:
            progress(message, fraction)

    t0 = time.perf_counter()
    with open(os.path.join(analysis_dir, "analysis.json"), encoding="utf-8") as fh:
        ana = json.load(fh)

    report("Preparing evidence for the vision model", 0.1)
    images = _pick_images(analysis_dir, ana) + _drain_closeups(analysis_dir, ana, out_dir)
    legend = "\n".join(f"{i + 1}. {label}" for i, (_, label) in enumerate(images))
    prompt = PROMPT.format(legend=legend, measurements=_measurements(ana), notes=notes or "(none)")
    content = [{"text": prompt}] + [bedrock.image_block(p) for p, _ in images]

    report(f"Asking {model_id} to rate severity", 0.3)
    resp = bedrock.converse(region, model_id, SYSTEM, content, temperature=0.0)
    report("Reading the model's answer", 0.9)
    assessment = _validate(bedrock.parse_json(resp["text"]))

    opencv_score = ana["risk"]["score"]
    checks = _cross_checks(assessment, ana)
    result = {
        "checks": checks,
        "model_id": model_id,
        "region": region,
        "assessment": assessment,
        "opencv": {"score": opencv_score, "level": ana["risk"]["level"]},
        "difference": round(assessment["severity_score"] - opencv_score, 1),
        "same_band": assessment["severity"] == ana["risk"]["level"],
        "opencv_cause_hint": (ana.get("water_location") or {}).get("cause_hint"),
        "images_sent": [{"path": os.path.relpath(p, os.path.dirname(analysis_dir)).replace("\\", "/"), "label": lbl}
                        for p, lbl in images],
        "usage": resp["usage"],
        "latency_ms": resp["latency_ms"],
        "raw_text": resp["text"],
        "timings_s": {"total": round(time.perf_counter() - t0, 2),
                      "model": round((resp["latency_ms"] or 0) / 1000, 2)},
    }
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "vlm.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    report("Severity check complete", 1.0)
    return result
