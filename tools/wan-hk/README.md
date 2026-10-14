# TaiwanChicken Shot04 — GitHub Actions executor package

Status: executor prepared for review. Publishing this code does not submit a
video task. A real API connection remains unverified until an authorized run
returns a task and a validated MP4.

This package is deliberately restricted to TaiwanChicken Shot04: one 8-second,
480P, 9:16 `wan3.0-video` first-frame generation in Alibaba Cloud Model Studio's
China (Hong Kong) region / Global deployment scope.

## Repository files

Repository: `opc-zachary/ai-training-knowledge`.

- `.github/workflows/wan-hk-shot04.yml`: manual workflow entry.
- `tools/wan-hk/runner.py`: fixed-shot API executor.
- `tools/wan-hk/request-shot04.json`: pinned request and first-frame hash.

Original source images stay in the local project media library. They are not
committed to the repository.

## Required GitHub binding

Create exactly these repository-level values through GitHub's normal encrypted
Secrets and Actions Variables controls:

- Secret `ALIYUN_MODEL_STUDIO_HK_API_KEY`: the Hong Kong Model Studio API key.
  The workflow injects it into the runner process environment. It is never passed
  on the command line, printed, included in an artifact, or written to JSON.
- Variable `ALIYUN_MODEL_STUDIO_HK_API_HOST`:
  `ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com`

The model, API host, workspace, and API key must all belong to the same Hong Kong
region. A binding check proves only that the values are present and locally
well-formed; it deliberately makes no network request and cannot prove account
permission, billing readiness, or model entitlement.

## Manual modes

The workflow has only `workflow_dispatch`. It has no push, pull-request,
schedule, or automatic retry trigger. Concurrency serializes all Shot04 runs and
does not cancel an in-progress paid task.

1. `check-binding` is the default. It validates the fixed local request and the
   presence/shape of the secret and host, writes a non-sensitive receipt, and
   makes no API request.
2. `generate` requires the literal confirmation `GENERATE04` and either a public HTTPS
   `first_frame_url` or the pinned 480P JPEG as `first_frame_base64`. The runner downloads that PNG into memory, rejects private
   hosts and redirects, and verifies this exact SHA-256 before any POST:
   `d0f0e907f6cc782cbd8818fda6295a16bbc6701df1160cf437e0b3184ffdc94e`.
   The JPEG transport has SHA-256
   `4027f106362e523db098403ea2f08d226768c1ccf14a3cfe9ebc1849a6228247`.
   It is a 480x854, 46,166-byte derivative of the original PNG, sent only as a
   transient workflow input. The runner reads it from the GitHub event file; it
   does not echo the image or bind it to a logged step environment variable.
   Total dispatch inputs must remain below GitHub's 65,535-character limit.
   The verified bytes are submitted as a Base64 data URI, so the source image is
   never committed or uploaded as an Actions artifact. A GitHub rerun where
   `github.run_attempt` is greater than 1 is refused for generation.
3. `resume` requires an existing UUID `resume_task_id`. It issues GET queries for
   that task only and never sends the generation POST.
4. `validate-existing` requires a digits-only `source_run_id` from this
   repository. It downloads the attempt-1 artifact from that prior GitHub run
   using the workflow's automatic `github.token`, then repeats the existing
   decode validation and uploads a new short-lived artifact. It does not load
   the Alibaba Cloud binding, submit a generation POST, or query a provider task.

The runner records `task_id`, safe task state, pinned image SHA, safe numeric
usage, and downloaded MP4 SHA in `output/shot04-receipt.json`. It never stores the
result's signed URL or the raw provider response. HTTP failures retain only the
HTTP status and a restricted provider error code. Server errors are treated as
an uncertain POST outcome rather than proof that no task was created. If a POST has an uncertain
outcome, the receipt says `POST_OUTCOME_UNKNOWN_DO_NOT_RETRY`; reconcile the task
in the Alibaba Cloud account before any later generation dispatch.

Before any operation that could call the provider, the workflow checks for
`ffprobe` and `ffmpeg` on the ephemeral Ubuntu runner. If either is absent, it
installs Ubuntu's `ffmpeg` package and then asserts that both commands exist.
The Python runner also reports a specific safe error if either command is still
missing, before a generation or resume API call can begin.

After a successful download, the workflow uses `ffprobe` to require one portrait
480P video of approximately eight seconds and `ffmpeg` to decode-check it. The
MP4, receipt, and validation JSON are uploaded as an Actions artifact retained
for two days. Download the reviewed MP4 and receipt to the project's approved
local/external storage before expiry. The MP4 is not committed to Git.
When an existing artifact is revalidated, `github_run_id` remains the original
generation run ID and `validation_github_run_id` records the new validation run.

## Deliberate limits

- Every separate, newly dispatched `generate` workflow starts with run attempt 1.
  GitHub concurrency and the rerun guard cannot prevent a human from launching a
  second paid dispatch after the first finishes. Check existing Actions runs,
  receipts, and Alibaba Cloud task history before each new `GENERATE04` dispatch.
- If the POST outcome is unknown and no valid `task_id` was returned, the runner
  cannot discover that task from public API data. Account-side reconciliation is
  required; do not dispatch another generation merely because no MP4 exists.
- Alibaba Cloud task IDs and result URLs are short-lived. Resume promptly, and
  recover the two-day GitHub artifact into project storage.
- When using the URL mode, the first-frame source must remain publicly reachable
  during the workflow. The pinned JPEG input mode needs no media host. A
  missing source, non-public host, changed file, wrong hash, unsupported PNG, or
  oversized image blocks generation before POST.
- `validate-existing` accepts only a positive decimal GitHub run ID and builds
  the artifact name from that validated value. It can read artifacts only from
  the current repository through the workflow's read-only Actions permission.
- The workflow does not prove visual quality, character identity, motion, sound,
  or suitability. `DOWNLOADED_AND_FFMPEG_VALIDATED` still requires human review.

## Local offline checks

These checks do not need a key and do not call Alibaba Cloud:

```bash
python3 runner.py --offline-validate
python3 -m py_compile runner.py
```

Do not test `generate` merely to validate wiring. Use `check-binding` first; a
real `generate` dispatch is a separately authorized paid operation.
