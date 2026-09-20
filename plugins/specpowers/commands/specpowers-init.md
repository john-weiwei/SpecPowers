---
description: Generate project constitution (quality/testing/UX/performance principles) and scan structural baseline
handoffs:
  - label: Start Feature With Exploration
    agent: specpowers-explore
    prompt: Start a new feature with exploration. I want to build...
  - label: Start Feature Directly
    agent: specpowers-propose
    prompt: Start a new feature directly. I want to build...
  - label: Quick Fix
    agent: specpowers-fast
    prompt: Quick fix mode. I need to fix...
---

## User Input

```text
$ARGUMENTS
```

## Outline

You are running the **specpowers-init** command. This is the project-initialization step — run it once per project.

Load the specpowers skill context (`SKILL.md`), then follow the workflow defined in `prompts/init.md`. When the skill is installed via plugin, these files live at `${PLUGIN_ROOT}/skills/specpowers/` (ZCode/Claude/Codex 各自的 `PLUGIN_ROOT` 变量)。

Summary of what you will do:
1. Read the constitution template at `templates/constitution-template.md`（位于 skill 目录内，即 `${PLUGIN_ROOT}/skills/specpowers/templates/constitution-template.md`），scan project signals (README, dependency manifests, existing structure), and **inline-generate** `.specpowers/constitution.md` (focus: quality, testing, UX, performance principles — 4 categories only, no structural rules). Constitution is generated self-sufficiently by this skill (no external dependency).
2. Baseline scan is auto-run by the deterministic layer (`init` 命令内部已调用 `scan()`). Verify `.specpowers/baseline.json` was created.
3. After writing `.specpowers/constitution.md`, **refresh the baseline** to fill `constitution_hash` (the first scan ran before the file existed):
   ```bash
   python -m specpowers_cli.bridge.facade baseline --root .
   ```
   Only run `python -m specpowers_cli.bridge.facade scan --root .` manually if baseline.json is still missing.
4. Prompt user to commit `.specpowers/constitution.md` and `.specpowers/baseline.json` for team sharing.

If `--force` is passed: delete existing constitution.md and baseline.json first, then regenerate.
