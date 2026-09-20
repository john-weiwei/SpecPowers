---
description: One-shot generate the OpenSpec change artifacts — proposal.md (from the explore design doc), delta spec.md, and tasks.md (merged former specify + plan stages); re-entering with an unarchived active feature opens a new iteration round of the SAME requirement (spec revised incrementally, tasks evolved per-round)
handoffs:
  - label: Build & Execute
    agent: specpowers-apply
    prompt: Execute the implementation plan. I want to build...
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/propose.md`.

You will:
1. **Iteration re-entry check first**: read `.specpowers/state.json` — if `stage` is `apply` and `feature` is non-empty (unarchived), follow the「重入识别」section of `prompts/propose.md`: confirm with the user to open Round <N+1> via `facade iterate`, then revise the existing spec/tasks incrementally (requirement identity is decided by archive state alone — same spec until archived)
2. Otherwise (normal flow): read `.specpowers/constitution.md` for project principles
3. If coming from explore: read the registered design doc (`state.json` `design_doc` field) for decision context, capability, and data-flow conclusions
4. Generate `openspec/changes/<feature>/proposal.md` (OpenSpec Why/What Changes/Capabilities/Impact + 「## 数据流契约」 section distilled from the design doc — apply 阶段硬依赖，缺失会被确定性层拒收)
5. Generate delta spec using OpenSpec format (ADDED Requirements + Scenario, Chinese, real WHEN/THEN) → `openspec/changes/<feature>/specs/<capability>/spec.md`
6. Decompose the delta spec into `openspec/changes/<feature>/tasks.md` (superpowers `writing-plans` slimmed: single tasks.md, `### Task N` headings, 场景引用/验收标准/依赖/并行/检查点 fields, 推荐执行方式 comment block at top; **Do NOT auto-commit**)
7. Self-review: scenario coverage / dependency graph / execution mode fit / cross-link data source backtracking
8. Tell user: next step is `/specpowers-apply`
