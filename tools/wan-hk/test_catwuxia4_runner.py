#!/usr/bin/env python3
"""Offline safety and media-gate tests for the fixed CatWomanWuxia runner."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock
import uuid

import catwuxia4_runner as runner


class CatWuxiaRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = runner.load_contract()
        self.shot = runner.selected_shot(self.contract, "01")

    def assert_code(self, expected: str, callable_, *args) -> None:
        with self.assertRaises(runner.SafeFailure) as caught:
            callable_(*args)
        self.assertEqual(caught.exception.code, expected)

    def receipt(self, *, task_id: str | None = None) -> dict:
        value = runner.base_receipt("generate", runner.HOST, self.contract, self.shot)
        value.update(
            {
                "status": "SUBMITTED",
                "task_id": task_id or str(uuid.uuid4()),
                "task_status": "SUCCEEDED",
                "usage": {"SR": 480},
                "media": {"sha256": "a" * 64},
            }
        )
        return value

    def test_fixed_contract_and_all_shots(self) -> None:
        self.assertEqual(tuple(self.contract["_shots_by_id"]), runner.EXPECTED_SHOT_IDS)
        self.assertEqual(runner.request_file_sha256(), runner.EXPECTED_REQUEST_SHA256)
        self.assertEqual(self.contract["parameters"], runner.EXPECTED_PARAMETERS)

    def test_local_transport_frames_match_fixed_sha_and_mime(self) -> None:
        generation = runner.ROOT.parent
        first = generation / (
            "CatWomanWuxia_Zachary_2026-10-15_"
            "Image_Shot01Transport_Review_v01.webp"
        )
        if not first.is_file():
            self.skipTest("Local review frames intentionally stay outside repository package")
        for shot_id in runner.EXPECTED_SHOT_IDS:
            shot = runner.selected_shot(self.contract, shot_id)
            path = generation / (
                "CatWomanWuxia_Zachary_2026-10-15_"
                f"Image_Shot{shot_id}Transport_Review_v01.webp"
            )
            data = path.read_bytes()
            self.assertEqual(runner.detected_image_mime(data), "image/webp")
            self.assertEqual(runner.sha256_bytes(data), shot["reference_image_sha256"])
            encoded = base64.b64encode(data).decode("ascii")
            inputs = {
                "mode": "generate",
                "shot": shot_id,
                "confirmation": runner.GENERATE_CONFIRMATION,
                "first_image_base64": encoded,
                "resume_task_id": "",
                "resume_receipt_base64": "",
            }
            self.assertLessEqual(
                len(json.dumps(inputs, ensure_ascii=False, separators=(",", ":"))),
                runner.MAX_DISPATCH_INPUT_CHARACTERS,
            )
            loaded, mime = runner.load_reference_image(inputs, shot)
            self.assertEqual(loaded, data)
            self.assertEqual(mime, "image/webp")

    def test_wrong_image_is_rejected(self) -> None:
        inputs = {"first_image_base64": base64.b64encode(b"not a webp").decode()}
        self.assert_code(
            "REFERENCE_IMAGE_FORMAT_INVALID",
            runner.load_reference_image,
            inputs,
            self.shot,
        )

    def test_generate_rejects_rerun_before_binding_or_post(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"GITHUB_RUN_ATTEMPT": "2"},
            clear=False,
        ), mock.patch.object(runner, "ensure_validation_tools"), mock.patch.object(
            runner, "validate_github_executor"
        ), mock.patch.object(
            runner, "load_binding", return_value=(runner.HOST, "unused-test-value")
        ), mock.patch.object(
            runner,
            "load_event_inputs",
            return_value={"mode": "generate", "shot": "01"},
        ), mock.patch.object(runner, "submit") as submit:
            self.assert_code(
                "GENERATE_REFUSED_ON_RERUN_ATTEMPT",
                runner.run_mode,
                "generate",
                "01",
                Path(directory),
            )
            submit.assert_not_called()

    def test_generate_rejects_wrong_confirmation_before_post(self) -> None:
        with tempfile.TemporaryDirectory() as directory, mock.patch.dict(
            os.environ,
            {"GITHUB_RUN_ATTEMPT": "1", "WAN_GENERATE_CONFIRMATION": "WRONG"},
            clear=False,
        ), mock.patch.object(runner, "ensure_validation_tools"), mock.patch.object(
            runner, "validate_github_executor"
        ), mock.patch.object(
            runner, "load_binding", return_value=(runner.HOST, "unused-test-value")
        ), mock.patch.object(
            runner,
            "load_event_inputs",
            return_value={"mode": "generate", "shot": "01"},
        ), mock.patch.object(runner, "submit") as submit:
            self.assert_code(
                "GENERATECATWUXIA24BATCH_CONFIRMATION_REQUIRED",
                runner.run_mode,
                "generate",
                "01",
                Path(directory),
            )
            submit.assert_not_called()

    def test_resume_requires_exact_receipt_binding(self) -> None:
        task_id = str(uuid.uuid4())
        evidence = self.receipt(task_id=task_id)
        runner.validate_resume_evidence(
            evidence, task_id, self.contract, self.shot
        )
        evidence["shot_id"] = "02"
        self.assert_code(
            "RESUME_EVIDENCE_BINDING_MISMATCH",
            runner.validate_resume_evidence,
            evidence,
            task_id,
            self.contract,
            self.shot,
        )

    def test_resume_path_reaches_get_only_poll(self) -> None:
        task_id = str(uuid.uuid4())
        evidence = self.receipt(task_id=task_id)
        encoded = base64.b64encode(
            (json.dumps(evidence, ensure_ascii=False) + "\n").encode()
        ).decode()
        inputs = {
            "mode": "resume",
            "shot": "01",
            "first_image_base64": "",
            "resume_task_id": task_id,
            "resume_receipt_base64": encoded,
        }
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            runner, "ensure_validation_tools"
        ), mock.patch.object(
            runner, "validate_github_executor"
        ), mock.patch.object(
            runner, "load_binding", return_value=(runner.HOST, "unused-test-value")
        ), mock.patch.object(
            runner, "load_event_inputs", return_value=inputs
        ), mock.patch.object(
            runner, "submit"
        ) as submit, mock.patch.object(
            runner, "poll"
        ) as poll:
            runner.run_mode("resume", "01", Path(directory))
            submit.assert_not_called()
            poll.assert_called_once()
            self.assertEqual(poll.call_args.args[2], task_id)

    def test_poll_uses_get_only(self) -> None:
        task_id = str(uuid.uuid4())
        receipt = self.receipt(task_id=task_id)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            runner,
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
                Path(directory) / runner.output_name("01"),
            )
            self.assertEqual(api.call_count, 1)
            self.assertIsNone(api.call_args.kwargs["payload"])

    def test_landscape_four_second_media_gate(self) -> None:
        receipt = self.receipt()
        rate = runner.validate_480p_landscape(
            854, 480, 4.0, "30/1", receipt, "a" * 64, "01"
        )
        self.assertEqual(rate, 30.0)
        self.assert_code(
            "VIDEO_RESOLUTION_NOT_480P_LANDSCAPE",
            runner.validate_480p_landscape,
            480,
            854,
            4.0,
            "30/1",
            receipt,
            "a" * 64,
            "01",
        )
        self.assert_code(
            "VIDEO_DURATION_NOT_APPROX_4_SECONDS",
            runner.validate_480p_landscape,
            854,
            480,
            5.0,
            "30/1",
            receipt,
            "a" * 64,
            "01",
        )
        self.assert_code(
            "VIDEO_FRAME_RATE_NOT_APPROX_30",
            runner.validate_480p_landscape,
            854,
            480,
            4.0,
            "24/1",
            receipt,
            "a" * 64,
            "01",
        )

    def test_unknown_post_is_not_retried(self) -> None:
        receipt = runner.base_receipt("generate", runner.HOST, self.contract, self.shot)
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            runner,
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

    def test_binding_and_workflow_are_fixed(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "ALIYUN_MODEL_STUDIO_HK_API_HOST": runner.HOST,
                "ALIYUN_MODEL_STUDIO_HK_API_KEY": "fixed-test-key",
            },
            clear=False,
        ):
            host, key = runner.load_binding()
            self.assertEqual(host, runner.HOST)
            self.assertEqual(key, "fixed-test-key")
        with mock.patch.dict(
            os.environ,
            {
                "ALIYUN_MODEL_STUDIO_HK_API_HOST": "wrong.example.invalid",
                "ALIYUN_MODEL_STUDIO_HK_API_KEY": "fixed-test-key",
            },
            clear=False,
        ):
            self.assert_code("BINDING_HOST_INVALID", runner.load_binding)
        workflow = (runner.ROOT / "wan-hk-catwuxia4.yml").read_text(encoding="utf-8")
        self.assertIn("group: wan-hk-shot04-paid-generation", workflow)
        self.assertIn("secrets.ALIYUN_MODEL_STUDIO_HK_API_KEY", workflow)
        self.assertIn("vars.ALIYUN_MODEL_STUDIO_HK_API_HOST", workflow)
        self.assertNotIn("first_image_base64: ${{", workflow)

    def test_github_executor_identity_is_fixed(self) -> None:
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
                "GITHUB_EXECUTOR_IDENTITY_MISMATCH",
                runner.validate_github_executor,
            )

    def test_check_request_does_not_load_binding(self) -> None:
        with mock.patch.object(
            runner, "load_binding", side_effect=AssertionError("binding must not load")
        ):
            with mock.patch.object(
                runner.sys,
                "argv",
                ["catwuxia4_runner.py", "--check-request", "--shot", "06"],
            ):
                self.assertEqual(runner.main(), 0)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg tools missing")
    def test_end_to_end_landscape_audio_decode_gate(self) -> None:
        with tempfile.TemporaryDirectory() as directory_text:
            directory = Path(directory_text)
            video = directory / runner.output_name("01")
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
            receipt = self.receipt()
            receipt["media"]["sha256"] = runner.sha256_bytes(video.read_bytes())
            runner.write_json(directory / runner.RECEIPT_NAME, receipt)
            runner.verify_video(video)
            validation = json.loads(
                (directory / runner.VALIDATION_NAME).read_text(encoding="utf-8")
            )
            self.assertEqual(validation["status"], "FFPROBE_AND_FFMPEG_VALIDATED")
            self.assertEqual(validation["shot_id"], "01")
            self.assertEqual(validation["width"], 854)
            self.assertEqual(validation["height"], 480)
            self.assertEqual(validation["frame_rate"], 30.0)
            self.assertGreaterEqual(validation["audio_stream_count"], 1)
            self.assertTrue(validation["full_ffmpeg_decode_passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
