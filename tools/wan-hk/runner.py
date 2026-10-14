#!/usr/bin/env python3
"""Manual-only Alibaba Cloud Wan 3.0 executor for TaiwanChicken Shot04.

The API key is accepted only through the process environment.  This program
never prints it, writes it to a receipt, or places it in a command argument.
"""

from __future__ import annotations

import argparse
import base64
import copy
import datetime as dt
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


ROOT = Path(__file__).resolve().parent
REQUEST_FILE = ROOT / "request-shot04.json"
MODEL = "wan3.0-video"
SHOT_ID = "04"
EXPECTED_FIRST_FRAME_SHA256 = (
    "d0f0e907f6cc782cbd8818fda6295a16bbc6701df1160cf437e0b3184ffdc94e"
)
OUTPUT_NAME = "TaiwanChicken_ZacharyChan_2026-10-10_Video_Shot04Grill_Review_v01.mp4"
HOST_PATTERN = re.compile(
    r"[a-zA-Z0-9-]+\.cn-hongkong\.maas\.aliyuncs\.com"
)
SAFE_CODE_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,80}")
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


def load_contract() -> dict:
    try:
        contract = json.loads(REQUEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SafeFailure("LOCAL_REQUEST_FILE_INVALID") from exc

    try:
        request = contract["request"]
        media = request["input"]["media"]
        parameters = request["parameters"]
    except (KeyError, TypeError) as exc:
        raise SafeFailure("LOCAL_REQUEST_SCHEMA_INVALID") from exc

    expected = {
        "project": "TaiwanChicken",
        "shot_id": SHOT_ID,
        "first_frame_sha256": EXPECTED_FIRST_FRAME_SHA256,
    }
    if any(contract.get(key) != value for key, value in expected.items()):
        raise SafeFailure("LOCAL_REQUEST_IDENTITY_MISMATCH")
    if request.get("model") != MODEL:
        raise SafeFailure("LOCAL_MODEL_MISMATCH")
    if not isinstance(media, list) or media != [
        {"type": "first_frame", "url": "__RUNTIME_VERIFIED_FIRST_FRAME_DATA_URI__"}
    ]:
        raise SafeFailure("LOCAL_MEDIA_TEMPLATE_INVALID")
    required_parameters = {
        "resolution": "480P",
        "ratio": "9:16",
        "duration": 8,
        "audio": True,
        "prompt_extend": True,
        "watermark": False,
    }
    if parameters != required_parameters:
        raise SafeFailure("LOCAL_PARAMETERS_MISMATCH")
    prompt = request["input"].get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20_000:
        raise SafeFailure("LOCAL_PROMPT_INVALID")
    return contract


def load_binding() -> tuple[str, str]:
    host = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_HOST", "").strip()
    key = os.environ.get("ALIYUN_MODEL_STUDIO_HK_API_KEY", "")
    if not HOST_PATTERN.fullmatch(host):
        raise SafeFailure("BINDING_HOST_INVALID")
    if not key or any(character.isspace() for character in key):
        raise SafeFailure("BINDING_SECRET_MISSING_OR_MALFORMED")
    return host, key


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
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise SafeFailure("FIRST_FRAME_HOST_NOT_PUBLIC")
    return parts


def fetch_verified_first_frame(url: str) -> bytes:
    ensure_public_https(url)
    request = urllib.request.Request(
        url, headers={"User-Agent": "TaiwanChicken-WanHK-Executor/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            final_url = response.geturl()
            ensure_public_https(final_url)
            declared = response.headers.get("Content-Length")
            if declared and int(declared) > MAX_IMAGE_BYTES:
                raise SafeFailure("FIRST_FRAME_TOO_LARGE")
            data = response.read(MAX_IMAGE_BYTES + 1)
    except SafeFailure:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise SafeFailure("FIRST_FRAME_DOWNLOAD_FAILED") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise SafeFailure("FIRST_FRAME_TOO_LARGE")
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SafeFailure("FIRST_FRAME_NOT_PNG")
    if hashlib.sha256(data).hexdigest() != EXPECTED_FIRST_FRAME_SHA256:
        raise SafeFailure("FIRST_FRAME_SHA256_MISMATCH")
    return data


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


def base_receipt(mode: str, host: str) -> dict:
    return {
        "project": "TaiwanChicken",
        "shot_id": SHOT_ID,
        "model": MODEL,
        "region": "China (Hong Kong)",
        "deployment_scope": "Global",
        "mode": mode,
        "api_host": host,
        "parameters": {
            "resolution": "480P",
            "ratio": "9:16",
            "duration": 8,
        },
        "first_frame_sha256": EXPECTED_FIRST_FRAME_SHA256,
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
        {
            "status": "POST_IN_PROGRESS_OUTCOME_UNKNOWN",
            "updated_utc": utc_now(),
        }
    )
    write_json(receipt_path, receipt)
    url = (
        f"https://{host}/api/v1/services/aigc/video-generation/video-synthesis"
    )
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
        {
            "task_id": task_id,
            "status": "SUBMITTED",
            "updated_utc": utc_now(),
        }
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
            url, headers={"User-Agent": "TaiwanChicken-WanHK-Executor/1.0"}
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
        if state not in {"PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"}:
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
                allowed = {
                    "video_count",
                    "duration",
                    "input_video_duration",
                    "output_video_duration",
                    "fps",
                    "SR",
                }
                receipt["usage"] = {
                    key_name: value
                    for key_name, value in usage.items()
                    if key_name in allowed and isinstance(value, (int, float))
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
    try:
        probe = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,width,height,r_frame_rate:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
        metadata = json.loads(probe.stdout)
        stream = metadata["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(metadata["format"]["duration"])
        if width >= height or min(width, height) != 480:
            raise SafeFailure("VIDEO_RESOLUTION_NOT_480P_PORTRAIT")
        if not 7.5 <= duration <= 8.5:
            raise SafeFailure("VIDEO_DURATION_NOT_8_SECONDS")
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
        IndexError,
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
        "codec": stream.get("codec_name"),
        "frame_rate": stream.get("r_frame_rate"),
        "validated_utc": utc_now(),
    }
    write_json(path.parent / "shot04-video-validation.json", validation)
    receipt_path = path.parent / "shot04-receipt.json"
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
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / "shot04-receipt.json"

    if mode == "check-binding":
        receipt = base_receipt(mode, host)
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
        if os.environ.get("WAN_GENERATE_CONFIRMATION", "") != "GENERATE04":
            raise SafeFailure("GENERATE04_CONFIRMATION_REQUIRED")
        first_frame_url = os.environ.get("WAN_FIRST_FRAME_URL", "").strip()
        if not first_frame_url:
            raise SafeFailure("FIRST_FRAME_PUBLIC_HTTPS_URL_REQUIRED")
        first_frame = fetch_verified_first_frame(first_frame_url)
        payload = copy.deepcopy(contract["request"])
        payload["input"]["media"][0]["url"] = (
            "data:image/png;base64," + base64.b64encode(first_frame).decode("ascii")
        )
        receipt = base_receipt(mode, host)
        receipt["status"] = "FIRST_FRAME_SHA256_VERIFIED"
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
    receipt = base_receipt(mode, host)
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
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
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
