"""Temporal reasoning over registered frames: motion and persistence."""
import cv2
import numpy as np

from .detection import kernel

MOTION_PX = 2.0     # optical-flow magnitude (px/frame) above which a pixel is "moving"


def motion_mask(prev_gray: np.ndarray, gray: np.ndarray) -> np.ndarray:
    """Dense Farneback optical flow between two registered frames; True where things move."""
    p = cv2.resize(prev_gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    g = cv2.resize(gray, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    flow = cv2.calcOpticalFlowFarneback(p, g, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    mag = cv2.magnitude(flow[..., 0], flow[..., 1]) * 2.0
    mag = cv2.resize(mag, (gray.shape[1], gray.shape[0]), interpolation=cv2.INTER_LINEAR)
    return cv2.dilate((mag > MOTION_PX).astype(np.uint8), kernel(9)) > 0


class Persistence:
    """Counts, per reference-frame pixel, how often water / debris / motion was seen."""

    def __init__(self, shape: tuple[int, int]):
        self.valid = np.zeros(shape, np.float32)
        self.water = np.zeros(shape, np.float32)
        self.debris = np.zeros(shape, np.float32)
        self.moving = np.zeros(shape, np.float32)
        self.frames = 0

    def add(self, valid, water, debris, moving) -> None:
        self.frames += 1
        self.valid += valid
        self.water += water & valid
        self.debris += debris & valid & ~moving     # passing cars / people are not debris
        self.moving += moving

    def maps(self) -> dict:
        """Fractions in [0, 1]; pixels seen in too few frames are zeroed."""
        enough = self.valid >= max(2.0, 0.4 * self.frames)
        denom = np.maximum(self.valid, 1.0)
        frac = lambda acc: np.where(enough, acc / denom, 0.0).astype(np.float32)  # noqa: E731
        return {"water": frac(self.water), "debris": frac(self.debris),
                "moving": frac(self.moving), "covered": enough}
