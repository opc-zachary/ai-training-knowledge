# AI Training Guangzhou Knowledge

Private, derived knowledge from the two-day AI Training Guangzhou programme. This repository is designed for invited collaborators who want to:

- read the course map in Markdown;
- retrieve a versioned JSON crosswalk through authenticated GitHub access;
- install the included Codex skill for course-related questions.

## Start here

- [Full course map](knowledge/full-course-map.md)
- [Day 1 — LaoHong](knowledge/day-1-laohong.md)
- [Day 2 — Channel reference](knowledge/day-2-channel-reference.md)
- [Ten detailed Day 1 video guides](knowledge/videos/day-1/README.md)
- [K00–K10 module handbooks](knowledge/modules/README.md)
- [Task router](knowledge/task-router.md)
- [Glossary](knowledge/glossary.md)
- [Learning paths](knowledge/learning-paths.md)
- [Machine-readable crosswalk](data/course-crosswalk.v1.json)
- [Source boundaries](SOURCE_BOUNDARIES.md)
- [Sharing policy](SHARING_POLICY.md)

## Authenticated JSON access

With GitHub CLI already authenticated as an invited collaborator:

```bash
gh api repos/opc-zachary/ai-training-knowledge/contents/data/course-crosswalk.v1.json \
  -H 'Accept: application/vnd.github.raw+json'
```

The stable REST URL is:

```text
https://api.github.com/repos/opc-zachary/ai-training-knowledge/contents/data/course-crosswalk.v1.json
```

A private repository requires authentication. Do not embed access tokens in prompts, scripts or repository files.

## Codex skill

See [Codex installation](examples/codex-install.md). The entry point is:

```text
skills/ai-training-guangzhou/SKILL.md
```

## Practical library

- `playbooks/`: research, author voice, visual reverse analysis, e-commerce visuals, AI video and data analysis.
- `templates/`: research brief, Agent workflow, QA, machine-readable Agent task and visual set plan.
- `exercises/`: beginner drills, practical capstones and verification drills.

## Current evidence status

- Day 1: mapped against ten processed video segments and derived course notes.
- Day 2: PDF-derived reference outline only; video cross-check remains pending.
- Schema: `1.0.0`; content release: `1.1.0`.

This repository contains no original videos, transcripts, subtitles, courseware files, screenshots or third-party code.
