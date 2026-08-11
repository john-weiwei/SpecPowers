---
description: Finalize the feature — 3-duties: verify constitution compliance, mark artifacts complete, post-merge structure check
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/archive.md`.

**Three duties** (archive never rejects, only escalates to human):

1. **Constitution check**: verify evidence exists for quality/testing/UX/performance principles. Missing evidence → warn but proceed.
2. **Finalize artifacts**: mark `openspec/changes/<feature>/tasks.md` tasks complete.
3. **Post-merge verification**: auto-detect multi-branch merges (merge commits or multi-author) → run structure consistency check. `--force-merge-check` forces this for rebase/squash workflows.

**Full 与 Fast 模式统一**：dispatcher 调用 `openspec archive <feature> --yes --json` 归档（合并主规格 `openspec/specs/<feature>/spec.md` + change 快照 `openspec/changes/archive/YYYY-MM-DD-<feature>/`）。强依赖 openspec CLI，CLI 不可用时拒绝归档（不降级）。full 与 fast 的唯一区别：fast 无 proposal.md（OpenSpec archive 对 proposal 内容是 informative only，不阻塞）。

After archive: stage resets to `ready`, feature name cleared. Ready for next feature.
