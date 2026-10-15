#!/usr/bin/env python3
"""Fixed one-shot Wan HK executor for ZariaFashion fashion trial 15 v01.

This wrapper reuses the already reviewed ZariaFashion Wan HK transport
implementation only when its SHA-256 is exact.  It fixes one 15-second,
480P, 9:16, audio-enabled shot.  Generate can issue at most one POST in
workflow attempt 1.  Resume requires bound evidence and uses provider GET
requests only.

The local frame and request remain review candidates until the user accepts
the woman's appearance and separately approves the one paid submission.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
REQUEST_FILE = ROOT / "request-fashiontrial15-v01.json"
BASE_RUNNER_SHA256 = "a095a8e6fa308a0d282118fc9b83997703ecb35263a0a790b2a66b6514b92ea0"
EXPECTED_REQUEST_SHA256 = "c598ca753c9a17a92885afdb08fddc335b0e0c8a87113d952c2068c0b2c4742e"
EXPECTED_PROJECT = "ZariaFashion"
EXPECTED_CLIENT = "Zachary Chan"
EXPECTED_BATCH_ID = "zaria-fashion-trial15-v01"
EXPECTED_CREATIVE_ID = "zaria-fashion-trial15-v01-shot01"
EXPECTED_REPOSITORY = "opc-zachary/ai-training-knowledge"
EXPECTED_WORKFLOW_PATH = ".github/workflows/wan-hk-fashiontrial15-v01.yml"
EXPECTED_SHOT_IDS = ("01",)
EXPECTED_PARAMETERS = {
    "resolution": "480P",
    "ratio": "9:16",
    "duration": 15,
    "audio": True,
    "prompt_extend": False,
}
EXPECTED_REFERENCE_MIME = "image/webp"
GENERATE_CONFIRMATION = "GENERATEFASHIONTRIAL15V01ONCE"
RECEIPT_NAME = "fashiontrial15-v01-receipt.json"
VALIDATION_NAME = "fashiontrial15-v01-video-validation.json"
OUTPUT_NAME = (
    "ZariaFashion_Zachary_2026-10-15_Video_"
    "FashionTrial15Raw480p_Review_v01.mp4"
)
OUTPUT_DIR_NAME = "output-fashiontrial15-v01"
FINAL_MARKER_PREFIX = "__FINAL_"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
MIN_DURATION_SECONDS = 14.5
MAX_DURATION_SECONDS = 15.5


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_reviewed_base():
    candidates = (
        ROOT / "catwuxia4_runner.py",
    )
    for path in candidates:
        if path.is_file() and _sha256(path) == BASE_RUNNER_SHA256:
            spec = importlib.util.spec_from_file_location(
                "fashiontrial15_v01_reviewed_base", path
            )
            if spec is None or spec.loader is None:
                break
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    raise RuntimeError("REVIEWED_BASE_RUNNER_MISSING_OR_SHA256_MISMATCH")


core = _load_reviewed_base()
SafeFailure = core.SafeFailure
ApiFailure = core.ApiFailure
HOST = core.HOST
MAX_DISPATCH_INPUT_CHARACTERS = core.MAX_DISPATCH_INPUT_CHARACTERS


def _sync_core() -> None:
    """Bind the reviewed transport to this exact single-shot contract."""
    core.ROOT = ROOT
    core.REQUEST_FILE = REQUEST_FILE
    core.EXPECTED_REQUEST_SHA256 = EXPECTED_REQUEST_SHA256
    core.EXPECTED_PROJECT = EXPECTED_PROJECT
    core.EXPECTED_CLIENT = EXPECTED_CLIENT
    core.EXPECTED_REPOSITORY = EXPECTED_REPOSITORY
    core.EXPECTED_WORKFLOW_PATH = EXPECTED_WORKFLOW_PATH
    core.EXPECTED_SHOT_IDS = EXPECTED_SHOT_IDS
    core.EXPECTED_PARAMETERS = EXPECTED_PARAMETERS
    core.GENERATE_CONFIRMATION = GENERATE_CONFIRMATION
    core.RECEIPT_NAME = RECEIPT_NAME
    core.VALIDATION_NAME = VALIDATION_NAME


def _contains_final_marker(value: object) -> bool:
    if isinstance(value, str):
        return value.startswith(FINAL_MARKER_PREFIX)
    if isinstance(value, list):
        return any(_contains_final_marker(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_final_marker(item) for item in value.values())
    return False


def load_contract() -> dict:
    if not SHA256_PATTERN.fullmatch(EXPECTED_REQUEST_SHA256):
        raise SafeFailure("PACKAGE_NOT_FINALIZED")
    try:
        raw = json.loads(REQUEST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SafeFailure("LOCAL_REQUEST_FILE_INVALID") from exc
    if _contains_final_marker(raw):
        raise SafeFailure("PACKAGE_NOT_FINALIZED")
    _sync_core()
    contract = core.load_contract()
    shot = core.selected_shot(contract, "01")
    if contract.get("batch_id") != EXPECTED_BATCH_ID:
        raise SafeFailure("LOCAL_BATCH_ID_NOT_FIXED")
    if shot.get("creative_id") != EXPECTED_CREATIVE_ID:
        raise SafeFailure("LOCAL_CREATIVE_ID_NOT_FIXED")
    if shot.get("reference_image_mime") != EXPECTED_REFERENCE_MIME:
        raise SafeFailure("LOCAL_REFERENCE_MIME_NOT_FIXED_WEBP")
    return contract


def selected_shot(contract: dict, shot_id: str = "01") -> dict:
    _sync_core()
    return core.selected_shot(contract, shot_id)


def output_name(shot_id: str = "01") -> str:
    if shot_id != "01":
        raise SafeFailure("SHOT_CHOICE_NOT_IN_FIXED_REQUEST")
    return OUTPUT_NAME


def base_receipt(mode: str, host: str, contract: dict, shot: dict) -> dict:
    _sync_core()
    receipt = core.base_receipt(mode, host, contract, shot)
    receipt.update(
        {
            "executor_contract": "fashiontrial15-v01-single-shot",
            "paid_submission_limit": 1,
            "automatic_paid_retries": 0,
            "rerun_paid_generation_allowed": False,
            "resume_provider_method": "GET_ONLY",
        }
    )
    return receipt


def load_binding() -> tuple[str, str]:
    _sync_core()
    return core.load_binding()


def validate_github_executor() -> None:
    _sync_core()
    core.validate_github_executor()


def load_event_inputs() -> dict:
    _sync_core()
    return core.load_event_inputs()


def load_reference_image(inputs: dict, shot: dict) -> tuple[bytes, str]:
    _sync_core()
    return core.load_reference_image(inputs, shot)


def validate_resume_evidence(
    receipt: dict, task_id: str, contract: dict, shot: dict
) -> None:
    _sync_core()
    core.validate_resume_evidence(receipt, task_id, contract, shot)


def submit(
    host: str,
    key: str,
    payload: dict,
    receipt_path: Path,
    receipt: dict,
) -> str:
    _sync_core()
    return core.submit(host, key, payload, receipt_path, receipt)


def poll(
    host: str,
    key: str,
    task_id: str,
    receipt_path: Path,
    receipt: dict,
    output_path: Path,
) -> None:
    _sync_core()
    core.poll(host, key, task_id, receipt_path, receipt, output_path)


def _usage_number(usage: dict, name: str, error_code: str) -> float:
    value = usage.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SafeFailure(error_code)
    return float(value)


def validate_provider_usage(receipt: dict) -> dict:
    """Require provider evidence for the exact paid 480P/15s/audio run."""
    usage = receipt.get("usage")
    if not isinstance(usage, dict):
        raise SafeFailure("VIDEO_RECEIPT_USAGE_MISSING")
    if _usage_number(usage, "SR", "VIDEO_RECEIPT_SR_NOT_480") != 480:
        raise SafeFailure("VIDEO_RECEIPT_SR_NOT_480")
    if _usage_number(
        usage, "video_count", "VIDEO_RECEIPT_VIDEO_COUNT_NOT_1"
    ) != 1:
        raise SafeFailure("VIDEO_RECEIPT_VIDEO_COUNT_NOT_1")
    if _usage_number(usage, "fps", "VIDEO_RECEIPT_FPS_NOT_30") != 30:
        raise SafeFailure("VIDEO_RECEIPT_FPS_NOT_30")
    if _usage_number(
        usage, "input_video_duration", "VIDEO_RECEIPT_INPUT_DURATION_NOT_0"
    ) != 0:
        raise SafeFailure("VIDEO_RECEIPT_INPUT_DURATION_NOT_0")
    output_duration = _usage_number(
        usage,
        "output_video_duration",
        "VIDEO_RECEIPT_OUTPUT_DURATION_NOT_APPROX_15_SECONDS",
    )
    if not MIN_DURATION_SECONDS <= output_duration <= MAX_DURATION_SECONDS:
        raise SafeFailure("VIDEO_RECEIPT_OUTPUT_DURATION_NOT_APPROX_15_SECONDS")
    return {
        "SR": usage["SR"],
        "video_count": usage["video_count"],
        "fps": usage["fps"],
        "input_video_duration": usage["input_video_duration"],
        "output_video_duration": usage["output_video_duration"],
    }


def validate_480p_portrait(
    width: int,
    height: int,
    duration: float,
    frame_rate: object,
    receipt: dict,
    media_sha256: str,
    expected_shot_id: str = "01",
) -> float:
    if receipt.get("task_status") != "SUCCEEDED":
        raise SafeFailure("VIDEO_RECEIPT_TASK_NOT_SUCCEEDED")
    validate_provider_usage(receipt)
    if receipt.get("parameters") != EXPECTED_PARAMETERS:
        raise SafeFailure("VIDEO_RECEIPT_PARAMETERS_MISMATCH")
    source = receipt.get("source")
    if (
        not isinstance(source, dict)
        or source.get("request_sha256") != EXPECTED_REQUEST_SHA256
    ):
        raise SafeFailure("VIDEO_RECEIPT_REQUEST_SHA256_MISMATCH")
    if receipt.get("shot_id") != expected_shot_id:
        raise SafeFailure("VIDEO_RECEIPT_SHOT_ID_MISMATCH")
    media = receipt.get("media")
    if not isinstance(media, dict) or media.get("sha256") != media_sha256:
        raise SafeFailure("VIDEO_RECEIPT_MEDIA_SHA256_MISMATCH")
    if (
        not isinstance(width, int)
        or not isinstance(height, int)
        or width >= height
        or width < 450
        or width > 520
        or height < 800
        or height > 960
        or abs((width / height) - (9 / 16)) > 0.02
    ):
        raise SafeFailure("VIDEO_RESOLUTION_NOT_480P_PORTRAIT")
    if not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
        raise SafeFailure("VIDEO_DURATION_NOT_APPROX_15_SECONDS")
    return core.parse_frame_rate(frame_rate)


def verify_video(path: Path) -> None:
    if not path.is_file() or path.name != OUTPUT_NAME:
        raise SafeFailure("VIDEO_VALIDATION_TARGET_INVALID")
    _sync_core()
    core.ensure_validation_tools()
    receipt = core.load_adjacent_receipt(path)
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
        video_streams = [item for item in streams if item.get("codec_type") == "video"]
        audio_streams = [item for item in streams if item.get("codec_type") == "audio"]
        if len(video_streams) != 1:
            raise SafeFailure("VIDEO_STREAM_COUNT_INVALID")
        if not audio_streams:
            raise SafeFailure("AUDIO_STREAM_MISSING")
        stream = video_streams[0]
        width = int(stream["width"])
        height = int(stream["height"])
        duration = float(metadata["format"]["duration"])
        media_sha256 = core.sha256_bytes(path.read_bytes())
        frame_rate = validate_480p_portrait(
            width,
            height,
            duration,
            stream.get("r_frame_rate"),
            receipt,
            media_sha256,
            "01",
        )
        provider_usage = validate_provider_usage(receipt)
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
        "shot_id": "01",
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
        "provider_usage": provider_usage,
        "full_ffmpeg_decode_passed": True,
        "validated_utc": core.utc_now(),
    }
    core.write_json(path.parent / VALIDATION_NAME, validation)
    receipt["status"] = "DOWNLOADED_AND_FFMPEG_VALIDATED"
    receipt["validation_sha256"] = core.canonical_sha256(validation)
    receipt["updated_utc"] = core.utc_now()
    core.write_json(path.parent / RECEIPT_NAME, receipt)
    print("FFPROBE_AND_FFMPEG_VALIDATED shot=01")


def run_mode(mode: str, output_dir: Path) -> None:
    contract = load_contract()
    shot = selected_shot(contract)
    validate_github_executor()
    if mode in {"generate", "resume"}:
        core.ensure_validation_tools()
    host, key = load_binding()
    output_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = output_dir / RECEIPT_NAME
    if receipt_path.exists():
        raise SafeFailure("OUTPUT_RECEIPT_ALREADY_EXISTS")

    if mode == "check-binding":
        receipt = base_receipt(mode, host, contract, shot)
        receipt["status"] = "BINDING_PRESENT_NOT_API_VERIFIED"
        core.write_json(receipt_path, receipt)
        print("BINDING_PRESENT_NOT_API_VERIFIED; no API request made")
        return

    inputs = load_event_inputs()
    if inputs.get("mode") != mode:
        raise SafeFailure("WORKFLOW_EVENT_MODE_MISMATCH")

    if mode == "generate":
        if core.parse_attempt() != 1:
            raise SafeFailure("GENERATE_REFUSED_ON_RERUN_ATTEMPT")
        if os.environ.get("WAN_GENERATE_CONFIRMATION", "") != GENERATE_CONFIRMATION:
            raise SafeFailure("GENERATEFASHIONTRIAL15V01ONCE_CONFIRMATION_REQUIRED")
        if inputs.get("resume_task_id") or inputs.get("resume_receipt_base64"):
            raise SafeFailure("GENERATE_RESUME_INPUTS_FORBIDDEN")
        reference_image, reference_mime = load_reference_image(inputs, shot)
        image_data_uri = (
            "data:"
            + reference_mime
            + ";base64,"
            + base64.b64encode(reference_image).decode("ascii")
        )
        payload = core.build_payload(contract, shot, image_data_uri)
        receipt = base_receipt(mode, host, contract, shot)
        receipt.update(
            {
                "status": "REFERENCE_IMAGE_SHA256_VERIFIED",
                "verified_reference_image_sha256": core.sha256_bytes(reference_image),
                "provider_payload_sha256": core.canonical_sha256(payload),
            }
        )
        core.write_json(receipt_path, receipt)
        task_id = submit(host, key, payload, receipt_path, receipt)
        poll(host, key, task_id, receipt_path, receipt, output_dir / OUTPUT_NAME)
        return

    if inputs.get("first_image_base64"):
        raise SafeFailure("RESUME_FIRST_IMAGE_FORBIDDEN")
    task_id = core.valid_uuid(inputs.get("resume_task_id"))
    if not task_id:
        raise SafeFailure("RESUME_TASK_ID_UUID_REQUIRED")
    prior_receipt, receipt_digest = core.decode_resume_receipt(inputs)
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
    core.write_json(receipt_path, receipt)
    poll(host, key, task_id, receipt_path, receipt, output_dir / OUTPUT_NAME)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=["check-binding", "generate", "resume"], default="check-binding"
    )
    parser.add_argument("--output-dir", type=Path, default=Path(OUTPUT_DIR_NAME))
    parser.add_argument("--check-request", action="store_true")
    parser.add_argument("--verify-output", type=Path)
    args = parser.parse_args()
    try:
        if args.check_request:
            contract = load_contract()
            shot = selected_shot(contract)
            print(
                "OFFLINE_CONTRACT_VALID request_sha256="
                + EXPECTED_REQUEST_SHA256
                + " shot=01 shot_contract_sha256="
                + core.shot_contract_digest(contract, shot)
            )
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
