---
description: Explore a feature requirement with the built-in specpowers-explore skill; the design doc (docs/specpowers/design/) is the deliverable — proposal.md is NOT written here (it moved to the propose stage); re-entering with an unarchived active feature opens a new iteration round of the SAME requirement (design doc revised incrementally)
handoffs:
  - label: Propose (Generate proposal/spec/tasks)
    agent: specpowers-propose
    prompt: Generate the OpenSpec change artifacts. I want to build...
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/explore.md`.

You will:
1. **Iteration re-entry check first**: read `.specpowers/state.json` — if `stage` is `propose`/`apply` and `feature` is non-empty (unarchived), follow the「重入识别」section of `prompts/explore.md`: confirm with the user to open Round <N+1> via `facade iterate` (approach-change path — design doc updated in place, proposal.md regenerated at the propose stage), then hand off to `/specpowers-propose` for incremental spec/tasks revision
2. Otherwise (normal flow): invoke the built-in `specpowers-explore` skill to explore the requirement (silent project exploration → 2-3 approaches compared on unified dimensions → single recommendation → design doc written under `docs/specpowers/design/`, incl. data-flow conclusions)
3. Interact with the user: clarifying questions, approach trade-offs (use Chinese, AskUserQuestion per `prompts/explore.md`)
4. **Register the design doc** with the deterministic layer (hard gate for propose):
   ```bash
   python -m specpowers_cli.bridge.facade record-design-doc <设计文档路径> --root .
   ```
5. Tell user: next step is `/specpowers-propose "<requirement>"` (one-shot proposal.md + spec.md + tasks.md)
