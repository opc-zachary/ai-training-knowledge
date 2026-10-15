#!/usr/bin/env python3
"""Fixed Wan HK executor for the six approved CatWomanWuxia storyboard shots.

This is deliberately not a generic video API client.  It accepts only the
immutable six-shot request beside this file, one pinned shot at a time, and the
existing Hong Kong binding names.  Generate performs at most one POST.  Resume
requires a receipt from that exact POST and performs GET requests only.

The API key is accepted only from the process environment.  It is never
printed, persisted, or placed in a command argument.  The first-frame Base64
is read from GitHub's event JSON so it is not copied into a logged environment
variable.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import datetime as dt
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parent
REQUEST_FILE = ROOT / "request-catwuxia4.json"
MODEL = "wan3.0-video"
# Finalized only after the root request and all six transport frames exist.
EXPECTED_REQUEST_SHA256 = "2cd34f9f722fa146603bd045e428bdc2af986af67e0fb36890e627e1a9548804"
EXPECTED_PROJECT = "CatWomanWuxia"
EXPECTED_CLIENT = "Zachary Chan"
EXPECTED_REPOSITORY = "opc-zachary/ai-training-knowledge"
EXPECTED_WORKFLOW_PATH = ".github/workflows/wan-hk-catwuxia4.yml"
EXPECTED_SHOT_IDS = ("01", "02", "03", "04", "05", "06")
EXPECTED_PARAMETERS = {
    "resolution": "480P",
    "ratio": "16:9",
    "duration": 4,
    "audio": True,
    "prompt_extend": False,
}
RUNTIME_MEDIA_PLACEHOLDER = "__RUNTIME_VERIFIED_REFERENCE_IMAGE_DATA_URI__"
GENERATE_CONFIRMATION = "GENERATECATWUXIA24BATCH"
RECEIPT_NAME = "catwuxia4-receipt.json"
VALIDATION_NAME = "catwuxia4-video-validation.json"
HOST = "ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com"
HOST_PATTERN = re.compile(r"[a-zA-Z0-9-]+\.cn-hongkong\.maas\.aliyuncs\.com")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,80}")
CREATIVE_ID_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,120}")
MAX_DISPATCH_INPUT_CHARACTERS = 65_535
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_RECEIPT_BYTES = 256 * 1024
MAX_VIDEO_BYTES = 512 * 1024 * 1024
POLL_LIMIT = 160
POLL_SECONDS = 15


class SafeFailure(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ApiFailure(Exception):
    def __init__(self, http_status: int | None, safe_code: str, outcome_known: bool):
        super().__init__(safe_code)
        self.http_status = http_status
        self.safe_code = safe_code
        self.outcome_known = outcome_known


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_sha256(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(encoded)


def safe_api_code(value: object, fallback: str) -> str:
    if isinstance(value, str) and SAFE_CODE_PATTERN.fullmatch(value):
        return value
    return fallback


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def valid_uuid(value: object) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def output_name(shot_id: str) -> str:
    return (
        "CatWomanWuxia_Zachary_2026-10-15_Video_"
        f"Shot{shot_id}Raw480p_Review_v01.mp4"
    )


def request_file_sha256() -> str:
    try:
        return sha256_bytes(REQUEST_FILE.read_bytes())
    except OSError as exc:
        raise SafeFailure("LOCAL_REQUEST_FILE_UNREADABLE") from exc


def ensure_validation_tools() -> None:
    if shutil.which("ffprobe") is None:
        raise SafeFailure("FFPROBE_COMMAND_NOT_FOUND")
    if shutil.which("ffmpeg") is None:
        raise SafeFailure("FFMPEG_COMMAND_NOT_FOUND")


def require_exact_keys(value: dict, keys: set[str], code: str) -> None:
    if set(value) != keys:
        raise SafeFailure(code)


def load_contract() -> dict:
    actual_request_sha256 = request_file_sha256()
    if actual_request_sha256 != EXPECTED_REQUEST_SHA256:
        raise SafeFailure("LOCAL_REQUEST_SHA256_MISMATCH")
    try:
        contract = json.loads(REQUEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SafeFailure("LOCAL_REQUEST_FILE_INVALID") from exc
    if not isinstance(contract, dict):
        raise SafeFailure("LOCAL_REQUEST_SCHEMA_INVALID")

    require_exact_keys(
        contract,
        {
            "schema_version",
            "project",
            "client",
            "batch_id",
            "model",
            "parameters",
            "media_placeholder",
            "shots",
        },
        "LOCAL_REQUEST_TOP_LEVEL_KEYS_INVALID",
    )
    if contract.get("schema_version") != 1:
        raise SafeFailure("LOCAL_REQUEST_SCHEMA_VERSION_INVALID")
    if contract.get("project") != EXPECTED_PROJECT or contract.get("client") != EXPECTED_CLIENT:
        raise SafeFailure("LOCAL_REQUEST_IDENTITY_MISMATCH")
    if contract.get("model") != MODEL:
        raise SafeFailure("LOCAL_MODEL_MISMATCH")
    if contract.get("parameters") != EXPECTED_PARAMETERS:
        raise SafeFailure("LOCAL_PARAMETERS_MISMATCH")
    if contract.get("media_placeholder") != RUNTIME_MEDIA_PLACEHOLDER:
        raise SafeFailure("LOCAL_MEDIA_PLACEHOLDER_INVALID")
    batch_id = contract.get("batch_id")
    if not isinstance(batch_id, str) or not CREATIVE_ID_PATTERN.fullmatch(batch_id):
        raise SafeFailure("LOCAL_BATCH_ID_INVALID")

    shots = contract.get("shots")
    if not isinstance(shots, list) or len(shots) != len(EXPECTED_SHOT_IDS):
        raise SafeFailure("LOCAL_SHOT_COUNT_INVALID")
    by_id: dict[str, dict] = {}
    for shot in shots:
        if not isinstance(shot, dict):
            raise SafeFailure("LOCAL_SHOT_SCHEMA_INVALID")
        require_exact_keys(
            shot,
            {
                "shot_id",
                "creative_id",
                "prompt",
                "reference_image_sha256",
                "reference_image_mime",
            },
            "LOCAL_SHOT_KEYS_INVALID",
        )
        shot_id = shot.get("shot_id")
        creative_id = shot.get("creative_id")
        prompt = shot.get("prompt")
        reference_sha256 = shot.get("reference_image_sha256")
        reference_mime = shot.get("reference_image_mime")
        if shot_id not in EXPECTED_SHOT_IDS or shot_id in by_id:
            raise SafeFailure("LOCAL_SHOT_ID_INVALID")
        if not isinstance(creative_id, str) or not CREATIVE_ID_PATTERN.fullmatch(creative_id):
            raise SafeFailure("LOCAL_CREATIVE_ID_INVALID")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
            raise SafeFailure("LOCAL_PROMPT_INVALID")
        if not isinstance(reference_sha256, str) or not SHA256_PATTERN.fullmatch(reference_sha256):
            raise SafeFailure("LOCAL_REFERENCE_SHA256_INVALID")
        if reference_mime not in {"image/webp", "image/jpeg", "image/png"}:
            raise SafeFailure("LOCAL_REFERENCE_MIME_INVALID")
        by_id[shot_id] = shot
    if tuple(shot["shot_id"] for shot in shots) != EXPECTED_SHOT_IDS:
        raise SafeFailure("LOCAL_SHOT_ORDER_INVALID")
    contract["_shots_by_id"] = by_id
    contract["_request_sha256"] = actual_request_sha256
    return contract


def selected_shot(contract: dict, shot_id: str) -> dict:
    if shot_id not in EXPECTED_SHOT_IDS:
        raise SafeFailure("SHOT_CHOICE_REQUIRED")
    shot = contract.get("_shots_by_id", {}).get(shot_id)
    if not isinstance(shot, dict):
        raise SafeFailure("SHOT_CHOICE_NOT_IN_FIXED_REQUEST")
    return shot


def shot_contract_digest(contract: dict, shot: dict) -> str:
    return canonical_sha256(
        {
            "schema_version": contract["schema_version"],
            "project": contract["project"],
            "client": contract["client"],
            "batch_id": contract["batch_id"],
            "model": contract["model"],
            "parameters": contract["parameters"],
            "media_placeholder": contract["media_placeholder"],
            "shot": shot,
        }
    )


def build_payload(contract: dict, shot: dict, image_data_uri: str) -> dict:
    return {
        "model": contract["model"],
        "input": {
            "prompt": shot["prompt"],
            "media": [{"type": "first_frame", "url": image_data_uri}],
        },
        "parameters": copy.deepcopy(contract["parameters"]),
    }


def load_binding() -> tuple[str, str]:
    host = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_HOST", "").strip()
    if not HOST_PATTERN.fullmatch(host) or host != HOST:
        raise SafeFailure("BINDING_HOST_INVALID")
    key = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_KEY", "")
    if not key or any(character.isspace() for character in key):
        raise SafeFailure("BINDING_SECRET_MISSING_OR_MALFORMED")
    return host, key


def validate_github_executor() -> None:
    workflow_prefix = EXPECTED_REPOSITORY + "/" + EXPECTED_WORKFLOW_PATH + "@"
    if (
        os.environ.get("GITHUB_ACTIONS") != "true"
        or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"
        or os.environ.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY
        or not os.environ.get("GITHUB_WORKFLOW_REF", "").startswith(workflow_prefix)
        or not os.environ.get("GITHUB_RUN_ID", "").isdigit()
    ):
        raise SafeFailure("GITHUB_EXECUTOR_IDENTITY_MISMATCH")


def load_event_inputs() -> dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        raise SafeFailure("GITHUB_EVENT_PATH_REQUIRED")
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        inputs = event["inputs"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SafeFailure("WORKFLOW_EVENT_INPUT_INVALID") from exc
    if not isinstance(inputs, dict):
        raise SafeFailure("WORKFLOW_EVENT_INPUT_INVALID")
    dispatch_characters = len(
        json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))
    )
    if dispatch_characters > MAX_DISPATCH_INPUT_CHARACTERS:
        raise SafeFailure("WORKFLOW_DISPATCH_INPUTS_TOO_LARGE")
    return inputs


def detected_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def load_reference_image(inputs: dict, shot: dict) -> tuple[bytes, str]:
    encoded = inputs.get("first_image_base64")
    if not isinstance(encoded, str) or not encoded:
        raise SafeFailure("REFERENCE_IMAGE_TRANSPORT_INVALID")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SafeFailure("REFERENCE_IMAGE_BASE64_INVALID") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise SafeFailure("REFERENCE_IMAGE_SIZE_INVALID")
    mime = detected_image_mime(data)
    if mime is None:
        raise SafeFailure("REFERENCE_IMAGE_FORMAT_INVALID")
    if mime != shot["reference_image_mime"]:
        raise SafeFailure("REFERENCE_IMAGE_MIME_MISMATCH")
    if sha256_bytes(data) != shot["reference_image_sha256"]:
        raise SafeFailure("REFERENCE_IMAGE_SHA256_MISMATCH")
    return data, mime


def decode_resume_receipt(inputs: dict) -> tuple[dict, str]:
    encoded = inputs.get("resume_receipt_base64")
    if not isinstance(encoded, str) or not encoded:
        raise SafeFailure("RESUME_RECEIPT_REQUIRED")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise SafeFailure("RESUME_RECEIPT_BASE64_INVALID") from exc
    if not raw or len(raw) > MAX_RECEIPT_BYTES:
        raise SafeFailure("RESUME_RECEIPT_SIZE_INVALID")
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("RESUME_RECEIPT_JSON_INVALID") from exc
    if not isinstance(receipt, dict):
        raise SafeFailure("RESUME_RECEIPT_JSON_INVALID")
    return receipt, sha256_bytes(raw)


def validate_resume_evidence(
    receipt: dict,
    task_id: str,
    contract: dict,
    shot: dict,
) -> None:
    allowed_statuses = {
        "SUBMITTED",
        "TASK_PENDING",
        "TASK_RUNNING",
        "QUERY_UNAVAILABLE_RESUME_SAME_TASK",
        "QUERY_RESPONSE_INVALID_RESUME_SAME_TASK",
        "POLL_WINDOW_ENDED_RESUME_SAME_TASK",
        "SUCCEEDED_RESULT_URL_MISSING_RESUME_SAME_TASK",
        "SUCCEEDED_DOWNLOAD_IN_PROGRESS",
        "DOWNLOADED_AWAITING_FFMPEG_VALIDATION",
    }
    source = receipt.get("source")
    if (
        receipt.get("project") != EXPECTED_PROJECT
        or receipt.get("client") != EXPECTED_CLIENT
        or receipt.get("batch_id") != contract["batch_id"]
        or receipt.get("shot_id") != shot["shot_id"]
        or receipt.get("creative_id") != shot["creative_id"]
        or receipt.get("task_id") != task_id
        or receipt.get("status") not in allowed_statuses
        or not isinstance(source, dict)
        or source.get("request_sha256") != EXPECTED_REQUEST_SHA256
        or source.get("shot_contract_sha256") != shot_contract_digest(contract, shot)
        or source.get("reference_image_sha256") != shot["reference_image_sha256"]
        or source.get("reference_image_mime") != shot["reference_image_mime"]
    ):
        raise SafeFailure("RESUME_EVIDENCE_BINDING_MISMATCH")


def decode_json_response(data: bytes, fallback: str) -> dict:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ApiFailure(None, fallback, False) from exc
    if not isinstance(value, dict):
        raise ApiFailure(None, fallback, False)
    return value


def api_json(url: str, key: str, payload: dict | None = None) -> dict:
    headers = {"Authorization": "Bearer " + key}
    body = None
    if payload is not None:
        headers.update(
            {"Content-Type": "application/json", "X-DashScope-Async": "enable"}
        )
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            status = response.status
            raw = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            raw = exc.read(2 * 1024 * 1024 + 1)
            parsed = json.loads(raw.decode("utf-8"))
            code = safe_api_code(
                parsed.get("code") if isinstance(parsed, dict) else None,
                "HTTP_ERROR",
            )
        except (OSError, UnicodeDecodeError, ValueError):
            code = "HTTP_ERROR"
        raise ApiFailure(status, code, 400 <= status < 500) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiFailure(None, "NETWORK_OR_TIMEOUT", False) from None
    if len(raw) > 2 * 1024 * 1024:
        raise ApiFailure(status, "RESPONSE_TOO_LARGE", False)
    return decode_json_response(raw, "RESPONSE_NOT_JSON")


def base_receipt(mode: str, host: str, contract: dict, shot: dict) -> dict:
    return {
        "project": EXPECTED_PROJECT,
        "client": EXPECTED_CLIENT,
        "batch_id": contract["batch_id"],
        "shot_id": shot["shot_id"],
        "creative_id": shot["creative_id"],
        "model": MODEL,
        "region": "China (Hong Kong)",
        "deployment_scope": "Global",
        "mode": mode,
        "api_host": host,
        "parameters": copy.deepcopy(EXPECTED_PARAMETERS),
        "source": {
            "request_file": REQUEST_FILE.name,
            "request_sha256": EXPECTED_REQUEST_SHA256,
            "shot_contract_sha256": shot_contract_digest(contract, shot),
            "reference_image_transport": (
                "workflow_dispatch.inputs.first_image_base64"
                if mode != "resume"
                else "bound_prior_generate_receipt"
            ),
            "reference_image_sha256": shot["reference_image_sha256"],
            "reference_image_mime": shot["reference_image_mime"],
        },
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "updated_utc": utc_now(),
    }


def record_api_failure(
    receipt_path: Path,
    receipt: dict,
    failure: ApiFailure,
    status: str,
) -> None:
    receipt.update(
        {
            "status": status,
            "http_status": failure.http_status,
            "safe_error_code": failure.safe_code,
            "updated_utc": utc_now(),
        }
    )
    write_json(receipt_path, receipt)


def submit(
    host: str,
    key: str,
    payload: dict,
    receipt_path: Path,
    receipt: dict,
) -> str:
    receipt.update(
        {"status": "POST_IN_PROGRESS_OUTCOME_UNKNOWN", "updated_utc": utc_now()}
    )
    write_json(receipt_path, receipt)
    url = f"https://{host}/api/v1/services/aigc/video-generation/video-synthesis"
    try:
        response = api_json(url, key, payload)
    except ApiFailure as failure:
        status = (
            "POST_REJECTED_NO_TASK_CREATED"
            if failure.outcome_known
            else "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY"
        )
        record_api_failure(receipt_path, receipt, failure, status)
        raise SafeFailure(status) from None
    task_id = valid_uuid(response.get("output", {}).get("task_id"))
    if not task_id:
        receipt.update(
            {
                "status": "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY",
                "safe_error_code": safe_api_code(
                    response.get("code"), "TASK_ID_MISSING"
                ),
                "updated_utc": utc_now(),
            }
        )
        write_json(receipt_path, receipt)
        raise SafeFailure("POST_OUTCOME_UNKNOWN_DO_NOT_RETRY")
    receipt.update(
        {"task_id": task_id, "status": "SUBMITTED", "updated_utc": utc_now()}
    )
    write_json(receipt_path, receipt)
    print("SUBMITTED shot=" + receipt["shot_id"] + " task_id=" + task_id, flush=True)
    return task_id


def download_video(url: str, target: Path) -> dict:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise SafeFailure("RESULT_URL_INVALID")
    if target.exists():
        raise SafeFailure("OUTPUT_ALREADY_EXISTS")
    temporary = target.with_suffix(target.suffix + ".partial")
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "CatWomanWuxia-WanHK-CatWuxia4/1.0"}
        )
        with urllib.request.urlopen(request, timeout=240) as response, temporary.open(
            "xb"
        ) as output:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or not final.hostname:
                raise SafeFailure("RESULT_REDIRECT_INVALID")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_VIDEO_BYTES:
                    raise SafeFailure("RESULT_VIDEO_TOO_LARGE")
                digest.update(chunk)
                output.write(chunk)
        with temporary.open("rb") as source:
            if b"ftyp" not in source.read(64):
                raise SafeFailure("RESULT_NOT_MP4")
        os.replace(temporary, target)
    except SafeFailure:
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SafeFailure("RESULT_DOWNLOAD_FAILED") from None
    return {"filename": target.name, "bytes": size, "sha256": digest.hexdigest()}


def poll(
    host: str,
    key: str,
    task_id: str,
    receipt_path: Path,
    receipt: dict,
    output_path: Path,
) -> None:
    receipt["task_id"] = task_id
    for _ in range(POLL_LIMIT):
        try:
            response = api_json(
                f"https://{host}/api/v1/tasks/{task_id}", key, payload=None
            )
        except ApiFailure as failure:
            record_api_failure(
                receipt_path,
                receipt,
                failure,
                "QUERY_UNAVAILABLE_RESUME_SAME_TASK",
            )
            raise SafeFailure("QUERY_UNAVAILABLE_RESUME_SAME_TASK") from None
        output = response.get("output")
        state = output.get("task_status") if isinstance(output, dict) else None
        if state not in {
            "PENDING",
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            "CANCELED",
            "UNKNOWN",
        }:
            receipt.update(
                {
                    "status": "QUERY_RESPONSE_INVALID_RESUME_SAME_TASK",
                    "safe_error_code": "TASK_STATUS_INVALID",
                    "updated_utc": utc_now(),
                }
            )
            write_json(receipt_path, receipt)
            raise SafeFailure("QUERY_RESPONSE_INVALID_RESUME_SAME_TASK")
        receipt.update({"task_status": state, "updated_utc": utc_now()})
        if state == "SUCCEEDED":
            usage = response.get("usage")
            if isinstance(usage, dict):
                allowed_usage = {
                    "video_count",
                    "duration",
                    "input_video_duration",
                    "output_video_duration",
                    "fps",
                    "SR",
                }
                receipt["usage"] = {
                    name: value
                    for name, value in usage.items()
                    if name in allowed_usage and isinstance(value, (int, float))
                }
            video_url = output.get("video_url")
            if not isinstance(video_url, str):
                receipt["status"] = "SUCCEEDED_RESULT_URL_MISSING_RESUME_SAME_TASK"
                write_json(receipt_path, receipt)
                raise SafeFailure("SUCCEEDED_RESULT_URL_MISSING_RESUME_SAME_TASK")
            receipt["status"] = "SUCCEEDED_DOWNLOAD_IN_PROGRESS"
            write_json(receipt_path, receipt)
            receipt["media"] = download_video(video_url, output_path)
            receipt["status"] = "DOWNLOADED_AWAITING_FFMPEG_VALIDATION"
            receipt["updated_utc"] = utc_now()
            write_json(receipt_path, receipt)
            print("DOWNLOADED shot=" + receipt["shot_id"] + " " + output_path.name)
            return
        if state in {"FAILED", "CANCELED", "UNKNOWN"}:
            receipt["status"] = "TASK_" + state
            receipt["safe_error_code"] = safe_api_code(
                output.get("code"), "NO_SAFE_API_CODE"
            )
            detail = str(output.get("message", "")).lower()
            receipt["safe_error_stage"] = next(
                (
                    label
                    for phrase, label in [
                        ("text (input)", "INPUT_TEXT_INSPECTION"),
                        ("image (input)", "INPUT_IMAGE_INSPECTION"),
                        ("video (output)", "OUTPUT_VIDEO_INSPECTION"),
                        ("audio (output)", "OUTPUT_AUDIO_INSPECTION"),
                    ]
                    if phrase in detail
                ),
                "INSPECTION_STAGE_NOT_SPECIFIED",
            )
            write_json(receipt_path, receipt)
            raise SafeFailure("TASK_" + state)
        receipt["status"] = "TASK_" + state
        write_json(receipt_path, receipt)
        time.sleep(POLL_SECONDS)
    receipt["status"] = "POLL_WINDOW_ENDED_RESUME_SAME_TASK"
    receipt["updated_utc"] = utc_now()
    write_json(receipt_path, receipt)
    raise SafeFailure("POLL_WINDOW_ENDED_RESUME_SAME_TASK")


def load_adjacent_receipt(path: Path) -> dict:
    receipt_path = path.parent / RECEIPT_NAME
    if not receipt_path.is_file():
        raise SafeFailure("VIDEO_RECEIPT_MISSING")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SafeFailure("VIDEO_RECEIPT_INVALID") from exc
    if not isinstance(receipt, dict):
        raise SafeFailure("VIDEO_RECEIPT_INVALID")
    return receipt


def parse_frame_rate(value: object) -> float:
    if not isinstance(value, str):
        raise SafeFailure("VIDEO_FRAME_RATE_INVALID")
    try:
        rate = float(Fraction(value))
    except (ValueError, ZeroDivisionError) as exc:
        raise SafeFailure("VIDEO_FRAME_RATE_INVALID") from exc
    if not 29.0 <= rate <= 31.0:
        raise SafeFailure("VIDEO_FRAME_RATE_NOT_APPROX_30")
    return rate


def validate_480p_landscape(
    width: int,
    height: int,
    duration: float,
    frame_rate: object,
    receipt: dict,
    media_sha256: str,
    expected_shot_id: str,
) -> float:
    if receipt.get("task_status") != "SUCCEEDED":
        raise SafeFailure("VIDEO_RECEIPT_TASK_NOT_SUCCEEDED")
    usage = receipt.get("usage")
    if not isinstance(usage, dict) or usage.get("SR") != 480:
        raise SafeFailure("VIDEO_RECEIPT_SR_NOT_480")
    if receipt.get("parameters") != EXPECTED_PARAMETERS:
        raise SafeFailure("VIDEO_RECEIPT_PARAMETERS_MISMATCH")
    source = receipt.get("source")
    if not isinstance(source, dict) or source.get("request_sha256") != EXPECTED_REQUEST_SHA256:
        raise SafeFailure("VIDEO_RECEIPT_REQUEST_SHA256_MISMATCH")
    if receipt.get("shot_id") != expected_shot_id:
        raise SafeFailure("VIDEO_RECEIPT_SHOT_ID_MISMATCH")
    media = receipt.get("media")
    if not isinstance(media, dict) or media.get("sha256") != media_sha256:
        raise SafeFailure("VIDEO_RECEIPT_MEDIA_SHA256_MISMATCH")
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width <= height
        or width < 800
        or width > 960
        or height < 450
        or height > 520
        or abs((width / height) - (16 / 9)) > 0.035
    ):
        raise SafeFailure("VIDEO_RESOLUTION_NOT_480P_LANDSCAPE")
    if not 3.5 <= duration <= 4.5:
        raise SafeFailure("VIDEO_DURATION_NOT_APPROX_4_SECONDS")
    return parse_frame_rate(frame_rate)


def verify_video(path: Path) -> None:
    match = re.fullmatch(
        r"CatWomanWuxia_Zachary_2026-10-15_Video_Shot(0[1-6])Raw480p_Review_v01\.mp4",
        path.name,
    )
    if not path.is_file() or match is None:
        raise SafeFailure("VIDEO_VALIDATION_TARGET_INVALID")
    expected_shot_id = match.group(1)
    ensure_validation_tools()
    receipt = load_adjacent_receipt(path)
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,r_frame_rate:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=90,
        )
        metadata = json.loads(probe.stdout)
        streams = metadata["streams"]
        video_streams = [s for s in streams if s.get("codec_type") == "video"]
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if len(video_streams) != 1:
            raise SafeFailure("VIDEO_STREAM_COUNT_INVALID")
        if not audio_streams:
            raise SafeFailure("AUDIO_STREAM_MISSING")
        stream = video_streams[0]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(metadata["format"]["duration"])
        media_sha256 = sha256_bytes(path.read_bytes())
        frame_rate = validate_480p_landscape(
            width,
            height,
            duration,
            stream.get("r_frame_rate"),
            receipt,
            media_sha256,
            expected_shot_id,
        )
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
            check=True,
            capture_output=True,
            timeout=360,
        )
    except SafeFailure:
        raise
    except (
        FileNotFoundError,
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SafeFailure("FFPROBE_OR_FFMPEG_VALIDATION_FAILED") from exc
    validation = {
        "status": "FFPROBE_AND_FFMPEG_VALIDATED",
        "shot_id": expected_shot_id,
        "request_sha256": EXPECTED_REQUEST_SHA256,
        "filename": path.name,
        "sha256": media_sha256,
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "video_codec": stream.get("codec_name"),
        "frame_rate": frame_rate,
        "audio_stream_count": len(audio_streams),
        "full_ffmpeg_decode_passed": True,
        "validated_utc": utc_now(),
    }
    write_json(path.parent / VALIDATION_NAME, validation)
    receipt_path = path.parent / RECEIPT_NAME
    receipt["status"] = "DOWNLOADED_AND_FFMPEG_VALIDATED"
    receipt["validation_sha256"] = canonical_sha256(validation)
    receipt["updated_utc"] = utc_now()
    write_json(receipt_path, receipt)
    print("FFPROBE_AND_FFMPEG_VALIDATED shot=" + expected_shot_id)


def parse_attempt() -> int:
    try:
        return int(os.environ.get("GITHUB_RUN_ATTEMPT", "1"))
    except ValueError as exc:
        raise SafeFailure("GITHUB_RUN_ATTEMPT_INVALID") from exc


def run_mode(mode: str, shot_id: str, output_dir: Path) -> None:
    contract = load_contract()
    shot = selected_shot(contract, shot_id)
    validate_github_executor()
    if mode in {"generate", "resume"}:
        ensure_validation_tools()
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / RECEIPT_NAME
    if receipt_path.exists():
        raise SafeFailure("OUTPUT_RECEIPT_ALREADY_EXISTS")

    if mode == "check-binding":
        receipt = base_receipt(mode, host, contract, shot)
        receipt["status"] = "BINDING_PRESENT_NOT_API_VERIFIED"
        write_json(receipt_path, receipt)
        print("BINDING_PRESENT_NOT_API_VERIFIED; no API request made")
        return

    inputs = load_event_inputs()
    if inputs.get("shot") != shot_id or inputs.get("mode") != mode:
        raise SafeFailure("WORKFLOW_EVENT_MODE_OR_SHOT_MISMATCH")

    if mode == "generate":
        if parse_attempt() != 1:
            raise SafeFailure("GENERATE_REFUSED_ON_RERUN_ATTEMPT")
        if os.environ.get("WAN_GENERATE_CONFIRMATION", "") != GENERATE_CONFIRMATION:
            raise SafeFailure("GENERATECATWUXIA24BATCH_CONFIRMATION_REQUIRED")
        if inputs.get("resume_task_id") or inputs.get("resume_receipt_base64"):
            raise SafeFailure("GENERATE_RESUME_INPUTS_FORBIDDEN")
        reference_image, reference_mime = load_reference_image(inputs, shot)
        image_data_uri = (
            "data:"
            + reference_mime
            + ";base64,"
            + base64.b64encode(reference_image).decode("ascii")
        )
        payload = build_payload(contract, shot, image_data_uri)
        receipt = base_receipt(mode, host, contract, shot)
        receipt.update(
            {
                "status": "REFERENCE_IMAGE_SHA256_VERIFIED",
                "verified_reference_image_sha256": sha256_bytes(reference_image),
                "provider_payload_sha256": canonical_sha256(payload),
            }
        )
        write_json(receipt_path, receipt)
        task_id = submit(host, key, payload, receipt_path, receipt)
        poll(
            host,
            key,
            task_id,
            receipt_path,
            receipt,
            output_dir / output_name(shot_id),
        )
        return

    if inputs.get("first_image_base64"):
        raise SafeFailure("RESUME_FIRST_IMAGE_FORBIDDEN")
    task_id = valid_uuid(inputs.get("resume_task_id"))
    if not task_id:
        raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    prior_receipt, receipt_digest = decode_resume_receipt(inputs)
    validate_resume_evidence(prior_receipt, task_id, contract, shot)
    receipt = base_receipt(mode, host, contract, shot)
    receipt.update(
        {
            "task_id": task_id,
            "status": "RESUME_QUERY_STARTING",
            "resume_evidence_sha256": receipt_digest,
            "original_github_run_id": prior_receipt.get("github_run_id"),
        }
    )
    write_json(receipt_path, receipt)
    poll(
        host,
        key,
        task_id,
        receipt_path,
        receipt,
        output_dir / output_name(shot_id),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["check-binding", "generate", "resume"],
        default="check-binding",
    )
    parser.add_argument("--shot", choices=EXPECTED_SHOT_IDS, default="01")
    parser.add_argument("--output-dir", type=Path, default=Path("output-catwuxia4"))
    parser.add_argument("--offline-validate", action="store_true")
    parser.add_argument(
        "--check-request",
        action="store_true",
        help="Read and validate only the fixed local request; never load bindings",
    )
    parser.add_argument("--verify-output", type=Path)
    args = parser.parse_args()
    try:
        if args.offline_validate or args.check_request:
            contract = load_contract()
            shot = selected_shot(contract, args.shot)
            print(
                "OFFLINE_CONTRACT_VALID"
                + " request_sha256="
                + EXPECTED_REQUEST_SHA256
                + " shot="
                + shot["shot_id"]
                + " shot_contract_sha256="
                + shot_contract_digest(contract, shot)
            )
            return 0
        if args.verify_output is not None:
            verify_video(args.verify_output.resolve())
            return 0
        run_mode(args.mode, args.shot, args.output_dir.resolve())
        return 0
    except SafeFailure as failure:
        print("ERROR " + failure.code, file=sys.stderr)
        return 1
    except Exception:
        print("ERROR UNEXPECTED_LOCAL_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
