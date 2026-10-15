#!/usr/bin/env python3
"""Approved-package executor for one fixed Starbay CityCanvas S01 proof.

The API key is accepted only through the process environment. This program
never prints it, writes it to an artifact, or places it in a command argument.
Base64 first-frame transport is read from GitHub's event JSON so it is not
copied into a logged workflow environment variable.

The pinned contract records Zachary Chan's bounded 2026-10-15 approval for one
S01 submission capped at HK$5. This local package is still unpublished; only the
Project's root owner may install the three mapped files and dispatch once.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parent
PACKAGE_ROOT = ROOT.parent
REQUEST_FILE = ROOT / "request-starbay-city-canvas-s01-approved-v04.json"
MODEL = "wan3.0-video"
EXPECTED_REQUEST_SHA256 = "e04f9f2a6f28d18b8e4c03131be6e1ccb4a4820caf8a604a1e20df4be855a936"
RUNTIME_MEDIA_PLACEHOLDER = "__RUNTIME_VERIFIED_FIRST_FRAME_DATA_URI__"
OUTPUT_NAME = "CityCanvasS01.mp4"
RECEIPT_NAME = "city-canvas-s01-approved-v04-receipt.json"
VALIDATION_NAME = "city-canvas-s01-approved-v04-video-validation.json"
EXPECTED_API_HOST = "ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com"
GENERATE_CONFIRMATION = "GENERATE_STARBAY_CITY_CANVAS_S01_V04_ONCE"
SOURCE_FRAME_SHA256 = "8c5389104fae70c6b1abfd1431850599838133641098a956d7a86c1c19748db0"
TRANSPORT_FRAME_SHA256 = "94eb1c07138db47b5f899a9bb0bc9b2efc4b5f10c421fb2116b8415293c582d6"
TRANSPORT_FRAME_BYTES = 46_464
SOURCE_FRAME_DIMENSIONS = (941, 1672)
TRANSPORT_FRAME_DIMENSIONS = (480, 854)
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,80}")
MAX_EVENT_IMAGE_CHARACTERS = 65_535
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 256 * 1024 * 1024


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


def request_file_sha256() -> str:
    try:
        return hashlib.sha256(REQUEST_FILE.read_bytes()).hexdigest()
    except OSError as exc:
        raise SafeFailure("LOCAL_REQUEST_FILE_UNREADABLE") from exc


def ensure_validation_tools() -> None:
    if shutil.which("ffprobe") is None:
        raise SafeFailure("FFPROBE_COMMAND_NOT_FOUND")
    if shutil.which("ffmpeg") is None:
        raise SafeFailure("FFMPEG_COMMAND_NOT_FOUND")


def detected_image_dimensions(data: bytes, mime: str) -> tuple[int, int] | None:
    if mime == "image/png" and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if mime != "image/jpeg" or not data.startswith(b"\xff\xd8"):
        return None
    position = 2
    start_of_frame = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            position += 1
            continue
        marker = data[position + 1]
        position += 2
        if marker in {0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(data):
            return None
        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            return None
        if marker in start_of_frame and segment_length >= 7:
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            return width, height
        position += segment_length
    return None


def validate_asset_bytes(
    data: bytes,
    expected_sha256: str,
    expected_mime: str,
    expected_dimensions: tuple[int, int],
    expected_bytes: int | None,
    error_prefix: str,
) -> None:
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise SafeFailure(error_prefix + "_SHA256_MISMATCH")
    if expected_bytes is not None and len(data) != expected_bytes:
        raise SafeFailure(error_prefix + "_BYTE_COUNT_MISMATCH")
    if detected_image_mime(data) != expected_mime:
        raise SafeFailure(error_prefix + "_MIME_MISMATCH")
    if detected_image_dimensions(data, expected_mime) != expected_dimensions:
        raise SafeFailure(error_prefix + "_DIMENSIONS_MISMATCH")


def verify_local_asset(
    relative_path: object,
    expected_sha256: str,
    expected_mime: str,
    expected_dimensions: tuple[int, int],
    expected_bytes: int | None,
    error_prefix: str,
) -> None:
    if not isinstance(relative_path, str):
        raise SafeFailure(error_prefix + "_PATH_INVALID")
    path = (PACKAGE_ROOT / relative_path).resolve()
    try:
        path.relative_to(PACKAGE_ROOT.resolve())
    except ValueError as exc:
        raise SafeFailure(error_prefix + "_PATH_OUTSIDE_PACKAGE") from exc
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SafeFailure(error_prefix + "_UNREADABLE") from exc
    validate_asset_bytes(
        data, expected_sha256, expected_mime, expected_dimensions,
        expected_bytes, error_prefix
    )


def approved_cost_hkd(contract: dict) -> tuple[Decimal, Decimal]:
    try:
        approval = contract["approval"]
        rate = Decimal(approval["rate_usd_per_second"])
        fx = Decimal(approval["planning_fx_hkd_per_usd"])
        cap = Decimal(approval["cost_cap_hkd"])
        declared_estimate = Decimal(approval["estimated_hkd"])
        duration = Decimal(contract["request"]["parameters"]["duration"])
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise SafeFailure("LOCAL_APPROVAL_COST_SCHEMA_INVALID") from exc
    if rate != Decimal("0.041256") or fx != Decimal("7.8"):
        raise SafeFailure("LOCAL_APPROVAL_COST_RATE_MISMATCH")
    calculated = rate * duration * fx
    rounded = calculated.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if rounded != declared_estimate or rounded != Decimal("1.61"):
        raise SafeFailure("LOCAL_APPROVAL_COST_ESTIMATE_MISMATCH")
    if calculated > cap:
        raise SafeFailure("LOCAL_APPROVAL_COST_CAP_EXCEEDED")
    if cap != Decimal("5.00"):
        raise SafeFailure("LOCAL_APPROVAL_COST_CAP_MISMATCH")
    return calculated, cap


def load_contract(verify_local_assets: bool = False) -> dict:
    actual_request_sha256 = request_file_sha256()
    if not SHA256_PATTERN.fullmatch(EXPECTED_REQUEST_SHA256):
        raise SafeFailure("LOCAL_EXPECTED_REQUEST_SHA256_INVALID")
    if actual_request_sha256 != EXPECTED_REQUEST_SHA256:
        raise SafeFailure("LOCAL_REQUEST_SHA256_MISMATCH")

    try:
        contract = json.loads(REQUEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SafeFailure("LOCAL_REQUEST_FILE_INVALID") from exc

    try:
        request = contract["request"]
        media = request["input"]["media"]
        parameters = request["parameters"]
        first_frame_sha256 = contract["first_frame_sha256"]
        source_first_frame_sha256 = contract["source_first_frame_sha256"]
    except (KeyError, TypeError) as exc:
        raise SafeFailure("LOCAL_REQUEST_SCHEMA_INVALID") from exc

    identity = {"creative_id": "city-canvas-paper-aperture-proof-v03"}
    if any(contract.get(key) != value for key, value in identity.items()):
        raise SafeFailure("LOCAL_REQUEST_IDENTITY_MISMATCH")
    if contract.get("status") != "APPROVED_FOR_ONE_PAID_SUBMISSION":
        raise SafeFailure("LOCAL_REQUEST_STATUS_MISMATCH")
    if request.get("model") != MODEL:
        raise SafeFailure("LOCAL_MODEL_MISMATCH")
    if media != [{"type": "first_frame", "url": RUNTIME_MEDIA_PLACEHOLDER}]:
        raise SafeFailure("LOCAL_MEDIA_TEMPLATE_INVALID")
    required_parameters = {
        "resolution": "480P",
        "ratio": "9:16",
        "duration": 5,
        "audio": False,
        "prompt_extend": False,
        "watermark": False,
    }
    if parameters != required_parameters:
        raise SafeFailure("LOCAL_PARAMETERS_MISMATCH")
    prompt = request["input"].get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise SafeFailure("LOCAL_PROMPT_INVALID")
    required_prompt_terms = (
        "same daylight Hong Kong street after rain",
        "golden paper poster remains attached to its kiosk",
        "single green tram on the right moves slowly",
        "camera dollies forward toward the existing aperture",
        "decorative campaign geometry, not an official logo",
        "No orange brand paper",
        "not a pan or zoom applied to a frozen still",
    )
    if any(term not in prompt for term in required_prompt_terms):
        raise SafeFailure("LOCAL_PROMPT_SCOPE_MISMATCH")

    if (
        source_first_frame_sha256 != SOURCE_FRAME_SHA256
        or contract.get("source_first_frame")
        != "assets/StarbayCityCanvas_Starbay_2026-10-15_PNG_Keyframe01_SourceCopy_v03.png"
    ):
        raise SafeFailure("LOCAL_SOURCE_FIRST_FRAME_METADATA_MISMATCH")
    if (
        first_frame_sha256 != TRANSPORT_FRAME_SHA256
        or contract.get("transport_first_frame")
        != "assets/StarbayCityCanvas_Starbay_2026-10-15_JPG_S01FirstFrame480x854_Transport_v03.jpg"
    ):
        raise SafeFailure("LOCAL_FIRST_FRAME_METADATA_MISMATCH")
    if contract.get("maximum_submissions") != 1:
        raise SafeFailure("LOCAL_MAXIMUM_SUBMISSIONS_MISMATCH")
    if contract.get("automatic_paid_retries") != 0:
        raise SafeFailure("LOCAL_AUTOMATIC_PAID_RETRIES_MISMATCH")
    if contract.get("authorization") != "GRANTED":
        raise SafeFailure("LOCAL_AUTHORIZATION_STATE_MISMATCH")
    if contract.get("expected_end_frame_bound") is not False:
        raise SafeFailure("LOCAL_END_FRAME_SCOPE_MISMATCH")
    approval = contract.get("approval")
    required_approval = {
        "approved_by": "Zachary Chan",
        "approved_date": "2026-10-15",
        "scope": "S01 WAN3 image-to-video proof only",
        "model": "wan3.0-video",
        "resolution": "480P",
        "ratio": "9:16",
        "duration_seconds": 5,
        "audio": False,
        "source_mode": "first_frame_only",
        "end_frame_bound": False,
        "maximum_submissions": 1,
        "automatic_paid_retries": 0,
        "rate_usd_per_second": "0.041256",
        "planning_fx_hkd_per_usd": "7.8",
        "estimated_hkd": "1.61",
        "cost_cap_hkd": "5.00",
        "creative_payload_changed": False,
        "result_requirement": "show resulting video",
    }
    if approval != required_approval:
        raise SafeFailure("LOCAL_APPROVAL_SCOPE_MISMATCH")
    approved_cost_hkd(contract)
    if verify_local_assets:
        verify_local_asset(
            contract.get("source_first_frame"), SOURCE_FRAME_SHA256,
            "image/png", SOURCE_FRAME_DIMENSIONS, None, "LOCAL_SOURCE_FIRST_FRAME"
        )
        verify_local_asset(
            contract.get("transport_first_frame"), TRANSPORT_FRAME_SHA256,
            "image/jpeg", TRANSPORT_FRAME_DIMENSIONS, TRANSPORT_FRAME_BYTES,
            "LOCAL_FIRST_FRAME"
        )
    return contract


def load_binding() -> tuple[str, str]:
    host = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_HOST", "").strip()
    key = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_KEY", "")
    if host != EXPECTED_API_HOST:
        raise SafeFailure("BINDING_HOST_INVALID")
    if not key or any(character.isspace() for character in key):
        raise SafeFailure("BINDING_SECRET_MISSING_OR_MALFORMED")
    return host, key


def detected_image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def ensure_public_https(url: str) -> urllib.parse.SplitResult:
    parts = urllib.parse.urlsplit(url)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.fragment
    ):
        raise SafeFailure("FIRST_FRAME_URL_NOT_PUBLIC_HTTPS")
    try:
        addresses = socket.getaddrinfo(parts.hostname, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SafeFailure("FIRST_FRAME_HOST_RESOLUTION_FAILED") from exc
    for address in addresses:
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise SafeFailure("FIRST_FRAME_HOST_NOT_PUBLIC")
    return parts


def fetch_first_frame(url: str) -> bytes:
    ensure_public_https(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": "StarbayCityCanvas-WanHK-S01-Proof/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            ensure_public_https(response.geturl())
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_IMAGE_BYTES:
                raise SafeFailure("FIRST_FRAME_SIZE_INVALID")
            data = response.read(MAX_IMAGE_BYTES + 1)
    except SafeFailure:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SafeFailure("FIRST_FRAME_DOWNLOAD_FAILED") from exc
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise SafeFailure("FIRST_FRAME_SIZE_INVALID")
    return data


def event_first_frame_base64() -> str:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        return ""
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        encoded = event.get("inputs", {}).get("first_frame_base64", "")
    except (OSError, ValueError, AttributeError) as exc:
        raise SafeFailure("WORKFLOW_EVENT_INPUT_INVALID") from exc
    if not isinstance(encoded, str):
        raise SafeFailure("FIRST_FRAME_BASE64_INVALID")
    return encoded


def load_first_frame(contract: dict) -> tuple[bytes, str, str]:
    encoded = event_first_frame_base64()
    url = os.environ.get("WAN_FIRST_FRAME_URL", "").strip()
    if bool(encoded) == bool(url):
        raise SafeFailure("EXACTLY_ONE_FIRST_FRAME_TRANSPORT_REQUIRED")
    if encoded:
        if len(encoded) > MAX_EVENT_IMAGE_CHARACTERS:
            raise SafeFailure("FIRST_FRAME_BASE64_TOO_LARGE")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise SafeFailure("FIRST_FRAME_BASE64_INVALID") from exc
        transport = "WORKFLOW_INPUT_BASE64"
    else:
        data = fetch_first_frame(url)
        transport = "PUBLIC_HTTPS"

    if not data or len(data) > MAX_IMAGE_BYTES:
        raise SafeFailure("FIRST_FRAME_SIZE_INVALID")
    mime = detected_image_mime(data)
    if mime is None:
        raise SafeFailure("FIRST_FRAME_FORMAT_INVALID")
    if mime != "image/jpeg":
        raise SafeFailure("FIRST_FRAME_MIME_MISMATCH")
    if hashlib.sha256(data).hexdigest() != contract["first_frame_sha256"]:
        raise SafeFailure("FIRST_FRAME_SHA256_MISMATCH")
    if len(data) != TRANSPORT_FRAME_BYTES:
        raise SafeFailure("FIRST_FRAME_BYTE_COUNT_MISMATCH")
    if detected_image_dimensions(data, mime) != TRANSPORT_FRAME_DIMENSIONS:
        raise SafeFailure("FIRST_FRAME_DIMENSIONS_MISMATCH")
    return data, mime, transport


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


def base_receipt(mode: str, host: str, contract: dict) -> dict:
    return {
        "project": "StarbayCityCanvas",
        "client": "Starbay Group",
        "creative_id": contract["creative_id"],
        "model": MODEL,
        "region": "China (Hong Kong)",
        "deployment_scope": "Global",
        "mode": mode,
        "api_host": host,
        "parameters": {
            "resolution": "480P",
            "ratio": "9:16",
            "duration": 5,
            "audio": False,
            "prompt_extend": False,
            "watermark": False,
        },
        "source": {
            "request_file": REQUEST_FILE.name,
            "request_sha256": EXPECTED_REQUEST_SHA256,
            "first_frame_sha256": contract["first_frame_sha256"],
            "first_frame_mime": "image/jpeg",
            "first_frame_dimensions": "480x854",
            "first_frame_bytes": TRANSPORT_FRAME_BYTES,
            "source_first_frame_sha256": contract["source_first_frame_sha256"],
            "source_first_frame_mime": "image/png",
            "source_first_frame_dimensions": "941x1672",
        },
        "authorization": contract["authorization"],
        "approval": {
            "approved_by": contract["approval"]["approved_by"],
            "approved_date": contract["approval"]["approved_date"],
            "scope": contract["approval"]["scope"],
            "result_requirement": contract["approval"]["result_requirement"],
        },
        "maximum_submissions": contract["maximum_submissions"],
        "automatic_paid_retries": contract["automatic_paid_retries"],
        "planning_cost": {
            "rate_usd_per_second": "0.041256",
            "duration_seconds": 5,
            "planning_fx_hkd_per_usd": "7.8",
            "estimated_hkd": "1.61",
            "one_shot_cap_hkd": "5.00",
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
    print("SUBMITTED task_id=" + task_id, flush=True)
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
            url, headers={"User-Agent": "StarbayCityCanvas-WanHK-S01-Proof/1.0"}
        )
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open(
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
        temporary.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        temporary.unlink(missing_ok=True)
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
    for _ in range(100):
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
        allowed_states = {
            "PENDING",
            "RUNNING",
            "SUCCEEDED",
            "FAILED",
            "CANCELED",
            "UNKNOWN",
        }
        if state not in allowed_states:
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
            print("DOWNLOADED " + output_path.name)
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
        time.sleep(15)

    receipt["status"] = "POLL_WINDOW_ENDED_RESUME_SAME_TASK"
    receipt["updated_utc"] = utc_now()
    write_json(receipt_path, receipt)
    raise SafeFailure("POLL_WINDOW_ENDED_RESUME_SAME_TASK")


def frame_rate_as_float(value: object) -> float:
    if not isinstance(value, str) or "/" not in value:
        raise SafeFailure("VIDEO_FRAME_RATE_INVALID")
    numerator_text, denominator_text = value.split("/", 1)
    try:
        numerator = int(numerator_text)
        denominator = int(denominator_text)
    except ValueError as exc:
        raise SafeFailure("VIDEO_FRAME_RATE_INVALID") from exc
    if denominator == 0:
        raise SafeFailure("VIDEO_FRAME_RATE_INVALID")
    return numerator / denominator


def verify_video(path: Path) -> None:
    if not path.is_file() or path.name != OUTPUT_NAME:
        raise SafeFailure("VIDEO_VALIDATION_TARGET_INVALID")
    ensure_validation_tools()
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=index,codec_type,codec_name,width,height,r_frame_rate,avg_frame_rate:format=duration",
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
        if audio_streams:
            raise SafeFailure("VIDEO_AUDIO_STREAM_PRESENT")
        stream = video_streams[0]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(metadata["format"]["duration"])
        frame_rate = frame_rate_as_float(stream.get("avg_frame_rate"))
        if width >= height or min(width, height) != 480:
            raise SafeFailure("VIDEO_RESOLUTION_NOT_480P_PORTRAIT")
        if not 4.5 <= duration <= 5.5:
            raise SafeFailure("VIDEO_DURATION_NOT_5_SECONDS")
        if abs(frame_rate - 30.0) > 0.01:
            raise SafeFailure("VIDEO_FRAME_RATE_NOT_30_FPS")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
            check=True,
            capture_output=True,
            timeout=180,
        )
    except SafeFailure:
        raise
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        KeyError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise SafeFailure("FFPROBE_OR_FFMPEG_VALIDATION_FAILED") from exc

    validation = {
        "status": "FFPROBE_FFMPEG_NO_AUDIO_VALIDATED",
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "video_codec": stream.get("codec_name"),
        "frame_rate": stream.get("avg_frame_rate"),
        "frame_rate_fps": frame_rate,
        "audio_stream_count": len(audio_streams),
        "validated_utc": utc_now(),
    }
    write_json(path.parent / VALIDATION_NAME, validation)
    receipt_path = path.parent / RECEIPT_NAME
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            receipt = None
        if isinstance(receipt, dict):
            receipt["status"] = "DOWNLOADED_AND_FFMPEG_VALIDATED"
            receipt["updated_utc"] = utc_now()
            write_json(receipt_path, receipt)
    print("FFPROBE_FFMPEG_NO_AUDIO_VALIDATED")


def validate_generate_preflight(
    contract: dict,
    output_dir: Path,
    confirmation: str,
    attempt_text: str,
) -> None:
    if contract.get("authorization") != "GRANTED":
        raise SafeFailure("PAID_GENERATION_NOT_AUTHORIZED")
    if contract.get("status") != "APPROVED_FOR_ONE_PAID_SUBMISSION":
        raise SafeFailure("PAID_GENERATION_STATUS_NOT_APPROVED")
    approved_cost_hkd(contract)
    if (output_dir / RECEIPT_NAME).exists() or (output_dir / OUTPUT_NAME).exists():
        raise SafeFailure("DUPLICATE_GUARD_EXISTING_EVIDENCE")
    try:
        attempt = int(attempt_text)
    except ValueError as exc:
        raise SafeFailure("GITHUB_RUN_ATTEMPT_INVALID") from exc
    if attempt != 1:
        raise SafeFailure("GENERATE_REFUSED_ON_RERUN_ATTEMPT")
    if confirmation != GENERATE_CONFIRMATION:
        raise SafeFailure("CITY_CANVAS_S01_V04_CONFIRMATION_REQUIRED")


def run_mode(mode: str, output_dir: Path) -> None:
    contract = load_contract()
    if mode == "generate":
        validate_generate_preflight(
            contract,
            output_dir,
            os.environ.get("WAN_GENERATE_CONFIRMATION", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        )
    if mode in {"generate", "resume"}:
        ensure_validation_tools()
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / RECEIPT_NAME

    if mode == "check-binding":
        receipt = base_receipt(mode, host, contract)
        receipt["status"] = "BINDING_PRESENT_NOT_API_VERIFIED"
        write_json(receipt_path, receipt)
        print("BINDING_PRESENT_NOT_API_VERIFIED; no API request made")
        return

    if mode == "generate":
        first_frame, first_frame_mime, transport = load_first_frame(contract)
        payload = copy.deepcopy(contract["request"])
        payload["input"]["media"][0]["url"] = (
            "data:"
            + first_frame_mime
            + ";base64,"
            + base64.b64encode(first_frame).decode("ascii")
        )
        receipt = base_receipt(mode, host, contract)
        receipt.update(
            {
                "status": "FIRST_FRAME_SHA256_VERIFIED",
                "verified_first_frame_sha256": hashlib.sha256(
                    first_frame
                ).hexdigest(),
                "first_frame_transport": transport,
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
            output_dir / OUTPUT_NAME,
        )
        return

    task_id = valid_uuid(os.environ.get("WAN_RESUME_TASK_ID", ""))
    if not task_id:
        raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SafeFailure("RESUME_RECEIPT_INVALID") from exc
        if not isinstance(receipt, dict):
            raise SafeFailure("RESUME_RECEIPT_INVALID")
        prior_task_id = receipt.get("task_id")
        if prior_task_id is not None and prior_task_id != task_id:
            raise SafeFailure("RESUME_TASK_ID_MISMATCH")
    else:
        receipt = base_receipt(mode, host, contract)
    receipt.update({"task_id": task_id, "mode": "resume", "status": "RESUME_QUERY_STARTING"})
    write_json(receipt_path, receipt)
    poll(
        host,
        key,
        task_id,
        receipt_path,
        receipt,
        output_dir / OUTPUT_NAME,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["check-binding", "generate", "resume"],
        default="check-binding",
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output-city-canvas-s01-approved-v04")
    )
    parser.add_argument("--offline-validate", action="store_true")
    parser.add_argument("--verify-output", type=Path)
    args = parser.parse_args()
    try:
        if args.offline_validate:
            load_contract(verify_local_assets=True)
            print("OFFLINE_CONTRACT_AND_LOCAL_ASSETS_VALID")
            return 0
        if args.verify_output is not None:
            verify_video(args.verify_output.resolve())
            return 0
        run_mode(args.mode, args.output_dir.resolve())
        return 0
    except SafeFailure as failure:
        print("ERROR " + failure.code, file=sys.stderr)
        return 1
    except Exception:
        print("ERROR UNEXPECTED_LOCAL_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
