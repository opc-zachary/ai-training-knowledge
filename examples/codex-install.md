# Install the Codex Skill

## 1. Clone with the collaborator's GitHub login

```bash
gh repo clone opc-zachary/ai-training-knowledge
cd ai-training-knowledge
```

## 2. Install without overwriting an existing skill

First check whether `ai-training-guangzhou` already exists in the user's Codex skills directory. If it exists, stop and review it instead of overwriting it. Otherwise copy the complete folder:

```text
skills/ai-training-guangzhou
```

into the user's Codex skills directory as:

```text
ai-training-guangzhou
```

The installed folder must contain `SKILL.md` and the `references/` directory together.

## 3. Use it

Example requests:

```text
Use $ai-training-guangzhou to explain the Day 1 research workflow.
```

```text
Use $ai-training-guangzhou to compare a Day 1 Skill with the Day 2 Harness concept.
```

```text
Use $ai-training-guangzhou to build a study route for K03, K05 and K09.
```

Day-two answers must remain labelled `reference_only` until the repository receives verified video mapping.
