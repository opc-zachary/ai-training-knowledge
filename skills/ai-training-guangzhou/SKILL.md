---
name: ai-training-guangzhou
description: Use when studying, explaining or applying the AI Training Guangzhou two-day course knowledge. 支援繁體／簡體中文，涵蓋第一天、第二天上午老洪及下午 Channel；必須區分 verified、video_classified_review 及 Raw transcript 邊界。
---

# AI Training Guangzhou

Use this skill to answer course questions, build a study sequence, locate the relevant day-one video segment, compare day-one execution with day-two system design, or adapt the course concepts into a practical workflow.

## Route the request

- For Traditional Chinese, read [references/zh-Hant-course.md](references/zh-Hant-course.md).
- For Simplified Chinese, read [references/zh-Hans-course.md](references/zh-Hans-course.md).
- When running from this repository and the user needs detailed Day 2 evidence, route through `day-2/README.md`, then the matching guide, timestamped transcript and QA JSON.
- For Old Hong Prompt, Context, Skill, AI workbench, enterprise automation or FDE questions, route first through `day-2/old-hong/README.md`; use its `LH-*` knowledge/workflow IDs and evidence map.

- For models, Agents, local workflow safety, research, Xiaohongshu insight, author voice, visual production, AI video, data analysis or QA, read [references/day-1.md](references/day-1.md).
- For workflow governance, GUI/CLI/API/MCP, Harness, Agent Team, FDE, OPC or Agent Boss, read [references/day-2.md](references/day-2.md).
- For requests involving source files, redistribution, transcripts, courseware or evidence status, read [references/source-boundaries.md](references/source-boundaries.md).
- For choosing the right course module, read [references/task-router.md](references/task-router.md).
- For executing research, writing, visual, video or data work, read [references/application-playbooks.md](references/application-playbooks.md).
- For a compact task, research, visual or QA structure, read [references/templates.md](references/templates.md).

## Response contract

1. Identify the relevant module or section before explaining it.
2. Label day-one mapped knowledge as verified video mapping, direct course mapping or video-led according to the reference.
3. Label Day 2 as `video_classified_review`; do not present Raw transcript as an official transcript.
4. When giving a study route, include the relevant day-one module ID and video time range where available.
5. Separate durable method from time-sensitive product or model claims.
6. Never claim that the original videos, transcripts, subtitles, slides or courseware are bundled with this skill.
7. Do not reproduce or reconstruct long source passages, copied prompts or third-party code.
8. Respond in the user's language; if Chinese is requested without a script preference, use Traditional Chinese.
9. For Old Hong answers, separate classroom meaning, editorial application and any newly added recommendation.

## Applying the knowledge

Turn course concepts into an explicit workflow with:

- goal and business decision;
- inputs and source quality;
- Agent or human roles;
- tools and permissions;
- output schema;
- verification and acceptance checks;
- reusable learning captured at the narrowest appropriate layer.

Do not treat a generated answer, dashboard, image or report as complete until its evidence and destination have been checked.

## Study answers

When the user wants to learn rather than execute:

1. name the module and evidence status;
2. explain the core idea;
3. give the video navigation range where available;
4. show the operating workflow;
5. give one exercise;
6. give an acceptance checklist;
7. connect it to the next relevant module.
