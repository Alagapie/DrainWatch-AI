"""Frame quality assessment and adaptive enhancement.

Each frame is scored first, and only the enhancements that fix its measured
problems are applied, so good frames are left untouched.
"""
import cv2
import numpy as np

PROCESSING_WIDTH = 960   # frames are resized to this width before analysis

BLUR_REJECT = 60.0       # Laplacian variance (contrast-stretched) below this: unusable
BLUR_LOW = 300.0         # below this: blurry -> unsharp mask
DARK = 75.0              # mean brightness below this: low light -> gamma
LOW_CONTRAST = 45.0      # grey-level std below this: low contrast -> CLAHE
NOISY = 6.0              # noise sigma (flat pixels) above this: noisy -> NL-means denoise

ENHANCEMENT_ORDER = ("gamma", "denoise", "clahe", "sharpen")


def resize_to_width(img: np.ndarray, width: int = PROCESSING_WIDTH) -> np.ndarray:
    h, w = img.shape[:2]
    if w <= width:
        return img
    return cv2.resize(img, (width, round(h * width / w)), interpolation=cv2.INTER_AREA)


_NOISE_KERNEL = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)


def _stretch(gray: np.ndarray) -> np.ndarray:
    """Percentile contrast stretch, so sharpness does not depend on exposure."""
    lo, hi = np.percentile(gray, (1, 99))
    if hi - lo < 1:
        return gray.astype(np.float32)
    return np.clip((gray.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.float32)


def noise_sigma(gray: np.ndarray) -> float:
    """Immerkaer's noise estimate, measured only on the flattest pixels.

    Texture (asphalt grain, gravel) also excites the Laplacian-like kernel, so
    pixels with strong local gradients are excluded before averaging.
    """
    g = gray.astype(np.float32)
    conv = np.abs(cv2.filter2D(g, -1, _NOISE_KERNEL))[1:-1, 1:-1]
    grad = cv2.magnitude(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))[1:-1, 1:-1]
    flat = grad <= np.percentile(grad, 25)
    if flat.sum() < 100:
        flat = np.ones_like(grad, bool)
    return float(np.sqrt(np.pi / 2) * conv[flat].mean() / 6.0)


def assess(bgr: np.ndarray) -> dict:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    sharpness = float(cv2.Laplacian(_stretch(gray), cv2.CV_32F).var())
    noise = noise_sigma(gray)
    brightness = float(gray.mean())
    contrast = float(gray.std())

    issues = [name for name, bad in (
        ("blurry", sharpness < BLUR_LOW),
        ("low_light", brightness < DARK),
        ("low_contrast", contrast < LOW_CONTRAST),
        ("noisy", noise > NOISY),
    ) if bad]
    return {
        "sharpness": round(sharpness, 1),
        "brightness": round(brightness, 1),
        "contrast": round(contrast, 1),
        "noise": round(noise, 2),
        "issues": issues,
        "usable": sharpness >= BLUR_REJECT,
    }


def gamma_correct(bgr: np.ndarray, target_mean: float = 115.0) -> np.ndarray:
    mean = max(float(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).mean()), 1.0)
    gamma = float(np.clip(np.log(target_mean / 255.0) / np.log(mean / 255.0), 0.3, 1.0))
    lut = (np.power(np.arange(256) / 255.0, gamma) * 255.0).clip(0, 255).astype(np.uint8)
    return cv2.LUT(bgr, lut)


def clahe(bgr: np.ndarray, clip_limit: float = 2.5) -> np.ndarray:
    l, a, b = cv2.split(cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB))
    l = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def denoise(bgr: np.ndarray) -> np.ndarray:
    return cv2.fastNlMeansDenoisingColored(bgr, None, 6, 6, 7, 21)


def sharpen(bgr: np.ndarray) -> np.ndarray:
    blurred = cv2.GaussianBlur(bgr, (0, 0), 2.0)
    return cv2.addWeighted(bgr, 1.6, blurred, -0.6, 0)


ENHANCERS = {"gamma": gamma_correct, "denoise": denoise, "clahe": clahe, "sharpen": sharpen}


def plan_enhancements(quality: dict) -> list[str]:
    issues = set(quality["issues"])
    steps = []
    if "low_light" in issues:
        steps.append("gamma")
    if "noisy" in issues:
        steps.append("denoise")
    if issues & {"low_light", "low_contrast"}:
        steps.append("clahe")
    if "blurry" in issues and "noisy" not in issues:   # sharpening amplifies noise
        steps.append("sharpen")
    return steps


def enhance(bgr: np.ndarray, steps: list[str]) -> np.ndarray:
    out = bgr
    for step in ENHANCEMENT_ORDER:
        if step in steps:
            out = ENHANCERS[step](out)
    return out
