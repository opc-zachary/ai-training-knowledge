#!/usr/bin/env python3
"""Extract and index one local screenshot for every Old Hong knowledge point."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCREENSHOT_BASE = ROOT / "day-2" / "old-hong" / "screenshots"
CATEGORY_NAMES = {
    "PE": "Prompt Engineering",
    "CTX": "Context 與 Prompt 排錯",
    "SKL": "Skill 搜尋、建立與架構",
    "WB": "個人 AI 工作台",
    "AUTO": "企業自動化",
    "FDE": "FDE 與企業落地",
    "QA": "測試、驗收與持續改進",
}


def hms_to_seconds(value: str) -> float:
    hours, minutes, seconds = value.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def seconds_to_timestamp(value: float) -> str:
    milliseconds = round(value * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def choose_timestamp(start: str, end: str) -> float:
    start_seconds = hms_to_seconds(start)
    end_seconds = hms_to_seconds(end)
    if end_seconds <= start_seconds:
        raise ValueError(f"invalid evidence range: {start}-{end}")
    return (start_seconds + end_seconds) / 2


def discover_sources(source_dir: Path, video_ids: set[str]) -> dict[str, Path]:
    if not source_dir.is_dir():
        raise ValueError(f"source directory does not exist: {source_dir}")
    candidates = [
        path for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in {".mp4", ".mov"}
    ]
    found: dict[str, Path] = {}
    for video_id in sorted(video_ids):
        matches = [path for path in candidates if video_id in path.name]
        if len(matches) > 1:
            raise ValueError(f"multiple source videos for {video_id}")
        if matches:
            found[video_id] = matches[0]
    missing = sorted(video_ids - set(found))
    if missing:
        raise ValueError(f"missing source videos: {missing}")
    return found


def build_filename(knowledge_id: str, video_id: str, seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    return f"{knowledge_id}_{video_id}_{milliseconds:09d}.jpg"


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def extract_frame(source: Path, seconds: float, output: Path) -> None:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite screenshot: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            "scale=1920:-2",
            "-q:v",
            "3",
            "-map_metadata",
            "-1",
            "-n",
            str(output),
        ]
    )


def probe_image(path: Path) -> tuple[int, int]:
    result = run(
        [
            shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height",
            "-of",
            "json",
            str(path),
        ]
    )
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_ocr(paths: list[Path], helper: Path) -> dict[str, dict]:
    if not paths:
        return {}
    result = run([shutil.which("swift") or "/usr/bin/swift", str(helper), *(str(path) for path in paths)])
    records: dict[str, dict] = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        records[item["path"]] = item
    missing = [str(path) for path in paths if str(path) not in records]
    if missing:
        raise ValueError(f"OCR did not return records for: {missing}")
    return records


def build_teaching_screenshot_index(records: list[dict], teaching: list[dict]) -> dict:
    by_knowledge = {item["knowledge_id"]: item["id"] for item in records}
    flows = []
    for item in teaching:
        screenshot_ids = [
            by_knowledge[knowledge_id]
            for knowledge_id in item.get("knowledge_points", [])
            if knowledge_id in by_knowledge
        ]
        flows.append(
            {
                "id": item["id"],
                "title": item["title"],
                "knowledge_points": item.get("knowledge_points", []),
                "screenshot_ids": screenshot_ids,
                "teaching_path": item.get("path", ""),
            }
        )
    return {
        "schema_version": "1.0.0",
        "content_version": "1.6.0",
        "count": len(flows),
        "teaching_flows": flows,
    }


def build_gallery(records: list[dict]) -> str:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in records:
        category = item["knowledge_id"].split("-")[1]
        grouped[category].append(item)
    lines = [
        "# 老洪 56 個知識點截圖畫廊",
        "",
        "每張圖片由對應知識點的 4K 課堂影片時間範圍抽取。OCR 是本機機器辨識結果，可能存在錯字；知識解釋以知識點文件及清理逐字稿為準。",
        "",
    ]
    for category in CATEGORY_NAMES:
        items = grouped.get(category, [])
        if not items:
            continue
        lines.extend([f"## {CATEGORY_NAMES[category]}", ""])
        for item in items:
            image_name = Path(item["path"]).name
            lines.extend(
                [
                    f"### {item['knowledge_id']}｜{item['title']}",
                    "",
                    f"![{item['knowledge_id']}](images/{image_name})",
                    "",
                    f"- Video：`{item['video_id']}`",
                    f"- Time：`{item['timestamp']}`",
                    f"- 說明：{item['description']}",
                    f"- OCR：{item['ocr_text'] if item['ocr_text'] else '未辨識到可靠文字'}",
                    "",
                ]
            )
    return "\n".join(lines)


def load_json(path: Path, key: str) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get(key)
    if not isinstance(items, list):
        raise ValueError(f"{path} key {key} must be a list")
    return items


def build_records(root: Path, source_dir: Path, resume: bool = False) -> list[dict]:
    old_hong = root / "day-2" / "old-hong"
    points = load_json(old_hong / "knowledge-points" / "knowledge-index.json", "knowledge_points")
    sources = discover_sources(source_dir, {item["video_id"] for item in points})
    image_dir = old_hong / "screenshots" / "images"
    image_paths: list[Path] = []
    draft_records: list[dict] = []
    for point in points:
        timestamp_seconds = choose_timestamp(point["start"], point["end"])
        filename = build_filename(point["id"], point["video_id"], timestamp_seconds)
        output = image_dir / filename
        if output.exists() and not resume:
            raise FileExistsError(f"refusing to overwrite screenshot: {output}")
        if not output.exists():
            extract_frame(sources[point["video_id"]], timestamp_seconds, output)
        image_paths.append(output)
        draft_records.append(
            {
                "id": point["id"].replace("LH-", "LH-SC-", 1),
                "knowledge_id": point["id"],
                "title": point["title"],
                "description": point["summary"],
                "video_id": point["video_id"],
                "timestamp": seconds_to_timestamp(timestamp_seconds),
                "evidence_start": point["start"],
                "evidence_end": point["end"],
                "path": output.relative_to(root).as_posix(),
                "knowledge_path": point["path"],
            }
        )
    helper = root / "scripts" / "ocr_macos_vision.swift"
    ocr = run_ocr(image_paths, helper)
    records = []
    for item, image_path in zip(draft_records, image_paths):
        width, height = probe_image(image_path)
        ocr_item = ocr[str(image_path)]
        records.append(
            {
                **item,
                "width": width,
                "height": height,
                "size_bytes": image_path.stat().st_size,
                "sha256": sha256(image_path),
                "ocr_status": ocr_item["status"],
                "ocr_languages": ocr_item.get("languages", []),
                "ocr_text": ocr_item.get("text", ""),
            }
        )
    return records


def write_json(path: Path, data: dict) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite index: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    screenshot_base = root / "day-2" / "old-hong" / "screenshots"
    records = build_records(root, args.source_dir.resolve(), resume=args.resume)
    screenshot_index = {
        "schema_version": "1.0.0",
        "content_version": "1.6.0",
        "count": len(records),
        "screenshots": records,
    }
    teaching = load_json(
        root / "day-2" / "old-hong" / "teaching-flows" / "teaching-index.json",
        "teaching_flows",
    )
    teaching_index = build_teaching_screenshot_index(records, teaching)
    write_json(screenshot_base / "screenshot-index.json", screenshot_index)
    write_json(screenshot_base / "teaching-screenshot-index.json", teaching_index)
    gallery_path = screenshot_base / "GALLERY.md"
    if gallery_path.exists():
        raise FileExistsError(f"refusing to overwrite gallery: {gallery_path}")
    gallery_path.write_text(build_gallery(records), encoding="utf-8")
    print(f"Old Hong screenshots written: {len(records)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
