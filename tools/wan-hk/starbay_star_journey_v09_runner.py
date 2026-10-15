#!/usr/bin/env python3
"""Pinned approved eight-shot WAN executor for StarbayStarJourney v09.

The approved contract records the direct user HKD20 bounded approval.
Approval metadata and the exact provider inputs are pinned by SHA256. Provider requests contain
only the pinned request payload plus locally verified first/last-frame data
URIs. Approval metadata is never sent to the provider.
"""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
from decimal import Decimal, InvalidOperation
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
CONTRACT_FILE = ROOT / "StarbayStarJourney_Starbay_2026-10-15_JSON_ExecutorContract_Approved_v09.json"
EXPECTED_CONTRACT_SHA256 = "de5d446787abb6a93c1e94ae49ee5673e880fe195880b8700e3c6e8cfa9206ba"
DEFAULT_ASSET_ROOT = ROOT / "starbay-star-journey-v09"
MODEL = "wan3.0-video"
EXPECTED_API_HOST = "ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com"
FIRST_FRAME_PLACEHOLDER = "__RUNTIME_HASH_VERIFIED_FIRST_FRAME_DATA_URI__"
LAST_FRAME_PLACEHOLDER = "__RUNTIME_HASH_VERIFIED_LAST_FRAME_DATA_URI__"
SHOT_IDS = tuple(f"S{number:02d}" for number in range(1, 9))
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,80}")
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


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def safe_api_code(value: object, fallback: str) -> str:
    if isinstance(value, str) and SAFE_CODE_PATTERN.fullmatch(value):
        return value
    return fallback


def valid_uuid(value: object) -> str | None:
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def safe_relative_path(root: Path, relative: object, code: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise SafeFailure(code + "_PATH_INVALID")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise SafeFailure(code + "_PATH_OUTSIDE_ASSET_ROOT") from exc
    return path


def detected_image_mime(data: bytes) -> str | None:
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if detected_image_mime(data) != "image/webp":
        return None
    position = 12
    while position + 8 <= len(data):
        chunk = data[position : position + 4]
        size = int.from_bytes(data[position + 4 : position + 8], "little")
        payload = data[position + 8 : position + 8 + size]
        if len(payload) != size:
            return None
        if chunk == b"VP8X" and size >= 10:
            width = 1 + int.from_bytes(payload[4:7], "little")
            height = 1 + int.from_bytes(payload[7:10], "little")
            return width, height
        if chunk == b"VP8 " and size >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            width = int.from_bytes(payload[6:8], "little") & 0x3FFF
            height = int.from_bytes(payload[8:10], "little") & 0x3FFF
            return width, height
        if chunk == b"VP8L" and size >= 5 and payload[0] == 0x2F:
            bits = int.from_bytes(payload[1:5], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        position += 8 + size + (size % 2)
    return None


def validate_frame_bytes(data: bytes, metadata: dict, code: str) -> None:
    if sha256_bytes(data) != metadata.get("sha256"):
        raise SafeFailure(code + "_SHA256_MISMATCH")
    if len(data) != metadata.get("bytes"):
        raise SafeFailure(code + "_BYTE_COUNT_MISMATCH")
    if detected_image_mime(data) != metadata.get("mime"):
        raise SafeFailure(code + "_MIME_MISMATCH")
    dimensions = metadata.get("dimensions")
    if not isinstance(dimensions, list) or len(dimensions) != 2:
        raise SafeFailure(code + "_DIMENSIONS_METADATA_INVALID")
    if webp_dimensions(data) != tuple(dimensions):
        raise SafeFailure(code + "_DIMENSIONS_MISMATCH")


def read_pinned_file(root: Path, metadata: dict, code: str) -> bytes:
    path = safe_relative_path(root, metadata.get("path"), code)
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise SafeFailure(code + "_UNREADABLE") from exc
    return data


def expected_parameters() -> dict:
    return {
        "resolution": "480P",
        "ratio": "9:16",
        "duration": 5,
        "audio": False,
        "prompt_extend": False,
        "watermark": False,
    }


def expected_media() -> list[dict]:
    return [
        {"type": "first_frame", "url": FIRST_FRAME_PLACEHOLDER},
        {"type": "last_frame", "url": LAST_FRAME_PLACEHOLDER},
    ]


def calculated_batch_cost(contract: dict) -> tuple[Decimal, Decimal]:
    try:
        approval = contract["approval"]
        rate = Decimal(approval["rate_usd_per_second"])
        fx = Decimal(approval["planning_fx_hkd_per_usd"])
        seconds = Decimal(approval["maximum_generated_seconds"])
        declared_usd = Decimal(approval["estimated_usd"])
        declared_hkd = Decimal(approval["estimated_hkd"])
        cap = Decimal(approval["cost_cap_hkd"])
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise SafeFailure("CONTRACT_COST_SCHEMA_INVALID") from exc
    if rate != Decimal("0.041256") or fx != Decimal("7.8") or seconds != Decimal("40"):
        raise SafeFailure("CONTRACT_COST_BASIS_MISMATCH")
    calculated_usd = rate * seconds
    calculated_hkd = calculated_usd * fx
    if calculated_usd != declared_usd or calculated_hkd != declared_hkd:
        raise SafeFailure("CONTRACT_COST_ESTIMATE_MISMATCH")
    if calculated_hkd > cap:
        raise SafeFailure("CONTRACT_COST_CAP_EXCEEDED")
    if cap != Decimal("20.00"):
        raise SafeFailure("CONTRACT_COST_CAP_MISMATCH")
    return calculated_hkd, cap


def validate_contract_shape(contract: dict) -> None:
    if contract.get("schema_version") != 1:
        raise SafeFailure("CONTRACT_SCHEMA_VERSION_INVALID")
    identity = {
        "project": "StarbayStarJourney",
        "client": "STARBAY / 灣星文化",
        "version": "v09",
    }
    if any(contract.get(key) != value for key, value in identity.items()):
        raise SafeFailure("CONTRACT_IDENTITY_MISMATCH")
    state = (contract.get("status"), contract.get("authorization"))
    if state not in {
        ("CANDIDATE_PAID_AUTHORIZATION_PENDING", "PENDING"),
        ("APPROVED_FOR_EIGHT_SHOT_BATCH", "GRANTED"),
    }:
        raise SafeFailure("CONTRACT_AUTHORIZATION_STATE_INVALID")
    approval = contract.get("approval")
    if not isinstance(approval, dict):
        raise SafeFailure("CONTRACT_APPROVAL_INVALID")
    if state[1] == "PENDING":
        if approval.get("approved_by") is not None or approval.get("approved_date") is not None:
            raise SafeFailure("PENDING_CONTRACT_MUST_NOT_NAME_APPROVER")
    elif not approval.get("approved_by") or not approval.get("approved_date"):
        raise SafeFailure("GRANTED_CONTRACT_APPROVAL_METADATA_REQUIRED")
    fixed_approval = {
        "maximum_total_submissions": 8,
        "maximum_per_shot_submissions": 1,
        "maximum_generated_seconds": 40,
        "automatic_paid_retries": 0,
    }
    if any(approval.get(key) != value for key, value in fixed_approval.items()):
        raise SafeFailure("CONTRACT_APPROVAL_SCOPE_MISMATCH")
    calculated_batch_cost(contract)
    provider = contract.get("provider", {})
    if provider.get("model") != MODEL or provider.get("api_host") != EXPECTED_API_HOST:
        raise SafeFailure("CONTRACT_PROVIDER_MISMATCH")
    if provider.get("api_key_binding") != "ALIYUN_MODEL_STUDIO_HK_API_KEY":
        raise SafeFailure("CONTRACT_KEY_BINDING_MISMATCH")
    if provider.get("api_host_binding") != "ALIYUN_MODEL_STUDIO_HK_API_HOST":
        raise SafeFailure("CONTRACT_HOST_BINDING_MISMATCH")
    if contract.get("request_parameters") != expected_parameters():
        raise SafeFailure("CONTRACT_PARAMETERS_MISMATCH")
    if contract.get("runtime_media_placeholders") != expected_media():
        raise SafeFailure("CONTRACT_MEDIA_PLACEHOLDERS_MISMATCH")
    execution = contract.get("execution", {})
    if execution.get("concurrency_group") != "wan-hk-shot04-paid-generation":
        raise SafeFailure("CONTRACT_CONCURRENCY_MISMATCH")
    if execution.get("run_attempt_required") != 1:
        raise SafeFailure("CONTRACT_RUN_ATTEMPT_MISMATCH")

    frames = contract.get("frames")
    shots = contract.get("shots")
    if not isinstance(frames, dict) or len(frames) != 9:
        raise SafeFailure("CONTRACT_FRAME_SET_INVALID")
    if not isinstance(shots, list) or [shot.get("id") for shot in shots] != list(SHOT_IDS):
        raise SafeFailure("CONTRACT_SHOT_SET_INVALID")
    if sum(frame.get("bytes", 0) for frame in frames.values()) != 651_202:
        raise SafeFailure("CONTRACT_FRAME_TOTAL_BYTES_MISMATCH")
    for number, shot in enumerate(shots, start=1):
        shot_id = f"S{number:02d}"
        if shot.get("id") != shot_id:
            raise SafeFailure("CONTRACT_SHOT_ORDER_INVALID")
        if shot.get("first_frame_id") not in frames or shot.get("last_frame_id") not in frames:
            raise SafeFailure("CONTRACT_SHOT_FRAME_REFERENCE_INVALID")
        if not SHA256_PATTERN.fullmatch(str(shot.get("request_sha256", ""))):
            raise SafeFailure("CONTRACT_REQUEST_SHA256_INVALID")
        if shot_id not in str(shot.get("request_path", "")):
            raise SafeFailure("CONTRACT_REQUEST_PATH_SHOT_MISMATCH")
        if shot_id not in str(shot.get("output_name", "")):
            raise SafeFailure("CONTRACT_OUTPUT_NAME_SHOT_MISMATCH")


def validate_request_payload(request: object, code: str) -> dict:
    if not isinstance(request, dict):
        raise SafeFailure(code + "_NOT_OBJECT")
    if set(request) != {"model", "input", "parameters"}:
        raise SafeFailure(code + "_TOP_LEVEL_KEYS_INVALID")
    if request.get("model") != MODEL:
        raise SafeFailure(code + "_MODEL_MISMATCH")
    if request.get("parameters") != expected_parameters():
        raise SafeFailure(code + "_PARAMETERS_MISMATCH")
    input_value = request.get("input")
    if not isinstance(input_value, dict) or set(input_value) != {"prompt", "media"}:
        raise SafeFailure(code + "_INPUT_KEYS_INVALID")
    prompt = input_value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise SafeFailure(code + "_PROMPT_INVALID")
    if input_value.get("media") != expected_media():
        raise SafeFailure(code + "_MEDIA_TEMPLATE_INVALID")
    return request


def load_contract(asset_root: Path = DEFAULT_ASSET_ROOT, verify_files: bool = True) -> dict:
    try:
        raw = CONTRACT_FILE.read_bytes()
        contract = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("CONTRACT_FILE_INVALID") from exc
    if sha256_bytes(raw) != EXPECTED_CONTRACT_SHA256:
        raise SafeFailure("CONTRACT_SHA256_MISMATCH_REPIN_REQUIRED")
    if not isinstance(contract, dict):
        raise SafeFailure("CONTRACT_FILE_INVALID")
    validate_contract_shape(contract)
    if not verify_files:
        return contract

    frames = contract["frames"]
    for frame_id, metadata in frames.items():
        data = read_pinned_file(asset_root, metadata, "FRAME_" + frame_id.upper())
        validate_frame_bytes(data, metadata, "FRAME_" + frame_id.upper())
    for shot in contract["shots"]:
        code = "REQUEST_" + shot["id"]
        path = safe_relative_path(asset_root, shot["request_path"], code)
        try:
            raw_request = path.read_bytes()
            request = json.loads(raw_request.decode("utf-8"))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise SafeFailure(code + "_FILE_INVALID") from exc
        if sha256_bytes(raw_request) != shot["request_sha256"]:
            raise SafeFailure(code + "_SHA256_MISMATCH")
        validate_request_payload(request, code)
    return contract


def select_shot(contract: dict, shot_id: str) -> dict:
    if shot_id not in SHOT_IDS:
        raise SafeFailure("SHOT_ID_INVALID")
    return next(shot for shot in contract["shots"] if shot["id"] == shot_id)


def expected_confirmation(shot_id: str) -> str:
    return f"GENERATE_STARBAY_STAR_JOURNEY_V09_{shot_id}_ONCE"


def receipt_name(shot_id: str) -> str:
    return f"starbay-star-journey-v09-{shot_id.lower()}-receipt.json"


def validation_name(shot_id: str) -> str:
    return f"starbay-star-journey-v09-{shot_id.lower()}-video-validation.json"


def validate_generate_preflight(
    contract: dict,
    shot: dict,
    output_dir: Path,
    confirmation: str,
    attempt_text: str,
) -> None:
    if contract.get("authorization") != "GRANTED":
        raise SafeFailure("PAID_GENERATION_NOT_AUTHORIZED_CONTRACT_PENDING")
    if contract.get("status") != "APPROVED_FOR_EIGHT_SHOT_BATCH":
        raise SafeFailure("PAID_GENERATION_STATUS_NOT_APPROVED")
    calculated_batch_cost(contract)
    if confirmation != expected_confirmation(shot["id"]):
        raise SafeFailure("SHOT_SPECIFIC_GENERATE_CONFIRMATION_REQUIRED")
    try:
        attempt = int(attempt_text)
    except ValueError as exc:
        raise SafeFailure("GITHUB_RUN_ATTEMPT_INVALID") from exc
    if attempt != 1:
        raise SafeFailure("GENERATE_REFUSED_ON_RERUN_ATTEMPT")
    if (output_dir / receipt_name(shot["id"])).exists() or (
        output_dir / shot["output_name"]
    ).exists():
        raise SafeFailure("DUPLICATE_GUARD_EXISTING_SHOT_EVIDENCE")


def load_binding() -> tuple[str, str]:
    host = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_HOST", "").strip()
    key = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_KEY", "")
    if host != EXPECTED_API_HOST:
        raise SafeFailure("BINDING_HOST_INVALID")
    if not key or any(character.isspace() for character in key):
        raise SafeFailure("BINDING_SECRET_MISSING_OR_MALFORMED")
    return host, key


def load_shot_request(contract: dict, shot: dict, asset_root: Path) -> dict:
    path = safe_relative_path(asset_root, shot["request_path"], "REQUEST_" + shot["id"])
    try:
        raw = path.read_bytes()
        request = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("SHOT_REQUEST_FILE_INVALID") from exc
    if sha256_bytes(raw) != shot["request_sha256"]:
        raise SafeFailure("SHOT_REQUEST_SHA256_MISMATCH")
    return validate_request_payload(request, "SHOT_REQUEST")


def load_frame(contract: dict, frame_id: str, asset_root: Path) -> tuple[bytes, dict]:
    metadata = contract["frames"][frame_id]
    data = read_pinned_file(asset_root, metadata, "FRAME_" + frame_id.upper())
    validate_frame_bytes(data, metadata, "FRAME_" + frame_id.upper())
    return data, metadata


def build_provider_payload(contract: dict, shot: dict, asset_root: Path) -> dict:
    request = copy.deepcopy(load_shot_request(contract, shot, asset_root))
    first_data, first_metadata = load_frame(contract, shot["first_frame_id"], asset_root)
    last_data, last_metadata = load_frame(contract, shot["last_frame_id"], asset_root)
    request["input"]["media"][0]["url"] = (
        "data:" + first_metadata["mime"] + ";base64," + base64.b64encode(first_data).decode("ascii")
    )
    request["input"]["media"][1]["url"] = (
        "data:" + last_metadata["mime"] + ";base64," + base64.b64encode(last_data).decode("ascii")
    )
    return request


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
        headers.update({"Content-Type": "application/json", "X-DashScope-Async": "enable"})
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            status = response.status
            raw = response.read(2 * 1024 * 1024 + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            parsed = json.loads(exc.read(2 * 1024 * 1024 + 1).decode("utf-8"))
            code = safe_api_code(parsed.get("code") if isinstance(parsed, dict) else None, "HTTP_ERROR")
        except (OSError, UnicodeDecodeError, ValueError):
            code = "HTTP_ERROR"
        raise ApiFailure(status, code, 400 <= status < 500) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiFailure(None, "NETWORK_OR_TIMEOUT", False) from None
    if len(raw) > 2 * 1024 * 1024:
        raise ApiFailure(status, "RESPONSE_TOO_LARGE", False)
    return decode_json_response(raw, "RESPONSE_NOT_JSON")


def base_receipt(mode: str, contract: dict, shot: dict, host: str) -> dict:
    first = contract["frames"][shot["first_frame_id"]]
    last = contract["frames"][shot["last_frame_id"]]
    return {
        "project": contract["project"],
        "client": contract["client"],
        "version": contract["version"],
        "shot_id": shot["id"],
        "mode": mode,
        "model": MODEL,
        "api_host": host,
        "authorization": contract["authorization"],
        "approval": {
            "approved_by": contract["approval"]["approved_by"],
            "approved_date": contract["approval"]["approved_date"],
            "scope": contract["approval"]["scope"],
            "batch_cap_hkd": contract["approval"]["cost_cap_hkd"],
        },
        "source": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "request_path": shot["request_path"],
            "request_sha256": shot["request_sha256"],
            "first_frame_id": shot["first_frame_id"],
            "first_frame_sha256": first["sha256"],
            "last_frame_id": shot["last_frame_id"],
            "last_frame_sha256": last["sha256"],
        },
        "maximum_submissions_for_shot": 1,
        "automatic_paid_retries": 0,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "updated_utc": utc_now(),
    }


def record_api_failure(path: Path, receipt: dict, failure: ApiFailure, status: str) -> None:
    receipt.update(
        {
            "status": status,
            "http_status": failure.http_status,
            "safe_error_code": failure.safe_code,
            "updated_utc": utc_now(),
        }
    )
    write_json(path, receipt)


def submit_once(host: str, key: str, payload: dict, path: Path, receipt: dict) -> str:
    receipt.update({"status": "POST_IN_PROGRESS_OUTCOME_UNKNOWN", "updated_utc": utc_now()})
    write_json(path, receipt)
    url = f"https://{host}/api/v1/services/aigc/video-generation/video-synthesis"
    try:
        response = api_json(url, key, payload)
    except ApiFailure as failure:
        status = "POST_REJECTED_NO_TASK_CREATED" if failure.outcome_known else "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY"
        record_api_failure(path, receipt, failure, status)
        raise SafeFailure(status) from None
    task_id = valid_uuid(response.get("output", {}).get("task_id"))
    if not task_id:
        receipt.update(
            {
                "status": "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY",
                "safe_error_code": safe_api_code(response.get("code"), "TASK_ID_MISSING"),
                "updated_utc": utc_now(),
            }
        )
        write_json(path, receipt)
        raise SafeFailure("POST_OUTCOME_UNKNOWN_DO_NOT_RETRY")
    receipt.update({"task_id": task_id, "status": "SUBMITTED", "updated_utc": utc_now()})
    write_json(path, receipt)
    print("SUBMITTED shot_id=" + receipt["shot_id"] + " task_id=" + task_id, flush=True)
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
        request = urllib.request.Request(url, headers={"User-Agent": "StarbayStarJourney-WanHK-v09/1.0"})
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("xb") as output:
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


def poll_get_only(
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
            response = api_json(f"https://{host}/api/v1/tasks/{task_id}", key, payload=None)
        except ApiFailure as failure:
            record_api_failure(receipt_path, receipt, failure, "QUERY_UNAVAILABLE_RESUME_SAME_TASK")
            raise SafeFailure("QUERY_UNAVAILABLE_RESUME_SAME_TASK") from None
        output = response.get("output")
        state = output.get("task_status") if isinstance(output, dict) else None
        if state not in {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}:
            receipt.update({"status": "QUERY_RESPONSE_INVALID_RESUME_SAME_TASK", "updated_utc": utc_now()})
            write_json(receipt_path, receipt)
            raise SafeFailure("QUERY_RESPONSE_INVALID_RESUME_SAME_TASK")
        receipt.update({"task_status": state, "status": "TASK_" + state, "updated_utc": utc_now()})
        write_json(receipt_path, receipt)
        if state == "SUCCEEDED":
            video_url = output.get("video_url")
            if not isinstance(video_url, str):
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
            receipt["safe_error_code"] = safe_api_code(output.get("code"), "NO_SAFE_API_CODE")
            write_json(receipt_path, receipt)
            raise SafeFailure("TASK_" + state)
        time.sleep(15)
    receipt["status"] = "POLL_WINDOW_ENDED_RESUME_SAME_TASK"
    write_json(receipt_path, receipt)
    raise SafeFailure("POLL_WINDOW_ENDED_RESUME_SAME_TASK")


def ensure_validation_tools() -> None:
    if shutil.which("ffprobe") is None:
        raise SafeFailure("FFPROBE_COMMAND_NOT_FOUND")
    if shutil.which("ffmpeg") is None:
        raise SafeFailure("FFMPEG_COMMAND_NOT_FOUND")


def frame_rate_as_float(value: object) -> float:
    if not isinstance(value, str) or "/" not in value:
        raise SafeFailure("VIDEO_FRAME_RATE_INVALID")
    numerator, denominator = value.split("/", 1)
    try:
        denominator_value = int(denominator)
        if denominator_value == 0:
            raise ValueError
        return int(numerator) / denominator_value
    except ValueError as exc:
        raise SafeFailure("VIDEO_FRAME_RATE_INVALID") from exc


def verify_video(path: Path, shot_id: str) -> None:
    if shot_id not in SHOT_IDS or not path.is_file() or shot_id not in path.name:
        raise SafeFailure("VIDEO_VALIDATION_TARGET_INVALID")
    ensure_validation_tools()
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=index,codec_type,codec_name,width,height,avg_frame_rate:format=duration",
                "-of", "json", str(path),
            ],
            check=True, capture_output=True, text=True, timeout=90,
        )
        metadata = json.loads(probe.stdout)
        streams = metadata["streams"]
        video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
        audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
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
            check=True, capture_output=True, timeout=180,
        )
    except SafeFailure:
        raise
    except (
        FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
        KeyError, TypeError, ValueError, json.JSONDecodeError,
    ) as exc:
        raise SafeFailure("FFPROBE_OR_FFMPEG_VALIDATION_FAILED") from exc
    result = {
        "status": "FFPROBE_FFMPEG_NO_AUDIO_VALIDATED",
        "shot_id": shot_id,
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "video_codec": stream.get("codec_name"),
        "frame_rate": stream.get("avg_frame_rate"),
        "frame_rate_fps": frame_rate,
        "audio_stream_count": 0,
        "validated_utc": utc_now(),
    }
    write_json(path.parent / validation_name(shot_id), result)
    receipt_path = path.parent / receipt_name(shot_id)
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            receipt = None
        if isinstance(receipt, dict):
            receipt.update({"status": "DOWNLOADED_AND_FFMPEG_VALIDATED", "updated_utc": utc_now()})
            write_json(receipt_path, receipt)
    print("FFPROBE_FFMPEG_NO_AUDIO_VALIDATED shot_id=" + shot_id)


def run_mode(mode: str, shot_id: str, output_dir: Path, asset_root: Path = DEFAULT_ASSET_ROOT) -> None:
    contract = load_contract(asset_root=asset_root, verify_files=True)
    shot = select_shot(contract, shot_id)
    if mode == "generate":
        validate_generate_preflight(
            contract,
            shot,
            output_dir,
            os.environ.get("WAN_GENERATE_CONFIRMATION", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        )
    if mode in {"generate", "resume"}:
        ensure_validation_tools()
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / receipt_name(shot_id)

    if mode == "check-binding":
        receipt = base_receipt(mode, contract, shot, host)
        receipt["status"] = "BINDING_PRESENT_NOT_API_VERIFIED"
        write_json(receipt_path, receipt)
        print("BINDING_PRESENT_NOT_API_VERIFIED; no API request made")
        return

    if mode == "generate":
        payload = build_provider_payload(contract, shot, asset_root)
        receipt = base_receipt(mode, contract, shot, host)
        receipt["status"] = "PINNED_REQUEST_AND_TWO_FRAMES_SHA256_VERIFIED"
        write_json(receipt_path, receipt)
        task_id = submit_once(host, key, payload, receipt_path, receipt)
        poll_get_only(host, key, task_id, receipt_path, receipt, output_dir / shot["output_name"])
        return

    task_id = valid_uuid(os.environ.get("WAN_RESUME_TASK_ID", ""))
    if not task_id:
        raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SafeFailure("RESUME_RECEIPT_INVALID") from exc
        if not isinstance(receipt, dict) or receipt.get("shot_id") != shot_id:
            raise SafeFailure("RESUME_RECEIPT_INVALID")
        if receipt.get("task_id") not in {None, task_id}:
            raise SafeFailure("RESUME_TASK_ID_MISMATCH")
    else:
        receipt = base_receipt(mode, contract, shot, host)
    receipt.update({"task_id": task_id, "mode": "resume", "status": "RESUME_QUERY_STARTING"})
    write_json(receipt_path, receipt)
    poll_get_only(host, key, task_id, receipt_path, receipt, output_dir / shot["output_name"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["check-binding", "generate", "resume"], default="check-binding")
    parser.add_argument("--shot-id", choices=SHOT_IDS, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("output-starbay-star-journey-v09"))
    parser.add_argument("--offline-validate", action="store_true")
    parser.add_argument("--asset-root", type=Path)
    parser.add_argument("--verify-output", type=Path)
    args = parser.parse_args()
    try:
        if args.offline_validate:
            root = args.asset_root.resolve() if args.asset_root else DEFAULT_ASSET_ROOT
            contract = load_contract(asset_root=root, verify_files=True)
            print("OFFLINE_CONTRACT_REQUESTS_AND_NINE_WEBP_VALID authorization=" + contract["authorization"])
            return 0
        if args.asset_root is not None:
            raise SafeFailure("ASSET_ROOT_OVERRIDE_OFFLINE_ONLY")
        if args.verify_output is not None:
            verify_video(args.verify_output.resolve(), args.shot_id)
            return 0
        run_mode(args.mode, args.shot_id, args.output_dir.resolve())
        return 0
    except SafeFailure as failure:
        print("ERROR " + failure.code, file=sys.stderr)
        return 1
    except Exception:
        print("ERROR UNEXPECTED_LOCAL_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
