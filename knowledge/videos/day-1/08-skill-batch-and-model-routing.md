# Video 08 — Skill Batch Production and Model Routing

- Video ID: `DJI_20260829170913_0018_D`
- Duration: 00:02:22
- Primary module: K07
- Evidence status: `direct_course_mapping`

## Purpose

This short bridge segment demonstrates two ideas: one reusable Skill can coordinate a multi-image e-commerce set, and an Agent product may connect to an external model provider when its built-in model is insufficient.

## Timeline

| Time | Topic | Detailed interpretation |
|---|---|---|
| 00:00–02:00 | One Skill, one coherent set | Product and reference inputs are processed as a connected batch. The Skill maintains relationships across head images and detail pages instead of generating unrelated files. |
| 02:00–02:22 | Break before next section | The image module closes and the class prepares to move into video. |

## Model-routing architecture

```text
Agent interface
  ↓
Reusable Skill
  ↓
Task plan and prompts
  ↓
Selected model endpoint
  ↓
Generated set
  ↓
Agent review and retry
```

## Why routing matters

- The best Agent interface may not contain the best image model.
- A custom endpoint can extend capability without replacing the whole workflow.
- The model provider, cost, availability and data handling remain separate decisions.
- A relay or unofficial intermediary introduces reliability, legal, privacy and provenance concerns.

## Operational requirements

1. Identify the exact model, not only the relay brand.
2. Test quality, latency and cost on a small sample.
3. Keep credentials out of shared prompts and files.
4. Use an authorised provider for business-sensitive inputs.
5. Define a fallback that does not silently change quality or privacy.
6. Log which model produced each deliverable.

## Routing decision table

| Decision | Question | Evidence to keep |
|---|---|---|
| Built-in or external | Does the Agent's built-in model meet the production requirement? | Same-brief sample comparison |
| Direct or relay | Is the provider identity, billing and data path clear? | Provider and endpoint record |
| Quality tier | Which model gives the best usable yield, not the best single sample? | Accepted/failed output counts |
| Cost control | What is the maximum generation spend per set? | Usage and cost log |
| Failure handling | What happens when the endpoint is unavailable? | Explicit stop or approved fallback |
| Data handling | May product images or client data leave the local environment? | Project authority and provider terms |

## Batch acceptance

- The Skill produces the planned number of independent files.
- Outputs form one visual system but do not repeat one composition.
- Each file records its role and validation status.
- A model change is visible in the run record.
- Failed calls are not silently retried through an unknown provider.
- The final set is checked as a set, not only image by image.

## Exercise

Draw the model-routing chain for one current workflow. Mark ownership, cost, data exposure, failure point and readback at every hop. If any hop is unknown, the workflow is not production-ready.

## Connection

[Video 09](09-ai-video-production.md) continues into moving-image generation and editing.
