#!/usr/bin/env python3
"""Pinned one-shot WAN HK executor for the StormMV Zachary v05 trial.

Generate can make exactly one paid POST for the pinned authorization.  It first
verifies the request, two private image payloads, exact public motion reference,
price ceiling, first run attempt, and GitHub Actions run-history ledger.  Resume
is GET-only.  Receipts exclude credentials, base64, event payloads, raw provider
responses, and signed result URLs.
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
MANIFEST_FILE = ROOT / "StormMV_Zachary_2026-10-15_JSON_ExecutorManifest_Template_v05.json"
EXPECTED_MANIFEST_SHA256 = "f3a67f3177a7cec8c4562f8f98b5ebe14d2e8b06d3ea753b51dcf02e0dea428d"
MODEL = "wan3.0-video"
EXPECTED_API_HOST = "ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com"
EXPECTED_REPOSITORY = "opc-zachary/ai-training-knowledge"
WORKFLOW_FILE = "wan-hk-storm-mv-zachary-v05.yml"
REFERENCE_URL_PLACEHOLDER = "__STORM_REFERENCE_VIDEO_PUBLIC_URL_REQUIRED_BEFORE_REPIN__"
IMAGE_PLACEHOLDERS = (
    "__RUNTIME_HASH_VERIFIED_SCENE_IMAGE_DATA_URI__",
    "__RUNTIME_HASH_VERIFIED_ZACHARY_IMAGE_DATA_URI__",
)
IMAGE_IDS = ("scene", "zachary")
CONFIRMATION = "GENERATE_STORM_MV_ZACHARY_V05_ONCE_HKD15_MAX"
AUTHORIZATION_ID = "STORM_MV_ZACHARY_V05_HKD15_ONE_POST_2026_10_15_A01"
EXPECTED_GENERATE_RUN_TITLE = (
    "StormMV_Zachary_v05 | generate | " + AUTHORIZATION_ID
)
MAX_REFERENCE_BYTES = 32 * 1024 * 1024
MAX_RESULT_BYTES = 512 * 1024 * 1024
MAX_IMAGE_BASE64_CHARACTERS = 60_000
MAX_EVENT_BYTES = 128 * 1024
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
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    mime = detected_image_mime(data)
    if mime == "image/png":
        if data[12:16] != b"IHDR":
            return None
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if mime != "image/webp":
        return None
    position = 12
    while position + 8 <= len(data):
        chunk = data[position : position + 4]
        size = int.from_bytes(data[position + 4 : position + 8], "little")
        payload = data[position + 8 : position + 8 + size]
        if len(payload) != size:
            return None
        if chunk == b"VP8X" and size >= 10:
            return (
                1 + int.from_bytes(payload[4:7], "little"),
                1 + int.from_bytes(payload[7:10], "little"),
            )
        if chunk == b"VP8 " and size >= 10 and payload[3:6] == b"\x9d\x01\x2a":
            return (
                int.from_bytes(payload[6:8], "little") & 0x3FFF,
                int.from_bytes(payload[8:10], "little") & 0x3FFF,
            )
        if chunk == b"VP8L" and size >= 5 and payload[0] == 0x2F:
            bits = int.from_bytes(payload[1:5], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        position += 8 + size + (size % 2)
    return None


def expected_parameters() -> dict:
    return {
        "resolution": "480P",
        "ratio": "16:9",
        "duration": 4,
        "audio": False,
        "prompt_extend": False,
        "watermark": False,
    }


def calculated_cost(manifest: dict) -> tuple[Decimal, Decimal]:
    try:
        approval = manifest["approval"]
        rate = Decimal(approval["rate_usd_per_second"])
        fx = Decimal(approval["planning_fx_hkd_per_usd"])
        input_seconds = Decimal(approval["input_video_seconds"])
        output_seconds = Decimal(approval["output_seconds"])
        billable_seconds = Decimal(approval["maximum_billable_seconds"])
        declared_usd = Decimal(approval["estimated_usd"])
        declared_hkd = Decimal(approval["estimated_hkd"])
        cap = Decimal(approval["cost_cap_hkd"])
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise SafeFailure("MANIFEST_COST_SCHEMA_INVALID") from exc
    if rate != Decimal("0.041256") or fx != Decimal("7.8"):
        raise SafeFailure("MANIFEST_COST_BASIS_MISMATCH")
    if input_seconds != Decimal("4") or output_seconds != Decimal("4"):
        raise SafeFailure("MANIFEST_DURATION_SCOPE_MISMATCH")
    if billable_seconds != input_seconds + output_seconds or billable_seconds != Decimal("8"):
        raise SafeFailure("MANIFEST_BILLABLE_SECONDS_MISMATCH")
    calculated_usd = rate * billable_seconds
    calculated_hkd = calculated_usd * fx
    if calculated_usd != declared_usd or calculated_hkd != declared_hkd:
        raise SafeFailure("MANIFEST_COST_ESTIMATE_MISMATCH")
    if declared_hkd != Decimal("2.5743744") or cap != Decimal("15.00"):
        raise SafeFailure("MANIFEST_COST_CAP_MISMATCH")
    if declared_hkd > cap:
        raise SafeFailure("MANIFEST_COST_CAP_EXCEEDED")
    return calculated_hkd, cap


def validate_exact_https_url(value: object) -> str:
    if not isinstance(value, str):
        raise SafeFailure("REFERENCE_URL_INVALID")
    parts = urllib.parse.urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.port not in {None, 443}
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or not parts.path
        or parts.path.endswith("/")
    ):
        raise SafeFailure("REFERENCE_URL_NOT_EXACT_PUBLIC_HTTPS_OBJECT")
    return value


def validate_manifest_shape(manifest: dict, allow_template: bool) -> None:
    fixed_identity = {
        "schema_version": 1,
        "project": "StormMV_Zachary",
        "client": "Zachary Chan / STARBAY",
        "version": "v05",
        "authorization": "GRANTED",
    }
    if any(manifest.get(key) != value for key, value in fixed_identity.items()):
        raise SafeFailure("MANIFEST_IDENTITY_OR_AUTHORIZATION_MISMATCH")
    provider = manifest.get("provider", {})
    expected_provider = {
        "model": MODEL,
        "api_host": EXPECTED_API_HOST,
        "api_key_binding": "ALIYUN_MODEL_STUDIO_HK_API_KEY",
        "api_host_binding": "ALIYUN_MODEL_STUDIO_HK_API_HOST",
        "region": "China (Hong Kong)",
        "repository": EXPECTED_REPOSITORY,
    }
    if any(provider.get(key) != value for key, value in expected_provider.items()):
        raise SafeFailure("MANIFEST_PROVIDER_OR_BINDING_MISMATCH")
    approval = manifest.get("approval", {})
    fixed_approval = {
        "approved_by": "Zachary Chan",
        "authorization_id": AUTHORIZATION_ID,
        "maximum_total_submissions": 1,
        "automatic_paid_retries": 0,
        "confirmation": CONFIRMATION,
    }
    if any(approval.get(key) != value for key, value in fixed_approval.items()):
        raise SafeFailure("MANIFEST_APPROVAL_SCOPE_MISMATCH")
    calculated_cost(manifest)

    execution = manifest.get("execution", {})
    fixed_execution = {
        "workflow": "manual_only",
        "workflow_file": WORKFLOW_FILE,
        "workflow_run_title_generate": EXPECTED_GENERATE_RUN_TITLE,
        "concurrency_group": "wan-hk-storm-mv-zachary-v05-paid-generation",
        "github_permissions": "contents:read,actions:read",
        "run_attempt_required": 1,
        "maximum_provider_posts": 1,
        "maximum_provider_posts_per_run": 1,
        "one_shot_ledger_max_pages": 20,
        "one_shot_ledger_page_size": 100,
    }
    if any(execution.get(key) != value for key, value in fixed_execution.items()):
        raise SafeFailure("MANIFEST_EXECUTION_SCOPE_MISMATCH")
    if not str(execution.get("unknown_post_outcome_policy", "")).startswith("DO_NOT_RETRY"):
        raise SafeFailure("MANIFEST_UNKNOWN_OUTCOME_POLICY_MISMATCH")

    transport = manifest.get("reference_transport", {})
    pending = transport.get("registration_state") == "PENDING_ROOT_EXACT_URL_AND_REPIN"
    registered = transport.get("registration_state") == "REGISTERED_EXACT_URL_PINNED"
    if pending:
        if not allow_template:
            raise SafeFailure("REFERENCE_URL_NOT_REGISTERED_REPIN_REQUIRED")
        if transport.get("expected_url") != REFERENCE_URL_PLACEHOLDER:
            raise SafeFailure("REFERENCE_TEMPLATE_PLACEHOLDER_MISMATCH")
        if manifest.get("status") != "APPROVED_ONE_SHOT_REFERENCE_URL_REPIN_REQUIRED":
            raise SafeFailure("MANIFEST_TEMPLATE_STATUS_MISMATCH")
    elif registered:
        validate_exact_https_url(transport.get("expected_url"))
        if manifest.get("status") != "APPROVED_ONE_SHOT_READY":
            raise SafeFailure("MANIFEST_REGISTERED_STATUS_MISMATCH")
    else:
        raise SafeFailure("REFERENCE_REGISTRATION_STATE_INVALID")
    expected_reference = {
        "sha256": "d95f30bb904695c28a6ab47cb951f1545ca04019e0697637e0ea786d383a9489",
        "bytes": 338620,
        "dimensions": [720, 404],
        "duration_seconds": 4,
        "fps": "30/1",
        "video_codec": "h264",
        "pixel_format": "yuv420p",
        "maximum_download_bytes": MAX_REFERENCE_BYTES,
    }
    if any(transport.get(key) != value for key, value in expected_reference.items()):
        raise SafeFailure("REFERENCE_METADATA_MISMATCH")

    images = manifest.get("images")
    if not isinstance(images, dict) or tuple(images) != IMAGE_IDS:
        raise SafeFailure("MANIFEST_IMAGE_SET_OR_ORDER_INVALID")
    for image_id, metadata in images.items():
        try:
            source_dimensions = metadata["source_dimensions"]
            dimensions = metadata["transport_dimensions"]
            byte_count = int(metadata["transport_bytes"])
            base64_count = int(metadata["transport_base64_characters"])
        except (KeyError, TypeError, ValueError) as exc:
            raise SafeFailure("MANIFEST_IMAGE_METADATA_INVALID") from exc
        if metadata.get("transport_mime") != "image/webp":
            raise SafeFailure("MANIFEST_IMAGE_MIME_INVALID")
        for key in ("source_sha256", "transport_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(metadata.get(key, ""))):
                raise SafeFailure("MANIFEST_IMAGE_SHA256_INVALID")
        if not isinstance(source_dimensions, list) or len(source_dimensions) != 2:
            raise SafeFailure("MANIFEST_SOURCE_IMAGE_DIMENSIONS_INVALID")
        if not isinstance(dimensions, list) or len(dimensions) != 2 or min(dimensions) < 240:
            raise SafeFailure("MANIFEST_TRANSPORT_IMAGE_DIMENSIONS_INVALID")
        if base64_count != 4 * ((byte_count + 2) // 3):
            raise SafeFailure("MANIFEST_IMAGE_BASE64_SIZE_INVALID")
        if base64_count >= MAX_IMAGE_BASE64_CHARACTERS:
            raise SafeFailure("MANIFEST_IMAGE_TOO_LARGE_FOR_PRIVATE_EVENT_INPUT")

    request_meta = manifest.get("request", {})
    if request_meta.get("image_order") != list(IMAGE_IDS):
        raise SafeFailure("MANIFEST_REQUEST_IMAGE_ORDER_INVALID")
    if not re.fullmatch(r"[0-9a-f]{64}", str(request_meta.get("sha256", ""))):
        raise SafeFailure("MANIFEST_REQUEST_SHA256_INVALID")
    if request_meta.get("reference_video_url") != transport.get("expected_url"):
        raise SafeFailure("MANIFEST_REQUEST_REFERENCE_URL_MISMATCH")
    if manifest.get("common_parameters") != expected_parameters():
        raise SafeFailure("MANIFEST_PARAMETERS_MISMATCH")
    output_validation = manifest.get("output_validation", {})
    if output_validation != {
        "duration_tolerance_seconds": 0.5,
        "short_edge_pixels": 480,
        "landscape_ratio": "16:9",
        "ratio_tolerance": 0.02,
        "required_audio_streams": 0,
        "full_decode_required": True,
    }:
        raise SafeFailure("MANIFEST_OUTPUT_VALIDATION_MISMATCH")
    excluded = set(manifest.get("receipt_policy", {}).get("exclude", []))
    expected_excluded = {
        "signed result URLs",
        "raw provider responses",
        "API keys",
        "GitHub tokens",
        "base64 image data",
        "workflow event payload",
    }
    if excluded != expected_excluded:
        raise SafeFailure("MANIFEST_RECEIPT_POLICY_MISMATCH")


def validate_request_payload(request: object, manifest: dict, allow_template: bool) -> dict:
    if not isinstance(request, dict) or set(request) != {"model", "input", "parameters"}:
        raise SafeFailure("REQUEST_TOP_LEVEL_KEYS_INVALID")
    if request.get("model") != MODEL or request.get("parameters") != expected_parameters():
        raise SafeFailure("REQUEST_MODEL_OR_PARAMETERS_MISMATCH")
    input_value = request.get("input")
    if not isinstance(input_value, dict) or set(input_value) != {"prompt", "media"}:
        raise SafeFailure("REQUEST_INPUT_KEYS_INVALID")
    prompt = input_value.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise SafeFailure("REQUEST_PROMPT_INVALID")
    expected_url = manifest["reference_transport"]["expected_url"]
    expected_media = [
        {"type": "reference_video", "url": expected_url},
        {"type": "reference_image", "url": IMAGE_PLACEHOLDERS[0]},
        {"type": "reference_image", "url": IMAGE_PLACEHOLDERS[1]},
    ]
    if input_value.get("media") != expected_media:
        raise SafeFailure("REQUEST_MEDIA_TEMPLATE_OR_ORDER_INVALID")
    if expected_url == REFERENCE_URL_PLACEHOLDER and not allow_template:
        raise SafeFailure("REFERENCE_URL_NOT_REGISTERED_REPIN_REQUIRED")
    if expected_url != REFERENCE_URL_PLACEHOLDER:
        validate_exact_https_url(expected_url)
    return request


def load_request(manifest: dict, allow_template: bool) -> dict:
    path = safe_relative_path(ROOT, manifest["request"].get("path"), "REQUEST")
    try:
        raw = path.read_bytes()
        request = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("REQUEST_FILE_INVALID") from exc
    if sha256_bytes(raw) != manifest["request"].get("sha256"):
        raise SafeFailure("REQUEST_SHA256_MISMATCH")
    return validate_request_payload(request, manifest, allow_template)


def load_manifest(allow_template: bool = False) -> dict:
    try:
        raw = MANIFEST_FILE.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("MANIFEST_FILE_INVALID") from exc
    if sha256_bytes(raw) != EXPECTED_MANIFEST_SHA256:
        raise SafeFailure("MANIFEST_SHA256_MISMATCH_REPIN_REQUIRED")
    if not isinstance(manifest, dict):
        raise SafeFailure("MANIFEST_FILE_INVALID")
    validate_manifest_shape(manifest, allow_template)
    load_request(manifest, allow_template)
    return manifest


def validate_image_bytes(data: bytes, metadata: dict, code: str) -> None:
    if sha256_bytes(data) != metadata.get("transport_sha256"):
        raise SafeFailure(code + "_SHA256_MISMATCH")
    if len(data) != metadata.get("transport_bytes"):
        raise SafeFailure(code + "_BYTE_COUNT_MISMATCH")
    if detected_image_mime(data) != metadata.get("transport_mime"):
        raise SafeFailure(code + "_MIME_MISMATCH")
    if image_dimensions(data) != tuple(metadata.get("transport_dimensions", [])):
        raise SafeFailure(code + "_DIMENSIONS_MISMATCH")


def decode_image_input(encoded: str, metadata: dict, code: str) -> bytes:
    if (
        not encoded
        or len(encoded) >= MAX_IMAGE_BASE64_CHARACTERS
        or any(character.isspace() for character in encoded)
    ):
        raise SafeFailure(code + "_BASE64_INPUT_INVALID")
    if len(encoded) != metadata.get("transport_base64_characters"):
        raise SafeFailure(code + "_BASE64_LENGTH_MISMATCH")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SafeFailure(code + "_BASE64_INPUT_INVALID") from exc
    validate_image_bytes(data, metadata, code)
    return data


def read_image_inputs_from_event(event_path: Path) -> tuple[str, str]:
    """Read private workflow inputs without copying them to env or output."""
    try:
        raw = event_path.read_bytes()
        if len(raw) > MAX_EVENT_BYTES:
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
    for name in ("scene_image_base64", "zachary_image_base64"):
        value = inputs.get(name, "")
        if not isinstance(value, str):
            raise SafeFailure("GITHUB_EVENT_IMAGE_INPUT_TYPE_INVALID")
        if len(value) >= MAX_IMAGE_BASE64_CHARACTERS or any(c.isspace() for c in value):
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


def build_provider_payload(manifest: dict, image_inputs: tuple[str, str]) -> dict:
    request = copy.deepcopy(load_request(manifest, allow_template=False))
    for index, image_id in enumerate(IMAGE_IDS):
        data = decode_image_input(
            image_inputs[index], manifest["images"][image_id], f"IMAGE_{index + 1}"
        )
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
                "stream=index,codec_type,codec_name,width,height,avg_frame_rate,pix_fmt:format=duration,size,format_name",
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


def full_decode(path: Path, code: str) -> None:
    try:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"],
            check=True, capture_output=True, timeout=300,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise SafeFailure(code) from exc


def validate_reference_video_file(path: Path, manifest: dict) -> dict:
    reference = manifest["reference_transport"]
    try:
        size = path.stat().st_size
        digest = sha256_bytes(path.read_bytes())
        with path.open("rb") as source:
            header = source.read(64)
    except OSError as exc:
        raise SafeFailure("REFERENCE_VIDEO_UNREADABLE") from exc
    if size != reference["bytes"]:
        raise SafeFailure("REFERENCE_VIDEO_BYTE_COUNT_MISMATCH")
    if digest != reference["sha256"]:
        raise SafeFailure("REFERENCE_VIDEO_SHA256_MISMATCH")
    if b"ftyp" not in header:
        raise SafeFailure("REFERENCE_VIDEO_NOT_MP4")
    metadata = probe_media(path)
    streams = metadata.get("streams", [])
    video_streams = [s for s in streams if s.get("codec_type") == "video"]
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    if len(video_streams) != 1 or audio_streams:
        raise SafeFailure("REFERENCE_VIDEO_STREAM_LAYOUT_INVALID")
    stream = video_streams[0]
    try:
        dimensions = [int(stream["width"]), int(stream["height"])]
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SafeFailure("REFERENCE_VIDEO_METADATA_INVALID") from exc
    if dimensions != reference["dimensions"]:
        raise SafeFailure("REFERENCE_VIDEO_DIMENSIONS_MISMATCH")
    if abs(duration - reference["duration_seconds"]) > 0.05:
        raise SafeFailure("REFERENCE_VIDEO_DURATION_MISMATCH")
    if stream.get("codec_name") != reference["video_codec"]:
        raise SafeFailure("REFERENCE_VIDEO_CODEC_MISMATCH")
    if stream.get("pix_fmt") != reference["pixel_format"]:
        raise SafeFailure("REFERENCE_VIDEO_PIXEL_FORMAT_MISMATCH")
    if stream.get("avg_frame_rate") != reference["fps"]:
        raise SafeFailure("REFERENCE_VIDEO_FRAME_RATE_MISMATCH")
    format_names = str(metadata.get("format", {}).get("format_name", "")).split(",")
    if "mp4" not in format_names:
        raise SafeFailure("REFERENCE_VIDEO_CONTAINER_NOT_MP4")
    full_decode(path, "REFERENCE_VIDEO_FULL_DECODE_FAILED")
    return {
        "url": reference["expected_url"],
        "sha256": digest,
        "bytes": size,
        "duration_seconds": duration,
        "dimensions": dimensions,
        "video_codec": stream.get("codec_name"),
        "fps": stream.get("avg_frame_rate"),
        "audio_stream_count": 0,
        "full_decode": "PASS",
    }


def fetch_and_validate_reference(manifest: dict, work_dir: Path) -> dict:
    reference = manifest["reference_transport"]
    url = validate_exact_https_url(reference["expected_url"])
    target = work_dir / "storm-motion-reference-v05.mp4"
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "StormMV-Zachary-WanHK-v05/1.0"}
        )
        with urllib.request.urlopen(request, timeout=180) as response, target.open("xb") as output:
            if response.geturl() != url:
                raise SafeFailure("REFERENCE_REDIRECT_NOT_EXACT_PINNED_URL")
            if response.headers.get_content_type() != "video/mp4":
                raise SafeFailure("REFERENCE_HTTP_CONTENT_TYPE_NOT_VIDEO_MP4")
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > reference["maximum_download_bytes"]:
                    raise SafeFailure("REFERENCE_VIDEO_TOO_LARGE")
                digest.update(chunk)
                output.write(chunk)
    except SafeFailure:
        target.unlink(missing_ok=True)
        raise
    except (urllib.error.URLError, TimeoutError, OSError):
        target.unlink(missing_ok=True)
        raise SafeFailure("REFERENCE_VIDEO_FETCH_FAILED") from None
    if size != reference["bytes"] or digest.hexdigest() != reference["sha256"]:
        target.unlink(missing_ok=True)
        raise SafeFailure("REFERENCE_VIDEO_NETWORK_BYTES_OR_SHA256_MISMATCH")
    return validate_reference_video_file(target, manifest)


def load_binding() -> tuple[str, str]:
    host = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_HOST", "").strip()
    key = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_KEY", "")
    if host != EXPECTED_API_HOST:
        raise SafeFailure("BINDING_HOST_INVALID")
    if not key or any(character.isspace() for character in key):
        raise SafeFailure("BINDING_SECRET_MISSING_OR_MALFORMED")
    return host, key


def read_workflow_run_page(page: int, page_size: int, token: str) -> dict:
    query = urllib.parse.urlencode(
        {"event": "workflow_dispatch", "per_page": page_size, "page": page}
    )
    url = (
        f"https://api.github.com/repos/{EXPECTED_REPOSITORY}/actions/workflows/"
        f"{WORKFLOW_FILE}/runs?{query}"
    )
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "StormMV-Zachary-OneShot-Ledger-v05",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SafeFailure("ONE_SHOT_LEDGER_READBACK_REQUIRED") from None
    if len(raw) > 4 * 1024 * 1024:
        raise SafeFailure("ONE_SHOT_LEDGER_RESPONSE_TOO_LARGE")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("ONE_SHOT_LEDGER_RESPONSE_INVALID") from exc
    if not isinstance(value, dict) or not isinstance(value.get("workflow_runs"), list):
        raise SafeFailure("ONE_SHOT_LEDGER_RESPONSE_INVALID")
    return value


def assert_one_shot_ledger_clear(manifest: dict) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SafeFailure("ONE_SHOT_LEDGER_REQUIRES_GITHUB_ACTIONS")
    if os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch":
        raise SafeFailure("ONE_SHOT_LEDGER_REQUIRES_WORKFLOW_DISPATCH")
    if os.environ.get("GITHUB_REPOSITORY") != EXPECTED_REPOSITORY:
        raise SafeFailure("ONE_SHOT_LEDGER_REPOSITORY_MISMATCH")
    token = os.environ.get("GITHUB_TOKEN", "")
    run_id_text = os.environ.get("GITHUB_RUN_ID", "")
    if not token or any(character.isspace() for character in token):
        raise SafeFailure("ONE_SHOT_LEDGER_TOKEN_MISSING")
    if not run_id_text.isdigit():
        raise SafeFailure("ONE_SHOT_LEDGER_RUN_ID_INVALID")
    current_run_id = int(run_id_text)
    execution = manifest["execution"]
    title = execution["workflow_run_title_generate"]
    page_size = execution["one_shot_ledger_page_size"]
    max_pages = execution["one_shot_ledger_max_pages"]
    scanned = 0
    total_count: int | None = None
    current_found = False
    for page in range(1, max_pages + 1):
        response = read_workflow_run_page(page, page_size, token)
        if total_count is None:
            try:
                total_count = int(response["total_count"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SafeFailure("ONE_SHOT_LEDGER_RESPONSE_INVALID") from exc
        runs = response["workflow_runs"]
        scanned += len(runs)
        for run in runs:
            if not isinstance(run, dict):
                raise SafeFailure("ONE_SHOT_LEDGER_RESPONSE_INVALID")
            run_id = run.get("id")
            display_title = run.get("display_title")
            if run_id == current_run_id:
                if display_title != title:
                    raise SafeFailure("ONE_SHOT_LEDGER_CURRENT_RUN_TITLE_MISMATCH")
                current_found = True
            elif display_title == title:
                raise SafeFailure("ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED_NEW_AUTH_REQUIRED")
        if len(runs) < page_size:
            break
    if not current_found:
        raise SafeFailure("ONE_SHOT_LEDGER_CURRENT_RUN_NOT_FOUND")
    if total_count is None or scanned < total_count:
        raise SafeFailure("ONE_SHOT_LEDGER_HISTORY_EXCEEDS_BOUNDED_SCAN")


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
            code = safe_api_code(
                parsed.get("code") if isinstance(parsed, dict) else None, "HTTP_ERROR"
            )
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


def base_receipt(mode: str, manifest: dict, host: str) -> dict:
    approval = manifest["approval"]
    reference = manifest["reference_transport"]
    return {
        "project": manifest["project"],
        "client": manifest["client"],
        "version": manifest["version"],
        "mode": mode,
        "model": MODEL,
        "api_host": host,
        "authorization": manifest["authorization"],
        "approval": {
            "approved_by": approval["approved_by"],
            "authorization_id": approval["authorization_id"],
            "approval_record": approval["approval_record"],
            "cost_cap_hkd": approval["cost_cap_hkd"],
            "estimated_hkd": approval["estimated_hkd"],
        },
        "source": {
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "request_path": manifest["request"]["path"],
            "request_sha256": manifest["request"]["sha256"],
            "reference_video_url": reference["expected_url"],
            "reference_video_sha256": reference["sha256"],
            "reference_video_bytes": reference["bytes"],
            "image_transport_sha256": [
                manifest["images"][image_id]["transport_sha256"] for image_id in IMAGE_IDS
            ],
        },
        "maximum_provider_posts_this_run": 1,
        "automatic_paid_retries": 0,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "updated_utc": utc_now(),
    }


def validate_generate_preflight(manifest: dict, output_dir: Path, confirmation: str) -> None:
    if manifest.get("authorization") != "GRANTED":
        raise SafeFailure("PAID_GENERATION_NOT_AUTHORIZED")
    if manifest.get("status") != "APPROVED_ONE_SHOT_READY":
        raise SafeFailure("REFERENCE_URL_NOT_REGISTERED_REPIN_REQUIRED")
    if confirmation != manifest["approval"]["confirmation"]:
        raise SafeFailure("GENERATE_CONFIRMATION_REQUIRED")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise SafeFailure("GENERATE_REQUIRES_GITHUB_RUN_ATTEMPT_1")
    calculated_cost(manifest)
    receipt_path = output_dir / "storm-mv-zachary-v05-receipt.json"
    output_path = output_dir / manifest["request"]["output_name"]
    if receipt_path.exists() or output_path.exists():
        raise SafeFailure("DUPLICATE_GUARD_EXISTING_RUN_EVIDENCE")
    assert_one_shot_ledger_clear(manifest)


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
    receipt.update(
        {
            "status": "POST_IN_PROGRESS_OUTCOME_UNKNOWN_NEW_AUTH_REQUIRED_FOR_ANY_NEW_POST",
            "updated_utc": utc_now(),
        }
    )
    write_json(path, receipt)
    url = f"https://{host}/api/v1/services/aigc/video-generation/video-synthesis"
    try:
        response, request_id = api_json(url, key, payload)
    except ApiFailure as failure:
        status = (
            "POST_REJECTED_NEW_AUTH_REQUIRED"
            if failure.outcome_known
            else "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY_NEW_AUTH_REQUIRED"
        )
        record_api_failure(path, receipt, failure, status)
        raise SafeFailure(status) from None
    output = response.get("output")
    task_id = valid_uuid(output.get("task_id") if isinstance(output, dict) else None)
    if not task_id:
        receipt.update(
            {
                "status": "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY_NEW_AUTH_REQUIRED",
                "safe_error_code": safe_api_code(response.get("code"), "TASK_ID_MISSING"),
                "request_id": request_id,
                "updated_utc": utc_now(),
            }
        )
        write_json(path, receipt)
        raise SafeFailure("POST_OUTCOME_UNKNOWN_DO_NOT_RETRY_NEW_AUTH_REQUIRED")
    receipt.update(
        {
            "task_id": task_id,
            "request_id": request_id,
            "status": "SUBMITTED_ONE_SHOT_CONSUMED",
            "provider_reported_usage": sanitize_usage(response),
            "updated_utc": utc_now(),
        }
    )
    write_json(path, receipt)
    print(f"SUBMITTED task_id={task_id}", flush=True)
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
            url, headers={"User-Agent": "StormMV-Zachary-WanHK-v05/1.0"}
        )
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
            response, request_id = api_json(
                f"https://{host}/api/v1/tasks/{task_id}", key, payload=None
            )
        except ApiFailure as failure:
            record_api_failure(
                receipt_path, receipt, failure, "QUERY_UNAVAILABLE_RESUME_SAME_TASK"
            )
            raise SafeFailure("QUERY_UNAVAILABLE_RESUME_SAME_TASK") from None
        output = response.get("output")
        state = output.get("task_status") if isinstance(output, dict) else None
        if state not in {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}:
            receipt.update(
                {"status": "QUERY_RESPONSE_INVALID_RESUME_SAME_TASK", "updated_utc": utc_now()}
            )
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


def verify_output_video(path: Path, manifest: dict) -> dict:
    if not path.is_file() or path.name != manifest["request"]["output_name"]:
        raise SafeFailure("VIDEO_VALIDATION_TARGET_INVALID")
    metadata = probe_media(path)
    streams = metadata.get("streams", [])
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video_streams) != 1:
        raise SafeFailure("VIDEO_STREAM_COUNT_INVALID")
    if len(audio_streams) != manifest["output_validation"]["required_audio_streams"]:
        raise SafeFailure("VIDEO_MUST_BE_SILENT")
    stream = video_streams[0]
    try:
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(metadata["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise SafeFailure("VIDEO_METADATA_INVALID") from exc
    if width <= height or min(width, height) != manifest["output_validation"]["short_edge_pixels"]:
        raise SafeFailure("VIDEO_RESOLUTION_NOT_480P_LANDSCAPE")
    target_ratio = Decimal(16) / Decimal(9)
    actual_ratio = Decimal(width) / Decimal(height)
    tolerance = Decimal(str(manifest["output_validation"]["ratio_tolerance"]))
    if abs(actual_ratio - target_ratio) > tolerance:
        raise SafeFailure("VIDEO_RATIO_NOT_16_9")
    requested_duration = manifest["common_parameters"]["duration"]
    if abs(duration - requested_duration) > manifest["output_validation"]["duration_tolerance_seconds"]:
        raise SafeFailure("VIDEO_DURATION_MISMATCH")
    full_decode(path, "FFMPEG_FULL_DECODE_FAILED")

    rate = Decimal(manifest["approval"]["rate_usd_per_second"])
    fx = Decimal(manifest["approval"]["planning_fx_hkd_per_usd"])
    input_seconds = Decimal(manifest["approval"]["input_video_seconds"])
    output_seconds = Decimal(str(duration))
    billable_seconds = input_seconds + output_seconds
    actual_usd = rate * billable_seconds
    actual_hkd = actual_usd * fx
    if actual_hkd > Decimal(manifest["approval"]["cost_cap_hkd"]):
        raise SafeFailure("VALIDATED_USAGE_EXCEEDS_APPROVED_CAP")
    result = {
        "status": "SILENT_DURATION_480P_16_9_FULL_DECODE_VALIDATED",
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "video_codec": stream.get("codec_name"),
        "audio_stream_count": 0,
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
    write_json(path.parent / "storm-mv-zachary-v05-video-validation.json", result)
    print("VALIDATED " + path.name)
    return result


def reproduce_transport(source_path: Path, dimensions: list[int]) -> bytes:
    if shutil.which("cwebp") is None:
        raise SafeFailure("CWEBP_COMMAND_NOT_FOUND")
    try:
        result = subprocess.run(
            [
                "cwebp", "-quiet", "-resize", str(dimensions[0]), str(dimensions[1]),
                "-q", "70", "-m", "6", str(source_path), "-o", "-",
            ],
            check=True, capture_output=True, timeout=120,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise SafeFailure("CWEBP_TRANSPORT_REPRODUCTION_FAILED") from exc
    return result.stdout


def validate_local_assets(manifest: dict) -> None:
    for image_id in IMAGE_IDS:
        metadata = manifest["images"][image_id]
        source_path = Path(metadata["source_path"])
        try:
            source = source_path.read_bytes()
        except OSError as exc:
            raise SafeFailure("LOCAL_SOURCE_IMAGE_UNREADABLE") from exc
        if (
            sha256_bytes(source) != metadata["source_sha256"]
            or len(source) != metadata["source_bytes"]
            or detected_image_mime(source) != "image/png"
            or image_dimensions(source) != tuple(metadata["source_dimensions"])
        ):
            raise SafeFailure("LOCAL_SOURCE_IMAGE_METADATA_MISMATCH")
        transport = reproduce_transport(source_path, metadata["transport_dimensions"])
        validate_image_bytes(transport, metadata, "LOCAL_TRANSPORT_" + image_id.upper())
    reference_path = Path(manifest["reference_transport"]["local_review_source_path"])
    validate_reference_video_file(reference_path, manifest)


def offline_validate(manifest: dict, validate_assets: bool) -> None:
    calculated_cost(manifest)
    load_request(manifest, allow_template=True)
    if validate_assets:
        validate_local_assets(manifest)
    print("OFFLINE_VALIDATION_PASS_TEMPLATE_REPIN_REQUIRED")


def run_mode(mode: str, manifest: dict, output_dir: Path) -> None:
    confirmation = os.environ.get("WAN_GENERATE_CONFIRMATION", "")
    resume_task_id = None
    if mode == "generate":
        validate_generate_preflight(manifest, output_dir, confirmation)
    elif mode == "resume":
        resume_task_id = valid_uuid(os.environ.get("WAN_RESUME_TASK_ID", ""))
        if not resume_task_id:
            raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "storm-mv-zachary-v05-receipt.json"
    output_path = output_dir / manifest["request"]["output_name"]

    if mode == "check-binding":
        receipt = base_receipt(mode, manifest, host)
        receipt["status"] = "BINDING_PRESENT_NOT_API_VERIFIED_ZERO_PROVIDER_CALLS"
        write_json(receipt_path, receipt)
        print("BINDING_PRESENT_NOT_API_VERIFIED_ZERO_PROVIDER_CALLS")
        return

    if mode == "generate":
        payload = build_provider_payload(manifest, runtime_image_inputs())
        with tempfile.TemporaryDirectory(prefix="storm-v05-reference-") as temporary:
            reference = fetch_and_validate_reference(manifest, Path(temporary))
        receipt = base_receipt(mode, manifest, host)
        receipt.update(
            {
                "status": "ONE_SHOT_LEDGER_REQUEST_IMAGES_AND_REFERENCE_VIDEO_VERIFIED",
                "verified_reference_video": reference,
            }
        )
        write_json(receipt_path, receipt)
        task_id = submit_once(host, key, payload, receipt_path, receipt)
        poll_get_only(host, key, task_id, receipt_path, receipt, output_path)
        return

    if resume_task_id is None:
        raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SafeFailure("RESUME_RECEIPT_INVALID") from exc
        if not isinstance(receipt, dict) or receipt.get("project") != manifest["project"]:
            raise SafeFailure("RESUME_RECEIPT_INVALID")
        if receipt.get("task_id") not in {None, resume_task_id}:
            raise SafeFailure("RESUME_TASK_ID_MISMATCH")
    else:
        receipt = base_receipt(mode, manifest, host)
    receipt.update(
        {"task_id": resume_task_id, "mode": "resume", "status": "RESUME_GET_ONLY_STARTING"}
    )
    write_json(receipt_path, receipt)
    poll_get_only(host, key, resume_task_id, receipt_path, receipt, output_path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["check-binding", "generate", "resume", "validate-existing"],
        default="check-binding",
    )
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-output")
    parser.add_argument("--offline-validate", action="store_true")
    parser.add_argument("--validate-local-assets", action="store_true")
    args = parser.parse_args()
    try:
        if args.offline_validate:
            manifest = load_manifest(allow_template=True)
            if args.output_dir or args.verify_output:
                raise SafeFailure("RUNTIME_ARGUMENT_NOT_ALLOWED_IN_OFFLINE_MODE")
            offline_validate(manifest, args.validate_local_assets)
            return 0
        manifest = load_manifest(allow_template=False)
        if args.mode == "validate-existing":
            if not args.verify_output:
                raise SafeFailure("VERIFY_OUTPUT_PATH_REQUIRED")
            path = safe_relative_path(ROOT, args.verify_output, "VERIFY_OUTPUT")
            verify_output_video(path, manifest)
            return 0
        if args.verify_output or args.validate_local_assets:
            raise SafeFailure("OFFLINE_OR_VALIDATION_ARGUMENT_IN_RUNTIME_MODE")
        output_dir = (
            args.output_dir.resolve()
            if args.output_dir
            else (ROOT / "output-storm-mv-zachary-v05").resolve()
        )
        try:
            output_dir.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise SafeFailure("OUTPUT_DIR_OUTSIDE_EXECUTOR_ROOT") from exc
        run_mode(args.mode, manifest, output_dir)
        return 0
    except SafeFailure as failure:
        print("ERROR " + failure.code, file=sys.stderr)
        return 1
    except Exception:
        print("ERROR UNEXPECTED_LOCAL_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
