"""Reading frames from a video or a set of photos."""
import os
from collections.abc import Iterator

import cv2
import numpy as np

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

SAMPLE_FPS = 3.0     # frames per second taken from a video
MAX_FRAMES = 60      # cap on sampled frames; long videos are sampled more sparsely


def is_video(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS


def video_info(path: str) -> dict:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"OpenCV could not open the video '{os.path.basename(path)}'. "
                         "Try re-exporting it as H.264 MP4.")
    info = {
        "fps": cap.get(cv2.CAP_PROP_FPS) or 25.0,
        "frame_count": int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0),
        "width": int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
        "height": int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
    }
    cap.release()
    info["duration_s"] = round(info["frame_count"] / info["fps"], 2) if info["frame_count"] else None
    return info


def sample_video(path: str, sample_fps: float = SAMPLE_FPS,
                 max_frames: int = MAX_FRAMES) -> Iterator[tuple[int, float, np.ndarray]]:
    """Yield (frame_index, timestamp_s, bgr) at roughly `sample_fps`."""
    info = video_info(path)
    fps = info["fps"]
    step = max(1, round(fps / sample_fps))
    if info["frame_count"] and info["frame_count"] / step > max_frames:
        step = info["frame_count"] // max_frames

    cap = cv2.VideoCapture(path)
    index = 0
    try:
        while cap.grab():          # grab() skips decoding frames we don't keep
            if index % step == 0:
                ok, frame = cap.retrieve()
                if ok and frame is not None:
                    yield index, index / fps, frame
            index += 1
    finally:
        cap.release()


def read_images(paths: list[str]) -> Iterator[tuple[int, float, np.ndarray, str]]:
    """Yield (index, pseudo-timestamp, bgr, filename) for each readable photo."""
    for i, path in enumerate(sorted(paths)):
        img = cv2.imread(path, cv2.IMREAD_COLOR)   # applies EXIF orientation
        if img is not None:
            yield i, float(i), img, os.path.basename(path)


def colour_histogram(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def novelty(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """0 = identical colour distribution, 1 = completely different."""
    return max(0.0, 1.0 - float(cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)))
