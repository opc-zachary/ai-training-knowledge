#!/usr/bin/env python3
"""Offline safety tests for the StormMV Zachary v05 one-shot executor."""

from __future__ import annotations

import base64
import copy
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parent
RUNNER_PATH = ROOT / "storm_mv_zachary_v05_runner.py"
SPEC = importlib.util.spec_from_file_location("storm_v05_runner", RUNNER_PATH)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class StormExecutorSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = runner.load_manifest(allow_template=True)

    def assert_safe_failure(self, expected_code: str, callback) -> None:
        with self.assertRaises(runner.SafeFailure) as caught:
            callback()
        self.assertEqual(caught.exception.code, expected_code)

    def registered_manifest(self) -> dict:
        manifest = copy.deepcopy(self.manifest)
        url = "https://media.example.invalid/private-opaque-object/storm-v05.mp4"
        manifest["status"] = "APPROVED_ONE_SHOT_READY"
        manifest["reference_transport"]["registration_state"] = "REGISTERED_EXACT_URL_PINNED"
        manifest["reference_transport"]["expected_url"] = url
        manifest["request"]["reference_video_url"] = url
        return manifest

    def require_local_sources(self) -> None:
        paths = [
            Path(self.manifest["reference_transport"]["local_review_source_path"]),
            *[
                Path(self.manifest["images"][image_id]["source_path"])
                for image_id in runner.IMAGE_IDS
            ],
        ]
        if not all(path.is_file() for path in paths):
            self.skipTest("Project-local source media are intentionally absent from the repository")

    def test_registered_manifest_is_pinned_and_pending_state_still_fails_closed(self) -> None:
        self.assertEqual(
            runner.sha256_bytes(runner.MANIFEST_FILE.read_bytes()),
            runner.EXPECTED_MANIFEST_SHA256,
        )
        runner.load_manifest(allow_template=False)
        pending = copy.deepcopy(self.manifest)
        pending["reference_transport"]["registration_state"] = "PENDING_ROOT_EXACT_URL_AND_REPIN"
        self.assert_safe_failure(
            "REFERENCE_URL_NOT_REGISTERED_REPIN_REQUIRED",
            lambda: runner.validate_manifest_shape(pending, allow_template=False),
        )

    def test_budget_counts_input_plus_output_under_approved_cap(self) -> None:
        calculated_hkd, cap = runner.calculated_cost(self.manifest)
        self.assertEqual(calculated_hkd, Decimal("2.5743744"))
        self.assertEqual(cap, Decimal("15.00"))
        self.assertEqual(self.manifest["approval"]["maximum_total_submissions"], 1)
        self.assertEqual(self.manifest["approval"]["automatic_paid_retries"], 0)

    def test_request_is_exact_silent_landscape_reference_edit(self) -> None:
        request = runner.load_request(self.manifest, allow_template=True)
        self.assertEqual(request["parameters"], runner.expected_parameters())
        self.assertEqual(
            [item["type"] for item in request["input"]["media"]],
            ["reference_video", "reference_image", "reference_image"],
        )
        self.assertNotIn("first_frame", json.dumps(request))
        self.assertNotIn("last_frame", json.dumps(request))
        self.assertEqual(
            runner.sha256_bytes(
                (ROOT / self.manifest["request"]["path"]).read_bytes()
            ),
            self.manifest["request"]["sha256"],
        )

    def test_local_sources_transport_recipes_and_motion_reference_validate(self) -> None:
        self.require_local_sources()
        runner.validate_local_assets(self.manifest)

    def test_reference_video_substitution_is_rejected(self) -> None:
        self.require_local_sources()
        source = Path(self.manifest["reference_transport"]["local_review_source_path"])
        altered = bytearray(source.read_bytes())
        altered[-1] ^= 1
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "reference.mp4"
            path.write_bytes(altered)
            self.assert_safe_failure(
                "REFERENCE_VIDEO_SHA256_MISMATCH",
                lambda: runner.validate_reference_video_file(path, self.manifest),
            )

    def test_private_images_are_read_only_from_event_file_without_output(self) -> None:
        source_values = [
            base64.b64encode(b"private-scene-value").decode("ascii"),
            base64.b64encode(b"private-zachary-value").decode("ascii"),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            event_path = Path(temporary) / "event.json"
            event_path.write_text(
                json.dumps(
                    {
                        "inputs": {
                            "scene_image_base64": source_values[0],
                            "zachary_image_base64": source_values[1],
                        }
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {
                    "GITHUB_ACTIONS": "true",
                    "GITHUB_EVENT_PATH": str(event_path),
                    "WAN_SCENE_IMAGE_BASE64": "environment-decoy-one",
                    "WAN_ZACHARY_IMAGE_BASE64": "environment-decoy-two",
                },
                clear=False,
            ), mock.patch("sys.stdout") as stdout, mock.patch("sys.stderr") as stderr:
                self.assertEqual(runner.runtime_image_inputs(), tuple(source_values))
            stdout.write.assert_not_called()
            stderr.write.assert_not_called()

    def test_image_substitution_and_whitespace_are_rejected(self) -> None:
        self.require_local_sources()
        scene_meta = self.manifest["images"]["scene"]
        zachary_meta = self.manifest["images"]["zachary"]
        scene = runner.reproduce_transport(
            Path(scene_meta["source_path"]), scene_meta["transport_dimensions"]
        )
        zachary = runner.reproduce_transport(
            Path(zachary_meta["source_path"]), zachary_meta["transport_dimensions"]
        )
        self.assert_safe_failure(
            "IMAGE_1_BASE64_LENGTH_MISMATCH",
            lambda: runner.decode_image_input(
                base64.b64encode(zachary).decode("ascii"), scene_meta, "IMAGE_1"
            ),
        )
        scene_b64 = base64.b64encode(scene).decode("ascii")
        self.assert_safe_failure(
            "IMAGE_1_BASE64_INPUT_INVALID",
            lambda: runner.decode_image_input(scene_b64 + "\n", scene_meta, "IMAGE_1"),
        )

    def test_workflow_never_maps_base64_into_environment_or_command(self) -> None:
        workflow = (ROOT / runner.WORKFLOW_FILE).read_text(encoding="utf-8")
        self.assertNotIn("WAN_SCENE_IMAGE_BASE64", workflow)
        self.assertNotIn("WAN_ZACHARY_IMAGE_BASE64", workflow)
        self.assertNotIn("${{ inputs.scene_image_base64 }}", workflow)
        self.assertNotIn("${{ inputs.zachary_image_base64 }}", workflow)
        self.assertIn("actions: read", workflow)

    def ledger_environment(self) -> dict[str, str]:
        return {
            "GITHUB_ACTIONS": "true",
            "GITHUB_EVENT_NAME": "workflow_dispatch",
            "GITHUB_REPOSITORY": runner.EXPECTED_REPOSITORY,
            "GITHUB_TOKEN": "present-but-never-logged",
            "GITHUB_RUN_ID": "222",
            "GITHUB_RUN_ATTEMPT": "1",
        }

    def test_one_shot_ledger_accepts_only_current_first_generate_run(self) -> None:
        page = {
            "total_count": 2,
            "workflow_runs": [
                {"id": 222, "display_title": runner.EXPECTED_GENERATE_RUN_TITLE},
                {
                    "id": 111,
                    "display_title": "StormMV_Zachary_v05 | check-binding | " + runner.AUTHORIZATION_ID,
                },
            ],
        }
        with mock.patch.dict(os.environ, self.ledger_environment(), clear=False), mock.patch.object(
            runner, "read_workflow_run_page", return_value=page
        ) as read_page:
            runner.assert_one_shot_ledger_clear(self.registered_manifest())
        read_page.assert_called_once()

    def test_one_shot_ledger_rejects_prior_generate_even_if_failed(self) -> None:
        page = {
            "total_count": 2,
            "workflow_runs": [
                {"id": 222, "display_title": runner.EXPECTED_GENERATE_RUN_TITLE},
                {"id": 111, "display_title": runner.EXPECTED_GENERATE_RUN_TITLE},
            ],
        }
        with mock.patch.dict(os.environ, self.ledger_environment(), clear=False), mock.patch.object(
            runner, "read_workflow_run_page", return_value=page
        ):
            self.assert_safe_failure(
                "ONE_SHOT_AUTHORIZATION_ALREADY_CONSUMED_NEW_AUTH_REQUIRED",
                lambda: runner.assert_one_shot_ledger_clear(self.registered_manifest()),
            )

    def test_generate_preflight_requires_exact_confirmation_and_first_attempt(self) -> None:
        manifest = self.registered_manifest()
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            runner, "assert_one_shot_ledger_clear"
        ) as ledger:
            with mock.patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "1"}, clear=False):
                self.assert_safe_failure(
                    "GENERATE_CONFIRMATION_REQUIRED",
                    lambda: runner.validate_generate_preflight(
                        manifest, Path(temporary), "WRONG"
                    ),
                )
                runner.validate_generate_preflight(
                    manifest, Path(temporary), runner.CONFIRMATION
                )
            with mock.patch.dict(os.environ, {"GITHUB_RUN_ATTEMPT": "2"}, clear=False):
                self.assert_safe_failure(
                    "GENERATE_REQUIRES_GITHUB_RUN_ATTEMPT_1",
                    lambda: runner.validate_generate_preflight(
                        manifest, Path(temporary), runner.CONFIRMATION
                    ),
                )
        ledger.assert_called_once_with(manifest)

    def test_check_binding_makes_zero_provider_and_ledger_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            runner, "api_json"
        ) as api_json, mock.patch.object(
            runner, "assert_one_shot_ledger_clear"
        ) as ledger:
            with mock.patch.dict(
                os.environ,
                {
                    "ALIYUN_MODEL_STUDIO_HK_API_HOST": runner.EXPECTED_API_HOST,
                    "ALIYUN_MODEL_STUDIO_HK_API_KEY": "present-but-not-used",
                },
                clear=False,
            ):
                runner.run_mode("check-binding", self.registered_manifest(), Path(temporary))
            api_json.assert_not_called()
            ledger.assert_not_called()

    def test_resume_is_get_only(self) -> None:
        task_id = "54a431fd-d909-4174-acf5-d0fa412d6fd4"
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            runner,
            "api_json",
            return_value=(
                {"output": {"task_status": "FAILED", "code": "TEST_FAILURE"}},
                "query-request",
            ),
        ) as api_json:
            with mock.patch.dict(
                os.environ,
                {
                    "ALIYUN_MODEL_STUDIO_HK_API_HOST": runner.EXPECTED_API_HOST,
                    "ALIYUN_MODEL_STUDIO_HK_API_KEY": "present-but-not-logged",
                    "WAN_RESUME_TASK_ID": task_id,
                },
                clear=False,
            ):
                self.assert_safe_failure(
                    "TASK_FAILED",
                    lambda: runner.run_mode(
                        "resume", self.registered_manifest(), Path(temporary)
                    ),
                )
            api_json.assert_called_once()
            self.assertIsNone(api_json.call_args.kwargs["payload"])

    def test_submit_once_posts_exactly_once_and_records_task(self) -> None:
        task_id = "54a431fd-d909-4174-acf5-d0fa412d6fd4"
        receipt = runner.base_receipt(
            "generate", self.registered_manifest(), runner.EXPECTED_API_HOST
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            runner,
            "api_json",
            return_value=(
                {"output": {"task_id": task_id}, "usage": {"video_duration": 4}},
                "post-request",
            ),
        ) as api_json:
            path = Path(temporary) / "receipt.json"
            result = runner.submit_once(
                runner.EXPECTED_API_HOST,
                "not-logged",
                {"pinned": True},
                path,
                receipt,
            )
            self.assertEqual(result, task_id)
            api_json.assert_called_once()
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["status"], "SUBMITTED_ONE_SHOT_CONSUMED")

    def test_uncertain_post_outcome_is_recorded_without_retry(self) -> None:
        receipt = runner.base_receipt(
            "generate", self.registered_manifest(), runner.EXPECTED_API_HOST
        )
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            runner,
            "api_json",
            side_effect=runner.ApiFailure(None, "NETWORK_OR_TIMEOUT", False),
        ) as api_json:
            path = Path(temporary) / "receipt.json"
            self.assert_safe_failure(
                "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY_NEW_AUTH_REQUIRED",
                lambda: runner.submit_once(
                    runner.EXPECTED_API_HOST,
                    "not-logged",
                    {"pinned": True},
                    path,
                    receipt,
                ),
            )
            api_json.assert_called_once()
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                saved["status"],
                "POST_OUTCOME_UNKNOWN_DO_NOT_RETRY_NEW_AUTH_REQUIRED",
            )

    def test_output_requires_silent_480p_landscape_16_9_and_duration(self) -> None:
        manifest = self.registered_manifest()
        output_name = manifest["request"]["output_name"]
        video_stream = {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 854,
            "height": 480,
            "avg_frame_rate": "30/1",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / output_name
            path.write_bytes(b"placeholder")
            valid = {"streams": [video_stream], "format": {"duration": "4.0"}}
            with mock.patch.object(runner, "probe_media", return_value=valid), mock.patch.object(
                runner, "full_decode"
            ):
                result = runner.verify_output_video(path, manifest)
                self.assertEqual(result["audio_stream_count"], 0)
            audio_bad = {
                "streams": [video_stream, {"codec_type": "audio", "codec_name": "aac"}],
                "format": {"duration": "4.0"},
            }
            with mock.patch.object(runner, "probe_media", return_value=audio_bad):
                self.assert_safe_failure(
                    "VIDEO_MUST_BE_SILENT",
                    lambda: runner.verify_output_video(path, manifest),
                )
            ratio_bad = copy.deepcopy(video_stream)
            ratio_bad["width"] = 800
            with mock.patch.object(
                runner,
                "probe_media",
                return_value={"streams": [ratio_bad], "format": {"duration": "4.0"}},
            ):
                self.assert_safe_failure(
                    "VIDEO_RATIO_NOT_16_9",
                    lambda: runner.verify_output_video(path, manifest),
                )

    def test_receipt_has_no_secret_base64_event_or_signed_url_fields(self) -> None:
        receipt = runner.base_receipt(
            "generate", self.registered_manifest(), runner.EXPECTED_API_HOST
        )
        text = json.dumps(receipt)
        for forbidden in (
            "api_key",
            "github_token",
            "base64",
            "event_payload",
            "result_url",
            "signed_url",
        ):
            self.assertNotIn(forbidden, text.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
