# Public GitHub and Raw Access

The repository is public. Reading the JSON does not require GitHub login.

## Raw URL

```bash
curl -L 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json'
```

Validate the public result:

```bash
curl -Ls 'https://raw.githubusercontent.com/opc-zachary/ai-training-knowledge/main/data/course-crosswalk.v1.json' \
  | jq -e '.content_version == "1.2.0"'
```

## GitHub CLI

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

The Contents API can also return raw media. Authentication is optional for normal public-rate access and may increase rate limits.

## Normal file view

Anyone can also open:

```text
https://github.com/opc-zachary/ai-training-knowledge/blob/main/data/course-crosswalk.v1.json
```

The normal file view and Raw URL should both be publicly readable after publication.
