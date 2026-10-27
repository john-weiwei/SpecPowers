---
name: specpowers-archive
description: 归档收尾——原则核查、产物标记与合体后校验，合并 delta spec 到主规格
---

# specpowers-archive — 归档收尾

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数；`--force-merge-check` 强制多分支合并校验）。

## Outline

Load the specpowers skill context, then follow `prompts/archive.md`.

**Three duties** (archive never rejects, only escalates to human):

1. **Constitution check**: verify evidence exists for quality/testing/UX/performance principles. Missing evidence → warn but proceed.
2. **Finalize artifacts**: mark `openspec/changes/<feature>/tasks.md` tasks complete.
3. **Post-merge verification**: auto-detect multi-branch merges (merge commits or multi-author) → run structure consistency check. `--force-merge-check` forces this for rebase/squash workflows.

**Full 与 Fast 模式统一**：dispatcher 调用 `openspec archive <feature> --yes --json` 归档（合并主规格 `openspec/specs/<capability>/spec.md` + change 快照 `openspec/changes/archive/YYYY-MM-DD-<feature>/`；fast 模式下 capability = feature）。强依赖 openspec CLI，CLI 不可用时拒绝归档（不降级）。full 与 fast 的唯一区别：fast 无 proposal.md（OpenSpec archive 对 proposal 内容是 informative only，不阻塞）。

After archive: stage resets to `ready`, feature name cleared. Ready for next feature.

**Do NOT commit code**: archive only finalizes (openspec archive + state transition), never runs `git add` / `git commit` — committing is left to the user.

完成后：stage 回到 `ready`；建议用户提交代码，下一个需求可调用技能 specpowers-explore / specpowers-propose / specpowers-fast / specpowers-auto（按需求形态四选一）。
