---
description: Create an OpenSpec delta spec (ADDED Requirements + Scenario) from a requirement, written to openspec/changes/<feature>/specs/<capability>/spec.md; re-entering with an unarchived active feature opens a new iteration round of the SAME requirement (spec revised incrementally in place)
handoffs:
  - label: Create Implementation Plan
    agent: specpowers-plan
    prompt: Create the implementation plan. I want to build...
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/specify.md`.

You will:
1. **Iteration re-entry check first**: read `.specpowers/state.json` — if `stage` is `plan`/`build` and `feature` is non-empty (unarchived), follow the「重入识别」section of `prompts/specify.md`: confirm with the user to open Round <N+1> via `facade iterate`, then revise the existing spec incrementally (requirement identity is decided by archive state alone — same spec until archived)
2. Otherwise (normal flow): read `.specpowers/constitution.md` for project principles
3. If coming from brainstorm: read `openspec/changes/<feature>/proposal.md` for decision context + capability
4. Generate delta spec using OpenSpec format (ADDED Requirements + Scenario, Chinese, real WHEN/THEN)
5. Write `openspec/changes/<feature>/specs/<capability>/spec.md`
6. Tell user: next step is `/specpowers-plan`
