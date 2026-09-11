---
description: Create an OpenSpec delta spec (ADDED Requirements + Scenario) from a requirement, written to openspec/changes/<feature>/specs/<capability>/spec.md
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
1. Read `.specpowers/constitution.md` for project principles
2. If coming from brainstorm: read `openspec/changes/<feature>/proposal.md` for decision context + capability
3. Generate delta spec using OpenSpec format (ADDED Requirements + Scenario, Chinese, real WHEN/THEN)
4. Write `openspec/changes/<feature>/specs/<capability>/spec.md`
5. Tell user: next step is `/specpowers-plan`
