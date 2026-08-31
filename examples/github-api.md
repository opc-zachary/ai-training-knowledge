# Authenticated GitHub API Access

The repository is private. Each collaborator authenticates with their own GitHub account.

## GitHub CLI

After the collaborator has completed GitHub CLI login themselves:

```bash
gh api repos/opc-zachary/ai-training-knowledge/contents/data/course-crosswalk.v1.json \
  -H 'Accept: application/vnd.github.raw+json'
```

Validate the returned JSON:

```bash
gh api repos/opc-zachary/ai-training-knowledge/contents/data/course-crosswalk.v1.json \
  -H 'Accept: application/vnd.github.raw+json' \
  | jq -e '.schema_version == "1.0.0"'
```

## REST URL

```text
https://api.github.com/repos/opc-zachary/ai-training-knowledge/contents/data/course-crosswalk.v1.json
```

Request it with the GitHub Contents API raw media type and the caller's own authentication. Do not paste a personal access token into a prompt, source file or shared command history.

## Normal file view

An invited collaborator can also open:

```text
https://github.com/opc-zachary/ai-training-knowledge/blob/main/data/course-crosswalk.v1.json
```

Unauthorised users should receive a not-found response because the repository is private.
