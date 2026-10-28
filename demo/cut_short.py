"""Cut the full demo recording down to a submission video under 3 minutes.

Keeps the strongest moments of demo/out/DrainWatch_demo.mp4, joins them with short
crossfades and exports 1920x1080 H.264. Writes the new caption times next to it so
the voice-over script can be matched.

    python demo/cut_short.py demo/out
"""
import json
import os
import subprocess
import sys

import imageio_ffmpeg

FADE = 0.4
# (start, end, label) in seconds of the full recording
CLIPS = [
    (0.5, 5.0, "Title"),
    (10.3, 18.8, "Problem"),
    (23.0, 30.0, "Solution"),
    (36.4, 53.0, "Live report"),
    (64.0, 72.0, "Processing"),
    (80.5, 119.5, "Flood result: recommendation, agent, severity, OpenCV"),
    (125.5, 173.8, "D-14 follow-up: agent tools, cause, OpenCV 5"),
    (180.5, 186.0, "Before/after enhancement"),
    (193.1, 219.0, "Human review, work order, audit trail"),
    (226.8, 235.8, "Architecture"),
    (258.5, 264.5, "Close"),
]


def main(out_dir):
    src = os.path.join(out_dir, "DrainWatch_demo.mp4")
    out = os.path.join(out_dir, "DrainWatch_demo_3min.mp4")
    chains, starts, t = [], [], 0.0
    for i, (a, b, _) in enumerate(CLIPS):
        chains.append(f"[0:v]trim={a}:{b},setpts=PTS-STARTPTS,"
                      f"scale=1920:1080:flags=lanczos,setsar=1,fps=30[c{i}]")
        starts.append(t)
        t += (b - a) - FADE
    total = t + FADE

    prev, offset = "c0", 0.0
    for i in range(1, len(CLIPS)):
        offset += (CLIPS[i - 1][1] - CLIPS[i - 1][0]) - FADE
        chains.append(f"[{prev}][c{i}]xfade=transition=fade:duration={FADE}:offset={offset:.2f}[x{i}]")
        prev = f"x{i}"
    chains.append(f"[{prev}]format=yuv420p[out]")

    cmd = [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", src,
           "-filter_complex", ";".join(chains), "-map", "[out]",
           "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-movflags", "+faststart", out]
    subprocess.run(cmd, check=True)

    with open(os.path.join(out_dir, "timeline.json"), encoding="utf-8") as fh:
        captions = json.load(fh)["captions"]
    timeline = []
    for (a, b, label), s in zip(CLIPS, starts):
        timeline.append({"t": round(s, 1), "scene": label})
        for c in captions:
            if a <= c["video_t"] < b and not c["caption"].startswith("[card"):
                timeline.append({"t": round(s + c["video_t"] - a, 1), "caption": c["caption"]})
    with open(os.path.join(out_dir, "timeline_3min.json"), "w", encoding="utf-8") as fh:
        json.dump({"duration": round(total, 1), "timeline": timeline}, fh, indent=2)
    print(f"video: {out} ({total:.1f} s)")


if __name__ == "__main__":
    main(sys.argv[1])
