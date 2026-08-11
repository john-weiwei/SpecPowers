---
description: Explore a feature requirement with brainstorming, produce OpenSpec proposal.md (Why/What Changes/Capabilities/Impact)
handoffs:
  - label: Define Specification
    agent: specpowers-specify
    prompt: Create the specification for this feature. I want to build...
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/brainstorm.md`.

You will:
1. Call superpowers `brainstorming` to explore the requirement
2. Propose 2-3 approaches with trade-offs (use Chinese)
3. **Always** write `openspec/changes/<feature>/proposal.md` (OpenSpec structure: Why/What Changes/Capabilities/Impact, Chinese)
4. Tell user: next step is `/specpowers-specify "<requirement>"`
