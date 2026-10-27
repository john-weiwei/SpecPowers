---
name: specpowers-apply
description: 执行构建——结构门禁三态校验（结构基线+修改范围比对）+ 能力池调度执行任务
---

# specpowers-apply — 执行构建

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context, then follow `prompts/apply.md`.

You will:
1. Read context: `.specpowers/constitution.md`, `.specpowers/baseline.json`, `openspec/changes/<feature>/tasks.md` (full mode) or delta spec (fast mode)
2. **Prompt user to choose execution mode** (`tasks.md` comment block recommends, user decides):
   - `conductor` → `executing-plans` (sequential execution, default)
   - `worktree` → `using-git-worktrees` (isolated workspace)
   - `subagent` → `subagent-driven-development` (one sub-agent per task)
   - `TDD` → `test-driven-development` (red-green-refactor cycle)
   - fast mode: only conductor/TDD available, worktree/subagent disabled
3. Run structure gate: `git diff` vs `.specpowers/baseline.json` → three-state judgment (pass/escalate/reject)
4. Invoke chosen superpowers skill to execute all tasks, check off `- [x]` in tasks.md
5. Verify: full mode checks delta spec Scenario THEN entries (cross-link fields against proposal's 「数据流契约」); fast mode checks delta spec Scenario (3-5)
6. Tell user: next step is `/specpowers-archive`

完成后：建议调用技能 specpowers-review（可选独立审查）与 specpowers-archive（用户直接 `/specpowers-archive` 调用，auto 模式下模型直接经 Skill 工具调用）。
