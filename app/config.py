import os

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATA_DIR = os.environ.get("DRAINWATCH_DATA_DIR", os.path.join(BASE_DIR, "data"))
    INSPECTIONS_DIR = os.path.join(DATA_DIR, "inspections")

    MAX_CONTENT_LENGTH = 300 * 1024 * 1024  # 300 MB per upload
    VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm", "m4v"}
    IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "webp"}
    MAX_IMAGES = 20
