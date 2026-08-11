---
description: Decompose delta spec into executable tasks.md (OpenSpec checkbox format) and recommend execution mode
handoffs:
  - label: Build & Execute
    agent: specpowers-build
    prompt: Execute the implementation plan. I want to build...
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/plan.md`.

You will:
1. Read `openspec/changes/<feature>/specs/<capability>/spec.md` (delta spec) for Scenario-based task decomposition
2. Call superpowers `writing-plans`, merge tasks into single `openspec/changes/<feature>/tasks.md` (`### Task N` heading format for task-brief script compat, Chinese content)
3. Task fields: 场景引用 / 验收标准 / 依赖 / 测试先行 (fixed fields, Chinese labels)
4. Add 推荐执行方式 comment block at top of tasks.md
5. **Do NOT auto-commit** — 只生成文件，不执行 git 操作
6. Self-review: task coverage / dependency graph / execution mode fit
7. Tell user: next step is `/specpowers-build`
