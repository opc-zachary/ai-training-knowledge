# K01 — Model, Agent and Tool Framework

## Objective

Select an AI operating stack according to the job rather than model popularity.

## Five layers

| Layer | Question |
|---|---|
| Business goal | What decision or deliverable is required? |
| Workflow/Agent | Who decomposes and advances the work? |
| Model | What reasoning, language or media capability is needed? |
| Tool | What files, APIs or applications must be used? |
| Verification | How will correctness and delivery be proven? |

## Selection workflow

1. Define the output and acceptance criteria.
2. Classify the task as dialogue, specialist generation or multi-step Agent work.
3. Identify text, image, audio, video, code and data capabilities.
4. Test two realistic candidates on the same brief.
5. Compare quality, latency, cost, consistency and edit burden.
6. Select the smallest stack that meets the requirement.
7. Record the model and tool used with the result.

## Acceptance

- The chosen stack can produce the required file or action.
- The underlying model is known.
- Cost and usable yield are measured.
- External actions have identity and permission controls.
- A fallback does not silently change quality or privacy.

## Failure signals

- “Best AI” is the only selection reason.
- The model name and app name are confused.
- Showcase output replaces task testing.
- No one can explain how the result was generated.
