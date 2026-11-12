---
name: specpowers-apply
description: 执行构建——结构门禁三态校验（结构基线+修改范围比对）+ 能力池调度执行任务
---

# specpowers-apply — 执行构建

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context (`SKILL.md`), then follow the contract `prompts/apply.md`. Both live in the **main skill directory `specpowers/`** — a sibling of this stage skill (NOT in this skill's own directory):

- 插件市场安装：`${PLUGIN_ROOT}/skills/specpowers/`——`PLUGIN_ROOT` 取宿主任意插件根变量（`*_PLUGIN_ROOT` 形态，如 `${ZCODE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_ROOT}`、`${CODEBUDDY_PLUGIN_ROOT}` 等，新工具同理）；变量不可用时按兄弟目录 `specpowers/` 定位，仍找不到则 Glob 搜索 `**/specpowers/prompts/apply.md`
- pip 安装（`specpowers init --integration <agent>` 或 `--skills-root <路径>`）：`<skills_root>/specpowers/`（如 WorkBuddy `.workbuddy/skills/specpowers/`、Claude `.claude/skills/specpowers/`）

You will:
0. **Init check first**: 检查 `.specpowers/constitution.md` 与 `.specpowers/baseline.json` 是否存在——任一缺失 = 项目未初始化：告知用户「检测到项目未初始化，先自动执行 specpowers-init」，加载 `prompts/init.md` 完整执行初始化（含提示用户提交两产物），完成后回到本技能第 1 步继续；两文件均存在则直接往下执行
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

会话粘滞（v2.7.0；v2.8.0 多活跃）：本对话后续消息默认延续 specpowers 流程语境——相关消息按锚点命中的需求走流程（命中哪个需求就按哪个需求的阶段契约处理）、无关消息照常回答并附一行活跃需求清单提醒（解除条件 per-feature：归档/reset 仅解除该需求的粘滞），多活跃时所有 facade 命令必须显式 --feature <slug>，判定规则见主技能 SKILL.md「会话粘滞」小节。
