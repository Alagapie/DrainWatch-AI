"""M5 - Inspection agent (Amazon Nova Pro tool use on Bedrock).

Perception -> decision -> action. The agent starts from the OpenCV measurements
and the severity check, calls OpenCV and information tools where the evidence
is weak or context is missing, and finishes with a prioritised recommendation
that a supervisor must approve. Every step is recorded in a trace.
"""
import json
import os
import re
import time

from . import bedrock, tools

MAX_TURNS = 12

SYSTEM = """You are DrainWatch, an agent that prioritises drainage work for a city maintenance team.
You receive OpenCV 5 measurements of uploaded street footage and a vision model's severity check.
Investigate with tools, then call submit_recommendation exactly once. A supervisor approves every action.

How to investigate (call tools before deciding; several calls in one turn are fine):
- Always call get_weather and get_site_history.
- Call find_nearby_reports when the inspection has coordinates.
- Call compare_with_previous_inspection when the site has earlier inspections.
- Call inspect_drain_closeup for each drain listed in real_drains (OpenCV zoom: are the grate openings visible?).
  Never for drains the severity check rejected.
- Call reanalyze_frame when frames had quality issues or the cross-check found problems
  (gamma/clahe for dark or low-contrast frames, denoise for noisy ones, sharpen for blurry ones).
- Use what the OpenCV tools return: a covered grate in the close-up supports drain_blockage; growth since the
  previous visit means the problem is getting worse (raise priority); a re-analysis that changes the water or
  debris numbers should change how much you trust OpenCV versus the severity check.

Priority:
- P1: critical severity; or high severity with heavy rain (>= 20 mm) expected; or getting worse since the last visit.
- P2: high severity; or medium severity with a drain blockage and rain expected.
- P3: medium severity.
- P4: low severity or nothing significant.
Raise the priority one step if the problem keeps recurring at this site; lower it one step only if the evidence is weak.

Action:
- create_work_order: the evidence clearly shows a problem a crew can fix. Pick the crew from the probable cause
  (drain_blockage -> drain_cleaning, surface_depression -> road_repair, drain_overloaded -> engineering_review).
- request_more_footage: no real drain is visible and the cause is unclear, or image quality is too poor to judge.
- route_to_supervisor: the evidence conflicts and your tools could not resolve it.
- monitor: low severity; re-check later.
If a nearby report within 30 m describes the same problem, say so (it may be a duplicate).
submit_recommendation runs a policy check on your priority and action. If it refuses, either follow the policy
or, only when the evidence truly justifies it, resubmit with override_reason explaining why.
Never invent tool results. Cite the numbers you used in reasoning and list them in evidence_used."""


def _brief(ctx: tools.AgentContext) -> str:
    rec, pre, ana, vlm = ctx.record, ctx.pre, ctx.ana, ctx.vlm or {}
    a = vlm.get("assessment", {})
    frames = [{"index": f["index"], "t": f["t"], "issues": f["quality"]["issues"], "keyframe": f["keyframe"]}
              for f in pre["frames"]][:30]
    payload = {
        "inspection": {"id": rec["inspection_id"], "submitted": rec["created_at"], "site": rec["site"],
                       "reporter_note": rec.get("notes"), "media": rec["media"]["kind"]},
        "preprocessing": {"frames_kept": pre["summary"]["kept"], "camera": pre["summary"]["camera_motion"],
                          "quality_issues": pre["summary"]["issue_counts"], "frames": frames},
        "opencv": {"risk": ana["risk"], "metrics": ana["metrics"], "time_comparison": ana["temporal_analysis"],
                   "drains": [{k: d.get(k) for k in ("drain_id", "kind", "obstruction_pct", "edge_wet_pct",
                                                     "debris_around_pct", "water_around_pct", "status")}
                              for d in ana["drains"]],
                   "water_location": {k: v for k, v in (ana.get("water_location") or {}).items() if k != "line"},
                   "scene_consistent": (ana.get("scene") or {}).get("consistent", True)},
        "severity_check": {k: a.get(k) for k in ("severity", "severity_score", "confidence", "scene_description",
                                                 "drain_condition", "water_extent", "water_type", "debris_types",
                                                 "hazards", "probable_cause", "recommended_crew", "surface_damage",
                                                 "opencv_drain_is_real", "reasoning")},
        "cross_check_issues": (vlm.get("checks") or {}).get("issues", []),
    }
    payload["real_drains"] = [d["drain_id"] for d in ctx.real_drains()]
    return ("Here is the inspection. Investigate with your tools, then submit your recommendation.\n"
            "submit_recommendation will refuse until the required checks have been run.\n\n"
            + json.dumps(payload, indent=1, default=str))


def _short(result: dict) -> dict:
    """Trim tool results stored in the trace (full results go to the model)."""
    return {k: v for k, v in result.items() if k not in ("daily_rain_mm",)}


def run(inspection_id: str, region: str, model_id: str, progress=None) -> dict:
    def report(message, fraction):
        if progress:
            progress(message, fraction)

    t0 = time.perf_counter()
    ctx = tools.AgentContext(inspection_id)
    if ctx.vlm is None:
        raise RuntimeError("The severity check has not run, so the agent has nothing to work from.")

    messages = [{"role": "user", "content": [{"text": _brief(ctx)}]}]
    trace, usage = [], {"inputTokens": 0, "outputTokens": 0}
    nudges = 0
    for turn in range(MAX_TURNS):
        report(f"Agent thinking (step {turn + 1})", min(0.1 + 0.08 * turn, 0.9))
        resp = bedrock.converse_messages(region, model_id, SYSTEM, messages, tools.tool_config(), max_tokens=1500)
        for k in usage:
            usage[k] += resp.get("usage", {}).get(k, 0)
        msg = resp["output"]["message"]
        messages.append(msg)

        uses = []
        for block in msg["content"]:
            text = re.sub(r"</?thinking>", "", block.get("text", "")).strip()
            if text:
                trace.append({"type": "thought", "text": text})
            if "toolUse" in block:
                uses.append(block["toolUse"])

        if not uses:
            if ctx.recommendation or nudges >= 2:
                break
            nudges += 1                         # model stopped without submitting: tell it exactly what is left
            missing = [t for t in ctx.required_checks() if t not in ctx.called]
            todo = (f"First call: {', '.join(missing)}. Then call submit_recommendation."
                    if missing else "Now call submit_recommendation with your decision.")
            trace.append({"type": "thought", "text": f"(DrainWatch reminded the agent: {todo})"})
            messages.append({"role": "user", "content": [{"text": f"You have not submitted yet. {todo}"}]})
            continue

        results = []
        for u in uses:
            report(f"Agent is using {u['name'].replace('_', ' ')}", min(0.15 + 0.08 * turn, 0.92))
            started = time.perf_counter()
            out = tools.call(ctx, u["name"], u.get("input") or {})
            trace.append({"type": "tool", "tool": u["name"], "kind": tools.KIND.get(u["name"], "data"),
                          "input": u.get("input") or {}, "output": _short(out),
                          "seconds": round(time.perf_counter() - started, 2)})
            results.append({"toolResult": {"toolUseId": u["toolUseId"],
                                           "content": [{"text": json.dumps(out, default=str)}],
                                           "status": "error" if "error" in out else "success"}})
        messages.append({"role": "user", "content": results})
        if ctx.recommendation:
            break

    if ctx.recommendation is None:
        with open(os.path.join(ctx.out_dir, "agent_failed.json"), "w", encoding="utf-8") as fh:
            json.dump({"trace": trace, "usage": usage, "last_messages": messages[-3:]}, fh, indent=2, default=str)
        steps = ", ".join(t["tool"] for t in trace if t["type"] == "tool") or "no tools"
        raise RuntimeError(f"The agent stopped without submitting a recommendation (it used: {steps}). "
                           "Click Try again; details are saved in agent/agent_failed.json.")

    result = {
        "model_id": model_id,
        "recommendation": ctx.recommendation,
        "trace": trace,
        "tools_used": [t["tool"] for t in trace if t["type"] == "tool"],
        "usage": usage,
        "timings_s": {"total": round(time.perf_counter() - t0, 2)},
    }
    with open(os.path.join(ctx.out_dir, "agent.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2, default=str)
    report("Recommendation ready for review", 1.0)
    return result
