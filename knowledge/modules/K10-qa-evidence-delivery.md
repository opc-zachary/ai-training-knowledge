# K10 — QA, Evidence and Delivery

## Objective

Prove that an AI-assisted result is correct enough, belongs to the right project and reached the intended destination.

## Four gates

| Gate | Question |
|---|---|
| Input | Were the correct sources, client and version used? |
| Process | Were method, model, tools and changes recorded? |
| Output | Does the deliverable meet content and format requirements? |
| Destination | Can the exact final object be read back where it was delivered? |

## Workflow

1. Define acceptance before execution.
2. Preserve source and version information.
3. Run deterministic checks where possible.
4. Inspect representative high-risk samples manually.
5. Reconcile important numbers and claims.
6. Review format, links, images and text.
7. Deliver to the exact target.
8. Read back independently.
9. Record remaining uncertainty.

## Completion labels

- Verified complete: destination and evidence both match.
- Locally complete / external pending: artefact is ready but destination action remains.
- Outcome uncertain: a write may have happened and requires reconciliation.
- Blocked: required source, identity, capability or authority is absent.

## Failure signals

- generated file is called complete without opening it;
- push or API acceptance is treated as public delivery;
- source conflict is hidden;
- one successful capability is used to assume another;
- uncertain write is retried without checking the exact object.
