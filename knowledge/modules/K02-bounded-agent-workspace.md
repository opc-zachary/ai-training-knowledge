# K02 — Bounded Agent Workspace

## Objective

Let an Agent operate productively without exposing unrelated projects or permitting uncontrolled actions.

## Workspace contract

```text
Project identity:
Task objective:
Allowed folder:
Allowed tools:
Allowed external destinations:
Prohibited actions:
Required output names:
Approval points:
Readback method:
```

## Workflow

1. Create a project-specific working folder.
2. Place only necessary inputs inside it.
3. Preserve originals and generate versioned outputs.
4. Start with minimum permissions.
5. Require a preview before material external actions.
6. Review file changes and logs.
7. Read back the final destination.

## Acceptance

- No unrelated file was accessed or modified.
- Every output has a clear project and version.
- External identity and destination are known.
- The final result exists where the user needs it.
- The action can be explained and audited.

## Common failures

- granting full access for convenience;
- mixing client folders;
- letting process files scatter across the desktop;
- treating an API acceptance as completed delivery;
- allowing an Agent to resolve a blocker by changing system settings.
