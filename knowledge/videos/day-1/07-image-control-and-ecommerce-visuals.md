# Video 07 — Image Control and E-commerce Visual Production

- Video ID: `DJI_20260829164130_0017_D`
- Duration: 00:27:41
- Primary modules: K06, K07
- Evidence status: `direct_course_mapping`

## Purpose

The video explains how to move from playful image generation to production-grade visual control. The practical methods are reference-guided generation, multi-image composition, local modification, visual reverse analysis and an Agent-driven set workflow for e-commerce assets.

## Timeline

| Time | Topic | Detailed interpretation |
|---|---|---|
| 00:00–02:00 | From text quality to image control | Image generation is easy to start but hard to specify. Production means the result can actually be used in a campaign, event or listing. |
| 02:00–04:00 | Model capability and reference image | Model quality strongly affects control and Chinese text. A suitable reference image reduces the burden of describing layout and mood from scratch. |
| 04:00–06:00 | Product-aware adaptation | A strong model may infer product and brand context, but inferred facts, price, QR code and claims still need verification. |
| 06:00–08:00 | Multi-image composition | Different inputs can supply layout, character, product, prop or scene. The instruction must assign each image a role. |
| 08:00–10:00 | Clothing, pose and local change | Replace garment, pose, logo or one region while explicitly preserving everything else. Fewer simultaneous changes improve fidelity. |
| 10:00–12:00 | Reverse analysis and lower-code workflows | Extract useful visual attributes and feed them into repeatable tools or tables for batch transformation. Choose the simplest tool that fits the scale. |
| 12:00–14:00 | Category-specific visual variables | Fashion depends on model presence and fabric; beauty depends on material expression; creative posters depend on concept and art direction. |
| 14:00–16:00 | Where AI loses “taste” | A model can reproduce objects and composition yet flatten intentional imperfection, humour, cultural nuance or a distinctive art-director choice. |
| 16:00–18:00 | Three control methods | Use reference image, compose several inputs and reverse-analyse visual attributes. Iterate because generation remains probabilistic. |
| 18:00–20:00 | Tool trade-offs | Chat canvas, node workflow and Agent-integrated generation offer different balances of precision, complexity, cost and reuse. |
| 20:00–22:00 | Vendor and tool stack | Knowing which model is integrated into which product affects quality, convenience and total cost. |
| 22:00–24:00 | E-commerce detail-page workflow | A product brief becomes selling-point architecture, screen sequence, visual expression, draft and final art. The Agent can compress this chain. |
| 24:00–26:00 | Batch generation and self-review | Product plus reference inputs can drive five head images and ten detail screens. The Agent plans prompts, generates, checks and retries. |
| 26:00–27:41 | Integrated versus local layout generation | Model-native composition and text overlay systems behave differently. Select based on fidelity, typography and editability rather than marketing labels. |

## Reference role assignment

| Input | Possible role | What not to inherit blindly |
|---|---|---|
| Layout reference | Grid, hierarchy, density | Brand name, claims, exact copy |
| Portrait/model | Identity or pose | Unauthorised likeness or styling |
| Product image | Shape, colour, packaging | Invented specifications |
| Scene reference | Light and atmosphere | Specific protected campaign elements |
| Material reference | Texture and macro proof | Unsupported product effect |

## Production-grade image brief

```text
Business objective:
Audience and use context:
Image role in the set:
Main message to prove:
Main subject:
Product visibility:
Reference roles:
Facts that must remain exact:
Elements allowed to change:
Elements that must not change:
Required ratio and text:
Acceptance checks:
```

## Set-level checks

- Every image has a distinct job.
- The main visual proves the message without depending entirely on text.
- Full-product heroes are not repeated on every screen.
- Visual DNA is coherent but composition is varied.
- Product shape, colour and visible packaging remain accurate.
- Chinese text is checked character by character.
- Price, certification and performance are never invented.
- Model identity and human-product interaction remain plausible.
- Failed outputs are regenerated rather than patched with hidden contradictions.

## Exercise

Take one product image and one authorised visual reference. Plan a five-image set in a table with:

- image role;
- message;
- visual proof;
- main subject;
- product exposure;
- reference dimension used;
- text;
- acceptance test.

Do not generate until the five rows form a coherent campaign rather than five variations of one hero.

## Connection

[Video 08](08-skill-batch-and-model-routing.md) shows the packaged Skill and model-routing layer behind this batch workflow.
