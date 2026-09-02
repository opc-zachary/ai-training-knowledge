#!/usr/bin/env python3
"""Build machine-readable indexes for the Old Hong learning package."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "day-2" / "old-hong"
POINT_HEADING = re.compile(r"^### (LH-[A-Z]+-\d{3})｜(.+)$", re.MULTILINE)
FIELD_LINE = re.compile(r"^- ([^：]+)：(.+)$", re.MULTILINE)
EVIDENCE = re.compile(
    r"^(DJI_\d{14}_\d{4}_D)\|(\d{2}:\d{2}:\d{2})-(\d{2}:\d{2}:\d{2})\|([A-Za-z_]+)$"
)
REQUIRED_POINT_FIELDS = {
    "一句話",
    "課堂原意",
    "整理與應用",
    "使用時機",
    "不適用",
    "下一步",
    "關聯流程",
    "Evidence",
}


def relative_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def hms_to_seconds(value: str) -> int:
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return hours * 3600 + minutes * 60 + seconds


def video_durations(root: Path) -> dict[str, float]:
    durations: dict[str, float] = {}
    transcript_root = root / "day-2" / "transcripts" / "zh-Hant" / "morning"
    for path in transcript_root.glob("*/transcript.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        durations[data["video_id"]] = float(data["audio_duration"])
    return durations


def parse_knowledge_points(path: Path, root: Path = ROOT) -> list[dict]:
    """Return normalized knowledge points from one Traditional Markdown file."""
    text = path.read_text(encoding="utf-8")
    matches = list(POINT_HEADING.finditer(text))
    points: list[dict] = []
    durations = video_durations(root)
    for index, match in enumerate(matches):
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end():body_end]
        fields = {key.strip(): value.strip().strip("`") for key, value in FIELD_LINE.findall(body)}
        missing = REQUIRED_POINT_FIELDS - set(fields)
        if missing:
            raise ValueError(f"{match.group(1)} missing fields: {sorted(missing)}")
        evidence_match = EVIDENCE.fullmatch(fields["Evidence"])
        if not evidence_match:
            raise ValueError(f"{match.group(1)} malformed Evidence")
        video_id, start, end, status = evidence_match.groups()
        if hms_to_seconds(start) >= hms_to_seconds(end):
            raise ValueError(f"{match.group(1)} evidence range is not increasing")
        if video_id in durations and hms_to_seconds(end) > durations[video_id] + 1:
            raise ValueError(f"{match.group(1)} evidence exceeds video duration")
        workflows = re.findall(r"LH-WF-\d{2}", fields["關聯流程"])
        points.append(
            {
                "id": match.group(1),
                "title": match.group(2).strip(),
                "summary": fields["一句話"],
                "classroom_meaning": fields["課堂原意"],
                "application": fields["整理與應用"],
                "when_to_use": fields["使用時機"],
                "not_for": fields["不適用"],
                "next_action": fields["下一步"],
                "workflows": workflows,
                "video_id": video_id,
                "start": start,
                "end": end,
                "status": status,
                "path": relative_path(path, root),
            }
        )
    return points


def parse_frontmatter(path: Path) -> tuple[dict[str, str], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"missing frontmatter: {path}")
    raw, body = text[4:].split("\n---\n", 1)
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            raise ValueError(f"malformed frontmatter line in {path}: {line}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields, body


def parse_workflows(path: Path, root: Path, knowledge_ids: set[str]) -> list[dict]:
    """Parse one workflow and validate its knowledge references and structure."""
    fields, body = parse_frontmatter(path)
    required = {"id", "title", "knowledge_points", "evidence"}
    missing = required - set(fields)
    if missing:
        raise ValueError(f"workflow missing fields: {sorted(missing)}")
    point_ids = [item.strip() for item in fields["knowledge_points"].split(",") if item.strip()]
    unknown = set(point_ids) - knowledge_ids
    if unknown:
        raise ValueError(f"{fields['id']} unknown knowledge IDs: {sorted(unknown)}")
    if "```mermaid" not in body:
        raise ValueError(f"{fields['id']} missing Mermaid flow")
    if len(re.findall(r"^\d+\. ", body, flags=re.MULTILINE)) < 4:
        raise ValueError(f"{fields['id']} must contain at least four numbered steps")
    if "## 產出物" not in body or "## 驗收標準" not in body:
        raise ValueError(f"{fields['id']} missing output or acceptance section")
    return [
        {
            "id": fields["id"],
            "title": fields["title"],
            "knowledge_points": point_ids,
            "evidence": fields["evidence"],
            "path": relative_path(path, root),
        }
    ]


def parse_teaching_flow(path: Path, root: Path, knowledge_ids: set[str], workflow_ids: set[str]) -> dict:
    fields, body = parse_frontmatter(path)
    required = {"id", "title", "knowledge_points", "workflows", "evidence"}
    missing = required - set(fields)
    if missing:
        raise ValueError(f"teaching flow missing fields: {sorted(missing)}")
    points = [item.strip() for item in fields["knowledge_points"].split(",") if item.strip()]
    workflows = [item.strip() for item in fields["workflows"].split(",") if item.strip()]
    if set(points) - knowledge_ids:
        raise ValueError(f"{fields['id']} contains unknown knowledge IDs")
    if set(workflows) - workflow_ids:
        raise ValueError(f"{fields['id']} contains unknown workflow IDs")
    for heading in ("## 分鐘級流程", "## 學員練習", "## 評分量規"):
        if heading not in body:
            raise ValueError(f"{fields['id']} missing {heading}")
    return {
        "id": fields["id"],
        "title": fields["title"],
        "knowledge_points": points,
        "workflows": workflows,
        "evidence": fields["evidence"],
        "path": relative_path(path, root),
    }


def ensure_unique(items: list[dict], label: str) -> None:
    counts = Counter(item["id"] for item in items)
    duplicates = sorted(item for item, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate {label} IDs: {duplicates}")


def build_indexes(root: Path = ROOT) -> tuple[dict, dict, dict]:
    """Build knowledge, workflow and teaching indexes from Traditional Markdown."""
    base = root / "day-2" / "old-hong"
    points = [
        item
        for path in sorted((base / "knowledge-points" / "zh-Hant").glob("*.md"))
        for item in parse_knowledge_points(path, root)
    ]
    ensure_unique(points, "knowledge")
    knowledge_ids = {item["id"] for item in points}
    workflows = [
        item
        for path in sorted((base / "workflows" / "zh-Hant").glob("*.md"))
        for item in parse_workflows(path, root, knowledge_ids)
    ]
    ensure_unique(workflows, "workflow")
    workflow_ids = {item["id"] for item in workflows}
    teaching = [
        parse_teaching_flow(path, root, knowledge_ids, workflow_ids)
        for path in sorted((base / "teaching-flows" / "zh-Hant").glob("*.md"))
    ]
    ensure_unique(teaching, "teaching")
    return (
        {"schema_version": "1.0.0", "content_version": "1.5.0", "count": len(points), "knowledge_points": points},
        {"schema_version": "1.0.0", "content_version": "1.5.0", "count": len(workflows), "workflows": workflows},
        {"schema_version": "1.0.0", "content_version": "1.5.0", "count": len(teaching), "teaching_flows": teaching},
    )


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outputs(root: Path = ROOT) -> tuple[int, int, int]:
    knowledge, workflows, teaching = build_indexes(root)
    base = root / "day-2" / "old-hong"
    write_json(base / "knowledge-points" / "knowledge-index.json", knowledge)
    write_json(base / "workflows" / "workflow-index.json", workflows)
    write_json(base / "teaching-flows" / "teaching-index.json", teaching)
    evidence = {
        "schema_version": "1.0.0",
        "content_version": "1.5.0",
        "count": knowledge["count"],
        "evidence": [
            {
                "knowledge_id": item["id"],
                "video_id": item["video_id"],
                "start": item["start"],
                "end": item["end"],
                "status": item["status"],
                "knowledge_path": item["path"],
                "timestamped_transcript": (
                    "day-2/transcripts/zh-Hant/morning/"
                    f"{item['video_id']}/timestamped.txt"
                ),
            }
            for item in knowledge["knowledge_points"]
        ],
    }
    write_json(base / "evidence" / "evidence-map.json", evidence)
    by_video = Counter(item["video_id"] for item in knowledge["knowledge_points"])
    report = [
        "# 老洪知識證據覆蓋報告",
        "",
        "狀態：Generated Review",
        "",
        f"知識點總數：{knowledge['count']}",
        "",
        "## 影片覆蓋",
        "",
        "| Video ID | 知識點 | 證據狀態 |",
        "|---|---:|---|",
    ]
    for video_id, count in sorted(by_video.items()):
        report.append(f"| `{video_id}` | {count} | Cleaned Review |")
    report.extend(
        [
            "",
            "## 邊界",
            "",
            "- 每個知識點均連接清理逐字稿時間碼。",
            "- 整理後解釋及延伸應用不是逐字引用。",
            "- 課堂未形成獨立方法的寒暄、設備操作及重複語句不抽成知識點。",
            "- 工具、公司及市場敘述保留課堂日期語境，當前使用時應重新核實。",
            "",
        ]
    )
    coverage = base / "evidence" / "coverage-report.md"
    coverage.parent.mkdir(parents=True, exist_ok=True)
    coverage.write_text("\n".join(report), encoding="utf-8")
    return knowledge["count"], workflows["count"], teaching["count"]


def main() -> int:
    knowledge_count, workflow_count, teaching_count = write_outputs()
    print(
        f"Old Hong indexes written: knowledge={knowledge_count}, "
        f"workflows={workflow_count}, teaching={teaching_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
