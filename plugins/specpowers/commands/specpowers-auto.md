---
description: Full-pipeline unattended mode with multi-round iteration — auto-drive all stages from a design doc (constitution→brainstorm→specify→plan→build→codex-review→archive). Before archive, every re-entry (new doc / same doc / verbal instruction) iterates the SAME change dir; archiving declares a new requirement.
---

## User Input

```text
$ARGUMENTS
```

支持形态：`<设计文档路径>`（fresh 必填）、`--instruction "<调整描述>"`（迭代轮无文档输入）、`--archive`（本轮跑完追加归档）、`--no-archive`（fresh 首轮跳过归档进入迭代模式）、`--new-round`（显式开启迭代轮）。

## Outline

Load the specpowers skill context, then follow `prompts/auto.md`.

You will:
1. Run the deterministic tri-branch gate first: `facade auto-status` decides **fresh** (new requirement) / **resume** (breakpoint continue) / **iterate** (new round of the SAME requirement) — requirement identity is decided solely by archive state, never by the design doc path or content
2. **fresh**: validate the design doc exists (missing = hard blocker), record HEAD as the review base into `.specpowers/auto_base.json`, parse the eight required elements (功能名/已定方案/核心调用链/必测场景清单/修改范围表/编码约束/外部依赖降级策略/硬性边界)
3. **iterate**: run `facade auto new-round` (stage → specify, feature slug locked, iteration_count += 1), pick full/light scope per the adjudication table — light still MUST revise spec.md and pass codex-review
4. Drive stages 0–7 (`/specpowers-constitution` → `/specpowers-brainstorm` → `/specpowers-specify` → `/specpowers-plan` → `/specpowers-build` → codex-review → `/specpowers-archive`), auto-adjudicating every confirm/gate node — never waiting for user input; iteration rounds revise spec.md incrementally, evolve tasks.md per-round with tombstones, and build only un-checked non-tombstoned tasks
5. Archive closure is dual-channel: manual `/specpowers-archive` after any round, or `--archive` on re-entry (pre-check: no unresolved blocking P1/P2). Iteration rounds default to NOT archiving; fresh archives by default (`--no-archive` overrides). After archive the base file is cleaned and `iteration_count` reset — the next auto run is a NEW requirement
6. Stop only on hard blockers; on interruption, re-entering `/specpowers-auto` resumes from the breakpoint
7. Emit the per-round summary report following `templates/auto-summary-template.md`
