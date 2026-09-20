---
description: Execute implementation — user chooses execution mode, structure gate validates, superpowers capability pool runs tasks
handoffs:
  - label: Archive & Finalize
    agent: specpowers-archive
    prompt: Archive and finalize the build results. I'm ready to archive...
---

## User Input

```text
$ARGUMENTS
```

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
