---
name: specpowers-archive
description: 归档收尾——原则核查、产物标记与合体后校验，合并 delta spec 到主规格
---

# specpowers-archive — 归档收尾

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数；`--force-merge-check` 强制多分支合并校验）。

## Outline

Load the specpowers skill context (`SKILL.md`), then follow the contract `prompts/archive.md`. Both live in the **main skill directory `specpowers/`** — a sibling of this stage skill (NOT in this skill's own directory):

- 插件市场安装：`${PLUGIN_ROOT}/skills/specpowers/`——`PLUGIN_ROOT` 取宿主任意插件根变量（`*_PLUGIN_ROOT` 形态，如 `${ZCODE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_ROOT}`、`${CODEBUDDY_PLUGIN_ROOT}` 等，新工具同理）；变量不可用时按兄弟目录 `specpowers/` 定位，仍找不到则 Glob 搜索 `**/specpowers/prompts/archive.md`
- pip 安装（`specpowers init --integration <agent>` 或 `--skills-root <路径>`）：`<skills_root>/specpowers/`（如 WorkBuddy `.workbuddy/skills/specpowers/`、Claude `.claude/skills/specpowers/`）

**Init check first**: 检查 `.specpowers/constitution.md` 与 `.specpowers/baseline.json` 是否存在——任一缺失 = 项目未初始化：告知用户「检测到项目未初始化，先自动执行 specpowers-init」，加载 `prompts/init.md` 完整执行初始化（含提示用户提交两产物），完成后回到本技能继续归档流程；两文件均存在则直接往下执行。

**Three duties** (archive never rejects, only escalates to human):

1. **Constitution check**: verify evidence exists for quality/testing/UX/performance principles. Missing evidence → warn but proceed.
2. **Finalize artifacts**: mark `openspec/changes/<feature>/tasks.md` tasks complete.
3. **Post-merge verification**: auto-detect multi-branch merges (merge commits or multi-author) → run structure consistency check. `--force-merge-check` forces this for rebase/squash workflows.

**Full 与 Fast 模式统一**：dispatcher 调用 `openspec archive <feature> --yes --json` 归档（合并主规格 `openspec/specs/<capability>/spec.md` + change 快照 `openspec/changes/archive/YYYY-MM-DD-<feature>/`；fast 模式下 capability = feature）。强依赖 openspec CLI，CLI 不可用时拒绝归档（不降级）。full 与 fast 的唯一区别：fast 无 proposal.md（OpenSpec archive 对 proposal 内容是 informative only，不阻塞）。

After archive: stage resets to `ready`, feature name cleared. Ready for next feature.

**Do NOT commit code**: archive only finalizes (openspec archive + state transition), never runs `git add` / `git commit` — committing is left to the user.

完成后：stage 回到 `ready`；建议用户提交代码，下一个需求可调用技能 specpowers-explore / specpowers-propose / specpowers-fast / specpowers-auto（按需求形态四选一）。

会话粘滞（v2.7.0）：归档后活跃需求清空，粘滞自然解除——此前本对话后续消息默认延续 specpowers 流程语境（判定规则见主技能 SKILL.md「会话粘滞」小节）。
