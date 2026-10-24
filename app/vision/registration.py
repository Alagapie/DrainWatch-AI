"""Frame registration: align every frame to a reference frame.

ORB features + RANSAC estimate a similarity transform (shift, rotation,
scale) per frame. Aligned frames let the analysis compare the same ground
pixels over time, which is how a persistent puddle is told apart from a
reflection that appears in one frame.
"""
import cv2
import numpy as np

MIN_MATCHES = 12
MIN_INLIER_RATIO = 0.25
SCALE_RANGE = (0.7, 1.4)


def _features(orb, bgr):
    return orb.detectAndCompute(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), None)


def align_to_reference(images: list[np.ndarray], ref_idx: int) -> list[dict]:
    """Return per-image {"ok", "matrix" (2x3 list or None), "inlier_ratio", "shift_px"}."""
    orb = cv2.ORB_create(nfeatures=1500)
    matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
    kp_ref, des_ref = _features(orb, images[ref_idx])

    results = []
    for i, img in enumerate(images):
        if i == ref_idx:
            results.append({"ok": True, "matrix": [[1, 0, 0], [0, 1, 0]], "inlier_ratio": 1.0, "shift_px": 0.0})
            continue
        results.append(_align(orb, matcher, img, kp_ref, des_ref))
    return results


def _align(orb, matcher, img, kp_ref, des_ref) -> dict:
    failed = {"ok": False, "matrix": None, "inlier_ratio": 0.0, "shift_px": None}
    if des_ref is None:
        return failed
    kp, des = _features(orb, img)
    if des is None or len(kp) < MIN_MATCHES:
        return failed
    matches = sorted(matcher.match(des, des_ref), key=lambda m: m.distance)[:400]
    if len(matches) < MIN_MATCHES:
        return failed

    src = np.float32([kp[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([kp_ref[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    M, inliers = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=4.0)
    if M is None or inliers is None:
        return failed

    ratio = float(inliers.sum()) / len(matches)
    scale = float(np.hypot(M[0, 0], M[1, 0]))
    if ratio < MIN_INLIER_RATIO or not SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
        return {**failed, "inlier_ratio": round(ratio, 3)}
    return {"ok": True, "matrix": np.round(M, 5).tolist(), "inlier_ratio": round(ratio, 3),
            "shift_px": round(float(np.hypot(M[0, 2], M[1, 2])), 1)}


def warp(img: np.ndarray, matrix, size: tuple[int, int], nearest: bool = False) -> np.ndarray:
    """Apply a stored 2x3 matrix; `size` is (width, height) of the reference frame."""
    flags = cv2.INTER_NEAREST if nearest else cv2.INTER_LINEAR
    return cv2.warpAffine(img, np.float32(matrix), size, flags=flags,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def camera_motion(alignments: list[dict]) -> str:
    """Describe how the camera moved, from the registration results."""
    ok = [a for a in alignments if a["ok"]]
    if len(alignments) < 2:
        return "single_frame"
    if len(ok) / len(alignments) < 0.5:
        return "moving"             # view changes too much to register (e.g. driving)
    max_shift = max(a["shift_px"] for a in ok)
    return "static" if max_shift < 8 else "handheld"
