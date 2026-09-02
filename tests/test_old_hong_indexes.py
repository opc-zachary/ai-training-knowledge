import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts" / "build_old_hong_indexes.py"


class OldHongIndexBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not BUILDER_PATH.is_file():
            raise AssertionError("scripts/build_old_hong_indexes.py is missing")
        spec = importlib.util.spec_from_file_location("build_old_hong_indexes", BUILDER_PATH)
        cls.builder = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.builder
        spec.loader.exec_module(cls.builder)

    def test_parse_knowledge_points_extracts_evidence(self):
        markdown = """# Sample

### LH-PE-001｜好 Prompt 是跑出來的

- 一句話：提示詞要由結果證明。
- 課堂原意：先執行再復盤。
- 整理與應用：保留版本差距。
- 使用時機：重複任務。
- 不適用：一次問答。
- 下一步：跑第一輪。
- 關聯流程：`LH-WF-01`
- Evidence：`DJI_20260830102734_0001_D|00:08:00-00:10:00|Cleaned_Review`
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.md"
            path.write_text(markdown, encoding="utf-8")
            points = self.builder.parse_knowledge_points(path, ROOT)
        self.assertEqual(points[0]["id"], "LH-PE-001")
        self.assertEqual(points[0]["workflows"], ["LH-WF-01"])
        self.assertEqual(points[0]["video_id"], "DJI_20260830102734_0001_D")
        self.assertEqual(points[0]["start"], "00:08:00")
        self.assertEqual(points[0]["end"], "00:10:00")

    def test_parse_knowledge_points_rejects_missing_fields(self):
        markdown = """### LH-PE-001｜不完整

- 一句話：只有一個欄位。
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.md"
            path.write_text(markdown, encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing fields"):
                self.builder.parse_knowledge_points(path, ROOT)

    def test_parse_workflows_validates_references(self):
        markdown = """---
id: LH-WF-01
title: 測試流程
knowledge_points: LH-PE-001,LH-QA-001
evidence: DJI_20260830102734_0001_D|00:08:00-00:10:00
---

```mermaid
flowchart LR
  A --> B
```

1. 第一步
2. 第二步
3. 第三步
4. 第四步

## 產出物

- 結果

## 驗收標準

- 通過
"""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "flow.md"
            path.write_text(markdown, encoding="utf-8")
            flows = self.builder.parse_workflows(path, ROOT, {"LH-PE-001", "LH-QA-001"})
        self.assertEqual(flows[0]["id"], "LH-WF-01")
        self.assertEqual(flows[0]["knowledge_points"], ["LH-PE-001", "LH-QA-001"])


if __name__ == "__main__":
    unittest.main()
