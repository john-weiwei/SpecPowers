---
name: specpowers-propose
description: 生成提案——从设计文档一站式产出 proposal/spec/tasks 三件套；未归档重入即迭代轮增量修订
---

# specpowers-propose — 提案生成

用户输入经技能 args 参数传入（用户直接 `/` 调用时为需求原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context, then follow `prompts/propose.md`.

You will:
1. **Iteration re-entry check first**: read `.specpowers/state.json` — if `stage` is `apply` and `feature` is non-empty (unarchived), follow the「重入识别」section of `prompts/propose.md`: confirm with the user to open Round <N+1> via `facade iterate`, then revise the existing spec/tasks incrementally (requirement identity is decided by archive state alone — same spec until archived)
2. Otherwise (normal flow): read `.specpowers/constitution.md` for project principles
3. If coming from explore: read the registered design doc (`state.json` `design_doc` field) for decision context, capability, and data-flow conclusions
4. Generate `openspec/changes/<feature>/proposal.md` (OpenSpec Why/What Changes/Capabilities/Impact + 「## 数据流契约」 section distilled from the design doc — apply 阶段硬依赖，缺失会被确定性层拒收)
5. Generate delta spec using OpenSpec format (ADDED Requirements + Scenario, Chinese, real WHEN/THEN) → `openspec/changes/<feature>/specs/<capability>/spec.md`
6. Decompose the delta spec into `openspec/changes/<feature>/tasks.md` (superpowers `writing-plans` slimmed: single tasks.md, `### Task N` headings, 场景引用/验收标准/依赖/并行/检查点 fields, 推荐执行方式 comment block at top; **Do NOT auto-commit**)
7. Self-review: scenario coverage / dependency graph / execution mode fit / cross-link data source backtracking
8. Tell user: next step is `/specpowers-apply`

完成后：三件套已生成到 `openspec/changes/<feature>/`；下一步建议调用技能 specpowers-apply（用户直接 `/specpowers-apply` 调用，auto 模式下模型直接经 Skill 工具调用）。
