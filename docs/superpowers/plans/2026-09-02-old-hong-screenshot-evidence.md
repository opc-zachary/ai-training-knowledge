# Old Hong Screenshot Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish 56 locally extracted, OCR-indexed Old Hong screenshots so every `LH-*` knowledge point has one directly viewable visual evidence item.

**Architecture:** A Python builder reads the existing knowledge and teaching indexes, extracts one 1920px JPEG from each knowledge-point evidence range with local ffmpeg, calls a local macOS Vision OCR helper, and generates two JSON indexes plus a Markdown gallery. The repository validator verifies one-to-one ID coverage, image dimensions, hashes, links and public source boundaries.

**Tech Stack:** Python 3 standard library, ffmpeg/ffprobe, Swift with macOS Vision, Markdown, JSON, Git and GitHub CLI.

## Global Constraints

- Read the four Case 3TB Old Hong 4K originals without changing, moving, renaming or overwriting them.
- Create exactly 56 JPEG screenshots, one per knowledge point, at width 1920px and under 1 MB each.
- Do not add overlays or change visible image content.
- Use local macOS Vision OCR only; no cloud transcription or OCR.
- Keep OCR text, editorial description and transcript evidence in separate fields.
- Do not commit local absolute paths, source filenames, credentials, original video or compressed video.
- GitHub completion requires Public raw readback and matching local/remote commit.

---

### Task 1: Add screenshot validation tests

**Files:**
- Modify: `tests/test_repository.py`
- Modify: `scripts/validate_repository.py`

**Interfaces:**
- Consumes: future screenshot indexes and image directory.
- Produces: `validate_old_hong_screenshots(root: Path) -> list[str]`.

- [ ] **Step 1: Write the failing test**

```python
def test_old_hong_screenshots(self):
    self.assertEqual(self.validator.validate_old_hong_screenshots(ROOT), [])
```

- [ ] **Step 2: Run the focused test**

Run `python3 -m unittest tests.test_repository.RepositoryTests.test_old_hong_screenshots -v`.

Expected: fail because the validator or package does not exist.

- [ ] **Step 3: Implement the validation gate**

Require `README.md`, `GALLERY.md`, `screenshot-index.json`, `teaching-screenshot-index.json` and 56 JPEG files. Parse each index, confirm 56 unique screenshot and knowledge IDs, compare against `knowledge-index.json`, decode dimensions with ffprobe, verify width 1920, size below 1 MB and SHA-256, and resolve all teaching references.

- [ ] **Step 4: Re-run the focused test**

Expected: assertion failure listing missing screenshot artifacts, proving the gate is active.

---

### Task 2: Build local extraction and OCR tools

**Files:**
- Create: `scripts/build_old_hong_screenshots.py`
- Create: `scripts/ocr_macos_vision.swift`
- Create: `tests/test_old_hong_screenshots.py`

**Interfaces:**
- Consumes: `knowledge-index.json`, `teaching-index.json` and `--source-dir` containing four videos whose filenames contain the four Video IDs.
- Produces: images, screenshot records, teaching relations and gallery data.

- [ ] **Step 1: Write failing unit tests**

Test `hms_to_seconds`, midpoint selection, collision-safe filename generation, source discovery, index record validation and gallery generation. Run the test file and confirm missing builder failure.

- [ ] **Step 2: Implement the Python builder**

Provide:

```python
def hms_to_seconds(value: str) -> float: ...
def choose_timestamp(start: str, end: str) -> float: ...
def discover_sources(source_dir: Path, video_ids: set[str]) -> dict[str, Path]: ...
def build_filename(knowledge_id: str, video_id: str, seconds: float) -> str: ...
def extract_frame(source: Path, seconds: float, output: Path) -> None: ...
def probe_image(path: Path) -> tuple[int, int]: ...
def build_records(root: Path, source_dir: Path) -> list[dict]: ...
def build_gallery(records: list[dict]) -> str: ...
```

Use ffmpeg `-n`, input seeking, one frame, `scale=1920:-2` and JPEG quality 3. Refuse to overwrite an existing file unless running verification only.

- [ ] **Step 3: Implement local Vision OCR**

The Swift helper accepts image paths, uses `VNRecognizeTextRequest` at accurate level with supported Chinese and English languages, and returns one JSON line per image containing `path`, `status`, `languages` and `text`.

- [ ] **Step 4: Run unit and OCR smoke tests**

Use one existing keyframe for the OCR smoke test. Require valid JSON output and no network dependency.

---

### Task 3: Extract, inspect and index 56 screenshots

**Files:**
- Create: `day-2/old-hong/screenshots/images/*.jpg`
- Create: `day-2/old-hong/screenshots/screenshot-index.json`
- Create: `day-2/old-hong/screenshots/teaching-screenshot-index.json`
- Create: `day-2/old-hong/screenshots/GALLERY.md`
- Create: `day-2/old-hong/screenshots/README.md`

**Interfaces:**
- Consumes: Task 2 builder and four 4K source videos.
- Produces: 56 evidence images and complete human/machine indexes.

- [ ] **Step 1: Run extraction**

Run the builder with the exact Case 3TB original-video directory passed only as a command argument. Do not write that path into outputs.

- [ ] **Step 2: Run local OCR**

Process all 56 images and merge results into `screenshot-index.json`. Empty OCR is allowed only with explicit `no_text_detected` status.

- [ ] **Step 3: Generate teaching index and gallery**

Map every teaching flow knowledge ID to its screenshot ID. Group `GALLERY.md` by the seven knowledge prefixes and embed repository-relative images.

- [ ] **Step 4: Inspect visual contact sheets**

Create temporary contact sheets outside the repository and visually inspect all 56 thumbnails. Re-extract only frames that are black, transition-blurred or unreadable, using a timestamp inside the original evidence range.

- [ ] **Step 5: Verify image data**

Require 56 images, four Video IDs covered, width 1920, all hashes and dimensions matching, and OCR statuses present.

---

### Task 4: Integrate, publish and read back

**Files:**
- Modify: `day-2/old-hong/README.md`
- Modify: `day-2/old-hong/TEAM_AND_AGENT_GUIDE.md`
- Modify: `day-2/README.md`
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `data/course-crosswalk.v1.json`
- Modify: `skills/ai-training-guangzhou/SKILL.md`
- Modify: `skills/ai-training-guangzhou/references/day-2.md`
- Modify: `CHANGELOG.md`
- Modify: `data/manifest.json`

**Interfaces:**
- Consumes: verified screenshot package.
- Produces: public content version `1.6.0` and GitHub raw access.

- [ ] **Step 1: Add all navigation routes**

Expose the Gallery, screenshot JSON and teaching screenshot JSON from human and Agent entry points. Update the crosswalk with counts and paths.

- [ ] **Step 2: Run complete verification**

```bash
python3 scripts/validate_repository.py --write-manifest
python3 scripts/validate_repository.py
python3 -m unittest tests/test_repository.py tests/test_old_hong_indexes.py tests/test_old_hong_screenshots.py -v
git diff --check
```

- [ ] **Step 3: Commit and push**

Commit the screenshot package, generator, tests, manifest and navigation updates, then push `main` to `origin`.

- [ ] **Step 4: Public readback**

Verify GitHub visibility is `PUBLIC`, local and remote commits match, remote screenshot count is 56, all four JSON/Markdown entry points return HTTP 200, one JPEG returns HTTP 200 and the remote index hashes match the downloaded image.
