#!/usr/bin/env python3
"""Validate the private derived-knowledge repository and its manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_VIDEO_IDS = {
    "DJI_20260829105645_0008_D",
    "DJI_20260829142315_0012_D",
    "DJI_20260829145059_0013_D",
    "DJI_20260829151841_0014_D",
    "DJI_20260829154635_0015_D",
    "DJI_20260829161417_0016_D",
    "DJI_20260829164130_0017_D",
    "DJI_20260829170913_0018_D",
    "DJI_20260829172735_0019_D",
    "DJI_20260829174902_0005_D",
}

PROHIBITED_EXTENSIONS = {
    ".mov", ".mp4", ".mkv", ".avi", ".m4a", ".mp3", ".wav",
    ".srt", ".vtt", ".pdf", ".zip", ".rar", ".7z", ".docx",
    ".xlsx", ".pptx", ".png", ".jpg", ".jpeg", ".webp",
}

PROHIBITED_TEXT = {
    "/Users/": "absolute macOS user path",
    "/Volumes/": "absolute volume path",
    "C:\\Users\\": "absolute Windows user path",
    "资料包_Windows无乱码版.zip": "source archive filename",
    "3hour-ai-digital-employee-course-v2.pdf": "source courseware filename",
    "github_pat_": "GitHub token prefix",
    "ghp_": "GitHub token prefix",
}

PUBLICATION_DIRS = (
    "knowledge", "data", "skills", "examples", "playbooks", "templates", "exercises", "locales", "day-2"
)
ROOT_PUBLICATION_FILES = (
    "README.md", "README.en.md", "SOURCE_BOUNDARIES.md", "SHARING_POLICY.md", "CHANGELOG.md"
)

OLD_HONG_REQUIRED_COUNTS = {
    "knowledge_points": (50, 70),
    "workflows": 12,
    "teaching_flows": 5,
    "templates": 8,
    "learning_paths": 4,
}


def required_files(root: Path) -> list[Path]:
    relative = [
        "README.md",
        "README.en.md",
        "SOURCE_BOUNDARIES.md",
        "SHARING_POLICY.md",
        "CHANGELOG.md",
        "knowledge/full-course-map.md",
        "knowledge/day-1-laohong.md",
        "knowledge/day-2-channel-reference.md",
        "knowledge/day-2-video-guides.md",
        "knowledge/videos/day-1/README.md",
        "knowledge/modules/README.md",
        "knowledge/glossary.md",
        "knowledge/learning-paths.md",
        "knowledge/task-router.md",
        "data/course-crosswalk.v1.json",
        "data/manifest.json",
        "skills/ai-training-guangzhou/SKILL.md",
        "skills/ai-training-guangzhou/references/day-1.md",
        "skills/ai-training-guangzhou/references/day-2.md",
        "skills/ai-training-guangzhou/references/source-boundaries.md",
        "skills/ai-training-guangzhou/references/task-router.md",
        "skills/ai-training-guangzhou/references/application-playbooks.md",
        "skills/ai-training-guangzhou/references/templates.md",
        "skills/ai-training-guangzhou/references/zh-Hant-course.md",
        "skills/ai-training-guangzhou/references/zh-Hans-course.md",
        "examples/github-api.md",
        "examples/codex-install.md",
        "playbooks/brand-research.md",
        "playbooks/author-voice.md",
        "playbooks/visual-reverse.md",
        "playbooks/ecommerce-visual.md",
        "playbooks/ai-video.md",
        "playbooks/data-analysis.md",
        "templates/research-brief.md",
        "templates/workflow-spec.md",
        "templates/output-qa.md",
        "templates/agent-task.json",
        "templates/visual-set-plan.md",
        "exercises/beginner.md",
        "exercises/practical.md",
        "exercises/verification.md",
        "day-2/README.md",
        "day-2/TEAM_CALLING_GUIDE.md",
        "day-2/transcripts/README.md",
        "day-2/classification/terminology.md",
        "day-2/evidence/keyframe-index.json",
        "day-2/manifests/day-2-public-manifest.json",
        "day-2/old-hong/README.md",
        "day-2/old-hong/TEAM_AND_AGENT_GUIDE.md",
        "day-2/old-hong/knowledge-points/knowledge-index.json",
        "day-2/old-hong/workflows/workflow-index.json",
        "day-2/old-hong/teaching-flows/teaching-index.json",
        "day-2/old-hong/evidence/evidence-map.json",
        "day-2/old-hong/screenshots/README.md",
        "day-2/old-hong/screenshots/GALLERY.md",
        "day-2/old-hong/screenshots/screenshot-index.json",
        "day-2/old-hong/screenshots/teaching-screenshot-index.json",
        "scripts/validate_repository.py",
        "tests/test_repository.py",
    ]
    locale_names = (
        "README.md",
        "full-course.md",
        "day-1-video-guides.md",
        "modules.md",
        "playbooks.md",
        "exercises-and-templates.md",
        "glossary.md",
        "day-2-reference.md",
        "day-2-video-guides.md",
        "codex-usage.md",
    )
    for locale in ("zh-Hant", "zh-Hans"):
        relative.extend(f"locales/{locale}/{name}" for name in locale_names)
    return [root / item for item in relative]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def publication_files(root: Path) -> list[Path]:
    files = [root / name for name in ROOT_PUBLICATION_FILES]
    for dirname in PUBLICATION_DIRS:
        base = root / dirname
        if base.exists():
            files.extend(path for path in base.rglob("*") if path.is_file())
    return sorted(set(files))


def repository_files(root: Path) -> list[Path]:
    ignored_parts = {".git", "__pycache__", "docs"}
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in ignored_parts for part in path.relative_to(root).parts)
        and path.name != ".DS_Store"
    )


def scan_prohibited(root: Path) -> list[str]:
    findings: list[str] = []
    for path in repository_files(root):
        if path.suffix.lower() in PROHIBITED_EXTENSIONS:
            relative = path.relative_to(root).as_posix()
            allowed_srt = path.suffix.lower() == ".srt" and relative.startswith("day-2/transcripts/zh-Hant/")
            allowed_jpg = path.suffix.lower() in {".jpg", ".jpeg"} and (
                relative.startswith("day-2/evidence/keyframes/")
                or relative.startswith("day-2/old-hong/screenshots/images/")
            )
            if not allowed_srt and not allowed_jpg:
                findings.append(f"prohibited extension: {relative}")

    for path in publication_files(root):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle, label in PROHIBITED_TEXT.items():
            if needle in text:
                findings.append(f"{label}: {path.relative_to(root)}")
    return sorted(findings)


def resource_paths(data: dict) -> list[str]:
    resources = data.get("resources", {})
    paths: list[str] = []
    for key in ("video_guides", "module_handbooks"):
        index = resources.get(key, {}).get("index")
        if index:
            paths.append(index)
    for key in ("playbooks", "templates", "exercises", "navigation"):
        paths.extend(resources.get(key, []))
    skill = resources.get("codex_skill")
    if skill:
        paths.append(skill)
    paths.extend(resources.get("locales", {}).values())
    old_hong = resources.get("old_hong_system", {})
    for key in (
        "root", "calling_guide", "knowledge_index", "workflow_index", "teaching_index", "evidence_map",
        "screenshot_gallery", "screenshot_index", "teaching_screenshot_index",
    ):
        path = old_hong.get(key)
        if path:
            paths.append(path)
    return paths


def validate_locales(root: Path) -> list[str]:
    errors: list[str] = []
    expected = {
        "README.md",
        "full-course.md",
        "day-1-video-guides.md",
        "modules.md",
        "playbooks.md",
        "exercises-and-templates.md",
        "glossary.md",
        "day-2-reference.md",
        "day-2-video-guides.md",
        "codex-usage.md",
    }
    hant_root = root / "locales" / "zh-Hant"
    hans_root = root / "locales" / "zh-Hans"
    hant_names = {path.name for path in hant_root.glob("*.md")}
    hans_names = {path.name for path in hans_root.glob("*.md")}
    if hant_names != expected:
        errors.append("zh-Hant file set does not match the ten expected locale files")
    if hans_names != expected:
        errors.append("zh-Hans file set does not match the ten expected locale files")

    traditional_markers = set("這個為與學習資訊據驗證務圖發產業關閉開後裡說寫還")
    for name in sorted(expected):
        hant_path = hant_root / name
        hans_path = hans_root / name
        if not hant_path.is_file() or not hans_path.is_file():
            continue
        hant = hant_path.read_text(encoding="utf-8")
        hans = hans_path.read_text(encoding="utf-8")
        minimum_length = 400 if name in {"README.md", "day-2-reference.md", "codex-usage.md"} else 800
        if len(hant) < minimum_length or len(hans) < minimum_length:
            errors.append(f"locale content too small: {name}")
        if hant.count("```") != hans.count("```"):
            errors.append(f"code fence count differs between locales: {name}")
        remaining = sorted(marker for marker in traditional_markers if marker in hans)
        if remaining:
            errors.append(f"traditional markers remain in zh-Hans/{name}: {''.join(remaining)}")
    return errors


def validate_markdown_links(root: Path) -> list[str]:
    errors: list[str] = []
    pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
    for path in publication_files(root):
        if path.suffix.lower() != ".md":
            continue
        text = path.read_text(encoding="utf-8")
        for raw_target in pattern.findall(text):
            target = raw_target.strip().split(" ", 1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative = target.split("#", 1)[0]
            resolved = (path.parent / relative).resolve()
            try:
                resolved.relative_to(root.resolve())
            except ValueError:
                errors.append(f"link escapes repository: {path.relative_to(root)} -> {target}")
                continue
            if not resolved.exists():
                errors.append(f"broken link: {path.relative_to(root)} -> {target}")
    return sorted(errors)


def validate_day2_detailed_package(root: Path) -> list[str]:
    errors: list[str] = []
    base = root / "day-2"
    hant_guides = list((base / "guides/zh-Hant").glob("*/*.md"))
    hans_guides = list((base / "guides/zh-Hans").glob("*/*.md"))
    if len(hant_guides) != 15:
        errors.append(f"expected 15 zh-Hant Day 2 guides/indexes, found {len(hant_guides)}")
    if len(hans_guides) != 15:
        errors.append(f"expected 15 zh-Hans Day 2 guides/indexes, found {len(hans_guides)}")

    transcript_root = base / "transcripts/zh-Hant"
    expected_names = {"transcript.txt", "timestamped.txt", "subtitle.srt", "transcript.json", "qa.json"}
    video_dirs = [path for path in transcript_root.glob("*/*") if path.is_dir()]
    if len(video_dirs) != 13:
        errors.append(f"expected 13 transcript directories, found {len(video_dirs)}")
    for directory in video_dirs:
        names = {path.name for path in directory.iterdir() if path.is_file()}
        if names != expected_names:
            errors.append(f"transcript file set mismatch: {directory.relative_to(root)}")
        for json_name in ("transcript.json", "qa.json"):
            try:
                json.loads((directory / json_name).read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                errors.append(f"invalid transcript JSON {directory / json_name}: {exc}")

    frame_files = list((base / "evidence/keyframes").glob("*/*.jpg"))
    if len(frame_files) != 117:
        errors.append(f"expected 117 keyframes, found {len(frame_files)}")
    index_path = base / "evidence/keyframe-index.json"
    try:
        frame_index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid keyframe index: {exc}")
        frame_index = {"count": 0, "frames": []}
    if frame_index.get("count") != 117 or len(frame_index.get("frames", [])) != 117:
        errors.append("keyframe index count mismatch")
    for item in frame_index.get("frames", []):
        path = root / item.get("path", "")
        if not path.is_file():
            errors.append(f"missing keyframe path: {item.get('path')}")
            continue
        if path.stat().st_size != item.get("size_bytes"):
            errors.append(f"keyframe size mismatch: {item.get('path')}")
        if sha256(path) != item.get("sha256"):
            errors.append(f"keyframe hash mismatch: {item.get('path')}")

    public_manifest_path = base / "manifests/day-2-public-manifest.json"
    try:
        public_manifest = json.loads(public_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid Day 2 public manifest: {exc}")
        public_manifest = {}
    if public_manifest.get("content_version") != "1.4.0":
        errors.append("Day 2 public manifest content_version must be 1.4.0")
    knowledge = public_manifest.get("knowledge", {})
    if knowledge.get("usable_video_guides") != 13 or knowledge.get("cleaned_transcripts") != 13:
        errors.append("Day 2 public manifest knowledge counts mismatch")
    if knowledge.get("classification_frames") != 117:
        errors.append("Day 2 public manifest frame count mismatch")

    oversized = [path.relative_to(root).as_posix() for path in base.rglob("*") if path.is_file() and path.stat().st_size > 1_000_000]
    if oversized:
        errors.append(f"Day 2 Git package contains oversized files: {oversized}")
    forbidden_media = [
        path.relative_to(root).as_posix()
        for path in base.rglob("*")
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov", ".lrf", ".pdf", ".zip"}
    ]
    if forbidden_media:
        errors.append(f"Day 2 Git package contains source/binary media: {forbidden_media}")
    return errors


def validate_old_hong_package(root: Path) -> list[str]:
    """Validate the bilingual, evidence-linked Old Hong learning package."""
    errors: list[str] = []
    base = root / "day-2" / "old-hong"
    required = [
        base / "README.md",
        base / "TEAM_AND_AGENT_GUIDE.md",
        base / "knowledge-points" / "knowledge-index.json",
        base / "workflows" / "workflow-index.json",
        base / "teaching-flows" / "teaching-index.json",
        base / "evidence" / "evidence-map.json",
        base / "evidence" / "coverage-report.md",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing Old Hong file: {path.relative_to(root)}")

    expected_markdown_counts = {
        "knowledge-points": 7,
        "workflows": OLD_HONG_REQUIRED_COUNTS["workflows"],
        "teaching-flows": OLD_HONG_REQUIRED_COUNTS["teaching_flows"],
        "templates": OLD_HONG_REQUIRED_COUNTS["templates"],
        "learning-paths": OLD_HONG_REQUIRED_COUNTS["learning_paths"],
    }
    for section, expected in expected_markdown_counts.items():
        hant = {path.name for path in (base / section / "zh-Hant").glob("*.md")}
        hans = {path.name for path in (base / section / "zh-Hans").glob("*.md")}
        if len(hant) != expected:
            errors.append(f"Old Hong {section} zh-Hant count must be {expected}, found {len(hant)}")
        if hans != hant:
            errors.append(f"Old Hong {section} zh-Hans paths do not match zh-Hant")

    def load_index(path: Path, key: str) -> list[dict]:
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid Old Hong JSON {path.relative_to(root)}: {exc}")
            return []
        items = data.get(key)
        if not isinstance(items, list):
            errors.append(f"Old Hong JSON key {key} must be a list: {path.relative_to(root)}")
            return []
        return items

    knowledge = load_index(base / "knowledge-points" / "knowledge-index.json", "knowledge_points")
    workflows = load_index(base / "workflows" / "workflow-index.json", "workflows")
    teaching = load_index(base / "teaching-flows" / "teaching-index.json", "teaching_flows")
    evidence = load_index(base / "evidence" / "evidence-map.json", "evidence")

    minimum, maximum = OLD_HONG_REQUIRED_COUNTS["knowledge_points"]
    if not minimum <= len(knowledge) <= maximum:
        errors.append(f"Old Hong knowledge point count must be {minimum}-{maximum}, found {len(knowledge)}")
    if len(workflows) != OLD_HONG_REQUIRED_COUNTS["workflows"]:
        errors.append(f"Old Hong workflow index must contain 12 records, found {len(workflows)}")
    if len(teaching) != OLD_HONG_REQUIRED_COUNTS["teaching_flows"]:
        errors.append(f"Old Hong teaching index must contain 5 records, found {len(teaching)}")
    if len(evidence) != len(knowledge):
        errors.append("Old Hong evidence count must match knowledge point count")

    def unique_ids(items: list[dict], label: str) -> set[str]:
        ids = [item.get("id") for item in items]
        if any(not isinstance(item, str) or not item for item in ids):
            errors.append(f"Old Hong {label} contains a missing ID")
        if len(ids) != len(set(ids)):
            errors.append(f"Old Hong {label} IDs are not unique")
        return {item for item in ids if isinstance(item, str) and item}

    knowledge_ids = unique_ids(knowledge, "knowledge")
    workflow_ids = unique_ids(workflows, "workflow")
    unique_ids(teaching, "teaching")
    evidence_ids = {item.get("knowledge_id") for item in evidence}
    if evidence and evidence_ids != knowledge_ids:
        errors.append("Old Hong evidence knowledge IDs do not match knowledge index")

    for item in knowledge + workflows + teaching:
        relative = item.get("path")
        if not relative or not (root / relative).is_file():
            errors.append(f"Old Hong index path missing: {relative}")
    for item in workflows:
        unknown = set(item.get("knowledge_points", [])) - knowledge_ids
        if unknown:
            errors.append(f"Old Hong workflow {item.get('id')} has unknown knowledge IDs: {sorted(unknown)}")
    for item in teaching:
        unknown_knowledge = set(item.get("knowledge_points", [])) - knowledge_ids
        unknown_workflows = set(item.get("workflows", [])) - workflow_ids
        if unknown_knowledge:
            errors.append(f"Old Hong teaching {item.get('id')} has unknown knowledge IDs")
        if unknown_workflows:
            errors.append(f"Old Hong teaching {item.get('id')} has unknown workflow IDs")

    if base.exists():
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt"}:
                continue
            text = path.read_text(encoding="utf-8")
            for needle in ("/Users/", "/Volumes/", "C:\\Users\\", "github_pat_", "ghp_"):
                if needle in text:
                    errors.append(f"Old Hong prohibited text in {path.relative_to(root)}: {needle}")
            if re.search(r"\.(?:mp4|mov|lrf|pdf|zip)(?:\b|\))", text, flags=re.IGNORECASE):
                errors.append(f"Old Hong prohibited source extension reference: {path.relative_to(root)}")
    return sorted(set(errors))


def jpeg_dimensions(path: Path) -> tuple[int, int]:
    """Read JPEG dimensions with the Python standard library."""
    with path.open("rb") as handle:
        if handle.read(2) != b"\xff\xd8":
            raise ValueError("not a JPEG")
        while True:
            marker_start = handle.read(1)
            if not marker_start:
                raise ValueError("JPEG dimensions not found")
            if marker_start != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in {b"\xd8", b"\xd9"}:
                continue
            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                raise ValueError("truncated JPEG marker")
            length = int.from_bytes(length_bytes, "big")
            if marker in {
                b"\xc0", b"\xc1", b"\xc2", b"\xc3",
                b"\xc5", b"\xc6", b"\xc7",
                b"\xc9", b"\xca", b"\xcb",
                b"\xcd", b"\xce", b"\xcf",
            }:
                data = handle.read(length - 2)
                if len(data) < 5:
                    raise ValueError("truncated JPEG size segment")
                return int.from_bytes(data[3:5], "big"), int.from_bytes(data[1:3], "big")
            handle.seek(length - 2, 1)


def validate_old_hong_screenshots(root: Path) -> list[str]:
    """Validate one screenshot per Old Hong knowledge point and teaching mappings."""
    errors: list[str] = []
    base = root / "day-2" / "old-hong" / "screenshots"
    required = [
        base / "README.md",
        base / "GALLERY.md",
        base / "screenshot-index.json",
        base / "teaching-screenshot-index.json",
    ]
    for path in required:
        if not path.is_file():
            errors.append(f"missing Old Hong screenshot file: {path.relative_to(root)}")

    def load(path: Path, key: str) -> list[dict]:
        if not path.is_file():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            errors.append(f"invalid Old Hong screenshot JSON {path.relative_to(root)}: {exc}")
            return []
        items = data.get(key)
        if not isinstance(items, list):
            errors.append(f"Old Hong screenshot JSON key {key} must be a list")
            return []
        return items

    screenshots = load(base / "screenshot-index.json", "screenshots")
    teaching = load(base / "teaching-screenshot-index.json", "teaching_flows")
    for path in (base / "screenshot-index.json", base / "teaching-screenshot-index.json"):
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("content_version") != "1.6.0":
                errors.append(f"Old Hong screenshot content_version must be 1.6.0: {path.relative_to(root)}")
    images = sorted((base / "images").glob("*.jpg"))
    if len(images) != 56:
        errors.append(f"Old Hong screenshot image count must be 56, found {len(images)}")
    if len(screenshots) != 56:
        errors.append(f"Old Hong screenshot index must contain 56 records, found {len(screenshots)}")
    if len(teaching) != 5:
        errors.append(f"Old Hong teaching screenshot index must contain 5 records, found {len(teaching)}")

    try:
        knowledge = json.loads(
            (root / "day-2/old-hong/knowledge-points/knowledge-index.json").read_text(encoding="utf-8")
        )["knowledge_points"]
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        errors.append(f"cannot load Old Hong knowledge index for screenshots: {exc}")
        knowledge = []
    knowledge_ids = {item.get("id") for item in knowledge}
    screenshot_ids = [item.get("id") for item in screenshots]
    screenshot_knowledge_ids = [item.get("knowledge_id") for item in screenshots]
    if len(screenshot_ids) != len(set(screenshot_ids)):
        errors.append("Old Hong screenshot IDs are not unique")
    if len(screenshot_knowledge_ids) != len(set(screenshot_knowledge_ids)):
        errors.append("Old Hong screenshot knowledge IDs are not unique")
    if screenshots and set(screenshot_knowledge_ids) != knowledge_ids:
        errors.append("Old Hong screenshots do not cover exactly the knowledge index IDs")

    for item in screenshots:
        relative = item.get("path", "")
        image_path = root / relative
        if not image_path.is_file():
            errors.append(f"missing Old Hong screenshot image: {relative}")
            continue
        if not relative.startswith("day-2/old-hong/screenshots/images/"):
            errors.append(f"Old Hong screenshot path outside image directory: {relative}")
        if image_path.stat().st_size >= 1_000_000:
            errors.append(f"Old Hong screenshot exceeds 1 MB: {relative}")
        if item.get("size_bytes") != image_path.stat().st_size:
            errors.append(f"Old Hong screenshot size mismatch: {relative}")
        if item.get("sha256") != sha256(image_path):
            errors.append(f"Old Hong screenshot hash mismatch: {relative}")
        try:
            width, height = jpeg_dimensions(image_path)
        except ValueError as exc:
            errors.append(f"invalid Old Hong screenshot JPEG {relative}: {exc}")
            continue
        if width != 1920:
            errors.append(f"Old Hong screenshot width must be 1920: {relative}")
        if item.get("width") != width or item.get("height") != height:
            errors.append(f"Old Hong screenshot dimensions mismatch: {relative}")
        if item.get("ocr_status") not in {"recognized", "no_text_detected", "unavailable"}:
            errors.append(f"Old Hong screenshot OCR status invalid: {relative}")

    known_screenshots = set(screenshot_ids)
    for item in teaching:
        unknown = set(item.get("screenshot_ids", [])) - known_screenshots
        if unknown:
            errors.append(f"Old Hong teaching screenshot references unknown IDs: {sorted(unknown)}")
    return sorted(set(errors))


def validate_crosswalk(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / "data" / "course-crosswalk.v1.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"crosswalk parse failed: {exc}"]

    if data.get("schema_version") != "1.0.0":
        errors.append("crosswalk schema_version must be 1.0.0")
    if data.get("content_version") != "1.6.0":
        errors.append("crosswalk content_version must be 1.6.0")
    if data.get("status") != "public-derived-knowledge":
        errors.append("crosswalk status must be public-derived-knowledge")
    distribution = data.get("distribution", {})
    if distribution.get("repository_visibility") != "PUBLIC":
        errors.append("distribution repository_visibility must be PUBLIC")
    if distribution.get("languages") != ["zh-Hant", "zh-Hans", "en"]:
        errors.append("distribution languages must be zh-Hant, zh-Hans and en")
    modules = data.get("day1", {}).get("modules", [])
    ids = [item.get("id") for item in modules]
    if ids != [f"K{i:02d}" for i in range(11)]:
        errors.append("day1 module IDs must be exactly K00-K10 in order")
    video_ids = {
        video.get("id")
        for module in modules
        for video in module.get("videos", [])
    }
    if video_ids != EXPECTED_VIDEO_IDS:
        errors.append("day1 video coverage does not match the ten expected identifiers")
    sections = data.get("day2", {}).get("sections", [])
    if len(sections) != 7:
        errors.append("day2 must contain seven sections")
    if data.get("source_boundary", {}).get("day2_video_mapping_complete") is not True:
        errors.append("day2_video_mapping_complete must be true")
    if data.get("day2", {}).get("evidence_status") != "video_classified_review":
        errors.append("day2 evidence_status must be video_classified_review")
    if not all(item.get("reference_only") is False for item in sections):
        errors.append("every day2 section must leave reference_only after video mapping")
    if not all(item.get("video_classified_review") is True for item in sections):
        errors.append("every day2 section must be video_classified_review")
    for relative in resource_paths(data):
        if not (root / relative).is_file():
            errors.append(f"resource path missing: {relative}")
    return errors


def manifest_candidates(root: Path) -> list[Path]:
    return [
        path for path in repository_files(root)
        if path.relative_to(root).as_posix() != "data/manifest.json"
    ]


def build_manifest(root: Path) -> dict:
    entries = []
    for path in manifest_candidates(root):
        entries.append({
            "path": path.relative_to(root).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return {
        "schema_version": "1.0.0",
        "project": "AITrainingGuangzhou",
        "visibility_required": "PUBLIC",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "files": entries,
    }


def write_manifest(root: Path) -> Path:
    path = root / "data" / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(build_manifest(root), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def verify_manifest(root: Path) -> list[str]:
    path = root / "data" / "manifest.json"
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest parse failed: {exc}"]

    errors: list[str] = []
    recorded = {item["path"]: item for item in manifest.get("files", [])}
    current = {
        path.relative_to(root).as_posix(): path
        for path in manifest_candidates(root)
    }
    if set(recorded) != set(current):
        errors.append("manifest path set does not match repository files")
        return errors
    for relative, file_path in current.items():
        item = recorded[relative]
        if item.get("size_bytes") != file_path.stat().st_size:
            errors.append(f"manifest size mismatch: {relative}")
        if item.get("sha256") != sha256(file_path):
            errors.append(f"manifest hash mismatch: {relative}")
    return errors


def validate(root: Path) -> list[str]:
    errors = [
        f"missing required file: {path.relative_to(root)}"
        for path in required_files(root)
        if not path.is_file()
    ]
    errors.extend(validate_crosswalk(root))
    errors.extend(scan_prohibited(root))
    errors.extend(validate_markdown_links(root))
    errors.extend(validate_locales(root))
    errors.extend(validate_day2_detailed_package(root))
    errors.extend(validate_old_hong_package(root))
    errors.extend(validate_old_hong_screenshots(root))
    errors.extend(verify_manifest(root))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write-manifest", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    if args.write_manifest:
        path = write_manifest(root)
        print(f"manifest written: {path.relative_to(root)}")
    errors = validate(root)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("repository validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
