"""M2 - Preprocessing.

media -> sampled frames -> quality scores -> blurry frames rejected
      -> adaptive enhancement -> keyframe selection -> registration
Writes frames and preprocess.json into `out_dir` for the analysis module.
"""
import json
import os
import time
from collections import Counter

import cv2

from . import frames as fr
from . import quality, registration

KEYFRAME_NOVELTY = 0.03     # colour-histogram change that makes a new keyframe
KEYFRAME_MAX_GAP_S = 2.0    # ...or this long since the last keyframe (video only)


def run(media_paths: list[str], out_dir: str, progress=None) -> dict:
    """Preprocess an inspection's media. `progress(message, fraction)` is optional."""
    def report(message, fraction):
        if progress:
            progress(message, fraction)

    t_start = time.perf_counter()
    raw_dir = os.path.join(out_dir, "frames", "raw")
    enh_dir = os.path.join(out_dir, "frames", "enhanced")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(enh_dir, exist_ok=True)

    # 1. Sample frames ------------------------------------------------------
    report("Reading footage", 0.02)
    videos = [p for p in media_paths if fr.is_video(p)]
    if videos:
        info = fr.video_info(videos[0])
        source = {"kind": "video", "file": os.path.basename(videos[0]), **info}
        samples = ((i, t, img, None) for i, t, img in fr.sample_video(videos[0]))
        expected = min(fr.MAX_FRAMES, max(1, round((info["duration_s"] or 10) * fr.SAMPLE_FPS)))
    else:
        source = {"kind": "images", "files": len(media_paths)}
        samples = fr.read_images(media_paths)
        expected = len(media_paths)

    # 2-4. Quality, rejection, enhancement, keyframes -------------------------
    records, images = [], []
    rejected, last_key_hist, last_key_t = 0, None, None
    for n, (index, t, img, name) in enumerate(samples):
        report(f"Checking quality of frame {n + 1}", 0.05 + 0.6 * min(n / expected, 1.0))
        raw = quality.resize_to_width(img)
        q = quality.assess(raw)
        if not q["usable"]:
            rejected += 1
            continue

        steps = quality.plan_enhancements(q)
        enhanced = quality.enhance(raw, steps)

        hist = fr.colour_histogram(raw)
        change = 1.0 if last_key_hist is None else fr.novelty(last_key_hist, hist)
        is_key = (last_key_hist is None or change >= KEYFRAME_NOVELTY or source["kind"] == "images"
                  or t - last_key_t >= KEYFRAME_MAX_GAP_S)
        if is_key:
            last_key_hist, last_key_t = hist, t

        fname = f"frame_{index:05d}.jpg"
        cv2.imwrite(os.path.join(raw_dir, fname), raw, [cv2.IMWRITE_JPEG_QUALITY, 92])
        cv2.imwrite(os.path.join(enh_dir, fname), enhanced, [cv2.IMWRITE_JPEG_QUALITY, 92])
        records.append({
            "index": index, "t": round(t, 2), "source_file": name,
            "raw": f"frames/raw/{fname}", "enhanced": f"frames/enhanced/{fname}",
            "width": raw.shape[1], "height": raw.shape[0],
            "quality": q, "enhancements": steps,
            "novelty": round(change, 3), "keyframe": is_key,
        })
        images.append(enhanced)

    if not records:
        raise ValueError("No usable frames: every frame was unreadable or too blurry.")
    t_frames = time.perf_counter()

    # 5. Registration -------------------------------------------------------
    report("Aligning frames (ORB + RANSAC)", 0.7)
    ref_idx = max(range(len(records)), key=lambda i: records[i]["quality"]["sharpness"])
    alignments = registration.align_to_reference(images, ref_idx)
    for rec, al in zip(records, alignments):
        rec["alignment"] = al
    t_align = time.perf_counter()

    # 6. Before/after example and summary -------------------------------------
    report("Writing results", 0.95)
    enhanced_recs = [r for r in records if r["enhancements"]]
    comparison = None
    if enhanced_recs:
        worst = min(enhanced_recs, key=lambda r: r["quality"]["brightness"] + r["quality"]["contrast"]
                    + min(r["quality"]["sharpness"], 200) / 4)
        comparison = {"index": worst["index"], "raw": worst["raw"], "enhanced": worst["enhanced"],
                      "issues": worst["quality"]["issues"], "enhancements": worst["enhancements"]}

    qualities = [r["quality"] for r in records]
    summary = {
        "sampled": len(records) + rejected,
        "kept": len(records),
        "rejected_blurry": rejected,
        "keyframes": sum(r["keyframe"] for r in records),
        "enhanced": len(enhanced_recs),
        "aligned": sum(a["ok"] for a in alignments),
        "reference_index": records[ref_idx]["index"],
        "camera_motion": registration.camera_motion(alignments),
        "issue_counts": dict(Counter(i for q in qualities for i in q["issues"])),
        "enhancement_counts": dict(Counter(s for r in records for s in r["enhancements"])),
        "mean_sharpness": round(sum(q["sharpness"] for q in qualities) / len(qualities), 1),
        "mean_brightness": round(sum(q["brightness"] for q in qualities) / len(qualities), 1),
    }
    result = {
        "opencv_version": cv2.__version__,
        "source": source,
        "summary": summary,
        "frames": records,
        "comparison": comparison,
        "timings_s": {
            "frames": round(t_frames - t_start, 2),
            "registration": round(t_align - t_frames, 2),
            "total": round(time.perf_counter() - t_start, 2),
        },
    }
    with open(os.path.join(out_dir, "preprocess.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=2)
    report("Preprocessing complete", 1.0)
    return result
