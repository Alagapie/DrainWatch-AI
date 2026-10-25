"""Evidence images: annotated frames, persistence heatmap, timeline chart, privacy blurring."""
import os

import cv2
import numpy as np

WATER = (255, 140, 0)    # BGR
DEBRIS = (40, 40, 230)
DRAIN = (60, 210, 60)
FONT = cv2.FONT_HERSHEY_SIMPLEX

_cascades = None


def _load_cascades() -> list:
    """Haar cascades for faces and licence plates, if this OpenCV build ships them."""
    global _cascades
    if _cascades is None:
        _cascades = []
        base = getattr(getattr(cv2, "data", None), "haarcascades", "")
        for name in ("haarcascade_frontalface_default.xml", "haarcascade_russian_plate_number.xml"):
            path = os.path.join(base, name)
            if os.path.exists(path):
                c = cv2.CascadeClassifier(path)
                if not c.empty():
                    _cascades.append(c)
    return _cascades


def blur_identifiers(img: np.ndarray) -> tuple[np.ndarray, int]:
    """Blur faces and licence plates. Returns (image, regions blurred)."""
    out = img.copy()
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    count = 0
    for c in _load_cascades():
        for (x, y, w, h) in c.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(24, 24)):
            out[y:y + h, x:x + w] = cv2.GaussianBlur(out[y:y + h, x:x + w], (0, 0), max(w, h) / 6)
            count += 1
    return out, count


def label(img, text, org, color=(255, 255, 255), scale=0.55):
    (tw, th), _ = cv2.getTextSize(text, FONT, scale, 1)
    x, y = org
    cv2.rectangle(img, (x, y - th - 8), (x + tw + 8, y + 3), (20, 20, 20), -1)
    cv2.putText(img, text, (x + 4, y - 3), FONT, scale, color, 1, cv2.LINE_AA)


def tint(img, mask, color, alpha=0.45):
    if mask is None or not mask.any():
        return
    layer = img.copy()
    layer[mask] = color
    cv2.addWeighted(layer, alpha, img, 1 - alpha, 0, dst=img)
    contours, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(img, contours, -1, color, 2, cv2.LINE_AA)


def draw_drains(img, drains):
    for d in drains:
        x, y, w, h = d["bbox"]
        cv2.rectangle(img, (x, y), (x + w, y + h), DRAIN, 2, cv2.LINE_AA)
        text = d.get("drain_id", "drain")
        if d.get("status"):
            text += f"  {d['status'].replace('_', ' ')}"
        label(img, text, (x, max(y - 2, 20)), DRAIN)


def annotate(img, water, debris, drains, caption: str) -> np.ndarray:
    out = img.copy()
    tint(out, water, WATER)
    tint(out, debris, DEBRIS)
    draw_drains(out, drains)
    label(out, caption, (8, 26))
    return out


def heatmap(ref_img, pers_water, pers_debris, drains) -> np.ndarray:
    pers = np.maximum(pers_water, pers_debris)
    heat = cv2.applyColorMap((pers * 255).astype(np.uint8), cv2.COLORMAP_JET)
    blended = cv2.addWeighted(heat, 0.6, ref_img, 0.4, 0)
    out = ref_img.copy()
    sel = pers > 0.15
    out[sel] = blended[sel]
    draw_drains(out, drains)
    label(out, "Persistence: red = present in most frames", (8, 26))
    return out


def timeline(per_frame: list[dict], width: int = 960, height: int = 260) -> np.ndarray:
    img = np.full((height, width, 3), 255, np.uint8)
    left, right, top, bottom = 52, 20, 34, 34
    pw, ph = width - left - right, height - top - bottom
    peak = max([5.0] + [max(r["water_pct"], r["debris_pct"]) for r in per_frame]) * 1.1
    cv2.rectangle(img, (left, top), (left + pw, top + ph), (215, 215, 215), 1)
    for k in range(5):
        y = top + int(ph * k / 4)
        cv2.line(img, (left, y), (left + pw, y), (238, 238, 238), 1)
        cv2.putText(img, f"{peak * (1 - k / 4):.0f}%", (6, y + 4), FONT, 0.4, (110, 110, 110), 1, cv2.LINE_AA)
    n = len(per_frame)
    x_at = lambda i: left + int(pw * i / max(n - 1, 1))  # noqa: E731
    for i, r in enumerate(per_frame):
        if not r["aligned"]:
            cv2.line(img, (x_at(i), top), (x_at(i), top + ph), (200, 200, 200), 1)
    for key, color in (("water_pct", WATER), ("debris_pct", DEBRIS)):
        pts = np.array([[x_at(i), top + ph - int(ph * r[key] / peak)] for i, r in enumerate(per_frame)], np.int32)
        if len(pts) > 1:
            cv2.polylines(img, [pts], False, color, 2, cv2.LINE_AA)
        for p in pts:
            cv2.circle(img, (int(p[0]), int(p[1])), 3, color, -1, cv2.LINE_AA)
    if n:
        cv2.putText(img, f"t={per_frame[0]['t']}s", (left, height - 12), FONT, 0.42, (110, 110, 110), 1, cv2.LINE_AA)
        cv2.putText(img, f"t={per_frame[-1]['t']}s", (left + pw - 70, height - 12), FONT, 0.42, (110, 110, 110), 1, cv2.LINE_AA)
    cv2.putText(img, "Water % of ground", (left + 6, 22), FONT, 0.5, WATER, 1, cv2.LINE_AA)
    cv2.putText(img, "Debris % of ground", (left + 200, 22), FONT, 0.5, DEBRIS, 1, cv2.LINE_AA)
    cv2.putText(img, "grey line = frame not aligned", (left + 400, 22), FONT, 0.45, (140, 140, 140), 1, cv2.LINE_AA)
    return img


def select_frames(per_frame: list[dict], sharpness: list[float], k: int = 4) -> list[int]:
    """Pick up to k informative, sharp, time-spread frames (indices into per_frame)."""
    scored = sorted(((r["water_pct"] + 2 * r["debris_pct"] + 10 * r["drains"] + 1) * min(s / 1000.0, 1.0), i)
                    for i, (r, s) in enumerate(zip(per_frame, sharpness)))
    gap = max(1, len(per_frame) // (2 * k))
    picked = []
    for _, i in reversed(scored):
        if all(abs(i - j) >= gap for j in picked):
            picked.append(i)
        if len(picked) == k:
            break
    return sorted(picked)


def save(path: str, img: np.ndarray) -> int:
    """Write a privacy-blurred JPEG. Returns the number of regions blurred."""
    safe, n = blur_identifiers(img)
    cv2.imwrite(path, safe, [cv2.IMWRITE_JPEG_QUALITY, 88])
    return n
