---
description: Full-pipeline unattended mode with requirement clarification + multi-round iteration — five-dimension doc check decides a stage ceiling (full runs to specpowers-review; unresolved-solution docs park at explore with a draft + questions), then auto-drive the stages from a design doc (init→explore→propose→apply→specpowers-review); archiving is NEVER automatic — only via explicit `--archive` (with the closure pre-check) or manual `/specpowers-archive`. Before archive, every re-entry (new doc / same doc / verbal instruction) iterates the SAME change dir; archiving declares a new requirement.
---

## User Input

```text
$ARGUMENTS
```

支持形态：`<设计文档路径>`（fresh 必填）、`--instruction "<调整描述>"`（迭代轮无文档输入；explore 停靠后重入时作为方案结论答复）、`--archive`（本轮跑完过收口前置检查后追加归档）、`--new-round`（显式开启迭代轮）。任何轮次（fresh/resume/iterate）默认都不归档。

## Outline

Load the specpowers skill context, then follow `prompts/auto.md`.

You will:
1. Run the deterministic tri-branch gate first: `facade auto-status` decides **fresh** (new requirement) / **resume** (breakpoint continue) / **iterate** (new round of the SAME requirement) — requirement identity is decided solely by archive state, never by the design doc path or content
2. **fresh**: validate the design doc exists (missing = hard blocker), record HEAD as the review base into `.specpowers/auto_base.json`, parse the eight required elements (功能名/已定方案/核心调用链/必测场景清单/修改范围表/编码约束/外部依赖降级策略/硬性边界), then run **requirement clarification**: five-dimension check (完整性/自洽性/可测性/明确性/边界一致性) decides a stage **ceiling** registered via `facade auto clarify --ceiling <full|explore>` + report to `.specpowers/auto_clarifications/<feature>.md` — zero new user params; ceiling=full runs straight through to specpowers-review, ceiling=explore (undefined solution / unjudgeable conflicts / >1/2 untestable scenarios) parks after explore with an unconverged `[未收敛]` design-doc draft + questions list (null feature name = hard blocker)
3. **iterate**: run `facade auto new-round` (stage → propose, feature slug locked, iteration_count += 1), incremental clarification (only ceiling maintain/upgrade, never downgrade), pick full/light scope per the adjudication table — light still MUST revise spec.md and pass specpowers-review; **resume with `clarification.pending_input=true` must NOT blindly continue** — prompt for `--instruction "<solution conclusion>"` or an updated doc re-entry (or `/specpowers-reset` to abandon)
4. Drive stages 0–7 (clarification → `/specpowers-init` → `/specpowers-explore` → `/specpowers-propose` → `/specpowers-apply` → specpowers-review builtin skill), then append step 8 `/specpowers-archive` ONLY when `--archive` is passed (after the closure pre-check) — auto-adjudicating every confirm/gate node, never waiting for user input; iteration rounds revise the artifacts incrementally (spec revised in place, tasks evolved per-round with tombstones), and apply only un-checked non-tombstoned tasks
5. Archive closure is dual-channel: manual `/specpowers-archive` after any round, or `--archive` on any auto run (pre-check: no unresolved blocking P1/P2). NO round archives by default — fresh, resume, and iterate all stop at specpowers-review; archiving is always an explicit act. After archive the base file is cleaned and `iteration_count` reset — the next auto run is a NEW requirement
6. Stop only on hard blockers (doc-content defects park at explore instead); on interruption, re-entering `/specpowers-auto` resumes from the breakpoint
7. Emit the per-round summary report following `templates/auto-summary-template.md` (must include the clarification ceiling + leftovers)
