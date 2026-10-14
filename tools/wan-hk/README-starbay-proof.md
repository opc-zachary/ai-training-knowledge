# Starbay Effect 8-second I2V proof — manual executor

Status: locally prepared for offline review. The exact source PNG and 480x854
JPEG transport are pinned separately, together with the final request-file
SHA-256. Committing or publishing these files does not submit a video task.

The fixed scope is one 8-second, 480P, 9:16 `wan3.0-video` image-to-video proof
in Alibaba Cloud Model Studio's China (Hong Kong) region / Global deployment
scope. The supplied frame remains outside Git. The shot uses an orange glass
hoop, matte-blue solid architecture, a curling physical paper sheet, a real 3D
camera orbit, and independently moving cloth/background objects. It requests no
generated text.

## Files

- `.github/workflows/wan-hk-starbay-proof.yml`: manual workflow entry.
- `tools/wan-hk/starbay_proof_runner.py`: fixed-request executor and validator.
- `tools/wan-hk/request-starbay-proof.json`: fixed creative/API contract.

## Pinning before publication

The canonical source PNG is 941x1672 with SHA-256
`6dd20d8fa98798fce48b1071a48c633505c72706987ace9d3e25ee78f9fceb27`.
The provider transport is a content-preserving 480x854 JPEG with SHA-256
`c085208bc7cfe81f9cf09ab1f648f08277145404c59d95889dc253a7b2de8c75`.
It is 37,319 bytes and 49,760 Base64 characters, within GitHub's dispatch input
limit. Any later source, transport, prompt, or request edit requires new hashes.

## Required existing repository binding

- Secret `ALIYUN_MODEL_STUDIO_HK_API_KEY`.
- Variable `ALIYUN_MODEL_STUDIO_HK_API_HOST`.

Only the existing workflow binding names are referenced. The runner never reads
back, prints, or saves the secret value. `check-binding` validates the fixed
contract and binding shapes without making a provider API request.

## Manual modes

1. `check-binding`: no provider request; produces a non-sensitive receipt.
2. `generate`: requires `GENERATE_STARBAY_PROOF`, exactly one first-frame
   transport, and workflow run attempt 1. It makes exactly one POST and never
   retries that POST automatically.
3. `resume`: requires an existing provider task UUID and sends GET requests
   only. It never submits a generation POST.

All paid Wan HK workflows share the existing concurrency group. A network
timeout, unreadable response, or missing task UUID is recorded as
`POST_OUTCOME_UNKNOWN_DO_NOT_RETRY`; reconcile that exact submission before any
new paid dispatch. A rerun attempt is refused in `generate` mode.

## Offline checks

The strict checks make no provider request and require no API key:

```bash
python3 -m py_compile tools/wan-hk/starbay_proof_runner.py
python3 tools/wan-hk/starbay_proof_runner.py --offline-validate
```

Do not use `generate` to test wiring. Publish the reviewed files first, run
`check-binding`, inspect its receipt, and treat the paid `generate` dispatch as
a separate deliberate action. A downloaded MP4 is accepted technically only
after `ffprobe` confirms portrait 480P and 7.5–8.5 seconds and `ffmpeg` decodes
the entire file. Visual review is still required before use.
