"""Tools the M5 agent can call.

OpenCV tools let the agent look again at the evidence (re-enhance a frame, zoom
into a drain, register against the previous visit). Information tools give it
context (site history, nearby reports, rainfall). submit_recommendation ends
the run; every recommendation waits for a human decision.
"""
import json
import math
import os
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

import cv2
import numpy as np

from ..inspections import storage
from ..vision import detection, evidence, quality, registration

ACTIONS = ["create_work_order", "request_more_footage", "route_to_supervisor", "monitor"]
CREWS = ["drain_cleaning", "road_repair", "engineering_review", "none"]
PRIORITIES = ["P1", "P2", "P3", "P4"]
RESPONSE_TIME = {"P1": "within 24 hours", "P2": "within 3 days", "P3": "within 2 weeks", "P4": "next routine round"}


class AgentContext:
    def __init__(self, inspection_id: str):
        self.inspection_id = inspection_id
        self.record = storage.load(inspection_id)
        self.dir = storage.inspection_dir(inspection_id)
        self.pre = storage.load_result(inspection_id, "preprocess")
        self.ana = storage.load_result(inspection_id, "analysis")
        self.vlm = storage.load_result(inspection_id, "vlm")
        self.out_dir = storage.stage_dir(inspection_id, "agent")
        os.makedirs(self.out_dir, exist_ok=True)
        self.recommendation: dict | None = None
        self.called: dict[str, dict] = {}      # tool name -> last successful result
        self.attempted: set[str] = set()       # tools tried, even if the data was unavailable

    def real_drains(self) -> list[dict]:
        if (self.vlm or {}).get("checks", {}).get("opencv_drain_false_positive"):
            return []
        return self.ana["drains"]

    def required_checks(self) -> list[str]:
        """Checks the agent must run before it may submit (the investigation policy)."""
        site = self.record["site"]
        has_coords = site.get("lat") is not None and site.get("lon") is not None
        needed = ["get_site_history"] + (["get_weather"] if has_coords else [])
        history = self.called.get("get_site_history", {})
        if history.get("earlier_inspections", 0) > 0:
            needed.append("compare_with_previous_inspection")
        if self.real_drains():
            needed.append("inspect_drain_closeup")
        quality_issues = set(self.pre["summary"]["issue_counts"]) & {"low_light", "blurry", "noisy"}
        if quality_issues or (self.vlm or {}).get("checks", {}).get("issues"):
            needed.append("reanalyze_frame")
        return needed

    def policy(self) -> dict:
        """The priority/action the evidence implies, computed by DrainWatch (not the model)."""
        a = (self.vlm or {}).get("assessment", {})
        severity = a.get("severity", "low")
        level = {"critical": 1, "high": 2, "medium": 3, "low": 4}[severity]
        reasons = [f"the severity is {severity}"]
        if self.called.get("get_site_history", {}).get("earlier_inspections", 0) > 0 and severity != "low":
            level -= 1
            reasons.append("it keeps happening at this site (one level more urgent)")
        if self.called.get("get_weather", {}).get("heavy_rain_expected") and severity in ("high", "medium"):
            level -= 1
            reasons.append("heavy rain is forecast (one level more urgent)")
        if self.called.get("compare_with_previous_inspection", {}).get("trend") == "worse":
            level -= 1
            reasons.append("it is worse than last time (one level more urgent)")
        level = max(1, min(4, level))
        if severity == "low" and level == 4:
            actions = ["monitor"]
        elif not a.get("drain_visible") and a.get("probable_cause") == "unclear" and severity in ("low", "medium"):
            actions = ["request_more_footage", "route_to_supervisor"]
        else:
            actions = ["create_work_order", "route_to_supervisor"]
        return {"priority": f"P{level}", "allowed_actions": actions, "reasons": reasons}

    def out(self, name: str) -> tuple[str, str]:
        """(absolute path, path relative to the inspection folder) for an agent output image."""
        return os.path.join(self.out_dir, name), f"agent/{name}"


# ---------------------------------------------------------------- helpers
def _distance_m(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(a))


def _summary(record: dict) -> dict:
    """Short description of another inspection for history / nearby results."""
    iid = record["inspection_id"]
    vlm = storage.load_result(iid, "vlm") or {}
    agent = storage.load_result(iid, "agent") or {}
    a = vlm.get("assessment", {})
    rec = agent.get("recommendation", {})
    return {"inspection_id": iid, "date": record["created_at"][:10], "site_id": record["site"].get("site_id"),
            "severity": a.get("severity"), "severity_score": a.get("severity_score"),
            "probable_cause": a.get("probable_cause"), "priority": rec.get("priority"),
            "action": rec.get("action"), "review": (record.get("review") or {}).get("decision")}


def _same_site(ctx: AgentContext, other: dict, radius_m: float = 30.0) -> bool:
    site, osite = ctx.record["site"], other["site"]
    if site.get("site_id") and osite.get("site_id"):
        return site["site_id"].strip().lower() == osite["site_id"].strip().lower()
    if None not in (site.get("lat"), site.get("lon"), osite.get("lat"), osite.get("lon")):
        return _distance_m(site["lat"], site["lon"], osite["lat"], osite["lon"]) <= radius_m
    return False


def _earlier_inspections(ctx: AgentContext) -> list[dict]:
    return [r for r in storage.list_all()
            if r["inspection_id"] != ctx.inspection_id and r["created_at"] < ctx.record["created_at"]]


def _primary_reference(ana: dict, base_dir: str) -> str | None:
    rel = (ana.get("evidence") or {}).get("reference")
    path = os.path.join(base_dir, "analysis", rel) if rel else None
    return path if path and os.path.exists(path) else None


def _coverage(det: dict) -> tuple[float, float]:
    ground = float(det["ground"].sum()) or 1.0
    return (round(100 * float(det["water"].sum()) / ground, 2), round(100 * float(det["debris"].sum()) / ground, 2))


# ---------------------------------------------------------------- OpenCV tools
def reanalyze_frame(ctx: AgentContext, frame_index: int, enhancements: list[str] | None = None) -> dict:
    frame = next((f for f in ctx.pre["frames"] if f["index"] == int(frame_index)), None)
    if frame is None:
        return {"error": f"frame {frame_index} not found", "available_frames": [f["index"] for f in ctx.pre["frames"]][:40]}
    raw = cv2.imread(os.path.join(ctx.dir, "preprocess", frame["raw"]))
    steps = [e for e in (enhancements or []) if e in quality.ENHANCERS]
    img = quality.enhance(raw, steps)
    det = detection.detect(img)
    water, debris = _coverage(det)
    before = next((r for r in ctx.ana["per_frame"] if r["index"] == frame["index"]), {})
    path, rel = ctx.out(f"reanalyzed_{frame['index']:05d}.jpg")
    evidence.save(path, evidence.annotate(img, det["water"], det["debris"], det["drains"],
                                          f"re-analysis [{' + '.join(steps) or 'no enhancement'}]  water {water}%  debris {debris}%"))
    return {"frame_index": frame["index"], "enhancements_applied": steps,
            "quality_after": {k: v for k, v in quality.assess(img).items() if k != "usable"},
            "before": {"water_pct": before.get("water_pct"), "debris_pct": before.get("debris_pct"), "drains": before.get("drains")},
            "after": {"water_pct": water, "debris_pct": debris, "drains": len(det["drains"])},
            "image": rel}


def inspect_drain_closeup(ctx: AgentContext, drain_id: str) -> dict:
    drain = next((d for d in ctx.ana["drains"] if d["drain_id"] == drain_id), None)
    if drain is None:
        return {"error": f"unknown drain {drain_id}", "drains": [d["drain_id"] for d in ctx.ana["drains"]]}
    if (ctx.vlm or {}).get("checks", {}).get("opencv_drain_false_positive"):
        return {"drain_id": drain_id, "warning": "The severity check rejected this box: it is not a real drain."}
    ref_path = _primary_reference(ctx.ana, ctx.dir)
    img = cv2.imread(ref_path)
    x, y, w, h = drain["bbox"]
    m = int(0.25 * max(w, h))
    H, W = img.shape[:2]
    x0, y0, x1, y1 = max(0, x - m), max(0, y - m), min(W, x + w + m), min(H, y + h + m)
    crop = quality.clahe(cv2.resize(img[y0:y1, x0:x1], None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC))
    inner = crop[2 * (y - y0):2 * (y - y0 + h), 2 * (x - x0):2 * (x - x0 + w)]
    fm = detection.feature_maps(inner)
    everywhere = np.ones(inner.shape[:2], bool)
    gray = fm["gray"]
    slots = float((gray < 0.6 * np.median(gray)).mean())
    debris = float(detection.debris_mask(fm, everywhere).mean())
    water = float(detection.water_mask(fm, everywhere).mean())
    regular = float(fm["orientation_focus"].mean())
    if slots >= 0.25 and debris < 0.15:
        verdict = "grate openings clearly visible: little or nothing blocking the grate"
    elif slots < 0.12:
        verdict = "grate openings barely visible: the grate is likely covered"
    else:
        verdict = "grate openings partly visible: partial covering"
    path, rel = ctx.out(f"closeup_{drain_id}.jpg")
    evidence.save(path, evidence.annotate(crop, None, None, [], f"{drain_id} close-up (2x, CLAHE): {verdict}"))
    return {"drain_id": drain_id, "kind": drain["kind"], "visible_slot_fraction": round(slots, 2),
            "debris_on_grate_pct": round(100 * debris, 1), "water_on_grate_pct": round(100 * water, 1),
            "bar_pattern_regularity": round(regular, 2), "verdict": verdict, "image": rel}


def compare_with_previous_inspection(ctx: AgentContext) -> dict:
    earlier = [r for r in _earlier_inspections(ctx) if _same_site(ctx, r) and r["status"].get("analysis") == "done"]
    if not earlier:
        return {"previous_inspections": 0, "note": "No earlier inspection of this site to compare with."}
    prev = earlier[0]                                     # list_all is newest first
    prev_ana = storage.load_result(prev["inspection_id"], "analysis")
    result = {"previous": _summary(prev),
              "opencv_then": {"water_pct": prev_ana["metrics"]["persistent_water_pct"],
                              "debris_pct": prev_ana["metrics"]["persistent_debris_pct"], "risk": prev_ana["risk"]["score"]},
              "opencv_now": {"water_pct": ctx.ana["metrics"]["persistent_water_pct"],
                             "debris_pct": ctx.ana["metrics"]["persistent_debris_pct"], "risk": ctx.ana["risk"]["score"]}}
    cur_path = _primary_reference(ctx.ana, ctx.dir)
    prev_path = _primary_reference(prev_ana, storage.inspection_dir(prev["inspection_id"]))
    if not cur_path or not prev_path:
        result["image_comparison"] = "unavailable"
        return result
    cur, old = cv2.imread(cur_path), cv2.imread(prev_path)
    old = cv2.resize(old, (cur.shape[1], cur.shape[0]))
    al = registration.align_to_reference([cur, old], ref_idx=0)[1]
    if not al["ok"]:
        result["image_comparison"] = "photos taken from too different a viewpoint to line up"
        return result
    old_aligned = registration.warp(old, al["matrix"], (cur.shape[1], cur.shape[0]))
    d_now, d_then = detection.detect(cur), detection.detect(old_aligned)
    (w_now, b_now), (w_then, b_then) = _coverage(d_now), _coverage(d_then)
    problem_now, problem_then = d_now["water"] | d_now["debris"], d_then["water"] | d_then["debris"]
    diff = cur.copy()
    evidence.tint(diff, problem_now & ~problem_then, (40, 40, 230))      # new since last visit
    evidence.tint(diff, problem_then & ~problem_now, (60, 200, 60))      # cleared since last visit
    evidence.label(diff, "red = new since last visit, green = cleared", (8, 26))
    evidence.label(old_aligned, f"previous visit {prev['created_at'][:10]}", (8, 26))
    path, rel = ctx.out("change_vs_previous.jpg")
    evidence.save(path, cv2.hconcat([old_aligned, diff]))
    trend = ("worse" if (w_now - w_then) + (b_now - b_then) > 2 else
             "better" if (w_now - w_then) + (b_now - b_then) < -2 else "about the same")
    result.update({"image_comparison": "registered (ORB + RANSAC)",
                   "water_pct_change": round(w_now - w_then, 2), "debris_pct_change": round(b_now - b_then, 2),
                   "trend": trend, "image": rel})
    return result


# ---------------------------------------------------------------- information tools
def get_site_history(ctx: AgentContext) -> dict:
    rows = [_summary(r) for r in _earlier_inspections(ctx) if _same_site(ctx, r)]
    out = {"site_id": ctx.record["site"].get("site_id"), "earlier_inspections": len(rows), "inspections": rows[:10]}
    if rows:
        out["recurring"] = True
        out["policy"] = ("This site has been reported before: the problem is recurring, so raise the priority one step. "
                         "Call compare_with_previous_inspection to measure whether it is getting worse.")
    return out


def find_nearby_reports(ctx: AgentContext, radius_m: float = 300, days: int = 14) -> dict:
    site = ctx.record["site"]
    if site.get("lat") is None or site.get("lon") is None:
        return {"error": "This inspection has no coordinates."}
    since = (datetime.now(timezone.utc) - timedelta(days=int(days))).isoformat()
    out = []
    for r in storage.list_all():
        s = r["site"]
        if r["inspection_id"] == ctx.inspection_id or s.get("lat") is None or r["created_at"] < since:
            continue
        dist = _distance_m(site["lat"], site["lon"], s["lat"], s["lon"])
        if dist <= float(radius_m):
            out.append({**_summary(r), "distance_m": round(dist)})
    out.sort(key=lambda r: r["distance_m"])
    return {"radius_m": radius_m, "days": days, "reports": out[:10],
            "possible_duplicates": [r["inspection_id"] for r in out if r["distance_m"] <= 30]}


def get_weather(ctx: AgentContext) -> dict:
    site = ctx.record["site"]
    if site.get("lat") is None or site.get("lon") is None:
        return {"error": "This inspection has no coordinates, so rainfall cannot be looked up."}
    q = urllib.parse.urlencode({"latitude": site["lat"], "longitude": site["lon"], "daily": "precipitation_sum",
                                "past_days": 3, "forecast_days": 3, "timezone": "auto"})
    try:
        with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=15) as resp:
            data = json.load(resp)
    except Exception as e:
        return {"error": f"Weather service unavailable: {e}"}
    days, rain = data["daily"]["time"], [r or 0.0 for r in data["daily"]["precipitation_sum"]]
    today = len(days) - 3
    return {"source": "Open-Meteo", "daily_rain_mm": dict(zip(days, rain)),
            "past_3_days_mm": round(sum(rain[:today]), 1), "next_3_days_mm": round(sum(rain[today:]), 1),
            "heavy_rain_expected": sum(rain[today:]) >= 20}


# ---------------------------------------------------------------- final action
def submit_recommendation(ctx: AgentContext, priority: str, action: str, crew: str, summary: str,
                          reasoning: str, evidence_used: list[str] | None = None, follow_up: str = "",
                          override_reason: str = "") -> dict:
    errors = []
    if priority not in PRIORITIES:
        errors.append(f"priority must be one of {PRIORITIES}")
    if action not in ACTIONS:
        errors.append(f"action must be one of {ACTIONS}")
    if crew not in CREWS:
        errors.append(f"crew must be one of {CREWS}")
    missing = [t for t in ctx.required_checks() if t not in ctx.attempted]
    if missing:
        errors.append("Investigation incomplete. Before submitting, call: " + ", ".join(missing))
    if errors:
        return {"error": "; ".join(errors)}

    # Policy check: the agent may deviate from what the evidence implies only with a stated reason.
    pol = ctx.policy()
    deviations = []
    if priority != pol["priority"]:
        deviations.append(f"priority {priority} differs from the policy priority {pol['priority']} "
                          f"({'; '.join(pol['reasons'])})")
    if action not in pol["allowed_actions"]:
        deviations.append(f"action {action} does not fit the evidence (expected one of {pol['allowed_actions']})")
    if deviations and not override_reason.strip():
        return {"error": "Policy check failed: " + " and ".join(deviations)
                + ". Resubmit following the policy, or keep your choice and explain it in override_reason."}

    ctx.recommendation = {"priority": priority, "response_time": RESPONSE_TIME[priority], "action": action,
                          "crew": crew if action == "create_work_order" else "none",
                          "summary": summary, "reasoning": reasoning, "evidence_used": evidence_used or [],
                          "follow_up": follow_up, "status": "awaiting_supervisor_approval",
                          "policy": {**pol, "followed": not deviations, "deviations": deviations,
                                     "override_reason": override_reason.strip() if deviations else ""}}
    return {"status": "submitted - waiting for a supervisor to approve, edit or reject"}


# ---------------------------------------------------------------- registry
_SPECS = [
    ("reanalyze_frame", reanalyze_frame,
     "OpenCV: re-run water/debris/drain detection on one frame with chosen enhancements. Use when frames were dark, "
     "blurry or noisy, or when OpenCV and the severity check disagree about water or debris.",
     {"frame_index": {"type": "integer", "description": "a frame index from the frames list"},
      "enhancements": {"type": "array", "items": {"type": "string", "enum": ["gamma", "denoise", "clahe", "sharpen"]}}},
     ["frame_index"]),
    ("inspect_drain_closeup", inspect_drain_closeup,
     "OpenCV: zoom into one detected drain (2x, contrast-enhanced) and measure how much of the grate's openings are "
     "visible and how much debris or water covers it. Use to confirm whether a real drain is blocked.",
     {"drain_id": {"type": "string", "description": "e.g. D1"}}, ["drain_id"]),
    ("compare_with_previous_inspection", compare_with_previous_inspection,
     "OpenCV: line up this site's previous inspection photo with the current one (ORB + RANSAC) and measure whether "
     "water and debris have grown or cleared since then.", {}, []),
    ("get_site_history", get_site_history,
     "Earlier inspections of this drain/site with their severity, cause, priority and review decision.", {}, []),
    ("find_nearby_reports", find_nearby_reports,
     "Other reports near this location: possible duplicates (within 30 m) or a wider problem in the area.",
     {"radius_m": {"type": "number"}, "days": {"type": "integer"}}, []),
    ("get_weather", get_weather,
     "Rainfall at this location for the past 3 days and the forecast for the next 3 days (mm).", {}, []),
    ("submit_recommendation", submit_recommendation,
     "Submit the final recommendation for a supervisor to approve. Call exactly once, at the end.",
     {"priority": {"type": "string", "enum": PRIORITIES},
      "action": {"type": "string", "enum": ACTIONS},
      "crew": {"type": "string", "enum": CREWS},
      "summary": {"type": "string", "description": "one sentence for the work order"},
      "reasoning": {"type": "string", "description": "2-4 sentences citing the evidence and tool results"},
      "evidence_used": {"type": "array", "items": {"type": "string"}},
      "follow_up": {"type": "string", "description": "what should happen next, e.g. re-inspect after the next rain"},
      "override_reason": {"type": "string", "description": "only if you deliberately deviate from the policy check: why"}},
     ["priority", "action", "crew", "summary", "reasoning"]),
]

REGISTRY = {name: fn for name, fn, *_ in _SPECS}
KIND = {"reanalyze_frame": "opencv", "inspect_drain_closeup": "opencv", "compare_with_previous_inspection": "opencv",
        "get_site_history": "data", "find_nearby_reports": "data", "get_weather": "data",
        "submit_recommendation": "action"}


def tool_config() -> dict:
    return {"tools": [{"toolSpec": {"name": name, "description": desc,
                                    "inputSchema": {"json": {"type": "object", "properties": props, "required": req}}}}
                      for name, _, desc, props, req in _SPECS]}


def call(ctx: AgentContext, name: str, args: dict) -> dict:
    fn = REGISTRY.get(name)
    if fn is None:
        return {"error": f"unknown tool {name}"}
    try:
        result = fn(ctx, **(args or {}))
    except TypeError as e:
        result = {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:
        result = {"error": f"{type(e).__name__}: {e}"}
    if not (isinstance(result, dict) and str(result.get("error", "")).startswith("bad arguments")):
        ctx.attempted.add(name)
    if "error" not in result:
        ctx.called[name] = result
    return result
