#!/usr/bin/env python3
"""Offline bounds tests for the fixed contact-proof v03 executor."""

from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import uuid

import contactproof4_v03_runner as runner


def fixed_request(image_sha256: str = "a" * 64) -> dict:
    return {
        "schema_version": 1,
        "project": runner.EXPECTED_PROJECT,
        "client": runner.EXPECTED_CLIENT,
        "batch_id": runner.EXPECTED_BATCH_ID,
        "model": "wan3.0-video",
        "parameters": dict(runner.EXPECTED_PARAMETERS),
        "media_placeholder": "__RUNTIME_VERIFIED_REFERENCE_IMAGE_DATA_URI__",
        "shots": [
            {
                "shot_id": "01",
                "creative_id": runner.EXPECTED_CREATIVE_ID,
                "prompt": "Fixed offline contact-proof prompt fixture.",
                "reference_image_sha256": image_sha256,
                "reference_image_mime": "image/webp",
            }
        ],
    }


@contextmanager
def finalized_fixture(image_sha256: str = "a" * 64):
    with tempfile.TemporaryDirectory() as directory_text:
        path = Path(directory_text) / "request-contactproof4-v03.json"
        raw = (json.dumps(fixed_request(image_sha256), ensure_ascii=False, indent=2) + "\n").encode()
        path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        with mock.patch.object(runner, "REQUEST_FILE", path), mock.patch.object(
            runner, "EXPECTED_REQUEST_SHA256", digest
        ):
            yield runner.load_contract()


class ContactProofV03RunnerTests(unittest.TestCase):
    def assert_code(self, expected: str, callable_, *args) -> None:
        with self.assertRaises(runner.SafeFailure) as caught:
            callable_(*args)
        self.assertEqual(caught.exception.code, expected)

    def receipt(self, contract: dict, *, task_id: str | None = None) -> dict:
        shot = runner.selected_shot(contract)
        value = runner.base_receipt("generate", runner.HOST, contract, shot)
        value.update(
            {
                "status": "SUBMITTED",
                "task_id": task_id or str(uuid.uuid4()),
                "task_status": "SUCCEEDED",
                "usage": {"SR": 480},
                "media": {"sha256": "b" * 64},
            }
        )
        return value

    def test_unfinalized_package_fails_closed(self) -> None:
        with mock.patch.object(
            runner, "EXPECTED_REQUEST_SHA256", "__FINAL_REQUEST_SHA256__"
        ):
            self.assert_code("PACKAGE_NOT_FINALIZED", runner.load_contract)

    def test_unfinalized_external_mode_never_loads_binding(self) -> None:
        with mock.patch.object(
            runner, "EXPECTED_REQUEST_SHA256", "__FINAL_REQUEST_SHA256__"
        ), mock.patch.object(
            runner, "load_binding", side_effect=AssertionError("binding must not load")
        ):
            self.assert_code(
                "PACKAGE_NOT_FINALIZED",
                runner.run_mode,
                "generate",
                Path("unused-output"),
            )

    def test_reviewed_base_runner_is_exact_hash(self) -> None:
        self.assertEqual(runner._sha256(Path(runner.core.__file__)), runner.BASE_RUNNER_SHA256)

    def test_finalized_contract_is_exact_single_shot(self) -> None:
        with finalized_fixture() as contract:
            self.assertEqual(tuple(contract["_shots_by_id"]), ("01",))
            self.assertEqual(contract["parameters"], runner.EXPECTED_PARAMETERS)
            self.assertEqual(contract["batch_id"], runner.EXPECTED_BATCH_ID)
            self.assertEqual(
                runner.selected_shot(contract)["creative_id"],
                runner.EXPECTED_CREATIVE_ID,
            )
            self.assertEqual(
                runner.selected_shot(contract)["reference_image_mime"], "image/webp"
            )

    def test_request_digest_change_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            path = Path(directory_text) / "request.json"
            path.write_text(json.dumps(fixed_request()) + "\n", encoding="utf-8")
            with mock.patch.object(runner, "REQUEST_FILE", path), mock.patch.object(
                runner, "EXPECTED_REQUEST_SHA256", "f" * 64
            ):
                self.assert_code("LOCAL_REQUEST_SHA256_MISMATCH", runner.load_contract)

    def test_reference_image_digest_and_mime_are_bound(self) -> None:
        webp = b"RIFF" + (4).to_bytes(4, "little") + b"WEBP" + b"test"
        digest = hashlib.sha256(webp).hexdigest()
        with finalized_fixture(digest) as contract:
            shot = runner.selected_shot(contract)
            inputs = {"first_image_base64": base64.b64encode(webp).decode("ascii")}
            loaded, mime = runner.load_reference_image(inputs, shot)
            self.assertEqual(loaded, webp)
            self.assertEqual(mime, "image/webp")
            inputs["first_image_base64"] = base64.b64encode(webp + b"x").decode("ascii")
            self.assert_code(
                "REFERENCE_IMAGE_SHA256_MISMATCH",
                runner.load_reference_image,
                inputs,
                shot,
            )

    def test_local_final_transport_fits_dispatch_limit(self) -> None:
        image = runner.ROOT.parent / (
            "CatWomanWuxia_Zachary_2026-10-15_"
            "Image_ContactProofTransport_Review_v03.webp"
        )
        if not image.is_file():
            self.skipTest("Transport WebP intentionally stays outside repository package")
        contract = runner.load_contract()
        shot = runner.selected_shot(contract)
        raw = image.read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), shot["reference_image_sha256"])
        inputs = {
            "mode": "generate",
            "confirmation": runner.GENERATE_CONFIRMATION,
            "first_image_base64": base64.b64encode(raw).decode("ascii"),
            "resume_task_id": "",
            "resume_receipt_base64": "",
        }
        characters = len(
            json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))
        )
        self.assertEqual(characters, 62792)
        self.assertLessEqual(characters, runner.MAX_DISPATCH_INPUT_CHARACTERS)
        loaded, mime = runner.load_reference_image(inputs, shot)
        self.assertEqual(loaded, raw)
        self.assertEqual(mime, "image/webp")

    def test_generate_rerun_refused_before_submit(self) -> None:
        with finalized_fixture(), tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ, {"GITHUB_RUN_ATTEMPT": "2"}, clear=False
        ), mock.patch.object(runner.core, "ensure_validation_tools"), mock.patch.object(
            runner, "validate_github_executor"
        ), mock.patch.object(
            runner, "load_binding", return_value=(runner.HOST, "unused-test-value")
        ), mock.patch.object(
            runner, "load_event_inputs", return_value={"mode": "generate"}
        ), mock.patch.object(runner, "submit") as submit:
            self.assert_code(
                "GENERATE_REFUSED_ON_RERUN_ATTEMPT",
                runner.run_mode,
                "generate",
                Path(directory),
            )
            submit.assert_not_called()

    def test_generate_wrong_confirmation_refused_before_submit(self) -> None:
        with finalized_fixture(), tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"GITHUB_RUN_ATTEMPT": "1", "WAN_GENERATE_CONFIRMATION": "WRONG"},
            clear=False,
        ), mock.patch.object(runner.core, "ensure_validation_tools"), mock.patch.object(
            runner, "validate_github_executor"
        ), mock.patch.object(
            runner, "load_binding", return_value=(runner.HOST, "unused-test-value")
        ), mock.patch.object(
            runner, "load_event_inputs", return_value={"mode": "generate"}
        ), mock.patch.object(runner, "submit") as submit:
            self.assert_code(
                "GENERATECONTACTPROOF4V03ONCE_CONFIRMATION_REQUIRED",
                runner.run_mode,
                "generate",
                Path(directory),
            )
            submit.assert_not_called()

    def test_unknown_post_calls_provider_once_and_forbids_retry(self) -> None:
        with finalized_fixture() as contract, tempfile.TemporaryDirectory() as directory:
            receipt = runner.base_receipt(
                "generate", runner.HOST, contract, runner.selected_shot(contract)
            )
            with mock.patch.object(
                runner.core,
                "api_json",
                side_effect=runner.ApiFailure(None, "NETWORK_OR_TIMEOUT", False),
            ) as api:
                self.assert_code(
                    "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY",
                    runner.submit,
                    runner.HOST,
                    "unused-test-value",
                    {"fixed": True},
                    Path(directory) / runner.RECEIPT_NAME,
                    receipt,
                )
                self.assertEqual(api.call_count, 1)
                written = json.loads(
                    (Path(directory) / runner.RECEIPT_NAME).read_text(encoding="utf-8")
                )
                self.assertEqual(written["status"], "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY")

    def test_resume_is_bound_and_never_calls_submit(self) -> None:
        with finalized_fixture() as contract:
            task_id = str(uuid.uuid4())
            prior = self.receipt(contract, task_id=task_id)
            encoded = base64.b64encode(
                (json.dumps(prior, ensure_ascii=False) + "\n").encode()
            ).decode()
            inputs = {
                "mode": "resume",
                "first_image_base64": "",
                "resume_task_id": task_id,
                "resume_receipt_base64": encoded,
            }
            with tempfile.TemporaryDirectory() as directory, mock.patch.object(
                runner.core, "ensure_validation_tools"
            ), mock.patch.object(runner, "validate_github_executor"), mock.patch.object(
                runner, "load_binding", return_value=(runner.HOST, "unused-test-value")
            ), mock.patch.object(
                runner, "load_event_inputs", return_value=inputs
            ), mock.patch.object(runner, "submit") as submit, mock.patch.object(
                runner, "poll"
            ) as poll:
                runner.run_mode("resume", Path(directory))
                submit.assert_not_called()
                poll.assert_called_once()
                self.assertEqual(poll.call_args.args[2], task_id)

    def test_poll_query_uses_get_only(self) -> None:
        with finalized_fixture() as contract, tempfile.TemporaryDirectory() as directory:
            task_id = str(uuid.uuid4())
            receipt = self.receipt(contract, task_id=task_id)
            with mock.patch.object(
                runner.core,
                "api_json",
                return_value={
                    "output": {
                        "task_status": "FAILED",
                        "code": "FixedTestFailure",
                        "message": "fixed test",
                    }
                },
            ) as api:
                self.assert_code(
                    "TASK_FAILED",
                    runner.poll,
                    runner.HOST,
                    "unused-test-value",
                    task_id,
                    Path(directory) / runner.RECEIPT_NAME,
                    receipt,
                    Path(directory) / runner.OUTPUT_NAME,
                )
                self.assertEqual(api.call_count, 1)
                self.assertIsNone(api.call_args.kwargs["payload"])

    def test_binding_workflow_and_mutex_are_fixed(self) -> None:
        workflow = (runner.ROOT / "wan-hk-contactproof4-v03.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("group: wan-hk-shot04-paid-generation", workflow)
        self.assertIn("secrets.ALIYUN_MODEL_STUDIO_HK_API_KEY", workflow)
        self.assertIn("vars.ALIYUN_MODEL_STUDIO_HK_API_HOST", workflow)
        self.assertIn("contactproof4_v03_runner.py", workflow)
        self.assertNotIn("first_image_base64: ${{", workflow)
        self.assertNotIn("- shot", workflow)

    def test_github_executor_identity_is_exact(self) -> None:
        expected = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": runner.EXPECTED_REPOSITORY,
            "GITHUB_WORKFLOW_REF": (
                runner.EXPECTED_REPOSITORY
                + "/"
                + runner.EXPECTED_WORKFLOW_PATH
                + "@refs/heads/main"
            ),
            "GITHUB_RUN_ID": "123456789",
        }
        with mock.patch.dict(os.environ, expected, clear=True):
            runner.validate_github_executor()
        expected["GITHUB_REPOSITORY"] = "someone/else"
        with mock.patch.dict(os.environ, expected, clear=True):
            self.assert_code(
                "GITHUB_EXECUTOR_IDENTITY_MISMATCH", runner.validate_github_executor
            )

    def test_media_gate_requires_landscape_four_seconds_and_audio_contract(self) -> None:
        with finalized_fixture() as contract:
            receipt = self.receipt(contract)
            rate = runner.validate_480p_landscape(
                854, 480, 4.0, "30/1", receipt, "b" * 64
            )
            self.assertEqual(rate, 30.0)
            self.assert_code(
                "VIDEO_DURATION_NOT_APPROX_4_SECONDS",
                runner.validate_480p_landscape,
                854,
                480,
                5.0,
                "30/1",
                receipt,
                "b" * 64,
            )

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg tools missing"
    )
    def test_end_to_end_decode_gate(self) -> None:
        with finalized_fixture() as contract, tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            video = directory / runner.OUTPUT_NAME
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "color=c=black:s=854x480:r=30:d=4",
                    "-f",
                    "lavfi",
                    "-i",
                    "sine=frequency=440:sample_rate=48000:duration=4",
                    "-c:v",
                    "mpeg4",
                    "-q:v",
                    "12",
                    "-c:a",
                    "aac",
                    "-shortest",
                    str(video),
                ],
                check=True,
                capture_output=True,
                timeout=60,
            )
            receipt = self.receipt(contract)
            receipt["media"]["sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
            runner.core.write_json(directory / runner.RECEIPT_NAME, receipt)
            runner.verify_video(video)
            validation = json.loads(
                (directory / runner.VALIDATION_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(validation["status"], "FFPROBE_AND_FFMPEG_VALIDATED")
            self.assertEqual(validation["width"], 854)
            self.assertEqual(validation["height"], 480)
            self.assertEqual(validation["frame_rate"], 30.0)
            self.assertGreaterEqual(validation["audio_stream_count"], 1)
            self.assertTrue(validation["full_ffmpeg_decode_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
