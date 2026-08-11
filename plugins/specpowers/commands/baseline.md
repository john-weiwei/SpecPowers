---
description: Manually refresh the structural baseline — re-scan top-level dirs, dependencies, and source patterns
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then run:

```bash
python -m specpowers_cli.bridge.facade baseline --root .
```

This re-scans the project and overwrites `.specpowers/baseline.json`. Prompt the user to review and commit the updated baseline for team sharing.

Use cases: team member added new top-level directories, introduced new dependency types, or baseline is stale (automatic drift warning already shown).
