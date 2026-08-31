#!/usr/bin/env python3
"""Validate the private derived-knowledge repository and its manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
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

PUBLICATION_DIRS = ("knowledge", "data", "skills", "examples")
ROOT_PUBLICATION_FILES = (
    "README.md", "SOURCE_BOUNDARIES.md", "SHARING_POLICY.md", "CHANGELOG.md"
)


def required_files(root: Path) -> list[Path]:
    relative = [
        "README.md",
        "SOURCE_BOUNDARIES.md",
        "SHARING_POLICY.md",
        "CHANGELOG.md",
        "knowledge/full-course-map.md",
        "knowledge/day-1-laohong.md",
        "knowledge/day-2-channel-reference.md",
        "data/course-crosswalk.v1.json",
        "data/manifest.json",
        "skills/ai-training-guangzhou/SKILL.md",
        "skills/ai-training-guangzhou/references/day-1.md",
        "skills/ai-training-guangzhou/references/day-2.md",
        "skills/ai-training-guangzhou/references/source-boundaries.md",
        "examples/github-api.md",
        "examples/codex-install.md",
        "scripts/validate_repository.py",
        "tests/test_repository.py",
    ]
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
            findings.append(f"prohibited extension: {path.relative_to(root)}")

    for path in publication_files(root):
        if not path.is_file() or path.suffix.lower() not in {".md", ".json", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8")
        for needle, label in PROHIBITED_TEXT.items():
            if needle in text:
                findings.append(f"{label}: {path.relative_to(root)}")
    return sorted(findings)


def validate_crosswalk(root: Path) -> list[str]:
    errors: list[str] = []
    path = root / "data" / "course-crosswalk.v1.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"crosswalk parse failed: {exc}"]

    if data.get("schema_version") != "1.0.0":
        errors.append("crosswalk schema_version must be 1.0.0")
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
    if not all(item.get("reference_only") is True for item in sections):
        errors.append("every day2 section must remain reference_only")
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
        "visibility_required": "PRIVATE",
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
