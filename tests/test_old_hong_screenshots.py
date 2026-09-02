import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts" / "build_old_hong_screenshots.py"


class OldHongScreenshotBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BUILDER_PATH.is_file():
            raise AssertionError("scripts/build_old_hong_screenshots.py is missing")
        spec = importlib.util.spec_from_file_location("build_old_hong_screenshots", BUILDER_PATH)
        cls.builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.builder
        spec.loader.exec_module(cls.builder)

    def test_time_conversion_and_midpoint(self):
        self.assertEqual(self.builder.hms_to_seconds("00:08:30"), 510.0)
        self.assertEqual(self.builder.choose_timestamp("00:08:00", "00:10:00"), 540.0)

    def test_filename_contains_stable_id_video_and_milliseconds(self):
        name = self.builder.build_filename(
            "LH-PE-001", "DJI_20260830102734_0001_D", 540.125
        )
        self.assertEqual(name, "LH-PE-001_DJI_20260830102734_0001_D_000540125.jpg")

    def test_discover_sources_finds_one_file_per_video(self):
        video_ids = {"DJI_20260830102734_0001_D", "DJI_20260830105517_0002_D"}
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            for video_id in video_ids:
                (source / f"course_{video_id}_4K.MP4").touch()
            found = self.builder.discover_sources(source, video_ids)
        self.assertEqual(set(found), video_ids)

    def test_discover_sources_rejects_missing_video(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "missing source videos"):
                self.builder.discover_sources(Path(directory), {"DJI_20260830102734_0001_D"})

    def test_gallery_groups_and_links_records(self):
        records = [
            {
                "id": "LH-SC-PE-001",
                "knowledge_id": "LH-PE-001",
                "title": "好 Prompt 是跑出來的",
                "description": "提示詞需要由結果驗證。",
                "video_id": "DJI_20260830102734_0001_D",
                "timestamp": "00:09:00.125",
                "path": "day-2/old-hong/screenshots/images/sample.jpg",
                "ocr_status": "recognized",
                "ocr_text": "Prompt",
            }
        ]
        gallery = self.builder.build_gallery(records)
        self.assertIn("Prompt Engineering", gallery)
        self.assertIn("![LH-PE-001](images/sample.jpg)", gallery)
        self.assertIn("00:09:00.125", gallery)

    def test_teaching_index_maps_knowledge_to_screenshots(self):
        records = [{"id": "LH-SC-PE-001", "knowledge_id": "LH-PE-001"}]
        teaching = [{"id": "LH-TF-01", "title": "Prompt", "knowledge_points": ["LH-PE-001"]}]
        result = self.builder.build_teaching_screenshot_index(records, teaching)
        self.assertEqual(result["teaching_flows"][0]["screenshot_ids"], ["LH-SC-PE-001"])


if __name__ == "__main__":
    unittest.main()
