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
        self.assertTrue(all(item["reference_only"] is True for item in sections))

    def test_no_prohibited_files_or_content(self):
        findings = self.validator.scan_prohibited(ROOT)
        self.assertEqual(findings, [])

    def test_skill_structure(self):
        skill_root = ROOT / "skills" / "ai-training-guangzhou"
        self.assertTrue((skill_root / "SKILL.md").is_file())
        self.assertEqual(
            {path.name for path in (skill_root / "references").glob("*.md")},
            {"day-1.md", "day-2.md", "source-boundaries.md"},
        )

    def test_manifest_hashes(self):
        errors = self.validator.verify_manifest(ROOT)
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
