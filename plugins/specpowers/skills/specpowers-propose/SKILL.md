---
name: specpowers-propose
description: 生成提案——从设计文档一站式产出 proposal/spec/tasks 三件套；未归档重入即迭代轮增量修订
---

# specpowers-propose — 提案生成

用户输入经技能 args 参数传入（用户直接 `/` 调用时为需求原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context (`SKILL.md`), then follow the contract `prompts/propose.md`. Both live in the **main skill directory `specpowers/`** — a sibling of this stage skill (NOT in this skill's own directory):

- 插件市场安装：`${PLUGIN_ROOT}/skills/specpowers/`——`PLUGIN_ROOT` 取宿主任意插件根变量（`*_PLUGIN_ROOT` 形态，如 `${ZCODE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_ROOT}`、`${CODEBUDDY_PLUGIN_ROOT}` 等，新工具同理）；变量不可用时按兄弟目录 `specpowers/` 定位，仍找不到则 Glob 搜索 `**/specpowers/prompts/propose.md`
- pip 安装（`specpowers init --integration <agent>` 或 `--skills-root <路径>`）：`<skills_root>/specpowers/`（如 WorkBuddy `.workbuddy/skills/specpowers/`、Claude `.claude/skills/specpowers/`）

You will:
0. **Init check first**: 检查 `.specpowers/constitution.md` 与 `.specpowers/baseline.json` 是否存在——任一缺失 = 项目未初始化：告知用户「检测到项目未初始化，先自动执行 specpowers-init」，加载 `prompts/init.md` 完整执行初始化（含提示用户提交两产物），完成后带着原 args 回到本技能第 1 步继续；两文件均存在则直接往下执行
1. **Iteration re-entry check first**: read `.specpowers/state.json` (v2.8.0: features 映射) — if the target feature's `stage` is `apply` (unarchived), follow the「重入识别」section of `prompts/propose.md`: confirm with the user to open Round <N+1> via `facade iterate --feature <slug>`, then revise the existing spec/tasks incrementally (requirement identity is decided by archive state alone, per-feature — same spec until that feature is archived)
2. Otherwise (normal flow): read `.specpowers/constitution.md` for project principles
3. If coming from explore: read the registered design doc (the target feature's `design_doc` in `state.json` features 映射, v2.8.0 per-feature) for decision context, capability, and data-flow conclusions
4. Generate `openspec/changes/<feature>/proposal.md` (OpenSpec Why/What Changes/Capabilities/Impact + 「## 数据流契约」 section distilled from the design doc — apply 阶段硬依赖，缺失会被确定性层拒收)
5. Generate delta spec using OpenSpec format (ADDED Requirements + Scenario, Chinese, real WHEN/THEN) → `openspec/changes/<feature>/specs/<capability>/spec.md`
6. Decompose the delta spec into `openspec/changes/<feature>/tasks.md` (superpowers `writing-plans` slimmed: single tasks.md, `### Task N` headings, 场景引用/验收标准/依赖/并行/检查点 fields, 推荐执行方式 comment block at top; **Do NOT auto-commit**)
7. Self-review: scenario coverage / dependency graph / execution mode fit / cross-link data source backtracking
8. Tell user: next step is `/specpowers-apply`

完成后：三件套已生成到 `openspec/changes/<feature>/`；下一步建议调用技能 specpowers-apply（用户直接 `/specpowers-apply` 调用，auto 模式下模型直接经 Skill 工具调用）。

会话粘滞（v2.7.0；v2.8.0 多活跃）：本对话后续消息默认延续 specpowers 流程语境——相关消息按锚点命中的需求走流程（命中哪个需求就按哪个需求的阶段契约处理）、无关消息照常回答并附一行活跃需求清单提醒（解除条件 per-feature：归档/reset 仅解除该需求的粘滞），多活跃时所有 facade 命令必须显式 --feature <slug>，判定规则见主技能 SKILL.md「会话粘滞」小节。
