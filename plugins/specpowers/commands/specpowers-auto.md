---
description: Full-pipeline unattended mode — auto-drive all stages from an authoritative design doc: constitution→brainstorm→specify→plan→build→codex-review→archive
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/auto.md`.

You will:
1. Validate preconditions: stage/dependency check via the deterministic layer, design doc existence, codex-review skill availability
2. Record the current HEAD commit as the review base point into `.specpowers/auto_base.json`
3. Parse the eight required elements from the authoritative design doc (功能名/已定方案/核心调用链/必测场景清单/修改范围表/编码约束/外部依赖降级策略/硬性边界) and persist them alongside the base point
4. Drive stages 0–7 unattended (`/specpowers-constitution` → `/specpowers-brainstorm` → `/specpowers-specify` → `/specpowers-plan` → `/specpowers-build` → codex-review → `/specpowers-archive`), auto-adjudicating every confirm/gate node per the adjudication rules table — never waiting for user input
5. Stop only on hard blockers (unavailable external dependency with no degradation, unrecoverable state-machine inconsistency, self-contradictory design doc); on interruption, a re-entry of `/specpowers-auto` resumes from the breakpoint
6. Emit the final summary report following `templates/auto-summary-template.md`
