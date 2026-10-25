"""Thin wrapper around the Amazon Bedrock Converse API."""
import json
import re
import threading

import boto3
import cv2
from botocore.config import Config as BotoConfig

_clients: dict[str, object] = {}
_lock = threading.Lock()


class BedrockError(RuntimeError):
    pass


def client(region: str):
    with _lock:
        if region not in _clients:
            _clients[region] = boto3.client(
                "bedrock-runtime", region_name=region,
                config=BotoConfig(read_timeout=120, retries={"max_attempts": 3, "mode": "adaptive"}))
        return _clients[region]


def image_block(path: str, max_side: int = 640) -> dict:
    """Load an image, downscale it and wrap it as a Converse image content block."""
    img = cv2.imread(path)
    if img is None:
        raise BedrockError(f"Cannot read image {path}")
    h, w = img.shape[:2]
    scale = max_side / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
    return {"image": {"format": "jpeg", "source": {"bytes": buf.tobytes()}}}


def converse(region: str, model_id: str, system: str, content: list, max_tokens: int = 1500,
             temperature: float = 0.1) -> dict:
    """Single-turn call. Returns {"text", "usage", "latency_ms", "stop_reason"}."""
    try:
        resp = client(region).converse(
            modelId=model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": content}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
    except Exception as e:  # botocore raises many types; surface a readable message
        raise BedrockError(_explain(e)) from e
    text = "".join(b.get("text", "") for b in resp["output"]["message"]["content"])
    return {"text": text, "usage": resp.get("usage", {}),
            "latency_ms": resp.get("metrics", {}).get("latencyMs"), "stop_reason": resp.get("stopReason")}


def converse_messages(region: str, model_id: str, system: str, messages: list, tool_config: dict | None = None,
                      max_tokens: int = 1500, temperature: float = 0.0) -> dict:
    """Multi-turn call (used by the agent's tool loop). Returns the raw Converse response."""
    kwargs = {"modelId": model_id, "system": [{"text": system}], "messages": messages,
              "inferenceConfig": {"maxTokens": max_tokens, "temperature": temperature}}
    if tool_config:
        kwargs["toolConfig"] = tool_config
    try:
        return client(region).converse(**kwargs)
    except Exception as e:
        raise BedrockError(_explain(e)) from e


def parse_json(text: str) -> dict:
    """Extract the first JSON object from model output (tolerates ```json fences and prose)."""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise BedrockError("The model did not return JSON.")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise BedrockError(f"The model returned malformed JSON: {e}") from e


def _explain(e: Exception) -> str:
    name = type(e).__name__
    msg = str(e)
    if name in ("NoCredentialsError", "PartialCredentialsError"):
        return "No AWS credentials found. Run 'aws configure' or set the keys in .env."
    if "AccessDenied" in msg:
        return "AWS denied access to the model. Enable Amazon Nova Pro under Bedrock > Model access, and check IAM permissions (bedrock:InvokeModel)."
    if "ValidationException" in msg and "model" in msg.lower():
        return f"Bedrock rejected the model ID or request: {msg}"
    if "ThrottlingException" in msg:
        return "Bedrock is throttling requests. Wait a moment and try again."
    if name in ("EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError"):
        return "Could not reach Amazon Bedrock. Check your internet connection."
    return f"{name}: {msg}"
