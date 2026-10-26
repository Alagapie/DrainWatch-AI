"""Turn the agent's tool trace into short, plain-language steps for non-technical readers."""

PLAIN_NAMES = {
    "get_site_history": "this site's history",
    "get_weather": "the rainfall",
    "find_nearby_reports": "nearby reports",
    "compare_with_previous_inspection": "a comparison with the last visit",
    "inspect_drain_closeup": "a close-up of the drain",
    "reanalyze_frame": "a second look at the photo",
    "severity_check": "the severity check",
}
CAUSES = {"drain_blockage": "a blocked drain", "surface_depression": "a dip in the road",
          "drain_overloaded": "more water than the drains can take", "unclear": "an unclear cause"}
ENHANCE = {"gamma": "brightening it", "clahe": "boosting the contrast", "denoise": "removing grain", "sharpen": "sharpening it"}


def _pct_change(before, after) -> str:
    if before is None or after is None:
        return ""
    return f"{before}% → {after}%"


def _history(o):
    n = o.get("earlier_inspections", 0)
    if not n:
        return "Checked this site's history", "This is the first report for this site."
    last = (o.get("inspections") or [{}])[0]
    text = f"This site has been reported {n} time{'s' if n > 1 else ''} before"
    if last.get("date"):
        text += f" (most recently on {last['date']}"
        if last.get("severity"):
            text += f", rated {last['severity']}"
        text += ")"
    return "Checked this site's history", text + ". Because it keeps happening, it gets a higher priority."


def _weather(o):
    if "error" in o:
        return "Checked rainfall", "Rainfall couldn't be checked because no location was given."
    text = (f"{o['past_3_days_mm']} mm of rain fell in the last 3 days and {o['next_3_days_mm']} mm is forecast "
            "for the next 3 days")
    text += ": heavy rain is coming, so this is more urgent." if o.get("heavy_rain_expected") else ": no heavy rain expected."
    return "Checked rainfall", text


def _nearby(o):
    if "error" in o:
        return "Looked for other reports nearby", "Nearby reports couldn't be checked because no location was given."
    reports, dups = o.get("reports", []), o.get("possible_duplicates", [])
    if not reports:
        return "Looked for other reports nearby", f"No other reports within {int(o.get('radius_m', 300))} m."
    radius = int(o.get("radius_m", 300))
    text = f"Found {len(reports)} other report{'s' if len(reports) > 1 else ''} within {radius} m"
    if dups and (radius <= 30 or len(dups) == len(reports)):
        text += ", so this may already have been reported."
    elif dups:
        text += f"; {len(dups)} {'is' if len(dups) == 1 else 'are'} within 30 m, so this may already have been reported."
    else:
        text += "."
    return "Looked for other reports nearby", text


def _compare(o):
    title = "Compared with the last visit"
    if o.get("previous_inspections") == 0 or "previous" not in o:
        return title, o.get("note") or "There is no earlier photo of this site to compare with."
    date = o["previous"].get("date", "an earlier date")
    if o.get("image_comparison") != "registered (ORB + RANSAC)":
        return title, f"There is an earlier photo from {date}, but it was taken from a different angle, so the two couldn't be lined up."
    trend = {"worse": "the problem is getting worse", "better": "the problem is improving",
             "about the same": "the problem hasn't changed"}.get(o.get("trend"), "")
    def change(label, v):
        v = v or 0
        return f"{label} didn't change" if abs(v) < 0.5 else f"{label} {'increased' if v > 0 else 'decreased'} by {abs(v):.1f}%"
    return title, (f"Lined up today's photo with the one from {date}: {change('water', o.get('water_pct_change'))} "
                   f"and {change('debris', o.get('debris_pct_change'))}, so {trend}.")


def _reanalyze(o):
    title = "Took a second look at the photo"
    if "error" in o:
        return title, "The photo could not be re-checked."
    how = " and ".join(ENHANCE.get(e, e) for e in o.get("enhancements_applied", [])) or "no changes"
    b, a = o.get("before", {}), o.get("after", {})
    water = _pct_change(b.get("water_pct"), a.get("water_pct"))
    debris = _pct_change(b.get("debris_pct"), a.get("debris_pct"))
    moved = abs((a.get("water_pct") or 0) - (b.get("water_pct") or 0)) + abs((a.get("debris_pct") or 0) - (b.get("debris_pct") or 0))
    verdict = "The result barely changed, so the first measurement holds." if moved < 3 else "The measurement changed noticeably after improving the image."
    return title, f"Re-checked the image after {how}. Water {water}, debris {debris}. {verdict}"


def _closeup(o):
    title = f"Zoomed in on drain {o.get('drain_id', '')}".strip()
    if o.get("warning"):
        return title, "Skipped: this box turned out not to be a real drain."
    if "error" in o:
        return title, "The drain could not be zoomed into."
    verdict = o.get("verdict", "")
    plain = ("The grate's openings are clearly visible, so the drain itself is not blocked." if "clearly visible" in verdict
             else "The grate's openings are barely visible, so the drain is likely covered." if "barely" in verdict
             else "Part of the grate is covered, so the drain is partly blocked.")
    return title, plain


def _submit(o, inp):
    err = o.get("error", "")
    if not err:
        return "Made the recommendation", "Sent to a supervisor for approval.", "done"
    if err.startswith("Investigation incomplete"):
        todo = [PLAIN_NAMES.get(t.strip(), t.strip()) for t in err.split("call:", 1)[-1].split(",")]
        items = todo[0] if len(todo) == 1 else ", ".join(todo[:-1]) + " and " + todo[-1]
        return ("Asked to check more first",
                f"The agent tried to decide too early. DrainWatch asked it to first check {items}.", "refused")
    if err.startswith("Policy check failed"):
        return ("Asked to reconsider",
                f"The agent suggested {inp.get('priority')}, but DrainWatch's rules point to a different priority "
                "or action for this evidence. It had to correct it or explain why.", "refused")
    return "Asked to fix the recommendation", "The recommendation was incomplete and had to be corrected.", "refused"


_DESCRIBE = {"get_site_history": _history, "get_weather": _weather, "find_nearby_reports": _nearby,
             "compare_with_previous_inspection": _compare, "reanalyze_frame": _reanalyze,
             "inspect_drain_closeup": _closeup}


def steps(trace: list[dict]) -> list[dict]:
    out = []
    for t in trace:
        if t.get("type") != "tool":
            continue
        o, inp = t.get("output") or {}, t.get("input") or {}
        if t["tool"] == "submit_recommendation":
            title, text, state = _submit(o, inp)
        elif t["tool"] in _DESCRIBE:
            title, text = _DESCRIBE[t["tool"]](o)
            state = "image" if t.get("kind") == "opencv" else "info"
        else:
            title, text, state = t["tool"].replace("_", " ").capitalize(), "", "info"
        out.append({"title": title, "text": text, "state": state, "image": o.get("image")})
    return out


def plain_evidence(items: list[str]) -> list[str]:
    """Replace tool names the agent lists as evidence with plain words."""
    return [PLAIN_NAMES.get(i, i).capitalize() for i in items]
