"""M6 - Human in the loop: supervisor decisions, work orders and their completion."""
import uuid
from datetime import datetime, timedelta, timezone

from . import storage

DECISIONS = {
    "approve": "Approved",
    "edit": "Approved with changes",
    "more_footage": "Asked for better footage",
    "reject": "Rejected",
}
PRIORITIES = ["P1", "P2", "P3", "P4"]
ACTIONS = ["create_work_order", "request_more_footage", "route_to_supervisor", "monitor"]
CREWS = ["drain_cleaning", "road_repair", "engineering_review", "none"]
DUE_DAYS = {"P1": 1, "P2": 3, "P3": 14, "P4": 30}
CREW_LABELS = {"drain_cleaning": "drain-cleaning crew", "road_repair": "road-repair crew",
               "engineering_review": "engineering review", "none": "no crew"}


class ReviewError(ValueError):
    pass


def submit(inspection_id: str, form) -> dict:
    record = storage.load(inspection_id)
    agent = storage.load_result(inspection_id, "agent")
    if record["status"].get("agent") != "done" or agent is None:
        raise ReviewError("There is no recommendation to review yet.")
    reviewer = (form.get("reviewer") or "").strip()
    decision = form.get("decision")
    note = (form.get("note") or "").strip()
    if not reviewer:
        raise ReviewError("Please enter your name so the decision can be recorded.")
    if decision not in DECISIONS:
        raise ReviewError("Please choose a decision.")
    if decision == "reject" and not note:
        raise ReviewError("Please give a reason for rejecting the recommendation.")

    rec = agent["recommendation"]
    final = {"priority": rec["priority"], "action": rec["action"], "crew": rec["crew"]}
    if decision == "edit":
        final = {"priority": form.get("priority"), "action": form.get("action"), "crew": form.get("crew")}
        if final["priority"] not in PRIORITIES or final["action"] not in ACTIONS or final["crew"] not in CREWS:
            raise ReviewError("Please choose a valid priority, action and crew.")
        if final["action"] == "create_work_order" and final["crew"] == "none":
            raise ReviewError("A work order needs a crew.")
    elif decision == "more_footage":
        final = {**final, "action": "request_more_footage", "crew": "none"}
    elif decision == "reject":
        final = {"priority": None, "action": "no_action", "crew": "none"}
    if final["action"] != "create_work_order":
        final["crew"] = "none"

    now = datetime.now(timezone.utc)
    work_order = None
    if decision in ("approve", "edit") and final["action"] == "create_work_order":
        work_order = {
            "id": f"WO-{now:%Y%m%d}-{uuid.uuid4().hex[:4].upper()}",
            "priority": final["priority"], "crew": final["crew"],
            "summary": rec["summary"], "created_at": now.isoformat(timespec="seconds"),
            "due": (now + timedelta(days=DUE_DAYS[final["priority"]])).isoformat(timespec="seconds"),
            "status": "open",
        }

    changed = [k for k in ("priority", "action", "crew") if final[k] != rec[k]] if decision == "edit" else []
    review = {"decision": decision, "label": DECISIONS[decision], "reviewer": reviewer, "note": note,
              "at": now.isoformat(timespec="seconds"), "agent_recommendation": {k: rec[k] for k in ("priority", "action", "crew")},
              "final": final, "changed": changed, "work_order": work_order}

    def change(r):
        r["review"] = review
        r["status"]["review"] = "done"
    storage.update(inspection_id, change)

    if decision == "reject":
        detail = f"No action taken (the agent had recommended {rec['priority']}, {rec['action'].replace('_', ' ')})"
    elif decision == "more_footage":
        detail = "Reporter asked for clearer footage; no crew sent yet"
    else:
        detail = f"{final['priority']}, {final['action'].replace('_', ' ')}"
    if changed:
        detail += f" (changed {', '.join(changed)} from the agent's {', '.join(str(rec[k]) for k in changed)})"
    if note:
        detail += f". Note: {note}"
    storage.audit(inspection_id, reviewer, DECISIONS[decision], detail)
    if work_order:
        storage.audit(inspection_id, "DrainWatch", f"Work order {work_order['id']} created",
                      f"{CREW_LABELS[work_order['crew']]}, due {work_order['due'][:10]}")
    return review


def complete_work_order(inspection_id: str, who: str, note: str = "") -> dict:
    who = (who or "").strip()
    if not who:
        raise ReviewError("Please enter your name.")
    record = storage.load(inspection_id)
    wo = (record.get("review") or {}).get("work_order")
    if not wo or wo["status"] != "open":
        raise ReviewError("There is no open work order for this inspection.")

    def change(r):
        r["review"]["work_order"].update(status="done", completed_by=who, completed_at=storage.now_iso(), completion_note=note)
    record = storage.update(inspection_id, change)
    storage.audit(inspection_id, who, f"Work order {wo['id']} completed", note)
    return record["review"]["work_order"]


def reset_for_rerun(inspection_id: str) -> None:
    """Re-running the analysis invalidates the decision: keep it in history and ask for a new review."""
    def change(r):
        if r.get("review"):
            r.setdefault("review_history", []).append(r.pop("review"))
        r["status"]["review"] = "pending"
    record = storage.load(inspection_id)
    if record.get("review"):
        storage.update(inspection_id, change)
        storage.audit(inspection_id, "DrainWatch", "Previous decision archived", "Analysis re-run; a new review is needed")


def all_work_orders() -> list[dict]:
    out = []
    for r in storage.list_all():
        wo = (r.get("review") or {}).get("work_order")
        if wo:
            out.append({**wo, "inspection_id": r["inspection_id"], "site": r["site"]})
    order = {"open": 0, "done": 1}
    return sorted(out, key=lambda w: (order.get(w["status"], 2), w["priority"], w["due"]))
