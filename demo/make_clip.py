"""Make a short handheld-style H.264 clip from a still photo, for the demo.

The camera drifts and shakes slightly and the light dims for a moment, so the
video exercises DrainWatch's frame registration, enhancement and persistence.

    python demo/make_clip.py <photo> <out.mp4>
"""
import sys

import cv2
import imageio_ffmpeg
import numpy as np

FPS, SECONDS = 30, 7
OUT_W, OUT_H = 960, 540
VIEW = 0.93            # the moving camera sees 93% of the photo, so the scale matches the photo itself


def main(src: str, dst: str) -> None:
    img = cv2.imread(src)
    H, W = img.shape[:2]
    rng = np.random.default_rng(7)
    writer = imageio_ffmpeg.write_frames(dst, (OUT_W, OUT_H), fps=FPS, codec="libx264",
                                         output_params=["-crf", "20"])
    writer.send(None)
    n = FPS * SECONDS
    zoom = OUT_W / (W * VIEW)
    for i in range(n):
        t = i / n
        cx = W / 2 + 0.025 * W * np.sin(2 * np.pi * t * 0.6) + rng.normal(0, 1.5)   # slow drift + hand shake
        cy = H / 2 + 0.02 * H * np.cos(2 * np.pi * t * 0.4) + rng.normal(0, 1.5)
        angle = 1.0 * np.sin(2 * np.pi * t * 0.5)
        M = cv2.getRotationMatrix2D((cx, cy), angle, zoom * (1.0 + 0.02 * np.sin(2 * np.pi * t * 0.3)))
        M[0, 2] += OUT_W / 2 - cx
        M[1, 2] += OUT_H / 2 - cy
        frame = cv2.warpAffine(img, M, (OUT_W, OUT_H), borderMode=cv2.BORDER_REFLECT)
        light = 1.0 - 0.45 * np.exp(-((t - 0.55) / 0.12) ** 2)              # a cloud passes over
        frame = np.clip(frame.astype(np.float32) * light + rng.normal(0, 3, frame.shape), 0, 255).astype(np.uint8)
        writer.send(np.ascontiguousarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    writer.close()
    print("wrote", dst)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
