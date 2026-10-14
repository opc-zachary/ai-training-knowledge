#!/usr/bin/env python3
"""Manual-only Alibaba Cloud Wan 3.0 executor for a fixed Taiwan food film.

The API key is accepted only through the process environment. This program
never prints it, writes it to an artifact, or places it in a command argument.
The reference image is read from GitHub's event JSON so its Base64 transport is
not copied into a logged workflow environment variable.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import copy
import datetime as dt
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
REQUEST_FILE = ROOT / "request-taiwan30.json"
MODEL = "wan3.0-video"
EXPECTED_REQUEST_SHA256 = "82ecd8950f9146ab36457d08a6d762e2a2eda33a557fe679797106b1893449da"
OUTPUT_NAME = (
    "TaiwanChicken_Starbay_2026-10-14_Video_"
    "TaiwanFood30Raw480p_Review_v01.mp4"
)
RECEIPT_NAME = "taiwan30-receipt.json"
VALIDATION_NAME = "taiwan30-video-validation.json"
RUNTIME_MEDIA_PLACEHOLDER = (
    "__RUNTIME_VERIFIED_REFERENCE_IMAGE_DATA_URI__"
)
HOST_PATTERN = re.compile(r"[a-zA-Z0-9-]+\.cn-hongkong\.maas\.aliyuncs\.com")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,80}")
MAX_EVENT_IMAGE_CHARACTERS = 65_535
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_VIDEO_BYTES = 512 * 1024 * 1024


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


def load_contract() -> dict:
    actual_request_sha256 = request_file_sha256()
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
        reference_sha256 = contract["reference_image_sha256"]
        reference_mime = contract["reference_image_mime"]
    except (KeyError, TypeError) as exc:
        raise SafeFailure("LOCAL_REQUEST_SCHEMA_INVALID") from exc

    if contract.get("project") != "TaiwanChicken":
        raise SafeFailure("LOCAL_REQUEST_IDENTITY_MISMATCH")
    if request.get("model") != MODEL:
        raise SafeFailure("LOCAL_MODEL_MISMATCH")
    if media != [
        {"type": "reference_image", "url": RUNTIME_MEDIA_PLACEHOLDER}
    ]:
        raise SafeFailure("LOCAL_MEDIA_TEMPLATE_INVALID")
    required_parameters = {
        "resolution": "480P",
        "ratio": "9:16",
        "duration": 30,
        "audio": True,
        "prompt_extend": False,
    }
    if parameters != required_parameters:
        raise SafeFailure("LOCAL_PARAMETERS_MISMATCH")
    prompt = request["input"].get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise SafeFailure("LOCAL_PROMPT_INVALID")
    if not isinstance(reference_sha256, str) or not SHA256_PATTERN.fullmatch(
        reference_sha256
    ):
        raise SafeFailure("LOCAL_REFERENCE_SHA256_INVALID")
    if reference_mime not in {"image/webp", "image/jpeg", "image/png"}:
        raise SafeFailure("LOCAL_REFERENCE_MIME_INVALID")
    return contract


def load_binding() -> tuple[str, str]:
    host = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_HOST", "").strip()
    key = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_KEY", "")
    if not HOST_PATTERN.fullmatch(host):
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


def load_reference_image(contract: dict) -> tuple[bytes, str]:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    if not event_path:
        raise SafeFailure("GITHUB_EVENT_PATH_REQUIRED")
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        encoded = event["inputs"]["first_image_base64"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise SafeFailure("WORKFLOW_EVENT_INPUT_INVALID") from exc
    if (
        not isinstance(encoded, str)
        or not encoded
        or len(encoded) > MAX_EVENT_IMAGE_CHARACTERS
    ):
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
    if mime != contract["reference_image_mime"]:
        raise SafeFailure("REFERENCE_IMAGE_MIME_MISMATCH")
    if hashlib.sha256(data).hexdigest() != contract["reference_image_sha256"]:
        raise SafeFailure("REFERENCE_IMAGE_SHA256_MISMATCH")
    return data, mime


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
        "project": "TaiwanChicken",
        "client": contract.get("client"),
        "model": MODEL,
        "region": "China (Hong Kong)",
        "deployment_scope": "Global",
        "mode": mode,
        "api_host": host,
        "parameters": {
            "resolution": "480P",
            "ratio": "9:16",
            "duration": 30,
            "audio": True,
            "prompt_extend": False,
        },
        "source": {
            "request_file": REQUEST_FILE.name,
            "request_sha256": EXPECTED_REQUEST_SHA256,
            "reference_image_transport": (
                "workflow_dispatch.inputs.first_image_base64"
            ),
            "reference_image_sha256": contract["reference_image_sha256"],
            "reference_image_mime": contract["reference_image_mime"],
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
        code = safe_api_code(response.get("code"), "TASK_ID_MISSING")
        receipt.update(
            {
                "status": "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY",
                "safe_error_code": code,
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
            url, headers={"User-Agent": "TaiwanChicken-WanHK-Taiwan30/1.0"}
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
    for _ in range(160):
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
            # Keep only a non-sensitive classification, never the raw provider message.
            detail = str(output.get("message", "")).lower()
            receipt["safe_error_stage"] = next((label for phrase, label in [
                ("text (input)", "INPUT_TEXT_INSPECTION"),
                ("image (input)", "INPUT_IMAGE_INSPECTION"),
                ("video (output)", "OUTPUT_VIDEO_INSPECTION"),
                ("audio (output)", "OUTPUT_AUDIO_INSPECTION"),
            ] if phrase in detail), "INSPECTION_STAGE_NOT_SPECIFIED")
            write_json(receipt_path, receipt)
            raise SafeFailure("TASK_" + state)

        receipt["status"] = "TASK_" + state
        write_json(receipt_path, receipt)
        time.sleep(15)

    receipt["status"] = "POLL_WINDOW_ENDED_RESUME_SAME_TASK"
    receipt["updated_utc"] = utc_now()
    write_json(receipt_path, receipt)
    raise SafeFailure("POLL_WINDOW_ENDED_RESUME_SAME_TASK")


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
        if width >= height or min(width, height) != 480:
            raise SafeFailure("VIDEO_RESOLUTION_NOT_480P_PORTRAIT")
        if not 29.0 <= duration <= 31.0:
            raise SafeFailure("VIDEO_DURATION_NOT_APPROX_30_SECONDS")
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
        "filename": path.name,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "width": width,
        "height": height,
        "duration_seconds": duration,
        "video_codec": stream.get("codec_name"),
        "frame_rate": stream.get("r_frame_rate"),
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
    print("FFPROBE_AND_FFMPEG_VALIDATED")


def run_mode(mode: str, output_dir: Path) -> None:
    contract = load_contract()
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
        attempt_text = os.environ.get("GITHUB_RUN_ATTEMPT", "1")
        try:
            attempt = int(attempt_text)
        except ValueError as exc:
            raise SafeFailure("GITHUB_RUN_ATTEMPT_INVALID") from exc
        if attempt != 1:
            raise SafeFailure("GENERATE_REFUSED_ON_RERUN_ATTEMPT")
        if os.environ.get("WAN_GENERATE_CONFIRMATION", "") != "GENERATE30":
            raise SafeFailure("GENERATE30_CONFIRMATION_REQUIRED")
        reference_image, reference_mime = load_reference_image(contract)
        payload = copy.deepcopy(contract["request"])
        payload["input"]["media"][0]["url"] = (
            "data:"
            + reference_mime
            + ";base64,"
            + base64.b64encode(reference_image).decode("ascii")
        )
        receipt = base_receipt(mode, host, contract)
        receipt.update(
            {
                "status": "REFERENCE_IMAGE_SHA256_VERIFIED",
                "verified_reference_image_sha256": hashlib.sha256(
                    reference_image
                ).hexdigest(),
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
    receipt = base_receipt(mode, host, contract)
    receipt.update({"task_id": task_id, "status": "RESUME_QUERY_STARTING"})
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
    parser.add_argument("--output-dir", type=Path, default=Path("output-taiwan30"))
    parser.add_argument("--offline-validate", action="store_true")
    parser.add_argument("--verify-output", type=Path)
    args = parser.parse_args()
    try:
        if args.offline_validate:
            load_contract()
            print("OFFLINE_CONTRACT_VALID")
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
