---
description: Reset pipeline state — clears state.json and lock file, returns to ready stage. Does NOT delete baseline.json.
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then run:

```bash
python -m specpowers_cli.bridge.facade reset --root .
```

This clears the pipeline state (stage/feature/mode) and removes any stale lock file. The fallback count is preserved (cannot reset your way around the 1-fallback limit).

Use cases: pipeline stuck mid-stage, lock file left after crash, want to abandon current feature and start fresh.

Note: baseline.json is NOT affected.
