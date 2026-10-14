# TaiwanChicken 30-second Taiwan food film — manual executor

Status: executor prepared for offline review. Committing or publishing these
files does not submit a video task. Only a manual `generate` dispatch with the
literal confirmation `GENERATE30` can send the fixed request.

This package is restricted to one 30-second, 480P, 9:16 `wan3.0-video`
generation in Alibaba Cloud Model Studio's China (Hong Kong) region / Global
deployment scope. Its fixed contract is `request-taiwan30.json`; the runner
requires the contract's pinned SHA-256 before any provider request.

## Repository files

- `.github/workflows/wan-hk-taiwan30.yml`: manual workflow entry.
- `tools/wan-hk/taiwan30_runner.py`: fixed-request API executor.
- `tools/wan-hk/request-taiwan30.json`: fixed script, request parameters,
  reference-image MIME, and reference-image SHA-256.

The original reference image stays outside Git. For `generate`, the caller
passes its Base64 text through the `first_image_base64` workflow input. The
runner reads that value only from GitHub's event JSON, decodes WebP/JPEG/PNG,
checks the detected MIME and pinned SHA-256, and inserts the verified bytes as a
data URI at runtime. It never prints the image or includes it in an artifact.
The total dispatch input payload must stay within GitHub's 65,535-character
limit.

## Required repository binding

- Secret `ALIYUN_MODEL_STUDIO_HK_API_KEY`. It is injected only into the runner
  process environment and is never printed, put on a command line, saved in a
  receipt, or read back.
- Variable `ALIYUN_MODEL_STUDIO_HK_API_HOST`, using the existing verified Hong
  Kong host.

The binding, model, and deployment must belong to the same Hong Kong region.
`check-binding` confirms only that the local contract and binding shapes are
valid. It makes no network request and does not prove entitlement or billing.

## Manual modes and exact inputs

1. `check-binding`: no other input. It validates the fixed contract and binding,
   writes a non-sensitive receipt, and makes no provider request.
2. `generate`: set `confirmation` to `GENERATE30` and
   `first_image_base64` to the exact pinned reference image. Generation is
   refused when `github.run_attempt` is not 1. The executor sends exactly one
   POST and never retries it automatically.
3. `resume`: set `resume_task_id` to the existing Alibaba Cloud task UUID. This
   mode issues GET requests for that task only and never sends a generation
   POST.

All three modes use the same concurrency group as the existing Shot04 executor,
so paid operations cannot overlap across the two workflows. Before `generate`
or `resume` can contact the provider, the workflow and runner both ensure that
`ffprobe` and `ffmpeg` exist.

The runner retains only safe task status, task UUID, numeric usage fields,
request/reference SHA provenance, output filename/size/SHA, and restricted error
codes. It never saves raw provider responses or signed result URLs. An uncertain
POST outcome is recorded as `POST_OUTCOME_UNKNOWN_DO_NOT_RETRY`; reconcile that
task before considering another paid dispatch.

After download, `ffprobe` requires one portrait video stream with a 480-pixel
short edge, approximately 30 seconds of duration, and at least one audio stream.
`ffmpeg` then decodes the full file. The MP4, receipt, and validation JSON are
uploaded in a two-day artifact. Technical validation does not prove the visual
quality or correctness of rendered titles; review the downloaded MP4 before use.

## Offline checks

These commands make no provider request and require no API key:

```bash
python3 -m py_compile tools/wan-hk/taiwan30_runner.py
python3 tools/wan-hk/taiwan30_runner.py --offline-validate
```

Do not use `generate` to test the wiring. Run `check-binding` first; the paid
dispatch is a separate, deliberate operation.
