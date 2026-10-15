# CityCanvas S01 WAN proof — approved executor package v04

Status: **APPROVED_PACKAGE_READY_FOR_ROOT_INTEGRATION**

Zachary Chan approved exactly one S01 `wan3.0-video` image-to-video proof on
2026-10-15: 480P, portrait 9:16, five seconds, silent, first frame only, no end
frame, no automatic paid retry, maximum one submission, and a HK$5 cap. The
requested result must be shown as a video. This directory records that bounded
approval but remains local and unpublished. Root retains sole authority to
install, publish, dispatch once, resume the same task, and read back the video.

## Immutable creative and provider payload

The `request` object, creative ID, prompt, model, parameters and frame hashes
are unchanged from
`../StarbayCityCanvas_Starbay_2026-10-15_JSON_S01ProofRequest_Review_v03.json`.
Approval metadata is top-level contract evidence and is not sent to the
provider; the runner posts only `contract["request"]` after inserting the
SHA-verified first-frame data URI.

- Approved contract SHA-256:
  `e04f9f2a6f28d18b8e4c03131be6e1ccb4a4820caf8a604a1e20df4be855a936`
- Source PNG: 941x1672,
  `8c5389104fae70c6b1abfd1431850599838133641098a956d7a86c1c19748db0`
- Transport JPEG: 480x854, 46,464 bytes,
  `94eb1c07138db47b5f899a9bb0bc9b2efc4b5f10c421fb2116b8415293c582d6`
- Output filename: `CityCanvasS01.mp4`

The exact offline cost guard computes:

`5 × US$0.041256 × HK$7.8/US$ = HK$1.608984`, rounded to HK$1.61.

Both the unrounded amount and declared estimate are below the approved HK$5
cap. A changed rate, FX, duration, estimate or cap fails closed before binding
access or a provider request.

## Publication mapping

Root should install these four reviewed files into the verified repository
without renaming their internal references:

| Local package source | Repository destination |
|---|---|
| `city_canvas_s01_approved_v04_runner.py` | `tools/wan-hk/city_canvas_s01_approved_v04_runner.py` |
| `request-starbay-city-canvas-s01-approved-v04.json` | `tools/wan-hk/request-starbay-city-canvas-s01-approved-v04.json` |
| `wan-hk-starbay-city-canvas-s01-approved-v04.workflow.yml` | `.github/workflows/wan-hk-starbay-city-canvas-s01-approved-v04.yml` |
| `README.md` | `tools/wan-hk/README-city-canvas-s01-approved-v04.md` |

`offline_check.py` is a local package verifier and is not one of the four
publication files.

The workflow source is manual `workflow_dispatch` only and has no schedule. It
retains shared paid-generation concurrency group
`wan-hk-shot04-paid-generation` with `cancel-in-progress: false`, and uses only
the existing binding names `ALIYUN_MODEL_STUDIO_HK_API_KEY` and
`ALIYUN_MODEL_STUDIO_HK_API_HOST`. The runner pins the exact host
`ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com`.

## Execution guards

Before binding access, approved `generate` requires all of the following:

- contract status `APPROVED_FOR_ONE_PAID_SUBMISSION` and authorization
  `GRANTED`;
- unchanged approval scope and passing HK$5 cost calculation;
- exact confirmation `GENERATE_STARBAY_CITY_CANVAS_S01_V04_ONCE`;
- workflow attempt `1`;
- no existing v04 receipt or `CityCanvasS01.mp4` in the output directory.

Generation then accepts exactly one URL or Base64 first-frame transport and
checks JPEG MIME, dimensions, byte count and SHA-256. The runner contains one
submission call and makes no automatic POST retry. It writes
`POST_IN_PROGRESS_OUTCOME_UNKNOWN` before POST. A timeout, unreadable response
or missing task UUID becomes `POST_OUTCOME_UNKNOWN_DO_NOT_RETRY`; root must
reconcile or resume the same task rather than start another paid submission.
`resume` validates one existing task UUID, refuses a conflicting receipt task
ID and uses GET requests only.

Downloaded video validation requires one portrait video stream, 480-pixel
short edge, duration 4.5–5.5 seconds, 30fps, zero audio streams and a successful
full-file FFmpeg decode. A provider success or downloaded file is intermediate
evidence until this validator passes and root shows the resulting video.

## Offline verification

Run in this package directory before publication:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 offline_check.py
```

The check performs no GitHub, provider or network request and does not load a
binding or secret. It verifies the `GRANTED` contract pin, immutable provider
payload, real local PNG/JPEG bytes, exact cost and cap, wrong-hash and over-cap
rejection, positive preflight, wrong-confirmation/rerun/duplicate rejection,
and mocked run-mode ordering before network. Synthetic MP4 checks prove the
silent five-second 30fps output path and rejection of audio-bearing and 24fps
files.

Completed result:

```text
PASS GRANTED contract, immutable provider payload, assets and cost cap
PASS confirmation, attempt, duplicate and mocked pre-network guard order
PASS manual workflow source, distinct v04 names and shared concurrency
FFPROBE_FFMPEG_NO_AUDIO_VALIDATED
PASS 5-second portrait 480P, 30fps, no-audio and full-decode validation
PASS audio-stream and wrong-fps rejection
OFFLINE_CHECKS_PASSED_NO_NETWORK_NO_BINDINGS
```

## Limitations

This package is approved local source, not a GitHub publication, binding
readback, provider submission, task result, validated production video or proof
that the requested video has been shown. Root must preserve one writer and the
existing route for integration and the sole dispatch.
