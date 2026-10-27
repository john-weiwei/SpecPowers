---
name: specpowers-init
description: 生成项目 constitution（质量/测试/UX/性能原则）并扫描结构基线，每项目执行一次
---

# specpowers-init — 项目初始化

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数；`--force` 时先删除既有 constitution.md 与 baseline.json 再重新生成）。

## Outline

You are running the **specpowers-init** stage skill. This is the project-initialization step — run it once per project.

Load the specpowers skill context (`SKILL.md`), then follow the workflow defined in `prompts/init.md`. When the skill is installed via plugin, these files live at `${PLUGIN_ROOT}/skills/specpowers/` (ZCode/Claude/Codex 各自的 `PLUGIN_ROOT` 变量).

Summary of what you will do:
1. Read the constitution template at `templates/constitution-template.md`（位于 skill 目录内，即 `${PLUGIN_ROOT}/skills/specpowers/templates/constitution-template.md`），scan project signals (README, dependency manifests, existing structure), and **inline-generate** `.specpowers/constitution.md` (focus: quality, testing, UX, performance principles — 4 categories only, no structural rules). Constitution is generated self-sufficiently by this skill (no external dependency).
2. Baseline scan is auto-run by the deterministic layer (`init` 命令内部已调用 `scan()`). Verify `.specpowers/baseline.json` was created.
3. After writing `.specpowers/constitution.md`, **refresh the baseline** to fill `constitution_hash` (the first scan ran before the file existed):
   ```bash
   python -m specpowers_cli.bridge.facade baseline --root .
   ```
   Only run `python -m specpowers_cli.bridge.facade scan --root .` manually if baseline.json is still missing.
4. Prompt user to commit `.specpowers/constitution.md` and `.specpowers/baseline.json` for team sharing.

完成后：提示用户提交 `.specpowers/constitution.md` 与 `.specpowers/baseline.json`；下一步建议调用技能 specpowers-explore / specpowers-propose / specpowers-fast（按需求形态三选一；用户直接 `/specpowers-xxx` 调用，auto 模式下模型直接经 Skill 工具调用）。
