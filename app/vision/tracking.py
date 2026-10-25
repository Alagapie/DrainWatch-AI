"""Drain tracking across registered frames with constant-velocity Kalman filters."""
import cv2
import numpy as np


class DrainTracker:
    def __init__(self, gate_px: float):
        self.gate = gate_px        # max distance between prediction and detection
        self.tracks: list[dict] = []

    @staticmethod
    def _kalman(x: float, y: float) -> cv2.KalmanFilter:
        kf = cv2.KalmanFilter(4, 2)
        kf.transitionMatrix = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32)
        kf.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        kf.processNoiseCov = np.eye(4, dtype=np.float32) * 1e-2
        kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 4.0
        kf.errorCovPost = np.eye(4, dtype=np.float32)
        kf.statePost = np.array([[x], [y], [0], [0]], np.float32)
        return kf

    def update(self, detections: list[dict], frame_index: int) -> None:
        """`detections` carry "bbox" in reference-frame coordinates."""
        predictions = [t["kf"].predict()[:2].ravel() for t in self.tracks]
        used = set()
        for d in detections:
            x, y, w, h = d["bbox"]
            cx, cy = x + w / 2.0, y + h / 2.0
            best, best_dist = None, self.gate
            for i, p in enumerate(predictions):
                dist = float(np.hypot(p[0] - cx, p[1] - cy))
                if i not in used and dist < best_dist:
                    best, best_dist = i, dist
            if best is None:
                self.tracks.append({"kf": self._kalman(cx, cy), "detections": [d], "frames": [frame_index]})
            else:
                track = self.tracks[best]
                track["kf"].correct(np.array([[cx], [cy]], np.float32))
                track["detections"].append(d)
                track["frames"].append(frame_index)
                used.add(best)

    def confirmed(self, min_hits: int) -> list[dict]:
        """Tracks seen often enough, most persistent first, with a median box."""
        out = []
        for t in self.tracks:
            if len(t["detections"]) < min_hits:
                continue
            boxes = np.array([d["bbox"] for d in t["detections"]])
            kinds = [d["kind"] for d in t["detections"]]
            out.append({"bbox": np.median(boxes, axis=0).astype(int).tolist(),
                        "hits": len(t["detections"]),
                        "score": float(np.mean([d["score"] for d in t["detections"]])),
                        "kind": max(set(kinds), key=kinds.count),
                        "frames": t["frames"]})
        return sorted(out, key=lambda t: -t["hits"])
