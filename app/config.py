import os

from dotenv import load_dotenv

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

load_dotenv(os.path.join(BASE_DIR, ".env"))

# Empty values in .env (e.g. "AWS_PROFILE=") would override the AWS CLI login; drop them.
for _key in ("AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"):
    if os.environ.get(_key) == "":
        del os.environ[_key]


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    DATA_DIR = os.environ.get("DRAINWATCH_DATA_DIR", os.path.join(BASE_DIR, "data"))
    INSPECTIONS_DIR = os.path.join(DATA_DIR, "inspections")

    MAX_CONTENT_LENGTH = 300 * 1024 * 1024  # 300 MB per upload
    VIDEO_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "webm", "m4v"}
    IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "webp"}
    MAX_IMAGES = 20

    AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
    BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
