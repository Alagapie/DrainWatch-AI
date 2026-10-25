"""Where does the water sit relative to the drain? (OpenCV geometry)

The answer points to the likely cause, which decides who should be sent:
  water gathered at the drain inlet, or debris on the grate -> drain blockage (cleaning crew)
  water pooled away from a clear drain                      -> surface depression (road repair)
Distances are measured with a distance transform from the drain boxes and are
expressed relative to the drain's size, so they do not depend on image scale.
"""
import cv2
import numpy as np

from .evidence import DRAIN, WATER, label, tint

NEAR = 0.5          # within half a drain-size of the grate counts as "at the drain"
AWAY = 1.0          # more than one drain-size away counts as "away from the drain"
TOUCHING = 0.15     # nearest water closer than this (x drain size) -> touching
PERIMETER_BAND = 0.08   # width of the band around the grate checked for wetness (x drain size)
MIN_DRAIN_SCORE = 0.45  # below this detector score the drain may be a false detection


def _drain_mask(shape, drains):
    mask = np.zeros(shape, np.uint8)
    for d in drains:
        x, y, w, h = d["bbox"]
        mask[max(0, y):y + h, max(0, x):x + w] = 1
    return mask


def water_drain_relation(water: np.ndarray, drains: list[dict], obstruction_pct: float | None,
                         water_pct: float) -> dict:
    if water_pct < 1.0 or not water.any():
        return {"relation": "no_water", "cause_hint": "none"}
    if not drains:
        return {"relation": "no_drain", "cause_hint": "unclear"}

    drain = _drain_mask(water.shape, drains)
    size = float(np.median([np.sqrt(d["bbox"][2] * d["bbox"][3]) for d in drains])) or 1.0
    dist = cv2.distanceTransform((1 - drain).astype(np.uint8), cv2.DIST_L2, 5)   # 0 inside drains
    water_dist = dist[water]
    near = float((water_dist <= NEAR * size).mean())
    away = float((water_dist > AWAY * size).mean())

    ys, xs = np.nonzero(water)
    k = int(np.argmin(water_dist))
    wx, wy = int(xs[k]), int(ys[k])
    nearest_px = float(water_dist[k])
    # Closest drain point to that water pixel (clamp into the nearest box).
    best = min(drains, key=lambda d: np.hypot(np.clip(wx, d["bbox"][0], d["bbox"][0] + d["bbox"][2]) - wx,
                                               np.clip(wy, d["bbox"][1], d["bbox"][1] + d["bbox"][3]) - wy))
    bx, by, bw, bh = best["bbox"]
    dx, dy = int(np.clip(wx, bx, bx + bw)), int(np.clip(wy, by, by + bh))

    # How much of the grate's edge is wet? Water backing up from a blocked inlet surrounds it;
    # a puddle in a dip touches it on one side at most.
    band = max(6, int(PERIMETER_BAND * size))
    ring = cv2.dilate(drain, cv2.getStructuringElement(cv2.MORPH_RECT, (2 * band + 1, 2 * band + 1))) & (1 - drain)
    wet_edge = float((water & (ring > 0)).sum()) / max(float(ring.sum()), 1.0)

    # Where is the bulk of the main puddle?
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(water.astype(np.uint8), connectivity=8)
    main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA])) if n > 1 else 0
    cx, cy = centroids[main] if main else (wx, wy)
    centre_gap = float(dist[int(np.clip(cy, 0, water.shape[0] - 1)), int(np.clip(cx, 0, water.shape[1] - 1))])

    relation = "touching" if nearest_px <= TOUCHING * size else "separated"
    blocked_grate = (obstruction_pct or 0) >= 15 or any(
        d.get("status") in ("blockage_suspected", "partial_obstruction", "debris_at_inlet") for d in drains)
    drain_confident = max(d.get("detector_score", 0) for d in drains) >= MIN_DRAIN_SCORE
    if not drain_confident:
        cause = "unclear"                 # the "drain" may be a false detection; don't guess a cause
    elif blocked_grate or wet_edge >= 0.30:
        cause = "drain_blockage"          # water gathers around the inlet instead of draining
    elif wet_edge < 0.15 and (centre_gap > NEAR * size or away >= 0.6):
        cause = "surface_depression"      # puddle sits in a low spot beside / away from a clear drain
    else:
        cause = "unclear"

    return {
        "relation": relation,
        "nearest_gap_px": round(nearest_px, 1),
        "nearest_gap_drain_sizes": round(nearest_px / size, 2),
        "drain_edge_wet_pct": round(100 * wet_edge, 1),
        "puddle_centre_gap_drain_sizes": round(centre_gap / size, 2),
        "water_near_drain_pct": round(100 * near, 1),
        "water_away_from_drain_pct": round(100 * away, 1),
        "cause_hint": cause,
        "drain_detection_confident": drain_confident,
        "line": [[dx, dy], [wx, wy]],
    }


def draw_relation(img: np.ndarray, water: np.ndarray, drains: list[dict], rel: dict) -> np.ndarray:
    out = img.copy()
    tint(out, water, WATER)
    for d in drains:
        x, y, w, h = d["bbox"]
        cv2.rectangle(out, (x, y), (x + w, y + h), DRAIN, 2, cv2.LINE_AA)
        label(out, d.get("drain_id", "drain"), (x, max(y - 2, 20)), DRAIN)
    if "line" in rel:
        (x1, y1), (x2, y2) = rel["line"]
        cv2.arrowedLine(out, (x1, y1), (x2, y2), (0, 255, 255), 2, cv2.LINE_AA, tipLength=0.08)
        label(out, f"gap {rel['nearest_gap_px']:.0f}px", ((x1 + x2) // 2 + 6, (y1 + y2) // 2), (0, 255, 255))
    captions = {"drain_blockage": "Water gathers at the drain: likely blockage",
                "surface_depression": "Water pools away from a clear drain: likely surface depression",
                "unclear": "Water / drain relation unclear"}
    text = captions.get(rel.get("cause_hint"), "")
    if "drain_edge_wet_pct" in rel:
        text += f"  (drain edge {rel['drain_edge_wet_pct']:.0f}% wet)"
    label(out, text, (8, 26))
    return out
