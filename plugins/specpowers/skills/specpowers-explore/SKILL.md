---
name: specpowers-explore
description: 探索需求——静默项目探索、方案统一维度对比、设计文档落盘登记；未归档重入即同需求迭代轮
---

# specpowers-explore — 需求探索

用户输入经技能 args 参数传入（用户直接 `/` 调用时为需求原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context, then follow `prompts/explore.md`.

You will:
1. **Iteration re-entry check first**: read `.specpowers/state.json` — if `stage` is `propose`/`apply` and `feature` is non-empty (unarchived), follow the「重入识别」section of `prompts/explore.md`: confirm with the user to open Round <N+1> via `facade iterate` (approach-change path — design doc updated in place, proposal.md regenerated at the propose stage), then hand off to `/specpowers-propose` for incremental spec/tasks revision
2. Otherwise (normal flow): 完整执行 `prompts/explore.md` 第一步的**探索引擎细则**（内联于该契约）：静默项目探索 → 2-3 approaches compared on unified dimensions → single recommendation → design doc written under `docs/specpowers/design/`, incl. data-flow conclusions
3. Interact with the user: clarifying questions, approach trade-offs (use Chinese, AskUserQuestion per `prompts/explore.md`)
4. **Register the design doc** with the deterministic layer (hard gate for propose):
   ```bash
   python -m specpowers_cli.bridge.facade record-design-doc <设计文档路径> --root .
   ```
5. Tell user: next step is `/specpowers-propose "<requirement>"` (one-shot proposal.md + spec.md + tasks.md)

完成后：设计文档已落盘并登记；下一步建议调用技能 specpowers-propose（用户直接 `/specpowers-propose "<需求>"` 调用，auto 模式下模型直接经 Skill 工具调用）。
