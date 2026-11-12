---
name: specpowers-explore
description: 探索需求——静默项目探索、方案统一维度对比、设计文档落盘登记；未归档重入即同需求迭代轮
---

# specpowers-explore — 需求探索

用户输入经技能 args 参数传入（用户直接 `/` 调用时为需求原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context (`SKILL.md`), then follow the contract `prompts/explore.md`. Both live in the **main skill directory `specpowers/`** — a sibling of this stage skill (NOT in this skill's own directory):

- 插件市场安装：`${PLUGIN_ROOT}/skills/specpowers/`——`PLUGIN_ROOT` 取宿主任意插件根变量（`*_PLUGIN_ROOT` 形态，如 `${ZCODE_PLUGIN_ROOT}`、`${CLAUDE_PLUGIN_ROOT}`、`${CODEBUDDY_PLUGIN_ROOT}` 等，新工具同理）；变量不可用时按兄弟目录 `specpowers/` 定位，仍找不到则 Glob 搜索 `**/specpowers/prompts/explore.md`
- pip 安装（`specpowers init --integration <agent>` 或 `--skills-root <路径>`）：`<skills_root>/specpowers/`（如 WorkBuddy `.workbuddy/skills/specpowers/`、Claude `.claude/skills/specpowers/`）

## 硬性产出契约（HARD DELIVERABLES）

以下四条为本阶段底线，**即使上方契约文件未能读取也必须成立**（完整流程、规则表与三模板见 `prompts/explore.md`）：

1. **静默探索，禁止提问循环**：先读项目代码再出方案；全程不逐个向用户提问，需用户决策的事项收集后在探索结论之后一次性批量提出，或打「需用户裁决」标记
2. **方案对比必须展示在对话中**：2-3 个方案 × 统一维度（核心思路/复杂度/性能影响/兼容性/推荐度）对比表 + 唯一推荐方案与推荐理由（禁止"都可以"）
3. **设计文档必须落盘**（不只在对话中展示）：Write 到 `docs/specpowers/design/YYYY-MM-DD-{name}-design.md`，中文，含 项目上下文/需求分析/方案对比/详细设计（架构/组件/数据流/接口/错误处理）/修改范围 章节，无 TBD/TODO 占位
4. **落盘后必须登记**（propose 硬依赖，未登记的设计文档 propose 阶段拒收）；`python -m` 执行失败时改用包装脚本 fallback（见主技能 SKILL.md「执行方式」节）

You will:
0. **Init check first**: 检查 `.specpowers/constitution.md` 与 `.specpowers/baseline.json` 是否存在——任一缺失 = 项目未初始化：告知用户「检测到项目未初始化，先自动执行 specpowers-init」，加载 `prompts/init.md` 完整执行初始化（含提示用户提交两产物），完成后带着原 args 回到本技能第 1 步继续；两文件均存在则直接往下执行
1. **Iteration re-entry check first**: read `.specpowers/state.json` (v2.8.0: features 映射,多需求各自一行) — if the target feature's `stage` is `propose`/`apply` (unarchived), follow the「重入识别」section of `prompts/explore.md`: confirm with the user to open Round <N+1> via `facade iterate` (approach-change path — a lightweight `design-round-<N>.md` delta doc lands in the change dir, the baseline design doc stays untouched and stays registered, proposal.md regenerated at the propose stage), then hand off to `/specpowers-propose` for incremental spec/tasks revision
2. Otherwise (normal flow): 完整执行 `prompts/explore.md` 第一步的**探索引擎细则**（内联于该契约）：静默项目探索 → 2-3 approaches compared on unified dimensions → single recommendation → design doc written under `docs/specpowers/design/`, incl. data-flow conclusions
3. Interact with the user **only for genuinely irreversible decisions** (approach selection with no clear winner / ambiguous requirements): batch them into ONE AskUserQuestion round **after** presenting the exploration conclusion — 默认不打断用户，禁止逐个提问循环（use Chinese, per `prompts/explore.md` 交互决策原则）
4. **Register the design doc** with the deterministic layer (hard gate for propose):
   ```bash
   python -m specpowers_cli.bridge.facade record-design-doc <设计文档路径> --root .
   ```
5. Tell user: next step is `/specpowers-propose "<requirement>"` (one-shot proposal.md + spec.md + tasks.md)

完成后：设计文档已落盘并登记；下一步建议调用技能 specpowers-propose（用户直接 `/specpowers-propose "<需求>"` 调用，auto 模式下模型直接经 Skill 工具调用）。

会话粘滞（v2.7.0；v2.8.0 多活跃）：本对话后续消息默认延续 specpowers 流程语境——相关消息按锚点命中的需求走流程（命中哪个需求就按哪个需求的阶段契约处理）、无关消息照常回答并附一行活跃需求清单提醒（解除条件 per-feature：归档/reset 仅解除该需求的粘滞），多活跃时所有 facade 命令必须显式 --feature <slug>，判定规则见主技能 SKILL.md「会话粘滞」小节。
