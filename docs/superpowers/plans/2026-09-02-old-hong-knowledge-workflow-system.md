# Old Hong Knowledge Workflow System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a bilingual, evidence-linked Old Hong learning and operating system containing 50–70 knowledge points, at least 12 workflows, five teaching flows, eight templates and four role-based learning paths.

**Architecture:** Traditional Chinese Markdown is the editorial source. A small Python index builder extracts stable IDs and evidence references into JSON, while local ICU conversion produces path-matched Simplified Chinese files. The existing repository validator enforces counts, links, JSON integrity, source boundaries and GitHub publication readiness.

**Tech Stack:** Markdown, JSON, Python 3 standard library, ICU `uconv`, Git and GitHub CLI.

## Global Constraints

- Use only the four Old Hong cleaned transcripts, timestamped transcripts, QA files, existing guides and linked keyframes as evidence.
- Every knowledge point must include a stable ID, Video ID and timestamp range.
- Separate classroom meaning, editorial interpretation and practical extension.
- Traditional Chinese is the editorial source; technical filenames, folders and JSON keys remain English.
- Do not publish original or compressed video, original PDF/ZIP, Raw Whisper hallucination text, credentials or local absolute paths.
- GitHub completion requires a Public repository, matching local/remote commit and raw public readback.
- Do not create a frontend, database or login system.

---

### Task 1: Add the Old Hong package contract and failing tests

**Files:**
- Modify: `tests/test_repository.py`
- Modify: `scripts/validate_repository.py`

**Interfaces:**
- Consumes: future `day-2/old-hong/` directory.
- Produces: `validate_old_hong_package(root: Path) -> list[str]` and a focused unit test.

- [ ] **Step 1: Write the failing repository test**

Add:

```python
def test_old_hong_package(self):
    self.assertEqual(self.validator.validate_old_hong_package(ROOT), [])
```

- [ ] **Step 2: Run the focused test and verify failure**

Run:

```bash
python3 -m unittest tests.test_repository.RepositoryTests.test_old_hong_package -v
```

Expected: failure because `validate_old_hong_package` or the package does not yet exist.

- [ ] **Step 3: Add the validation contract**

Implement a validator that requires:

```python
OLD_HONG_REQUIRED_COUNTS = {
    "knowledge_points": (50, 70),
    "workflows": 12,
    "teaching_flows": 5,
    "templates": 8,
    "learning_paths": 4,
}
```

The function must parse all three JSON indexes, confirm ID uniqueness, resolve referenced Markdown paths, validate evidence-map targets, compare Traditional/Simplified relative paths and reject local absolute paths or prohibited source extensions.

- [ ] **Step 4: Re-run the focused test**

Expected: failure listing missing Old Hong files and counts, proving the gate is active.

- [ ] **Step 5: Commit the test contract**

```bash
git add tests/test_repository.py scripts/validate_repository.py
git commit -m "test: define Old Hong knowledge package contract"
```

---

### Task 2: Author 56 evidence-linked knowledge points

**Files:**
- Create: `day-2/old-hong/knowledge-points/zh-Hant/prompt-engineering.md`
- Create: `day-2/old-hong/knowledge-points/zh-Hant/context-debugging.md`
- Create: `day-2/old-hong/knowledge-points/zh-Hant/skill-design.md`
- Create: `day-2/old-hong/knowledge-points/zh-Hant/ai-workbench.md`
- Create: `day-2/old-hong/knowledge-points/zh-Hant/enterprise-automation.md`
- Create: `day-2/old-hong/knowledge-points/zh-Hant/fde-delivery.md`
- Create: `day-2/old-hong/knowledge-points/zh-Hant/qa-improvement.md`
- Create: `scripts/build_old_hong_indexes.py`
- Create: `day-2/old-hong/knowledge-points/knowledge-index.json`
- Create: `day-2/old-hong/evidence/evidence-map.json`
- Create: `day-2/old-hong/evidence/coverage-report.md`

**Interfaces:**
- Consumes: four `day-2/transcripts/zh-Hant/morning/*/transcript.json` files and knowledge Markdown sections.
- Produces: 56 knowledge records with IDs `LH-PE-*`, `LH-CTX-*`, `LH-SKL-*`, `LH-WB-*`, `LH-AUTO-*`, `LH-FDE-*` and `LH-QA-*`.

- [ ] **Step 1: Define the Markdown evidence syntax**

Each point uses:

```markdown
### LH-PE-001｜好 Prompt 是跑出來的

- 一句話：提示詞需要經過執行、觀察及修訂，而不是一次寫定。
- 課堂原意：老洪將好提示詞描述為由實際結果反覆打磨而來。
- 整理與應用：先保留問題定義，再改變方法或約束，避免每輪全部重寫。
- 使用時機：需要重複交付同類任務時。
- 不適用：一次性低風險問答。
- 下一步：完成一輪隔離測試並記錄差距。
- 關聯流程：`LH-WF-01`、`LH-WF-03`
- Evidence：`DJI_20260830102734_0001_D|00:08:00-00:10:00|Cleaned_Review`
```

- [ ] **Step 2: Author eight points per category**

Create exactly 56 points across the seven files. Every point must contain all eight fields above and use a timestamp inside its source video duration.

- [ ] **Step 3: Build the JSON indexer**

Implement:

```python
def parse_knowledge_points(path: Path) -> list[dict]:
    """Return id, title, summary, workflows, video_id, start, end, status and path."""

def build_indexes(root: Path) -> tuple[dict, dict]:
    """Build knowledge-index.json and evidence-map.json from authored Markdown."""
```

The script must reject duplicate IDs, missing fields, malformed evidence and timestamps beyond the corresponding transcript `audio_duration`.

- [ ] **Step 4: Generate indexes and coverage report**

Run:

```bash
python3 scripts/build_old_hong_indexes.py
python3 -m json.tool day-2/old-hong/knowledge-points/knowledge-index.json >/dev/null
python3 -m json.tool day-2/old-hong/evidence/evidence-map.json >/dev/null
```

Expected: `56 knowledge points`, `56 evidence mappings`, and coverage of all four Old Hong videos.

- [ ] **Step 5: Commit the knowledge layer**

```bash
git add day-2/old-hong/knowledge-points day-2/old-hong/evidence scripts/build_old_hong_indexes.py
git commit -m "docs: add Old Hong evidence-linked knowledge points"
```

---

### Task 3: Build 12 executable work flows

**Files:**
- Create: `day-2/old-hong/workflows/zh-Hant/01-industry-research-prompt.md`
- Create: `day-2/old-hong/workflows/zh-Hant/02-isolated-prompt-test.md`
- Create: `day-2/old-hong/workflows/zh-Hant/03-prompt-review-versioning.md`
- Create: `day-2/old-hong/workflows/zh-Hant/04-context-overload-recovery.md`
- Create: `day-2/old-hong/workflows/zh-Hant/05-four-layer-prompt-debugging.md`
- Create: `day-2/old-hong/workflows/zh-Hant/06-skill-discovery-assessment.md`
- Create: `day-2/old-hong/workflows/zh-Hant/07-validated-work-to-skill.md`
- Create: `day-2/old-hong/workflows/zh-Hant/08-skill-top-level-design.md`
- Create: `day-2/old-hong/workflows/zh-Hant/09-ai-workbench-mvp.md`
- Create: `day-2/old-hong/workflows/zh-Hant/10-data-feedback-review.md`
- Create: `day-2/old-hong/workflows/zh-Hant/11-automation-option-selection.md`
- Create: `day-2/old-hong/workflows/zh-Hant/12-fde-pilot-delivery.md`
- Create: `day-2/old-hong/workflows/workflow-index.json`

**Interfaces:**
- Consumes: stable knowledge-point IDs.
- Produces: workflow IDs `LH-WF-01` through `LH-WF-12` with knowledge and evidence references.

- [ ] **Step 1: Author all workflow files**

Each file must include YAML frontmatter with `id`, `title`, `knowledge_points` and `evidence`, then sections for purpose, inputs, roles, pre-check, Mermaid flow, numbered procedure, decision branches, outputs, acceptance criteria and failure recovery.

- [ ] **Step 2: Extend the index builder**

Add:

```python
def parse_workflows(path: Path) -> list[dict]:
    """Return workflow metadata and validate referenced knowledge IDs."""
```

Write `workflow-index.json` with 12 ordered records.

- [ ] **Step 3: Validate flow integrity**

Run the builder and assert that every workflow has at least four numbered steps, one Mermaid block, one output and one acceptance criterion.

- [ ] **Step 4: Commit the workflow layer**

```bash
git add day-2/old-hong/workflows scripts/build_old_hong_indexes.py
git commit -m "docs: add Old Hong executable workflows"
```

---

### Task 4: Build teaching flows, templates and role paths

**Files:**
- Create: five files under `day-2/old-hong/teaching-flows/zh-Hant/`
- Create: `day-2/old-hong/teaching-flows/teaching-index.json`
- Create: eight files under `day-2/old-hong/templates/zh-Hant/`
- Create: four files under `day-2/old-hong/learning-paths/zh-Hant/`

**Interfaces:**
- Consumes: knowledge IDs and workflow IDs.
- Produces: teaching IDs `LH-TF-01`–`LH-TF-05`, eight reusable forms and four role curricula.

- [ ] **Step 1: Author four 60–90 minute teaching modules**

Each module must contain audience, prerequisites, learning outcomes, minute-level agenda, instructor prompts, demonstration, learner exercise, checking questions, homework, rubric and evidence references.

- [ ] **Step 2: Author the one-day combined course**

Create `05-one-day-individual-to-enterprise.md` with a 360-minute agenda, breaks, four module transitions, capstone exercise and final acceptance rubric.

- [ ] **Step 3: Author eight copy-ready templates**

Create forms for industry research prompt design, isolated testing, prompt debugging, Skill assessment, Skill specification, workbench MVP, monthly data review and FDE pilot handover. Each must have instructions, fillable tables and completion criteria.

- [ ] **Step 4: Author four role learning paths**

Create paths for manager, content/marketing operator, AI consultant/solution designer and FDE. Each path lists order, required points, workflows, exercises and completion evidence.

- [ ] **Step 5: Extend indexes and validate references**

Build `teaching-index.json`; confirm all teaching and role-path references resolve to existing knowledge/workflow IDs.

- [ ] **Step 6: Commit the teaching system**

```bash
git add day-2/old-hong/teaching-flows day-2/old-hong/templates day-2/old-hong/learning-paths scripts/build_old_hong_indexes.py
git commit -m "docs: add Old Hong teaching system and templates"
```

---

### Task 5: Add Simplified Chinese, navigation and repository integration

**Files:**
- Create: path-matched files under each `zh-Hans/` directory.
- Create: `day-2/old-hong/README.md`
- Create: `day-2/old-hong/TEAM_AND_AGENT_GUIDE.md`
- Modify: `day-2/README.md`
- Modify: `day-2/TEAM_CALLING_GUIDE.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `locales/zh-Hant/README.md`
- Modify: `locales/zh-Hans/README.md`
- Modify: `skills/ai-training-guangzhou/SKILL.md`
- Modify: `skills/ai-training-guangzhou/references/day-2.md`
- Modify: `data/course-crosswalk.v1.json`
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: complete Traditional content.
- Produces: bilingual public navigation and machine-readable resource routes at content version `1.5.0`.

- [ ] **Step 1: Convert all editorial files**

For every `zh-Hant/*.md`, run local ICU Traditional-to-Simplified conversion into the matching `zh-Hans/` path. Preserve filenames, IDs, links, code fences, Video IDs and timestamps.

- [ ] **Step 2: Sample-check conversion**

Check at least one file from knowledge points, workflows, teaching flows, templates and learning paths. Confirm no code fence count or internal link difference.

- [ ] **Step 3: Write the Old Hong entry pages**

`README.md` must route human readers by goal. `TEAM_AND_AGENT_GUIDE.md` must provide exact raw GitHub URLs, JSON routing examples and citation rules.

- [ ] **Step 4: Integrate existing repository navigation**

Add the Old Hong system to all listed entry points, set `content_version` to `1.5.0`, and expose paths for all three indexes and the evidence map.

- [ ] **Step 5: Commit repository integration**

```bash
git add day-2 README.md README.en.md locales skills data/course-crosswalk.v1.json CHANGELOG.md
git commit -m "docs: integrate bilingual Old Hong learning system"
```

---

### Task 6: Complete verification, manifest and GitHub publication

**Files:**
- Modify: `data/manifest.json`
- Modify: `scripts/validate_repository.py`
- Modify: `tests/test_repository.py`

**Interfaces:**
- Consumes: complete Old Hong package.
- Produces: validated GitHub `main` publication and independent public readback.

- [ ] **Step 1: Run all local gates**

```bash
python3 scripts/build_old_hong_indexes.py
python3 scripts/validate_repository.py --write-manifest
python3 scripts/validate_repository.py
python3 -m unittest tests/test_repository.py -v
git diff --check
```

Expected: index counts `56/12/5`, repository validation passed, all tests passed and no whitespace errors.

- [ ] **Step 2: Review publication scope**

Search `day-2/old-hong/` for `/Users/`, `/Volumes/`, source archive names, credential prefixes and prohibited media extensions. Expected: no findings.

- [ ] **Step 3: Commit final generated state**

```bash
git add data/manifest.json scripts/validate_repository.py tests/test_repository.py day-2/old-hong
git commit -m "test: verify Old Hong public knowledge package"
```

- [ ] **Step 4: Push the Public repository**

```bash
git push origin main
```

- [ ] **Step 5: Verify GitHub destination**

Confirm through GitHub that visibility is `PUBLIC`, default branch is `main`, and local/remote commit hashes match.

- [ ] **Step 6: Perform raw public readback**

Require HTTP 200 and valid content for:

```text
day-2/old-hong/README.md
day-2/old-hong/knowledge-points/knowledge-index.json
day-2/old-hong/workflows/workflow-index.json
day-2/old-hong/teaching-flows/teaching-index.json
day-2/old-hong/evidence/evidence-map.json
day-2/old-hong/templates/zh-Hant/01-industry-research-prompt-design.md
```

- [ ] **Step 7: Report the exact delivered boundary**

Report counts, commit, public links, tests and the excluded original-media boundary. Do not treat push output alone as completion.
