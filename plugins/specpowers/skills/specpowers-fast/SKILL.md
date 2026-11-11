---
name: specpowers-fast
description: 判定小改动走快速通道——跳过探索与提案直接编码，完成后进 apply 收尾
---

# specpowers-fast — 快速通道

用户输入经技能 args 参数传入（用户直接 `/` 调用时为需求原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context (`SKILL.md`), then follow the contract `prompts/fast_mode.md`. Both live in the **main skill directory `specpowers/`** — a sibling of this stage skill (NOT in this skill's own directory):

- 插件市场安装：`${PLUGIN_ROOT}/skills/specpowers/`——`PLUGIN_ROOT` 取宿主任意插件根变量（`*_PLUGIN_ROOT` 形态，如 `${ZCODE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_ROOT}`、`${CODEBUDDY_PLUGIN_ROOT}` 等，新工具同理）；变量不可用时按兄弟目录 `specpowers/` 定位，仍找不到则 Glob 搜索 `**/specpowers/prompts/fast_mode.md`
- pip 安装（`specpowers init --integration <agent>` 或 `--skills-root <路径>`）：`<skills_root>/specpowers/`（如 WorkBuddy `.workbuddy/skills/specpowers/`、Claude `.claude/skills/specpowers/`）

You will:
0. **Init check first**: 检查 `.specpowers/constitution.md` 与 `.specpowers/baseline.json` 是否存在——任一缺失 = 项目未初始化：告知用户「检测到项目未初始化，先自动执行 specpowers-init」，加载 `prompts/init.md` 完整执行初始化（含提示用户提交两产物），完成后带着原 args 回到本技能第 1 步继续；两文件均存在则直接往下执行
1. Analyze the requirement against the small-change signal set (bugfix / single-file / no-new-scenario / config-only / text-only / refactor-only)
2. Output structured judgment: `[理由：<signals>，置信度：<高/中/低>]`
3. If small: present confirmation prompt. User confirms → skip to coding.
4. If not small: suggest upgrading to full pipeline (`/specpowers-explore` or `/specpowers-propose`)
5. Generate 3-5 item acceptance checklist
6. User completes their own coding, then runs `/specpowers-apply`

完成后：用户自行编码，然后建议调用技能 specpowers-apply（用户直接 `/specpowers-apply` 调用，auto 模式下模型直接经 Skill 工具调用）。

会话粘滞（v2.7.0）：本对话后续消息默认延续 specpowers 流程语境——相关消息走流程、无关消息照常回答并附一行活跃需求提醒（解除条件=归档/reset），判定规则见主技能 SKILL.md「会话粘滞」小节。
