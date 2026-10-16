#!/usr/bin/env python3
"""Approved three-shot 9:16 Storm MV v09 executor.
One POST per exact shot authorization, three POSTs maximum within HKD45;
no automatic paid retries; GET-only resume and sanitized receipts.
Identity v08 and vertical scene v09 remain private runtime inputs.
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
MANIFEST_FILE = ROOT / "StormMV_Zachary_2026-10-16_JSON_ExecutorManifest_Approved_v09.json"
EXPECTED_MANIFEST_SHA256 = "1be84a5cda9ceadf2de419819a6c3b481f4d77efc7e6012e969d0aae8f00892a"
STAGED_ONLY_BUILD = False
MODEL = "wan3.0-video"
EXPECTED_API_HOST = "ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com"
EXPECTED_REPOSITORY = "opc-zachary/ai-training-knowledge"
WORKFLOW_FILE = "wan-hk-storm-mv-zachary-full-mv-v09.yml"
WORKFLOW_TITLE_PREFIX = "StormMV_Zachary_v09"
SHOT_IDS = ("s01", "s02", "s03")
IDENTITY_PLACEHOLDER = "__RUNTIME_HASH_VERIFIED_ZACHARY_V08_IMAGE_DATA_URI__"
SCENE_PLACEHOLDER = "__RUNTIME_HASH_VERIFIED_SECONDARY_SCENE_IMAGE_DATA_URI__"
PROMPT_MEDIA_MAPPING_PREFIX = (
    "媒體對應（固定順序）：影片1=第1個reference_video，是本鏡動作與攝影運鏡依據；"
    "圖片1=第1個reference_image，是v08 Zachary唯一臉部及身份依據；"
    "圖片2=第2個reference_image，只供白衣、黑領帶、髮型、抽煙氣氛與場景質感參考，"
    "絕不可覆蓋圖片1的臉部身份。如圖片1與圖片2的人臉有任何分歧，必須以圖片1為準。"
)
MAX_REFERENCE_BYTES = 32 * 1024 * 1024
MAX_RESULT_BYTES = 512 * 1024 * 1024
MAX_IMAGE_BASE64_CHARACTERS = 60_000
MAX_EVENT_BYTES = 128 * 1024
MAX_API_RESPONSE_BYTES = 2 * 1024 * 1024
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,160}")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


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


def validate_exact_https_url(value: object, code: str) -> str:
    if not isinstance(value, str):
        raise SafeFailure(code + "_INVALID")
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
        raise SafeFailure(code + "_NOT_EXACT_PUBLIC_HTTPS_OBJECT")
    return value


def expected_parameters() -> dict:
    return {
        "resolution": "720P",
        "ratio": "9:16",
        "duration": 10,
        "audio": False,
        "prompt_extend": False,
        "watermark": False,
    }


def shot_by_id(manifest: dict, shot_id: str) -> dict:
    for shot in manifest.get("shots", []):
        if isinstance(shot, dict) and shot.get("shot_id") == shot_id:
            return shot
    raise SafeFailure("SHOT_ID_NOT_PINNED")


def expected_generate_title(shot: dict) -> str:
    confirmation = shot.get("confirmation")
    if not isinstance(confirmation, str) or not confirmation:
        raise SafeFailure("SHOT_CONFIRMATION_NOT_PINNED")
    return f"{WORKFLOW_TITLE_PREFIX} | generate-shot | {shot['shot_id']} | {confirmation}"


def calculated_cost(manifest: dict) -> tuple[Decimal, Decimal]:
    try:
        approval = manifest["approval"]
        rate = Decimal(approval["rate_usd_per_second"])
        fx = Decimal(approval["planning_fx_hkd_per_usd"])
        total_input = Decimal(approval["total_input_video_seconds"])
        total_output = Decimal(approval["total_output_seconds"])
        total_billable = Decimal(approval["maximum_billable_seconds"])
        declared_usd = Decimal(approval["estimated_usd"])
        declared_hkd = Decimal(approval["estimated_hkd"])
        cap = Decimal(approval["cost_cap_hkd"])
    except (KeyError, TypeError, InvalidOperation) as exc:
        raise SafeFailure("MANIFEST_COST_SCHEMA_INVALID") from exc
    if rate != Decimal("0.082513") or fx != Decimal("8.0"):
        raise SafeFailure("MANIFEST_COST_BASIS_MISMATCH")
    if total_input != Decimal("29.033333333333333") or total_output != Decimal("30"):
        raise SafeFailure("MANIFEST_TOTAL_DURATION_MISMATCH")
    if (
        total_billable != total_input + total_output
        or total_billable != Decimal("59.033333333333333")
    ):
        raise SafeFailure("MANIFEST_TOTAL_BILLABLE_SECONDS_MISMATCH")
    summed_input = Decimal("0")
    summed_output = Decimal("0")
    summed_usd = Decimal("0")
    summed_hkd = Decimal("0")
    for shot in manifest.get("shots", []):
        try:
            cost = shot["cost"]
            input_seconds = Decimal(cost["input_video_seconds"])
            output_seconds = Decimal(cost["output_seconds"])
            billable = Decimal(cost["maximum_billable_seconds"])
            shot_usd = Decimal(cost["estimated_usd"])
            shot_hkd = Decimal(cost["estimated_hkd"])
        except (KeyError, TypeError, InvalidOperation) as exc:
            raise SafeFailure("SHOT_COST_SCHEMA_INVALID") from exc
        if billable != input_seconds + output_seconds:
            raise SafeFailure("SHOT_BILLABLE_SECONDS_MISMATCH")
        if input_seconds + output_seconds > Decimal("30"):
            raise SafeFailure("SHOT_INPUT_PLUS_OUTPUT_EXCEEDS_30_SECONDS")
        if shot_usd != billable * rate or shot_hkd != shot_usd * fx:
            raise SafeFailure("SHOT_COST_ESTIMATE_MISMATCH")
        summed_input += input_seconds
        summed_output += output_seconds
        summed_usd += shot_usd
        summed_hkd += shot_hkd
    if (summed_input, summed_output) != (total_input, total_output):
        raise SafeFailure("SHOT_DURATION_SUM_MISMATCH")
    if summed_usd != declared_usd or summed_hkd != declared_hkd:
        raise SafeFailure("MANIFEST_COST_ESTIMATE_MISMATCH")
    if declared_hkd > cap or cap != Decimal("45.00"):
        raise SafeFailure("MANIFEST_COST_CAP_MISMATCH")
    return declared_hkd, cap


def validate_identity_metadata(manifest: dict) -> None:
    image = manifest.get("identity_image", {})
    fixed = {'source_sha256': '3072605a69d3e6d44033bcbcb12bb80c8027ed0cb2eaf186e7fbaf97673417d1', 'source_bytes': 2058588, 'source_dimensions': [1086, 1448], 'transport_sha256': 'da0326afd1faeafb1e8c500caee4866600edc18bd96eeed91b0f86d26d36aa6d', 'transport_mime': 'image/webp', 'transport_bytes': 7670, 'transport_base64_characters': 10228, 'transport_dimensions': [360, 480], 'transport_source': 'GITHUB_EVENT_PATH only', 'repository_binary_allowed': False, 'logging_allowed': False}
    if any(image.get(key) != value for key, value in fixed.items()):
        raise SafeFailure("IDENTITY_METADATA_MISMATCH")
    if image["transport_base64_characters"] != 4 * ((image["transport_bytes"] + 2) // 3):
        raise SafeFailure("IDENTITY_BASE64_SIZE_INVALID")
    if image["transport_base64_characters"] >= MAX_IMAGE_BASE64_CHARACTERS:
        raise SafeFailure("IDENTITY_TOO_LARGE_FOR_PRIVATE_EVENT_INPUT")


def validate_scene_metadata(manifest: dict) -> None:
    image = manifest.get("secondary_scene_image", {})
    fixed = {'role': 'Image 2: secondary clothing, atmosphere and vertical scene reference only; Image 1 v08 remains sole face and identity authority', 'source_sha256': '6d76d38401aee82926eca776f3ff0550f40d0d9fd9d713258b29dae8e344892e', 'source_bytes': 1087270, 'source_dimensions': [720, 1280], 'transport_sha256': '888190d14bb62a5917eea4269268dda2d1eaf656e013b866f1590132f10a3e8e', 'transport_mime': 'image/webp', 'transport_bytes': 9074, 'transport_base64_characters': 12100, 'transport_dimensions': [270, 480], 'transport_source': 'GITHUB_EVENT_PATH only', 'repository_binary_allowed': False, 'logging_allowed': False, 'identity_authority': False}
    if any(image.get(key) != value for key, value in fixed.items()):
        raise SafeFailure("SECONDARY_SCENE_METADATA_MISMATCH")
    if image["transport_base64_characters"] != 4 * ((image["transport_bytes"] + 2) // 3):
        raise SafeFailure("SECONDARY_SCENE_BASE64_SIZE_INVALID")
    if image["transport_base64_characters"] >= MAX_IMAGE_BASE64_CHARACTERS:
        raise SafeFailure("SECONDARY_SCENE_TOO_LARGE_FOR_PRIVATE_EVENT_INPUT")


def validate_manifest_shape(manifest: dict, allow_staged: bool) -> None:
    fixed_identity = {
        "schema_version": 1,
        "project": "StormMV_Zachary",
        "client": "Zachary Chan / STARBAY",
        "version": "v09",
    }
    if any(manifest.get(key) != value for key, value in fixed_identity.items()):
        raise SafeFailure("MANIFEST_IDENTITY_MISMATCH")
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
    constraints = manifest.get("official_constraints", {})
    expected_constraints = {
        "reference_video_max_seconds_per_clip": 15,
        "reference_video_max_total_seconds": 15,
        "input_plus_output_max_seconds": 30,
        "output_duration_must_be_integer": True,
        "reference_and_image_combination_supported": True,
    }
    if any(constraints.get(key) != value for key, value in expected_constraints.items()):
        raise SafeFailure("OFFICIAL_CONSTRAINTS_MISMATCH")
    if "720P" not in constraints.get("supported_output_resolutions", []):
        raise SafeFailure("OFFICIAL_720P_SUPPORT_NOT_PINNED")
    approval = manifest.get("approval", {})
    if approval.get("maximum_total_submissions") != 3:
        raise SafeFailure("BATCH_POST_LIMIT_MISMATCH")
    if approval.get("maximum_provider_posts_per_run") != 1:
        raise SafeFailure("PER_RUN_POST_LIMIT_MISMATCH")
    if approval.get("automatic_paid_retries") != 0:
        raise SafeFailure("AUTOMATIC_RETRY_MUST_BE_ZERO")
    if approval.get("discount_assumed") is not False or approval.get("free_quota_assumed") is not False:
        raise SafeFailure("DISCOUNT_OR_FREE_QUOTA_MUST_NOT_BE_ASSUMED")
    calculated_cost(manifest)
    # Runtime validation must stop on the missing paid authorization before it
    # evaluates URLs, bindings, event payloads, or any other live-path input.
    if not allow_staged and approval.get("approved") is not True:
        raise SafeFailure("PAID_GENERATION_NOT_AUTHORIZED")
    execution = manifest.get("execution", {})
    fixed_execution = {
        "workflow_file": WORKFLOW_FILE,
        "concurrency_group": "wan-hk-storm-mv-zachary-v09-full-mv-paid-generation",
        "github_permissions": "contents:read,actions:read",
        "run_attempt_required": 1,
        "maximum_provider_posts": 3,
        "maximum_provider_posts_per_run": 1,
        "one_shot_ledger_max_pages": 20,
        "one_shot_ledger_page_size": 100,
        "poll_max_attempts": 100,
        "poll_interval_seconds": 15,
    }
    if any(execution.get(key) != value for key, value in fixed_execution.items()):
        raise SafeFailure("MANIFEST_EXECUTION_SCOPE_MISMATCH")
    if not str(execution.get("unknown_post_outcome_policy", "")).startswith("DO_NOT_RETRY"):
        raise SafeFailure("MANIFEST_UNKNOWN_OUTCOME_POLICY_MISMATCH")
    validate_identity_metadata(manifest)
    validate_scene_metadata(manifest)
    shots = manifest.get("shots")
    if not isinstance(shots, list) or tuple(shot.get("shot_id") for shot in shots) != SHOT_IDS:
        raise SafeFailure("MANIFEST_SHOT_SET_OR_ORDER_INVALID")
    expected_frames = {
        "s01": ([2, 301], 300, "10.000000"),
        "s02": ([302, 601], 300, "10.000000"),
        "s03": ([602, 872], 271, "9.033333333333333"),
    }
    for shot in shots:
        shot_id = shot["shot_id"]
        frames, count, duration = expected_frames[shot_id]
        if shot.get("storyboard_order") != SHOT_IDS.index(shot_id) + 1:
            raise SafeFailure("SHOT_STORYBOARD_ORDER_MISMATCH")
        if shot.get("source_frames_inclusive") != frames or shot.get("source_frame_count") != count:
            raise SafeFailure("SHOT_SOURCE_FRAME_RANGE_MISMATCH")
        if shot.get("source_crop") != {"width": 720, "height": 404, "x": 0, "y": 278}:
            raise SafeFailure("SHOT_SOURCE_CROP_MISMATCH")
        reference = shot.get("reference_transport", {})
        fixed_reference = {
            "dimensions": [720, 404],
            "duration_seconds": duration,
            "fps": "30/1",
            "video_codec": "h264",
            "pixel_format": "yuv420p",
            "required_audio_streams": 0,
            "maximum_download_bytes": MAX_REFERENCE_BYTES,
        }
        if any(reference.get(key) != value for key, value in fixed_reference.items()):
            raise SafeFailure("SHOT_REFERENCE_METADATA_MISMATCH")
        if Decimal(duration) > Decimal("15"):
            raise SafeFailure("SHOT_REFERENCE_EXCEEDS_15_SECONDS")
        if shot.get("parameters") != expected_parameters():
            raise SafeFailure("SHOT_PARAMETERS_MISMATCH")
        request = shot.get("request", {})
        if request.get("reference_video_url") != reference.get("expected_url"):
            raise SafeFailure("SHOT_REQUEST_REFERENCE_URL_MISMATCH")
        if not SHA256_PATTERN.fullmatch(str(request.get("sha256", ""))):
            raise SafeFailure("SHOT_REQUEST_SHA256_INVALID")
        prompt_source = shot.get("prompt_source", {})
        if (
            not isinstance(prompt_source.get("path"), str)
            or not SHA256_PATTERN.fullmatch(str(prompt_source.get("sha256", "")))
            or not isinstance(prompt_source.get("bytes"), int)
            or prompt_source["bytes"] <= 0
        ):
            raise SafeFailure("SHOT_PROMPT_SOURCE_METADATA_INVALID")
        load_request(shot, allow_staged=allow_staged)
        staged_reference = reference.get("registration_state") == "PENDING_SEPARATE_PUBLIC_UPLOAD_AUTHORIZATION"
        if allow_staged and staged_reference:
            if not str(reference.get("expected_url", "")).startswith(f"__STORM_V09_{shot_id.upper()}_"):
                raise SafeFailure("SHOT_REFERENCE_PLACEHOLDER_MISMATCH")
            if not SHA256_PATTERN.fullmatch(str(reference.get("sha256", ""))):
                raise SafeFailure("STAGED_LOCAL_REFERENCE_SHA256_NOT_PINNED")
            if not isinstance(reference.get("bytes"), int) or not 0 < reference["bytes"] <= MAX_REFERENCE_BYTES:
                raise SafeFailure("STAGED_LOCAL_REFERENCE_BYTE_COUNT_INVALID")
            if reference.get("public_upload_approved") is not False:
                raise SafeFailure("STAGED_PUBLIC_UPLOAD_MUST_NOT_BE_APPROVED")
            if reference.get("public_readback_verified") is not False:
                raise SafeFailure("STAGED_PUBLIC_READBACK_MUST_NOT_BE_VERIFIED")
        else:
            if reference.get("registration_state") != "REGISTERED_EXACT_URL_PINNED":
                raise SafeFailure("SHOT_REFERENCE_NOT_REGISTERED")
            validate_exact_https_url(reference.get("expected_url"), "SHOT_REFERENCE_URL")
            if not SHA256_PATTERN.fullmatch(str(reference.get("sha256", ""))):
                raise SafeFailure("SHOT_REFERENCE_SHA256_INVALID")
            if not isinstance(reference.get("bytes"), int) or not 0 < reference["bytes"] <= MAX_REFERENCE_BYTES:
                raise SafeFailure("SHOT_REFERENCE_BYTE_COUNT_INVALID")
        if allow_staged:
            if shot.get("approval") is not False or shot.get("dispatch_enabled") is not False:
                raise SafeFailure("STAGED_SHOT_MUST_NOT_BE_APPROVED_OR_DISPATCHABLE")
            if any(shot.get(key) is not None for key in (
                "authorization_id", "confirmation", "workflow_run_title_generate"
            )):
                raise SafeFailure("STAGED_SHOT_AUTHORIZATION_FIELDS_MUST_BE_NULL")
        else:
            if shot.get("approval") is not True or shot.get("dispatch_enabled") is not True:
                raise SafeFailure("SHOT_PAID_GENERATION_NOT_AUTHORIZED")
            if shot.get("workflow_run_title_generate") != expected_generate_title(shot):
                raise SafeFailure("SHOT_GENERATE_TITLE_MISMATCH")
            if Decimal(str(shot.get("cost", {}).get("approved_cap_hkd"))) <= 0:
                raise SafeFailure("SHOT_COST_CAP_NOT_APPROVED")
    staged_manifest = (
        manifest.get("authorization") == "NOT_GRANTED"
        and manifest.get("dispatch_enabled") is False
        and manifest.get("staged_only_build") is True
        and approval.get("approved") is False
        and manifest.get("status") == "STAGED_AWAITING_NEW_EXACT_USER_APPROVAL_AND_REFERENCE_UPLOADS"
    )
    if allow_staged:
        if not staged_manifest:
            raise SafeFailure("STAGED_MANIFEST_FAIL_CLOSED_FIELDS_INVALID")
    else:
        if manifest.get("authorization") != "GRANTED" or approval.get("approved") is not True:
            raise SafeFailure("PAID_GENERATION_NOT_AUTHORIZED")
        if manifest.get("dispatch_enabled") is not True or manifest.get("staged_only_build") is not False:
            raise SafeFailure("PAID_DISPATCH_NOT_ENABLED")
        if manifest.get("status") != "APPROVED_THREE_SHOT_READY":
            raise SafeFailure("PAID_MANIFEST_STATUS_NOT_READY")


def validate_request_payload(request: object, shot: dict, allow_staged: bool) -> dict:
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
    required_prompt_fragments = (
        "影片1=第1個reference_video",
        "圖片1=第1個reference_image",
        "圖片2=第2個reference_image",
        "v08 Zachary唯一臉部及身份依據",
        "白衣中央主角",
        "Zachary",
    )
    if any(fragment not in prompt for fragment in required_prompt_fragments):
        raise SafeFailure("REQUEST_EDIT_INTENT_NOT_BOUND")
    expected_url = shot["reference_transport"]["expected_url"]
    expected_media = [
        {"type": "reference_video", "url": expected_url},
        {"type": "reference_image", "url": IDENTITY_PLACEHOLDER},
        {"type": "reference_image", "url": SCENE_PLACEHOLDER},
    ]
    if input_value.get("media") != expected_media:
        raise SafeFailure("REQUEST_MEDIA_TEMPLATE_OR_ORDER_INVALID")
    if not allow_staged:
        validate_exact_https_url(expected_url, "SHOT_REFERENCE_URL")
    return request


def load_request(shot: dict, allow_staged: bool) -> dict:
    path = safe_relative_path(ROOT, shot["request"].get("path"), "REQUEST")
    try:
        raw = path.read_bytes()
        request = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("REQUEST_FILE_INVALID") from exc
    if sha256_bytes(raw) != shot["request"].get("sha256"):
        raise SafeFailure("REQUEST_SHA256_MISMATCH")
    return validate_request_payload(request, shot, allow_staged)


def load_manifest(allow_staged: bool = False) -> dict:
    try:
        raw = MANIFEST_FILE.read_bytes()
        manifest = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise SafeFailure("MANIFEST_FILE_INVALID") from exc
    if sha256_bytes(raw) != EXPECTED_MANIFEST_SHA256:
        raise SafeFailure("MANIFEST_SHA256_MISMATCH_REPIN_REQUIRED")
    if not isinstance(manifest, dict):
        raise SafeFailure("MANIFEST_FILE_INVALID")
    validate_manifest_shape(manifest, allow_staged)
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


def decode_private_image_input(encoded: str, metadata: dict, code: str) -> bytes:
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


def read_private_inputs_from_event(event_path: Path) -> tuple[str, str, str]:
    """Read shot ID and two private images without copying payloads to env/output."""
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
    shot_id = inputs.get("shot_id")
    encoded_identity = inputs.get("zachary_image_base64")
    encoded_scene = inputs.get("secondary_scene_image_base64")
    if shot_id not in SHOT_IDS:
        raise SafeFailure("GITHUB_EVENT_SHOT_ID_INVALID")
    if not isinstance(encoded_identity, str) or len(encoded_identity) >= MAX_IMAGE_BASE64_CHARACTERS:
        raise SafeFailure("GITHUB_EVENT_IDENTITY_INPUT_INVALID")
    if any(character.isspace() for character in encoded_identity):
        raise SafeFailure("GITHUB_EVENT_IDENTITY_INPUT_INVALID")
    if not isinstance(encoded_scene, str) or len(encoded_scene) >= MAX_IMAGE_BASE64_CHARACTERS:
        raise SafeFailure("GITHUB_EVENT_SECONDARY_SCENE_INPUT_INVALID")
    if any(character.isspace() for character in encoded_scene):
        raise SafeFailure("GITHUB_EVENT_SECONDARY_SCENE_INPUT_INVALID")
    return shot_id, encoded_identity, encoded_scene


def runtime_private_inputs(expected_shot_id: str) -> tuple[str, str]:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SafeFailure("GENERATE_REQUIRES_GITHUB_ACTIONS_EVENT_INPUT")
    event_path_text = os.environ.get("GITHUB_EVENT_PATH", "")
    event_path = Path(event_path_text)
    if not event_path_text or not event_path.is_absolute():
        raise SafeFailure("GITHUB_EVENT_PATH_INVALID")
    event_shot_id, encoded_identity, encoded_scene = read_private_inputs_from_event(event_path)
    if event_shot_id != expected_shot_id:
        raise SafeFailure("GITHUB_EVENT_SHOT_ID_MISMATCH")
    return encoded_identity, encoded_scene


def build_provider_payload(
    manifest: dict,
    shot: dict,
    encoded_identity: str,
    encoded_scene: str,
) -> dict:
    request = copy.deepcopy(load_request(shot, allow_staged=False))
    identity_data = decode_private_image_input(
        encoded_identity, manifest["identity_image"], "IDENTITY"
    )
    scene_data = decode_private_image_input(
        encoded_scene, manifest["secondary_scene_image"], "SECONDARY_SCENE"
    )
    request["input"]["media"][1]["url"] = (
        "data:image/webp;base64," + base64.b64encode(identity_data).decode("ascii")
    )
    request["input"]["media"][2]["url"] = (
        "data:image/webp;base64," + base64.b64encode(scene_data).decode("ascii")
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
            check=True, capture_output=True, timeout=600,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise SafeFailure(code) from exc


def validate_reference_video_file(path: Path, shot: dict) -> dict:
    reference = shot["reference_transport"]
    if not SHA256_PATTERN.fullmatch(str(reference.get("sha256", ""))):
        raise SafeFailure("REFERENCE_VIDEO_SHA256_NOT_PINNED")
    if not isinstance(reference.get("bytes"), int):
        raise SafeFailure("REFERENCE_VIDEO_BYTE_COUNT_NOT_PINNED")
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
    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
    audio_streams = [stream for stream in streams if stream.get("codec_type") == "audio"]
    if len(video_streams) != 1 or len(audio_streams) != reference["required_audio_streams"]:
        raise SafeFailure("REFERENCE_VIDEO_STREAM_LAYOUT_INVALID")
    stream = video_streams[0]
    try:
        dimensions = [int(stream["width"]), int(stream["height"])]
        duration = Decimal(str(metadata["format"]["duration"]))
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise SafeFailure("REFERENCE_VIDEO_METADATA_INVALID") from exc
    if dimensions != reference["dimensions"]:
        raise SafeFailure("REFERENCE_VIDEO_DIMENSIONS_MISMATCH")
    if abs(duration - Decimal(reference["duration_seconds"])) > Decimal("0.05"):
        raise SafeFailure("REFERENCE_VIDEO_DURATION_MISMATCH")
    if duration < Decimal("1") or duration > Decimal("15"):
        raise SafeFailure("REFERENCE_VIDEO_DURATION_OUTSIDE_OFFICIAL_RANGE")
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
        "shot_id": shot["shot_id"],
        "url": reference["expected_url"],
        "sha256": digest,
        "bytes": size,
        "duration_seconds": str(duration),
        "dimensions": dimensions,
        "video_codec": stream.get("codec_name"),
        "fps": stream.get("avg_frame_rate"),
        "audio_stream_count": len(audio_streams),
        "full_decode": "PASS",
    }


def fetch_and_validate_reference(shot: dict, work_dir: Path) -> dict:
    reference = shot["reference_transport"]
    url = validate_exact_https_url(reference["expected_url"], "REFERENCE_URL")
    target = work_dir / f"storm-motion-reference-v09-{shot['shot_id']}.mp4"
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(
            url, headers={"User-Agent": "StormMV-Zachary-WanHK-v09/1.0"}
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
    return validate_reference_video_file(target, shot)


def require_live_build(manifest: dict) -> None:
    if STAGED_ONLY_BUILD or manifest.get("staged_only_build") is not False:
        raise SafeFailure("STAGED_ONLY_BUILD_EXTERNAL_CALLS_DISABLED")
    if manifest.get("authorization") != "GRANTED" or manifest.get("dispatch_enabled") is not True:
        raise SafeFailure("PAID_DISPATCH_NOT_AUTHORIZED")


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
            "User-Agent": "StormMV-Zachary-Shot-Ledger-v09",
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


def assert_one_shot_ledger_clear(manifest: dict, shot: dict) -> None:
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
    title = expected_generate_title(shot)
    execution = manifest["execution"]
    page_size = execution["one_shot_ledger_page_size"]
    max_pages = execution["one_shot_ledger_max_pages"]
    scanned = 0
    total_count: int | None = None
    current_found = False
    authorized_titles = {expected_generate_title(item) for item in manifest["shots"]}
    batch_generate_run_count = 0
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
            if display_title in authorized_titles:
                batch_generate_run_count += 1
            if run_id == current_run_id:
                if display_title != title:
                    raise SafeFailure("ONE_SHOT_LEDGER_CURRENT_RUN_TITLE_MISMATCH")
                current_found = True
            elif display_title == title:
                raise SafeFailure("SHOT_AUTHORIZATION_ALREADY_CONSUMED_NEW_AUTH_REQUIRED")
        if len(runs) < page_size:
            break
    if not current_found:
        raise SafeFailure("ONE_SHOT_LEDGER_CURRENT_RUN_NOT_FOUND")
    if total_count is None or scanned < total_count:
        raise SafeFailure("ONE_SHOT_LEDGER_HISTORY_EXCEEDS_BOUNDED_SCAN")
    if batch_generate_run_count > manifest["approval"]["maximum_total_submissions"]:
        raise SafeFailure("BATCH_MAXIMUM_POST_AUTHORIZATIONS_EXCEEDED")


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
            raw = response.read(MAX_API_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        try:
            parsed = json.loads(exc.read(MAX_API_RESPONSE_BYTES + 1).decode("utf-8"))
            code = safe_api_code(
                parsed.get("code") if isinstance(parsed, dict) else None, "HTTP_ERROR"
            )
        except (OSError, UnicodeDecodeError, ValueError):
            code = "HTTP_ERROR"
        raise ApiFailure(status, code, 400 <= status < 500) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise ApiFailure(None, "NETWORK_OR_TIMEOUT", False) from None
    if len(raw) > MAX_API_RESPONSE_BYTES:
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


def base_receipt(mode: str, manifest: dict, shot: dict, host: str) -> dict:
    reference = shot["reference_transport"]
    return {
        "project": manifest["project"],
        "client": manifest["client"],
        "version": manifest["version"],
        "shot_id": shot["shot_id"],
        "mode": mode,
        "model": MODEL,
        "api_host": host,
        "authorization": manifest["authorization"],
        "approval": {
            "authorization_id": shot["authorization_id"],
            "batch_cost_cap_hkd": manifest["approval"]["cost_cap_hkd"],
            "shot_approved_cap_hkd": shot["cost"]["approved_cap_hkd"],
            "shot_estimated_hkd": shot["cost"]["estimated_hkd"],
        },
        "source": {
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "request_path": shot["request"]["path"],
            "request_sha256": shot["request"]["sha256"],
            "reference_video_url": reference["expected_url"],
            "reference_video_sha256": reference["sha256"],
            "reference_video_bytes": reference["bytes"],
            "identity_transport_sha256": manifest["identity_image"]["transport_sha256"],
            "secondary_scene_transport_sha256": (
                manifest["secondary_scene_image"]["transport_sha256"]
            ),
        },
        "maximum_provider_posts_this_run": 1,
        "automatic_paid_retries": 0,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "updated_utc": utc_now(),
    }


def output_paths(output_dir: Path, shot: dict) -> tuple[Path, Path, Path]:
    stem = f"storm-mv-zachary-v09-{shot['shot_id']}"
    return (
        output_dir / f"{stem}-receipt.json",
        output_dir / shot["request"]["output_name"],
        output_dir / f"{stem}-video-validation.json",
    )


def validate_generate_preflight(
    manifest: dict, shot: dict, output_dir: Path, confirmation: str
) -> None:
    require_live_build(manifest)
    if shot.get("approval") is not True or shot.get("dispatch_enabled") is not True:
        raise SafeFailure("SHOT_PAID_GENERATION_NOT_AUTHORIZED")
    if confirmation != shot.get("confirmation"):
        raise SafeFailure("SHOT_GENERATE_CONFIRMATION_REQUIRED")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise SafeFailure("GENERATE_REQUIRES_GITHUB_RUN_ATTEMPT_1")
    calculated_cost(manifest)
    receipt_path, output_path, validation_path = output_paths(output_dir, shot)
    if receipt_path.exists() or output_path.exists() or validation_path.exists():
        raise SafeFailure("DUPLICATE_GUARD_EXISTING_RUN_EVIDENCE")
    assert_one_shot_ledger_clear(manifest, shot)


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
    print(f"SUBMITTED shot_id={receipt['shot_id']} task_id={task_id}", flush=True)
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
            url, headers={"User-Agent": "StormMV-Zachary-WanHK-v09/1.0"}
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
    poll_max_attempts: int,
    poll_interval_seconds: int,
) -> None:
    receipt["task_id"] = task_id
    for _ in range(poll_max_attempts):
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
        time.sleep(poll_interval_seconds)
    receipt["status"] = "POLL_WINDOW_ENDED_RESUME_SAME_TASK"
    write_json(receipt_path, receipt)
    raise SafeFailure("POLL_WINDOW_ENDED_RESUME_SAME_TASK")


def verify_output_video(path: Path, manifest: dict, shot: dict) -> dict:
    if not path.is_file() or path.name != shot["request"]["output_name"]:
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
        duration = Decimal(str(metadata["format"]["duration"]))
    except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
        raise SafeFailure("VIDEO_METADATA_INVALID") from exc
    if width >= height or min(width, height) != manifest["output_validation"]["short_edge_pixels"]:
        raise SafeFailure("VIDEO_RESOLUTION_NOT_720P_PORTRAIT")
    target_ratio = Decimal(9) / Decimal(16)
    actual_ratio = Decimal(width) / Decimal(height)
    tolerance = Decimal(str(manifest["output_validation"]["ratio_tolerance"]))
    if abs(actual_ratio - target_ratio) > tolerance:
        raise SafeFailure("VIDEO_RATIO_NOT_9_16")
    requested_duration = Decimal(str(shot["parameters"]["duration"]))
    if abs(duration - requested_duration) > Decimal(str(manifest["output_validation"]["duration_tolerance_seconds"])):
        raise SafeFailure("VIDEO_DURATION_MISMATCH")
    full_decode(path, "FFMPEG_FULL_DECODE_FAILED")
    rate = Decimal(manifest["approval"]["rate_usd_per_second"])
    fx = Decimal(manifest["approval"]["planning_fx_hkd_per_usd"])
    input_seconds = Decimal(shot["cost"]["input_video_seconds"])
    billable_seconds = input_seconds + duration
    actual_usd = rate * billable_seconds
    actual_hkd = actual_usd * fx
    shot_cap = shot["cost"].get("approved_cap_hkd")
    if shot_cap is not None and actual_hkd > Decimal(str(shot_cap)):
        raise SafeFailure("VALIDATED_USAGE_EXCEEDS_APPROVED_SHOT_CAP")
    if actual_hkd > Decimal(manifest["approval"]["cost_cap_hkd"]):
        raise SafeFailure("VALIDATED_USAGE_EXCEEDS_APPROVED_BATCH_CAP")
    result = {
        "status": "SILENT_DURATION_720P_9_16_FULL_DECODE_VALIDATED",
        "shot_id": shot["shot_id"],
        "filename": path.name,
        "sha256": sha256_bytes(path.read_bytes()),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": str(duration),
        "video_codec": stream.get("codec_name"),
        "audio_stream_count": 0,
        "full_decode": "PASS",
        "actual_usage": {
            "verified_input_video_seconds": str(input_seconds),
            "validated_output_video_seconds": str(duration),
            "actual_billable_seconds": str(billable_seconds),
            "rate_usd_per_second": str(rate),
            "actual_usd": str(actual_usd),
            "planning_fx_hkd_per_usd": str(fx),
            "actual_hkd": str(actual_hkd),
        },
        "validated_utc": utc_now(),
    }
    _, _, validation_path = output_paths(path.parent, shot)
    write_json(validation_path, result)
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
    image = manifest["identity_image"]
    source_path = Path(image["source_path"])
    try:
        source = source_path.read_bytes()
    except OSError as exc:
        raise SafeFailure("LOCAL_IDENTITY_SOURCE_UNREADABLE") from exc
    if (
        sha256_bytes(source) != image["source_sha256"]
        or len(source) != image["source_bytes"]
        or detected_image_mime(source) != "image/png"
        or image_dimensions(source) != tuple(image["source_dimensions"])
    ):
        raise SafeFailure("LOCAL_IDENTITY_SOURCE_METADATA_MISMATCH")
    transport = reproduce_transport(source_path, image["transport_dimensions"])
    validate_image_bytes(transport, image, "LOCAL_IDENTITY_TRANSPORT")
    scene = manifest["secondary_scene_image"]
    scene_source_path = Path(scene["source_path"])
    try:
        scene_source = scene_source_path.read_bytes()
    except OSError as exc:
        raise SafeFailure("LOCAL_SECONDARY_SCENE_SOURCE_UNREADABLE") from exc
    if (
        sha256_bytes(scene_source) != scene["source_sha256"]
        or len(scene_source) != scene["source_bytes"]
        or detected_image_mime(scene_source) != "image/png"
        or image_dimensions(scene_source) != tuple(scene["source_dimensions"])
    ):
        raise SafeFailure("LOCAL_SECONDARY_SCENE_SOURCE_METADATA_MISMATCH")
    scene_transport = reproduce_transport(scene_source_path, scene["transport_dimensions"])
    validate_image_bytes(scene_transport, scene, "LOCAL_SECONDARY_SCENE_TRANSPORT")
    for shot in manifest["shots"]:
        reference = shot["reference_transport"]
        prompt_source = shot["prompt_source"]
        try:
            prompt_raw = Path(prompt_source["path"]).read_bytes()
            prompt_text = prompt_raw.decode("utf-8").strip()
        except (OSError, UnicodeDecodeError) as exc:
            raise SafeFailure("LOCAL_PROMPT_SOURCE_UNREADABLE") from exc
        if (
            len(prompt_raw) != prompt_source["bytes"]
            or sha256_bytes(prompt_raw) != prompt_source["sha256"]
            or (
                PROMPT_MEDIA_MAPPING_PREFIX + "\n\n" + prompt_text
                != load_request(shot, allow_staged=True)["input"]["prompt"]
            )
        ):
            raise SafeFailure("LOCAL_PROMPT_SOURCE_METADATA_OR_REQUEST_MISMATCH")
        validate_reference_video_file(Path(reference["local_review_source_path"]), shot)


def offline_validate(manifest: dict, validate_assets: bool) -> None:
    calculated_cost(manifest)
    for shot in manifest["shots"]:
        load_request(shot, allow_staged=True)
    if validate_assets:
        validate_local_assets(manifest)
    print("OFFLINE_VALIDATION_PASS_ZERO_PROVIDER_CALLS")


def run_mode(mode: str, manifest: dict, shot: dict, output_dir: Path) -> None:
    require_live_build(manifest)
    confirmation = os.environ.get("WAN_GENERATE_CONFIRMATION", "")
    resume_task_id = None
    if mode == "generate-shot":
        validate_generate_preflight(manifest, shot, output_dir, confirmation)
    elif mode == "resume-shot":
        resume_task_id = valid_uuid(os.environ.get("WAN_RESUME_TASK_ID", ""))
        if not resume_task_id:
            raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path, output_path, _ = output_paths(output_dir, shot)
    if mode == "check-binding":
        receipt = base_receipt(mode, manifest, shot, host)
        receipt["status"] = "BINDING_PRESENT_NOT_API_VERIFIED_ZERO_PROVIDER_CALLS"
        write_json(receipt_path, receipt)
        print("BINDING_PRESENT_NOT_API_VERIFIED_ZERO_PROVIDER_CALLS")
        return
    if mode == "generate-shot":
        encoded_identity, encoded_scene = runtime_private_inputs(shot["shot_id"])
        payload = build_provider_payload(
            manifest, shot, encoded_identity, encoded_scene
        )
        with tempfile.TemporaryDirectory(prefix=f"storm-v09-{shot['shot_id']}-reference-") as temporary:
            reference = fetch_and_validate_reference(shot, Path(temporary))
        receipt = base_receipt(mode, manifest, shot, host)
        receipt.update(
            {
                "status": "ONE_SHOT_LEDGER_IDENTITY_AND_REFERENCE_VERIFIED",
                "verified_reference_video": reference,
            }
        )
        write_json(receipt_path, receipt)
        task_id = submit_once(host, key, payload, receipt_path, receipt)
        poll_get_only(
            host, key, task_id, receipt_path, receipt, output_path,
            manifest["execution"]["poll_max_attempts"],
            manifest["execution"]["poll_interval_seconds"],
        )
        return
    if mode != "resume-shot" or resume_task_id is None:
        raise SafeFailure("RUNTIME_MODE_INVALID")
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SafeFailure("RESUME_RECEIPT_INVALID") from exc
        if (
            not isinstance(receipt, dict)
            or receipt.get("project") != manifest["project"]
            or receipt.get("shot_id") != shot["shot_id"]
        ):
            raise SafeFailure("RESUME_RECEIPT_INVALID")
        if receipt.get("task_id") not in {None, resume_task_id}:
            raise SafeFailure("RESUME_TASK_ID_MISMATCH")
    else:
        receipt = base_receipt(mode, manifest, shot, host)
    receipt.update(
        {"task_id": resume_task_id, "mode": "resume-shot", "status": "RESUME_GET_ONLY_STARTING"}
    )
    write_json(receipt_path, receipt)
    poll_get_only(
        host, key, resume_task_id, receipt_path, receipt, output_path,
        manifest["execution"]["poll_max_attempts"],
        manifest["execution"]["poll_interval_seconds"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=[
            "validate-package", "validate-local-assets", "check-binding",
            "generate-shot", "resume-shot", "validate-existing",
        ],
        default="validate-package",
    )
    parser.add_argument("--shot-id", choices=SHOT_IDS)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--verify-output")
    args = parser.parse_args()
    try:
        if args.mode in {"validate-package", "validate-local-assets"}:
            if args.output_dir or args.verify_output:
                raise SafeFailure("RUNTIME_ARGUMENT_NOT_ALLOWED_IN_OFFLINE_MODE")
            manifest = load_manifest(allow_staged=False)
            offline_validate(manifest, args.mode == "validate-local-assets")
            return 0
        if not args.shot_id:
            raise SafeFailure("SHOT_ID_REQUIRED")
        if args.mode == "validate-existing":
            manifest = load_manifest(allow_staged=False)
            shot = shot_by_id(manifest, args.shot_id)
            if not args.verify_output:
                raise SafeFailure("VERIFY_OUTPUT_PATH_REQUIRED")
            path = safe_relative_path(ROOT, args.verify_output, "VERIFY_OUTPUT")
            verify_output_video(path, manifest, shot)
            return 0
        if args.verify_output:
            raise SafeFailure("VERIFY_OUTPUT_ONLY_ALLOWED_FOR_VALIDATE_EXISTING")
        manifest = load_manifest(allow_staged=False)
        shot = shot_by_id(manifest, args.shot_id)
        output_dir = (
            args.output_dir.resolve()
            if args.output_dir
            else (ROOT / "output-storm-mv-zachary-v09" / args.shot_id).resolve()
        )
        try:
            output_dir.relative_to(ROOT.resolve())
        except ValueError as exc:
            raise SafeFailure("OUTPUT_DIR_OUTSIDE_EXECUTOR_ROOT") from exc
        run_mode(args.mode, manifest, shot, output_dir)
        return 0
    except SafeFailure as failure:
        print("ERROR " + failure.code, file=sys.stderr)
        return 1
    except Exception:
        print("ERROR UNEXPECTED_LOCAL_FAILURE", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
