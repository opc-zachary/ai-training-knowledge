import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = ROOT / "scripts" / "validate_repository.py"


class RepositoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not VALIDATOR_PATH.is_file():
            raise AssertionError("scripts/validate_repository.py is missing")
        spec = importlib.util.spec_from_file_location("validate_repository", VALIDATOR_PATH)
        cls.validator = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.validator
        spec.loader.exec_module(cls.validator)

    def test_required_files(self):
        missing = [str(path) for path in self.validator.required_files(ROOT) if not path.is_file()]
        self.assertEqual(missing, [])

    def test_crosswalk_contract(self):
        data = json.loads((ROOT / "data" / "course-crosswalk.v1.json").read_text())
        self.assertEqual(data["schema_version"], "1.0.0")
        self.assertEqual(data["content_version"], "1.5.0")
        self.assertEqual(data["status"], "public-derived-knowledge")
        self.assertEqual(data["distribution"]["repository_visibility"], "PUBLIC")
        self.assertEqual(data["distribution"]["languages"], ["zh-Hant", "zh-Hans", "en"])
        modules = data["day1"]["modules"]
        self.assertEqual([item["id"] for item in modules], [f"K{i:02d}" for i in range(11)])
        video_ids = {
            video["id"]
            for module in modules
            for video in module["videos"]
        }
        self.assertEqual(video_ids, self.validator.EXPECTED_VIDEO_IDS)
        sections = data["day2"]["sections"]
        self.assertEqual(len(sections), 7)
        self.assertTrue(data["source_boundary"]["day2_video_mapping_complete"])
        self.assertEqual(data["day2"]["evidence_status"], "video_classified_review")
        self.assertTrue(all(item["reference_only"] is False for item in sections))
        self.assertTrue(all(item["video_classified_review"] is True for item in sections))
        self.assertEqual(data["day2"]["video_summary"]["total"], 18)
        self.assertEqual(data["day2"]["video_summary"]["usable_core_or_supporting"], 13)
        self.assertEqual(data["day2"]["video_summary"]["rejected_ambient_or_hallucination"], 5)
        self.assertEqual(data["day2"]["video_summary"]["individual_guides_zh_hant"], 13)
        self.assertEqual(data["day2"]["video_summary"]["individual_guides_zh_hans"], 13)
        self.assertEqual(data["day2"]["video_summary"]["cleaned_transcript_file_set"], 65)
        self.assertTrue(data["source_boundary"]["contains_transcript_or_subtitle"])
        self.assertFalse(data["source_boundary"]["contains_raw_hallucinated_transcript"])
        resources = data["resources"]
        self.assertEqual(resources["video_guides"]["count"], 10)
        self.assertEqual(resources["module_handbooks"]["count"], 11)
        old_hong = resources["old_hong_system"]
        self.assertEqual(old_hong["knowledge_points"], 56)
        self.assertEqual(old_hong["workflows"], 12)
        self.assertEqual(old_hong["teaching_flows"], 5)
        self.assertEqual(old_hong["templates"], 8)
        self.assertEqual(old_hong["learning_paths"], 4)
        for path in self.validator.resource_paths(data):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_no_prohibited_files_or_content(self):
        findings = self.validator.scan_prohibited(ROOT)
        self.assertEqual(findings, [])

    def test_skill_structure(self):
        skill_root = ROOT / "skills" / "ai-training-guangzhou"
        self.assertTrue((skill_root / "SKILL.md").is_file())
        self.assertTrue(
            {
                "day-1.md",
                "day-2.md",
                "source-boundaries.md",
                "task-router.md",
                "application-playbooks.md",
                "templates.md",
            }.issubset({path.name for path in (skill_root / "references").glob("*.md")})
        )

    def test_detailed_content_inventory(self):
        guides = list((ROOT / "knowledge" / "videos" / "day-1").glob("[0-9][0-9]-*.md"))
        modules = list((ROOT / "knowledge" / "modules").glob("K[0-9][0-9]-*.md"))
        playbooks = list((ROOT / "playbooks").glob("*.md"))
        templates = list((ROOT / "templates").glob("*"))
        exercises = list((ROOT / "exercises").glob("*.md"))
        self.assertEqual(len(guides), 10)
        self.assertEqual(len(modules), 11)
        self.assertEqual(len(playbooks), 6)
        self.assertEqual(len(templates), 5)
        self.assertEqual(len(exercises), 3)
        self.assertTrue(all(path.stat().st_size >= 2500 for path in guides))
        self.assertTrue(all(path.stat().st_size >= 900 for path in modules))

    def test_markdown_links(self):
        self.assertEqual(self.validator.validate_markdown_links(ROOT), [])

    def test_day2_detailed_package(self):
        self.assertEqual(self.validator.validate_day2_detailed_package(ROOT), [])

    def test_old_hong_package(self):
        self.assertEqual(self.validator.validate_old_hong_package(ROOT), [])

    def test_old_hong_screenshots(self):
        self.assertEqual(self.validator.validate_old_hong_screenshots(ROOT), [])

    def test_chinese_locales(self):
        self.assertEqual(self.validator.validate_locales(ROOT), [])
        for locale_name in ("zh-Hant", "zh-Hans"):
            locale_root = ROOT / "locales" / locale_name
            self.assertEqual(len(list(locale_root.glob("*.md"))), 10)
        self.assertIn("繁體中文完整版", (ROOT / "locales/zh-Hant/README.md").read_text())
        self.assertIn("简体中文完整版", (ROOT / "locales/zh-Hans/README.md").read_text())

    def test_manifest_hashes(self):
        errors = self.validator.verify_manifest(ROOT)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
