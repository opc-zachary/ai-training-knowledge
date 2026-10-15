#!/usr/bin/env python3
"""Pinned WAN HK executor for the approved STARBAY three-segment edit.

One generate invocation can POST exactly one pinned segment.  B must be run
first; A and C additionally require the root writer's post-B usability gate.
Reference video and image bytes are verified before any paid POST.  Resume is
GET-only.  Receipts never contain credentials, base64, raw responses, or signed
result URLs.
"""

from __future__ import annotations

import argparse
import base64
import binascii
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
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parent
CONTRACT_FILE = ROOT / "StarbayThreeCharacter_Starbay_2026-10-15_JSON_ExecutorContract_Approved_v01.json"
EXPECTED_CONTRACT_SHA256 = "7c80e2e9fcbc73e9caec93efcdbe3d77739fefb38344a533fe1527678c1db57f"
MODEL = "wan3.0-video"
EXPECTED_API_HOST = "ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com"
REFERENCE_HOST = "opc-file.promopioneers.cc"
REFERENCE_PATH_PREFIX = "/metaops/starbay/2026/10/"
IMAGE_PLACEHOLDERS = (
    "__RUNTIME_HASH_VERIFIED_IMAGE_1_DATA_URI__",
    "__RUNTIME_HASH_VERIFIED_IMAGE_2_DATA_URI__",
)
SEGMENT_IDS = ("A", "B", "C")
GENERATION_ORDER = ("B", "A", "C")
B_REVIEW_GATE = "B_REVIEWED_USABLE_CONTINUE_APPROVED_BATCH"
MAX_REFERENCE_BYTES = 32 * 1024 * 1024
MAX_RESULT_BYTES = 512 * 1024 * 1024
MAX_BASE64_CHARACTERS = 60_000
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,120}")


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
        raise SafeFailure(code + "_PATH_OUTSIDE_ROOT") from exc
    return path


def detected_image_mime(data: bytes) -> str | None:
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
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


def expected_parameters(duration: int) -> dict:
    return {
        "resolution": "480P",
        "ratio": "9:16",
        "duration": duration,
        "audio": True,
        "prompt_extend": False,
        "watermark": False,
    }


def expected_media(contract: dict, segment_id: str) -> list[dict]:
    segment = contract["segments"][segment_id]
    media = [{"type": "reference_video", "url": segment["reference_video_url"]}]
    for index, _image_id in enumerate(segment["image_ids"]):
        media.append({"type": "reference_image", "url": IMAGE_PLACEHOLDERS[index]})
    return media


def calculated_batch_cost(contract: dict) -> tuple[Decimal, Decimal]:
    try:
        approval = contract["approval"]
        rate = Decimal(approval["rate_usd_per_second"])
        fx = Decimal(approval["planning_fx_hkd_per_usd"])
        input_seconds = Decimal(approval["total_input_video_seconds"])
        output_seconds = Decimal(approval["total_output_seconds"])
        billable_seconds = Decimal(approval["maximum_billable_seconds"])
        declared_usd = Decimal(approval["estimated_usd"])
        declared_hkd = Decimal(approval["estimated_hkd"])
        cap = Decimal(approval["cost_cap_hkd"])
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise SafeFailure("CONTRACT_COST_SCHEMA_INVALID") from exc
    if rate != Decimal("0.041256") or fx != Decimal("7.8"):
        raise SafeFailure("CONTRACT_COST_BASIS_MISMATCH")
    if input_seconds != Decimal("17") or output_seconds != Decimal("17"):
        raise SafeFailure("CONTRACT_DURATION_TOTAL_MISMATCH")
    if billable_seconds != input_seconds + output_seconds or billable_seconds != Decimal("34"):
        raise SafeFailure("CONTRACT_BILLABLE_SECONDS_MISMATCH")
    calculated_usd = rate * billable_seconds
    calculated_hkd = calculated_usd * fx
    if calculated_usd != declared_usd or calculated_hkd != declared_hkd:
        raise SafeFailure("CONTRACT_COST_ESTIMATE_MISMATCH")
    if declared_hkd != Decimal("10.9410912") or cap != Decimal("15.00"):
        raise SafeFailure("CONTRACT_COST_CAP_MISMATCH")
    if declared_hkd > cap:
        raise SafeFailure("CONTRACT_COST_CAP_EXCEEDED")
    return calculated_hkd, cap


def validate_contract_shape(contract: dict) -> None:
    fixed_identity = {
        "schema_version": 1,
        "project": "StarbayThreeCharacterReference",
        "client": "STARBAY / 灣星文化",
        "version": "v01",
        "status": "APPROVED_FOR_THREE_SEGMENT_BATCH",
        "authorization": "GRANTED",
    }
    if any(contract.get(key) != value for key, value in fixed_identity.items()):
        raise SafeFailure("CONTRACT_IDENTITY_OR_AUTHORIZATION_MISMATCH")
    provider = contract.get("provider", {})
    expected_provider = {
        "model": MODEL,
        "api_host": EXPECTED_API_HOST,
        "api_key_binding": "ALIYUN_MODEL_STUDIO_HK_API_KEY",
        "api_host_binding": "ALIYUN_MODEL_STUDIO_HK_API_HOST",
        "repository": "opc-zachary/ai-training-knowledge",
    }
    if any(provider.get(key) != value for key, value in expected_provider.items()):
        raise SafeFailure("CONTRACT_PROVIDER_OR_BINDING_MISMATCH")
    approval = contract.get("approval", {})
    fixed_approval = {
        "approved_by": "Zachary Chan",
        "approval_quote": "批准：整批上限 HK$15，三段各一次，並登記 STARBAY 專用素材路線",
        "maximum_total_submissions": 3,
        "maximum_per_segment_submissions": 1,
        "automatic_paid_retries": 0,
    }
    if any(approval.get(key) != value for key, value in fixed_approval.items()):
        raise SafeFailure("CONTRACT_APPROVAL_SCOPE_MISMATCH")
    if not approval.get("approved_at_utc"):
        raise SafeFailure("CONTRACT_APPROVAL_TIME_REQUIRED")
    calculated_batch_cost(contract)

    transport = contract.get("reference_transport", {})
    if transport.get("scheme") != "https" or transport.get("host") != REFERENCE_HOST:
        raise SafeFailure("CONTRACT_REFERENCE_HOST_MISMATCH")
    if transport.get("path_prefix") != REFERENCE_PATH_PREFIX:
        raise SafeFailure("CONTRACT_REFERENCE_PATH_PREFIX_MISMATCH")

    execution = contract.get("execution", {})
    fixed_execution = {
        "workflow": "manual_only",
        "workflow_file": "wan-hk-starbay-three-character-v01.yml",
        "concurrency_group": "wan-hk-starbay-three-character-v01-paid-generation",
        "github_permissions": "contents:read",
        "run_attempt_required": 1,
        "generation_order": list(GENERATION_ORDER),
        "maximum_provider_posts": 3,
        "maximum_provider_posts_per_run": 1,
    }
    if any(execution.get(key) != value for key, value in fixed_execution.items()):
        raise SafeFailure("CONTRACT_EXECUTION_SCOPE_MISMATCH")
    if not str(execution.get("unknown_post_outcome_policy", "")).startswith("DO_NOT_RETRY"):
        raise SafeFailure("CONTRACT_UNKNOWN_OUTCOME_POLICY_MISMATCH")

    images = contract.get("images")
    if not isinstance(images, dict) or set(images) != {"zijian", "zachary", "channel"}:
        raise SafeFailure("CONTRACT_IMAGE_SET_INVALID")
    for image_id, metadata in images.items():
        try:
            dimensions = metadata["transport_dimensions"]
            byte_count = int(metadata["transport_bytes"])
            base64_count = int(metadata["transport_base64_characters"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SafeFailure("CONTRACT_IMAGE_METADATA_INVALID") from exc
        if metadata.get("transport_mime") != "image/webp":
            raise SafeFailure("CONTRACT_IMAGE_MIME_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get("transport_sha256", ""))):
            raise SafeFailure("CONTRACT_IMAGE_SHA256_INVALID")
        if not isinstance(dimensions, list) or len(dimensions) != 2 or min(dimensions) < 240:
            raise SafeFailure("CONTRACT_IMAGE_DIMENSIONS_INVALID")
        if base64_count != 4 * ((byte_count + 2) // 3) or base64_count >= MAX_BASE64_CHARACTERS:
            raise SafeFailure("CONTRACT_IMAGE_BASE64_SIZE_INVALID")
        if not str(metadata.get("transport_filename", "")).endswith(".webp"):
            raise SafeFailure("CONTRACT_IMAGE_FILENAME_INVALID")

    segments = contract.get("segments")
    if not isinstance(segments, dict) or set(segments) != set(SEGMENT_IDS):
        raise SafeFailure("CONTRACT_SEGMENT_SET_INVALID")
    fixed_segments = {
        "A": (4, 4, 8, "2.5743744", ["zijian"]),
        "B": (8, 8, 16, "5.1487488", ["zachary", "channel"]),
        "C": (5, 5, 10, "3.2179680", ["zijian"]),
    }
    for segment_id, expected in fixed_segments.items():
        segment = segments[segment_id]
        actual = (
            segment.get("duration_seconds"),
            segment.get("input_video_seconds"),
            segment.get("maximum_billable_seconds"),
            segment.get("estimated_hkd"),
            segment.get("image_ids"),
        )
        if actual != expected or segment.get("maximum_submissions") != 1:
            raise SafeFailure("CONTRACT_SEGMENT_SCOPE_MISMATCH")
        if segment.get("confirmation") != f"GENERATE_STARBAY_THREE_CHARACTER_V01_{segment_id}_ONCE":
            raise SafeFailure("CONTRACT_SEGMENT_CONFIRMATION_MISMATCH")
        validate_reference_url(segment.get("reference_video_url"), segment_id)
        if not re.fullmatch(r"[0-9a-f]{64}", str(segment.get("reference_video_sha256", ""))):
            raise SafeFailure("CONTRACT_REFERENCE_SHA256_INVALID")
        if not re.fullmatch(r"[0-9a-f]{64}", str(segment.get("request_sha256", ""))):
            raise SafeFailure("CONTRACT_REQUEST_SHA256_INVALID")
        dimensions = segment.get("reference_video_dimensions")
        if dimensions != [480, 1040]:
            raise SafeFailure("CONTRACT_REFERENCE_DIMENSIONS_INVALID")
        if int(segment.get("reference_video_bytes", 0)) <= 0:
            raise SafeFailure("CONTRACT_REFERENCE_BYTES_INVALID")
        if segment_id not in str(segment.get("output_name", "")):
            raise SafeFailure("CONTRACT_OUTPUT_NAME_SEGMENT_MISMATCH")

    validation = contract.get("output_validation", {})
    expected_validation = {
        "duration_tolerance_seconds": 0.5,
        "short_edge_pixels": 480,
        "portrait_ratio": "9:16",
        "ratio_tolerance": 0.01,
        "minimum_audio_streams": 1,
        "full_decode_required": True,
    }
    if validation != expected_validation:
        raise SafeFailure("CONTRACT_OUTPUT_VALIDATION_MISMATCH")
    excluded = set(contract.get("receipt_policy", {}).get("exclude", []))
    if excluded != {"signed result URLs", "raw provider responses", "API keys", "base64 image data"}:
        raise SafeFailure("CONTRACT_RECEIPT_POLICY_MISMATCH")


def validate_reference_url(value: object, segment_id: str) -> str:
    if not isinstance(value, str):
        raise SafeFailure("REFERENCE_URL_INVALID")
    parts = urllib.parse.urlsplit(value)
    expected_suffix = (
        f"StarbayThreeCharacter_Starbay_2026-10-15_MP4_ReferenceBlock{segment_id}_Internal_v01.mp4"
    )
    if (
        parts.scheme != "https"
        or parts.hostname != REFERENCE_HOST
        or parts.port not in {None, 443}
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or not parts.path.startswith(REFERENCE_PATH_PREFIX)
        or parts.path != REFERENCE_PATH_PREFIX + expected_suffix
    ):
        raise SafeFailure("REFERENCE_URL_OUTSIDE_APPROVED_SCOPE")
    return value


def validate_request_payload(request: object, contract: dict, segment_id: str) -> dict:
    if not isinstance(request, dict) or set(request) != {"model", "input", "parameters"}:
        raise SafeFailure("REQUEST_TOP_LEVEL_KEYS_INVALID")
    segment = contract["segments"][segment_id]
    if request.get("model") != MODEL:
        raise SafeFailure("REQUEST_MODEL_MISMATCH")
    if request.get("parameters") != expected_parameters(segment["duration_seconds"]):
        raise SafeFailure("REQUEST_PARAMETERS_MISMATCH")
    input_value = request.get("input")
    if not isinstance(input_value, dict) or set(input_value) != {"prompt", "media"}:
        raise SafeFailure("REQUEST_INPUT_KEYS_INVALID")
    prompt = input_value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise SafeFailure("REQUEST_PROMPT_INVALID")
    if input_value.get("media") != expected_media(contract, segment_id):
        raise SafeFailure("REQUEST_MEDIA_TEMPLATE_OR_ORDER_INVALID")
    media_types = [item.get("type") for item in input_value["media"] if isinstance(item, dict)]
    if media_types.count("reference_video") != 1:
        raise SafeFailure("REQUEST_REFERENCE_VIDEO_COUNT_INVALID")
    if any(kind not in {"reference_video", "reference_image"} for kind in media_types):
        raise SafeFailure("REQUEST_FORBIDDEN_MEDIA_TYPE")
    return request


def load_request(contract: dict, segment_id: str) -> dict:
    segment = contract["segments"][segment_id]
    path = safe_relative_path(ROOT, segment.get("request_path"), "REQUEST")
    try:
        raw = path.read_bytes()
        request = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("REQUEST_FILE_INVALID") from exc
    if sha256_bytes(raw) != segment.get("request_sha256"):
        raise SafeFailure("REQUEST_SHA256_MISMATCH")
    return validate_request_payload(request, contract, segment_id)


def load_contract() -> dict:
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
    for segment_id in SEGMENT_IDS:
        load_request(contract, segment_id)
    return contract


def validate_image_bytes(data: bytes, metadata: dict, code: str) -> None:
    if sha256_bytes(data) != metadata.get("transport_sha256"):
        raise SafeFailure(code + "_SHA256_MISMATCH")
    if len(data) != metadata.get("transport_bytes"):
        raise SafeFailure(code + "_BYTE_COUNT_MISMATCH")
    if detected_image_mime(data) != metadata.get("transport_mime"):
        raise SafeFailure(code + "_MIME_MISMATCH")
    dimensions = metadata.get("transport_dimensions")
    if webp_dimensions(data) != tuple(dimensions):
        raise SafeFailure(code + "_DIMENSIONS_MISMATCH")
    if min(dimensions) < 240:
        raise SafeFailure(code + "_DIMENSIONS_BELOW_240")


def decode_image_input(encoded: str, metadata: dict, code: str) -> bytes:
    if not encoded or len(encoded) >= MAX_BASE64_CHARACTERS or any(character.isspace() for character in encoded):
        raise SafeFailure(code + "_BASE64_INPUT_INVALID")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SafeFailure(code + "_BASE64_INPUT_INVALID") from exc
    validate_image_bytes(data, metadata, code)
    return data


def read_image_inputs_from_event(event_path: Path) -> tuple[str, str]:
    """Read private image inputs from the local workflow event file only.

    GitHub makes workflow-dispatch inputs available in ``GITHUB_EVENT_PATH``.
    Reading that file avoids copying portrait base64 into a step ``env`` block,
    which GitHub Actions may render in logs.  This function deliberately emits
    no value, event payload, or masking command to stdout/stderr.
    """
    try:
        raw = event_path.read_bytes()
        if len(raw) > 256 * 1024:
            raise SafeFailure("GITHUB_EVENT_FILE_TOO_LARGE")
        event = json.loads(raw.decode("utf-8"))
    except SafeFailure:
        raise
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("GITHUB_EVENT_FILE_INVALID") from exc
    inputs = event.get("inputs") if isinstance(event, dict) else None
    if not isinstance(inputs, dict):
        raise SafeFailure("GITHUB_EVENT_INPUTS_INVALID")
    values: list[str] = []
    for name in ("image_1_base64", "image_2_base64"):
        value = inputs.get(name, "")
        if not isinstance(value, str):
            raise SafeFailure("GITHUB_EVENT_IMAGE_INPUT_TYPE_INVALID")
        if len(value) >= MAX_BASE64_CHARACTERS or any(character.isspace() for character in value):
            raise SafeFailure("GITHUB_EVENT_IMAGE_INPUT_FORMAT_INVALID")
        values.append(value)
    return values[0], values[1]


def runtime_image_inputs() -> tuple[str, str]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SafeFailure("GENERATE_REQUIRES_GITHUB_ACTIONS_EVENT_INPUTS")
    event_path_text = os.environ.get("GITHUB_EVENT_PATH", "")
    event_path = Path(event_path_text)
    if not event_path_text or not event_path.is_absolute():
        raise SafeFailure("GITHUB_EVENT_PATH_INVALID")
    return read_image_inputs_from_event(event_path)


def build_provider_payload(contract: dict, segment_id: str, image_inputs: list[str]) -> dict:
    segment = contract["segments"][segment_id]
    if len(image_inputs) != len(segment["image_ids"]):
        raise SafeFailure("IMAGE_INPUT_COUNT_INVALID")
    request = copy.deepcopy(load_request(contract, segment_id))
    for index, image_id in enumerate(segment["image_ids"]):
        data = decode_image_input(image_inputs[index], contract["images"][image_id], f"IMAGE_{index + 1}")
        request["input"]["media"][index + 1]["url"] = (
            "data:image/webp;base64," + base64.b64encode(data).decode("ascii")
        )
    return request


def ensure_validation_tools() -> None:
    if shutil.which("ffprobe") is None:
        raise SafeFailure("FFPROBE_COMMAND_NOT_FOUND")
    if shutil.which("ffmpeg") is None:
        raise SafeFailure("FFMPEG_COMMAND_NOT_FOUND")


def probe_media(path: Path) -> dict:
    ensure_validation_tools()
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries",
                "stream=index,codec_type,codec_name,width,height,avg_frame_rate:format=duration,size,format_name",
                "-of", "json", str(path),
            ],
            check=True, capture_output=True, text=True, timeout=120,
        )
        metadata = json.loads(result.stdout)
    except (
        FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired,
        ValueError, json.JSONDecodeError,
    ) as exc:
        raise SafeFailure("FFPROBE_FAILED") from exc
    if not isinstance(metadata, dict):
        raise SafeFailure("FFPROBE_RESULT_INVALID")
    return metadata


def validate_reference_video_file(path: Path, contract: dict, segment_id: str) -> dict:
    segment = contract["segments"][segment_id]
    try:
        size = path.stat().st_size
        digest = sha256_bytes(path.read_bytes())
        with path.open("rb") as source:
            header = source.read(64)
    except OSError as exc:
        raise SafeFailure("REFERENCE_VIDEO_UNREADABLE") from exc
    if size != segment["reference_video_bytes"]:
        raise SafeFailure("REFERENCE_VIDEO_BYTE_COUNT_MISMATCH")
    if digest != segment["reference_video_sha256"]:
        raise SafeFailure("REFERENCE_VIDEO_SHA256_MISMATCH")
    if b"ftyp" not in header:
        raise SafeFailure("REFERENCE_VIDEO_NOT_MP4")
    metadata = probe_media(path)
    streams = metadata.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    if len(video_streams) != 1:
        raise SafeFailure("REFERENCE_VIDEO_STREAM_COUNT_INVALID")
    stream = video_streams[0]
    dimensions = [int(stream.get("width", 0)), int(stream.get("height", 0))]
    try:
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SafeFailure("REFERENCE_VIDEO_DURATION_INVALID") from exc
    if dimensions != segment["reference_video_dimensions"]:
        raise SafeFailure("REFERENCE_VIDEO_DIMENSIONS_MISMATCH")
    format_name = str(metadata.get("format", {}).get("format_name", ""))
    if "mp4" not in format_name.split(","):
        raise SafeFailure("REFERENCE_VIDEO_CONTAINER_NOT_MP4")
    if abs(duration - segment["input_video_seconds"]) > 0.05:
        raise SafeFailure("REFERENCE_VIDEO_DURATION_MISMATCH")
    return {
        "url": segment["reference_video_url"],
        "sha256": digest,
        "bytes": size,
        "duration_seconds": duration,
        "dimensions": dimensions,
        "video_codec": stream.get("codec_name"),
    }


def fetch_and_validate_reference(contract: dict, segment_id: str, work_dir: Path) -> dict:
    segment = contract["segments"][segment_id]
    url = validate_reference_url(segment["reference_video_url"], segment_id)
    target = work_dir / f"reference-{segment_id}.mp4"
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "StarbayThreeCharacter-WanHK-v01/1.0"}
        )
        with urllib.request.urlopen(request, timeout=180) as response, target.open("xb") as output:
            final_url = response.geturl()
            if final_url != url:
                raise SafeFailure("REFERENCE_REDIRECT_NOT_EXACT_PINNED_URL")
            content_type = response.headers.get_content_type()
            if content_type != "video/mp4":
                raise SafeFailure("REFERENCE_HTTP_CONTENT_TYPE_NOT_VIDEO_MP4")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_REFERENCE_BYTES:
                    raise SafeFailure("REFERENCE_VIDEO_TOO_LARGE")
                digest.update(chunk)
                output.write(chunk)
    except SafeFailure:
        target.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        target.unlink(missing_ok=True)
        raise SafeFailure("REFERENCE_VIDEO_FETCH_FAILED") from None
    if size != segment["reference_video_bytes"] or digest.hexdigest() != segment["reference_video_sha256"]:
        target.unlink(missing_ok=True)
        raise SafeFailure("REFERENCE_VIDEO_NETWORK_BYTES_OR_SHA256_MISMATCH")
    return validate_reference_video_file(target, contract, segment_id)


def load_binding() -> tuple[str, str]:
    host = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_HOST", "").strip()
    key = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_KEY", "")
    if host != EXPECTED_API_HOST:
        raise SafeFailure("BINDING_HOST_INVALID")
    if not key or any(character.isspace() for character in key):
        raise SafeFailure("BINDING_SECRET_MISSING_OR_MALFORMED")
    return host, key


def decode_json_response(data: bytes, fallback: str) -> dict:
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ApiFailure(None, fallback, False) from exc
    if not isinstance(value, dict):
        raise ApiFailure(None, fallback, False)
    return value


def response_request_id(headers: object, payload: dict) -> str | None:
    candidates = [payload.get("request_id"), payload.get("requestId")]
    if hasattr(headers, "get"):
        candidates.extend([headers.get("x-request-id"), headers.get("x-acs-request-id")])
    for value in candidates:
        if isinstance(value, str) and SAFE_CODE_PATTERN.fullmatch(value):
            return value
    return None


def api_json(url: str, key: str, payload: dict | None = None) -> tuple[dict, str | None]:
    headers = {"Authorization": "Bearer " + key}
    body = None
    if payload is not None:
        headers.update({"Content-Type": "application/json", "X-DashScope-Async": "enable"})
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            status = response.status
            response_headers = response.headers
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
    parsed = decode_json_response(raw, "RESPONSE_NOT_JSON")
    return parsed, response_request_id(response_headers, parsed)


def sanitize_usage(response: dict) -> dict:
    result: dict[str, int | float | str] = {}
    containers = [response.get("usage")]
    output = response.get("output")
    if isinstance(output, dict):
        containers.append(output.get("usage"))
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key, value in container.items():
            if not isinstance(key, str) or not SAFE_CODE_PATTERN.fullmatch(key):
                continue
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                result[key] = value
            elif isinstance(value, str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
                result[key] = value
    return result


def receipt_name(segment_id: str) -> str:
    return f"starbay-three-character-v01-{segment_id.lower()}-receipt.json"


def validation_name(segment_id: str) -> str:
    return f"starbay-three-character-v01-{segment_id.lower()}-video-validation.json"


def base_receipt(mode: str, contract: dict, segment_id: str, host: str) -> dict:
    segment = contract["segments"][segment_id]
    return {
        "project": contract["project"],
        "client": contract["client"],
        "version": contract["version"],
        "segment": segment_id,
        "mode": mode,
        "model": MODEL,
        "api_host": host,
        "authorization": contract["authorization"],
        "approval": {
            "approved_by": contract["approval"]["approved_by"],
            "approved_at_utc": contract["approval"]["approved_at_utc"],
            "approval_quote": contract["approval"]["approval_quote"],
            "batch_cost_cap_hkd": contract["approval"]["cost_cap_hkd"],
            "segment_estimated_hkd": segment["estimated_hkd"],
        },
        "source": {
            "contract_sha256": EXPECTED_CONTRACT_SHA256,
            "request_path": segment["request_path"],
            "request_sha256": segment["request_sha256"],
            "reference_video_url": segment["reference_video_url"],
            "reference_video_sha256": segment["reference_video_sha256"],
            "reference_video_bytes": segment["reference_video_bytes"],
            "image_transport_sha256": [
                contract["images"][image_id]["transport_sha256"] for image_id in segment["image_ids"]
            ],
        },
        "maximum_provider_posts_this_run": 1,
        "automatic_paid_retries": 0,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "updated_utc": utc_now(),
    }


def validate_generate_preflight(
    contract: dict,
    segment_id: str,
    output_dir: Path,
    confirmation: str,
    b_review_gate: str,
    attempt_text: str,
) -> None:
    if contract.get("authorization") != "GRANTED" or contract.get("status") != "APPROVED_FOR_THREE_SEGMENT_BATCH":
        raise SafeFailure("PAID_GENERATION_NOT_AUTHORIZED")
    segment = contract["segments"][segment_id]
    if confirmation != segment["confirmation"]:
        raise SafeFailure("SEGMENT_GENERATE_CONFIRMATION_REQUIRED")
    if attempt_text != "1":
        raise SafeFailure("GENERATE_REQUIRES_GITHUB_RUN_ATTEMPT_1")
    if segment_id in {"A", "C"} and b_review_gate != B_REVIEW_GATE:
        raise SafeFailure("B_USABILITY_REVIEW_GATE_REQUIRED_FOR_A_OR_C")
    calculated_batch_cost(contract)
    segment_cost = (
        Decimal(segment["maximum_billable_seconds"])
        * Decimal(contract["approval"]["rate_usd_per_second"])
        * Decimal(contract["approval"]["planning_fx_hkd_per_usd"])
    )
    if segment_cost != Decimal(segment["estimated_hkd"]):
        raise SafeFailure("SEGMENT_COST_ESTIMATE_MISMATCH")
    if (output_dir / receipt_name(segment_id)).exists() or (output_dir / segment["output_name"]).exists():
        raise SafeFailure("DUPLICATE_GUARD_EXISTING_SEGMENT_EVIDENCE")


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
        response, request_id = api_json(url, key, payload)
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
                "request_id": request_id,
                "updated_utc": utc_now(),
            }
        )
        write_json(path, receipt)
        raise SafeFailure("POST_OUTCOME_UNKNOWN_DO_NOT_RETRY")
    receipt.update(
        {
            "task_id": task_id,
            "request_id": request_id,
            "status": "SUBMITTED",
            "provider_reported_usage": sanitize_usage(response),
            "updated_utc": utc_now(),
        }
    )
    write_json(path, receipt)
    print(f"SUBMITTED segment={receipt['segment']} task_id={task_id}", flush=True)
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
        request = urllib.request.Request(url, headers={"User-Agent": "StarbayThreeCharacter-WanHK-v01/1.0"})
        with urllib.request.urlopen(request, timeout=180) as response, temporary.open("xb") as output:
            final = urllib.parse.urlsplit(response.geturl())
            if final.scheme != "https" or not final.hostname or final.username or final.password:
                raise SafeFailure("RESULT_REDIRECT_INVALID")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_RESULT_BYTES:
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
            response, request_id = api_json(f"https://{host}/api/v1/tasks/{task_id}", key, payload=None)
        except ApiFailure as failure:
            record_api_failure(receipt_path, receipt, failure, "QUERY_UNAVAILABLE_RESUME_SAME_TASK")
            raise SafeFailure("QUERY_UNAVAILABLE_RESUME_SAME_TASK") from None
        output = response.get("output")
        state = output.get("task_status") if isinstance(output, dict) else None
        if state not in {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}:
            receipt.update({"status": "QUERY_RESPONSE_INVALID_RESUME_SAME_TASK", "updated_utc": utc_now()})
            write_json(receipt_path, receipt)
            raise SafeFailure("QUERY_RESPONSE_INVALID_RESUME_SAME_TASK")
        receipt.update(
            {
                "task_status": state,
                "status": "TASK_" + state,
                "last_query_request_id": request_id,
                "provider_reported_usage": sanitize_usage(response),
                "updated_utc": utc_now(),
            }
        )
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


def verify_output_video(path: Path, contract: dict, segment_id: str) -> dict:
    segment = contract["segments"][segment_id]
    if not path.is_file() or f"_{segment_id}_" not in path.name:
        raise SafeFailure("VIDEO_VALIDATION_TARGET_INVALID")
    metadata = probe_media(path)
    streams = metadata.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video_streams) != 1:
        raise SafeFailure("VIDEO_STREAM_COUNT_INVALID")
    if len(audio_streams) < contract["output_validation"]["minimum_audio_streams"]:
        raise SafeFailure("VIDEO_AUDIO_STREAM_MISSING")
    stream = video_streams[0]
    try:
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SafeFailure("VIDEO_METADATA_INVALID") from exc
    if width >= height or min(width, height) != contract["output_validation"]["short_edge_pixels"]:
        raise SafeFailure("VIDEO_RESOLUTION_NOT_480P_PORTRAIT")
    target_ratio = Decimal(9) / Decimal(16)
    actual_ratio = Decimal(width) / Decimal(height)
    if abs(actual_ratio - target_ratio) > Decimal(str(contract["output_validation"]["ratio_tolerance"])):
        raise SafeFailure("VIDEO_RATIO_NOT_9_16")
    if abs(duration - segment["duration_seconds"]) > contract["output_validation"]["duration_tolerance_seconds"]:
        raise SafeFailure("VIDEO_DURATION_MISMATCH")
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
            check=True, capture_output=True, timeout=300,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise SafeFailure("FFMPEG_FULL_DECODE_FAILED") from exc

    rate = Decimal(contract["approval"]["rate_usd_per_second"])
    fx = Decimal(contract["approval"]["planning_fx_hkd_per_usd"])
    input_seconds = Decimal(segment["input_video_seconds"])
    output_seconds = Decimal(str(duration))
    billable_seconds = input_seconds + output_seconds
    actual_usd = rate * billable_seconds
    actual_hkd = actual_usd * fx
    if actual_hkd > Decimal(contract["approval"]["cost_cap_hkd"]):
        raise SafeFailure("VALIDATED_USAGE_EXCEEDS_BATCH_CAP")
    result = {
        "status": "DURATION_AUDIO_480P_RATIO_FULL_DECODE_VALIDATED",
        "segment": segment_id,
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "ratio": f"{width}:{height}",
        "duration_seconds": duration,
        "video_codec": stream.get("codec_name"),
        "audio_stream_count": len(audio_streams),
        "audio_codecs": [item.get("codec_name") for item in audio_streams],
        "full_decode": "PASS",
        "actual_usage": {
            "verified_input_video_seconds": str(input_seconds),
            "validated_output_video_seconds": str(output_seconds),
            "actual_billable_seconds": str(billable_seconds),
            "rate_usd_per_second": str(rate),
            "actual_usd": str(actual_usd),
            "planning_fx_hkd_per_usd": str(fx),
            "actual_hkd": str(actual_hkd),
        },
        "validated_utc": utc_now(),
    }
    write_json(path.parent / validation_name(segment_id), result)
    receipt_path = path.parent / receipt_name(segment_id)
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            receipt = None
        if isinstance(receipt, dict):
            receipt.update(
                {
                    "status": "DOWNLOADED_AND_FFMPEG_VALIDATED",
                    "actual_usage": result["actual_usage"],
                    "technical_validation": {
                        "sha256": result["sha256"],
                        "bytes": result["bytes"],
                        "width": width,
                        "height": height,
                        "duration_seconds": duration,
                        "audio_stream_count": len(audio_streams),
                        "full_decode": "PASS",
                    },
                    "updated_utc": utc_now(),
                }
            )
            write_json(receipt_path, receipt)
    print(f"DURATION_AUDIO_480P_RATIO_FULL_DECODE_VALIDATED segment={segment_id}")
    return result


def offline_validate(contract: dict, transport_root: Path | None) -> None:
    for segment_id in SEGMENT_IDS:
        load_request(contract, segment_id)
    if transport_root is not None:
        for image_id, metadata in contract["images"].items():
            path = transport_root / metadata["transport_filename"]
            try:
                data = path.read_bytes()
            except OSError as exc:
                raise SafeFailure("OFFLINE_TRANSPORT_IMAGE_UNREADABLE") from exc
            validate_image_bytes(data, metadata, "OFFLINE_IMAGE_" + image_id.upper())
    print("OFFLINE_CONTRACT_THREE_REQUESTS_AND_OPTIONAL_TRANSPORT_VALID")


def run_mode(mode: str, segment_id: str, output_dir: Path) -> None:
    contract = load_contract()
    if segment_id not in SEGMENT_IDS:
        raise SafeFailure("SEGMENT_REQUIRED")
    resume_task_id: str | None = None
    if mode == "generate":
        validate_generate_preflight(
            contract,
            segment_id,
            output_dir,
            os.environ.get("WAN_GENERATE_CONFIRMATION", ""),
            os.environ.get("WAN_B_REVIEW_GATE", ""),
            os.environ.get("GITHUB_RUN_ATTEMPT", ""),
        )
    elif mode == "resume":
        resume_task_id = valid_uuid(os.environ.get("WAN_RESUME_TASK_ID", ""))
        if not resume_task_id:
            raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / receipt_name(segment_id)

    if mode == "check-binding":
        receipt = base_receipt(mode, contract, segment_id, host)
        receipt["status"] = "BINDING_PRESENT_NOT_API_VERIFIED_ZERO_PROVIDER_CALLS"
        write_json(receipt_path, receipt)
        print("BINDING_PRESENT_NOT_API_VERIFIED_ZERO_PROVIDER_CALLS")
        return

    if mode == "generate":
        image_1, image_2 = runtime_image_inputs()
        expected_count = len(contract["segments"][segment_id]["image_ids"])
        if expected_count == 1 and image_2:
            raise SafeFailure("EXTRA_IMAGE_2_NOT_ALLOWED_FOR_SEGMENT")
        image_inputs = [image_1] if expected_count == 1 else [image_1, image_2]
        payload = build_provider_payload(contract, segment_id, image_inputs)
        with tempfile.TemporaryDirectory(prefix="starbay-reference-") as temporary:
            reference = fetch_and_validate_reference(contract, segment_id, Path(temporary))
        receipt = base_receipt(mode, contract, segment_id, host)
        receipt.update(
            {
                "status": "PINNED_REQUEST_IMAGES_AND_REFERENCE_VIDEO_VERIFIED",
                "verified_reference_video": reference,
            }
        )
        write_json(receipt_path, receipt)
        task_id = submit_once(host, key, payload, receipt_path, receipt)
        poll_get_only(
            host,
            key,
            task_id,
            receipt_path,
            receipt,
            output_dir / contract["segments"][segment_id]["output_name"],
        )
        return

    if resume_task_id is None:
        raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SafeFailure("RESUME_RECEIPT_INVALID") from exc
        if not isinstance(receipt, dict) or receipt.get("segment") != segment_id:
            raise SafeFailure("RESUME_RECEIPT_INVALID")
        if receipt.get("task_id") not in {None, resume_task_id}:
            raise SafeFailure("RESUME_TASK_ID_MISMATCH")
    else:
        receipt = base_receipt(mode, contract, segment_id, host)
    receipt.update({"task_id": resume_task_id, "mode": "resume", "status": "RESUME_GET_ONLY_STARTING"})
    write_json(receipt_path, receipt)
    poll_get_only(
        host,
        key,
        resume_task_id,
        receipt_path,
        receipt,
        output_dir / contract["segments"][segment_id]["output_name"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["check-binding", "generate", "resume", "validate-existing"],
        default="check-binding",
    )
    parser.add_argument("--segment", choices=SEGMENT_IDS, default="B")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-output", type=Path)
    parser.add_argument("--offline-validate", action="store_true")
    parser.add_argument("--transport-root", type=Path)
    args = parser.parse_args()
    try:
        contract = load_contract()
        if args.offline_validate:
            transport_root = args.transport_root.resolve() if args.transport_root else None
            offline_validate(contract, transport_root)
            return 0
        if args.mode == "validate-existing":
            if args.verify_output is None:
                raise SafeFailure("VERIFY_OUTPUT_PATH_REQUIRED")
            verify_output_video(args.verify_output.resolve(), contract, args.segment)
            return 0
        if args.verify_output is not None or args.transport_root is not None:
            raise SafeFailure("OFFLINE_ONLY_ARGUMENT_IN_RUNTIME_MODE")
        output_dir = (
            args.output_dir.resolve()
            if args.output_dir
            else (Path("output-starbay-three-character-v01") / args.segment).resolve()
        )
        run_mode(args.mode, args.segment, output_dir)
        return 0
    except SafeFailure as failure:
        print("ERROR " + failure.code, file=sys.stderr)
        return 1
    except Exception:
        print("ERROR UNEXPECTED_LOCAL_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
