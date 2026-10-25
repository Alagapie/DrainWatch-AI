"""Per-frame detection: water, debris and drain candidates.

Classical OpenCV cues, chosen so each one has a physical reason:
  water   smooth surface (low relative texture) + reflective / dark / muddy colour
  debris  saturated colours (plastics) or dense, irregular edges (clutter)
  drains  grates are parallel bars -> gradient energy in 1-2 orientations;
          kerb inlets are dark, elongated rectangular slots
"""
import cv2
import numpy as np

GROUND_TOP = 0.30   # top 30% of a street-level frame is usually sky / buildings


def kernel(size: int) -> np.ndarray:
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


def ground_mask(shape, top: float = GROUND_TOP) -> np.ndarray:
    mask = np.zeros(shape[:2], dtype=bool)
    mask[int(shape[0] * top):] = True
    return mask


def feature_maps(bgr: np.ndarray) -> dict:
    """Shared per-pixel cues used by all detectors."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    g = gray.astype(np.float32)

    # Relative local std: water is smooth; shadows on asphalt keep their grain.
    mean = cv2.blur(g, (7, 7))
    sq = cv2.blur(g * g, (7, 7))
    rel_std = np.sqrt(np.maximum(sq - mean * mean, 0)) / (mean + 10.0)

    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 60, 160)
    edge_density = cv2.blur((edges > 0).astype(np.float32), (21, 21))

    # Local histogram of gradient orientations (8 bins of 22.5 deg).
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag, ang = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    bins = np.clip((np.mod(ang, 180.0) / 22.5).astype(np.int32), 0, 7)
    hist = np.stack([cv2.blur(np.where(bins == b, mag, 0).astype(np.float32), (21, 21)) for b in range(8)])
    total = hist.sum(axis=0) + 1e-6
    orientation_focus = np.sort(hist, axis=0)[-2:].sum(axis=0) / total   # 0.25 random .. 1.0 parallel
    orientation_focus[cv2.blur(mag, (21, 21)) < 20] = 0.0

    return {"gray": gray, "hsv": hsv, "rel_std": rel_std,
            "edge_density": edge_density, "orientation_focus": orientation_focus}


def remove_small(mask: np.ndarray, min_frac: float) -> np.ndarray:
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), connectivity=8)
    keep = np.zeros(n, dtype=bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= min_frac * mask.size
    return keep[labels]


def _clean(mask: np.ndarray, open_k: int, close_k: int, min_frac: float) -> np.ndarray:
    m = mask.astype(np.uint8) * 255
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel(open_k))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel(close_k))
    return remove_small(m > 0, min_frac)


def water_mask(fm: dict, ground: np.ndarray, exclude: np.ndarray | None = None) -> np.ndarray:
    """Water differs from the surrounding road: brighter (reflection) or darker, and smoother."""
    h, s, v = cv2.split(fm["hsv"])
    road_v = float(np.median(v[ground])) if ground.any() else float(np.median(v))
    road_texture = float(np.median(fm["rel_std"][ground])) if ground.any() else 0.1

    smooth = fm["rel_std"] < min(0.05, 0.6 * road_texture)
    smooth = cv2.medianBlur(smooth.astype(np.uint8) * 255, 5) > 0
    reflective = (v > max(1.25 * road_v, road_v + 35)) & (s < 70)      # sky / lights mirrored in water
    dark_still = (v < 0.6 * road_v) & (s < 90)                          # dark pool on lighter road
    muddy = ((h >= 8) & (h <= 30) & (s >= 50) & (s <= 170) & (v >= 50) & (v <= 210)
             & (fm["rel_std"] < 0.12))                                   # brown floodwater (may ripple)
    candidate = ((smooth & (reflective | dark_still)) | muddy) & ground & (fm["edge_density"] < 0.10)
    if exclude is not None:
        candidate &= ~exclude
    return _clean(candidate, 5, 15, 0.003)


def debris_mask(fm: dict, ground: np.ndarray, exclude: np.ndarray | None = None) -> np.ndarray:
    """Debris stands out from the road: saturated colour, or clutter busier than the road's own texture."""
    h, s, v = cv2.split(fm["hsv"])
    vegetation = (h >= 35) & (h <= 85)
    colourful = (s >= 110) & (v >= 70) & ~vegetation                     # plastics, bags, cans, dry leaves
    road_edges = float(np.median(fm["edge_density"][ground])) if ground.any() else 0.1
    clutter = (fm["edge_density"] > max(0.22, 1.6 * road_edges)) & (fm["orientation_focus"] < 0.45)
    if exclude is not None:
        clutter &= ~exclude                                              # grate bars are not clutter
    return _clean((colourful | clutter) & ground, 3, 7, 0.0015)


def _iou(a, b) -> float:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    return inter / float(aw * ah + bw * bh - inter + 1e-6)


def detect_drains(fm: dict, ground: np.ndarray, max_out: int = 5) -> list[dict]:
    gray = fm["gray"]
    H, W = gray.shape
    area = float(H * W)
    median = float(np.median(gray[ground])) if ground.any() else float(np.median(gray))
    found = []

    # Grates: focused orientations, edge-dense, mix of dark slots and lighter bars.
    dark_frac = cv2.blur((gray < 0.7 * median).astype(np.float32), (15, 15))
    grate = ((fm["orientation_focus"] > 0.55) & (fm["edge_density"] > 0.12)
             & (dark_frac > 0.15) & (dark_frac < 0.85) & ground)
    m = cv2.morphologyEx(grate.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel(11))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel(5))
    for c in cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        a = cv2.contourArea(c)
        if not 0.002 * area <= a <= 0.15 * area:
            continue
        _, (rw, rh), _ = cv2.minAreaRect(c)
        if min(rw, rh) < 1:
            continue
        rectangularity = a / (rw * rh)
        if rectangularity < 0.45 or max(rw, rh) / min(rw, rh) > 6:
            continue
        x, y, w, h = cv2.boundingRect(c)
        roi = (slice(y, y + h), slice(x, x + w))
        score = (fm["orientation_focus"][roi].mean() * min(fm["edge_density"][roi].mean() / 0.25, 1.0)
                 * rectangularity)
        found.append({"bbox": [x, y, w, h], "score": round(float(score), 3), "kind": "grate"})

    # Dark elongated slots: a row of parallel slots is a grate, a lone long slot is a kerb inlet.
    slots = _dark_slots(gray, ground, median, area)
    found += _group_slots(slots, W, H)

    # Merge overlapping detections (keep the best score, union the box).
    found.sort(key=lambda d: d["score"], reverse=True)
    kept = []
    for d in found:
        overlap = next((k for k in kept if _iou(d["bbox"], k["bbox"]) > 0.1 or _contains(k["bbox"], d["bbox"])), None)
        if overlap is None:
            kept.append(d)
        else:
            overlap["bbox"] = _union(overlap["bbox"], d["bbox"])

    # A small detection hugging a bigger grate is part of that grate (its frame, an edge slot or its
    # shadow), not a separate drain.
    area_of = lambda b: b[2] * b[3]  # noqa: E731
    grates = sorted((k for k in kept if k["kind"] == "grate"), key=lambda k: -area_of(k["bbox"]))
    out = []
    for k in kept:
        parent = next((g for g in grates if g is not k and area_of(g["bbox"]) > area_of(k["bbox"])
                       and _iou(k["bbox"], _expand(g["bbox"], 0.25)) > 0), None)
        if parent is None or (k["kind"] == "grate" and area_of(k["bbox"]) >= 0.3 * area_of(parent["bbox"])):
            out.append(k)
    return out[:max_out]


def _expand(bbox, frac):
    x, y, w, h = bbox
    dx, dy = int(w * frac), int(h * frac)
    return [x - dx, y - dy, w + 2 * dx, h + 2 * dy]


def _contains(outer, inner) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    cx, cy = ix + iw / 2, iy + ih / 2
    return ox <= cx <= ox + ow and oy <= cy <= oy + oh


def _union(a, b):
    x0, y0 = min(a[0], b[0]), min(a[1], b[1])
    x1, y1 = max(a[0] + a[2], b[0] + b[2]), max(a[1] + a[3], b[1] + b[3])
    return [x0, y0, x1 - x0, y1 - y0]


def _dark_slots(gray, ground, median, area) -> list[dict]:
    mask = cv2.morphologyEx(((gray < 0.5 * median) & ground).astype(np.uint8) * 255, cv2.MORPH_OPEN, kernel(3))
    slots = []
    for c in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        a = cv2.contourArea(c)
        if not 0.0004 * area <= a <= 0.05 * area:
            continue
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(c)
        if min(rw, rh) < 2:
            continue
        long_side, short_side = max(rw, rh), min(rw, rh)
        if a / (rw * rh) < 0.55 or not 2.0 <= long_side / short_side <= 14.0:
            continue
        axis = angle if rw >= rh else angle + 90.0          # direction of the long side
        slots.append({"center": (cx, cy), "long": long_side, "short": short_side,
                      "axis": axis % 180.0, "bbox": list(cv2.boundingRect(c))})
    return slots


def _group_slots(slots, W, H) -> list[dict]:
    """Cluster parallel, similar-sized, closely spaced slots into grates."""
    groups, used = [], set()
    for i, s in enumerate(slots):
        if i in used:
            continue
        group, used_i = [s], {i}
        changed = True
        while changed:                                       # grow the cluster transitively
            changed = False
            for j, t in enumerate(slots):
                if j in used_i:
                    continue
                for g in group:
                    d_axis = abs((g["axis"] - t["axis"] + 90) % 180 - 90)
                    dist = np.hypot(g["center"][0] - t["center"][0], g["center"][1] - t["center"][1])
                    if (d_axis < 15 and 0.6 < t["long"] / g["long"] < 1.6
                            and dist < 1.5 * g["long"] and dist > 0.8 * g["short"]):
                        group.append(t)
                        used_i.add(j)
                        changed = True
                        break
        used |= used_i
        groups.append(group)

    out = []
    for g in groups:
        box = g[0]["bbox"]
        for s in g[1:]:
            box = _union(box, s["bbox"])
        pad = int(0.25 * np.mean([s["short"] for s in g])) + 4
        x, y = max(0, box[0] - pad), max(0, box[1] - pad)
        box = [x, y, min(W - x, box[2] + 2 * pad), min(H - y, box[3] + 2 * pad)]
        if len(g) >= 3:
            out.append({"bbox": box, "score": round(min(0.4 + 0.08 * len(g), 0.9), 3), "kind": "grate"})
        elif len(g) == 1 and g[0]["long"] / g[0]["short"] >= 4 and g[0]["long"] > 0.08 * W:
            out.append({"bbox": box, "score": 0.35, "kind": "kerb_inlet"})
    return out


def detect(bgr: np.ndarray) -> dict:
    """Run all detectors on one frame."""
    fm = feature_maps(bgr)
    ground = ground_mask(bgr.shape)
    drains = detect_drains(fm, ground)
    in_drain = np.zeros(ground.shape, bool)
    for d in drains:
        x, y, w, h = d["bbox"]
        in_drain[y:y + h, x:x + w] = True
    return {"ground": ground, "gray": fm["gray"], "drains": drains,
            "water": water_mask(fm, ground, exclude=in_drain),
            "debris": debris_mask(fm, ground, exclude=in_drain)}
