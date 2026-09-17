---
description: Explore a feature requirement with brainstorming, produce OpenSpec proposal.md (Why/What Changes/Capabilities/Impact); re-entering with an unarchived active feature opens a new iteration round of the SAME requirement (proposal revised incrementally with iteration history)
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
1. **Iteration re-entry check first**: read `.specpowers/state.json` — if `stage` is `specify`/`plan`/`build` and `feature` is non-empty (unarchived), follow the「重入识别」section of `prompts/brainstorm.md`: confirm with the user to open a new iteration round via `facade iterate` (approach-change path — proposal.md updated in place with「## 迭代历史」), then hand off to `/specpowers-specify` for incremental spec revision
2. Otherwise (normal flow): call superpowers `brainstorming` to explore the requirement
3. Propose 2-3 approaches with trade-offs (use Chinese)
4. **Always** write `openspec/changes/<feature>/proposal.md` (OpenSpec structure: Why/What Changes/Capabilities/Impact, Chinese)
5. Tell user: next step is `/specpowers-specify "<requirement>"`
