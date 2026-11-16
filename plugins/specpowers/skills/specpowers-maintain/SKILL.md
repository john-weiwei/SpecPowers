---
name: specpowers-maintain
description: 重置流水线状态或刷新结构基线——按用户意图分流执行两项维护动作
---

# specpowers-maintain — 维护（状态重置 / 基线刷新）

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数；自由文本，可为空）。**用户无需记忆任何参数**——自然语言描述意图即可（如「放弃这个需求」「刷新一下基线」），分流判断由模型完成。

## 分流规则（三层判定）

1. **意图语义判断（主路径）**：意图指向「放弃需求 / 流水线卡死 / 锁残留 / 恢复重来 / 归档冲突同步」→ 执行分支 A（状态重置）；指向「刷新基线 / 新增顶层目录 / 新增依赖类型 / 基线过期」→ 执行分支 B（基线刷新）。
2. **显式子动作词（快捷形态）**：args 或触发语境含 `reset` / `baseline` 字样时直接按词分流——确定性层报错文案（锁冲突 / state 损坏 / 基线过期提示）引导的调用形态自带子动作词，模型照抄即可。
3. **意图不明 → 必问**：args 为空且无法从语境判定意图时，**不得执行任何命令**，输出两个动作的说明让用户选择（重置是破坏性动作、基线刷新是覆盖性动作，均不可猜）。

## Outline

Load the specpowers skill context (`SKILL.md`) — it lives in the **main skill directory `specpowers/`**, a sibling of this stage skill (插件市场 `${PLUGIN_ROOT}/skills/specpowers/`；pip 安装 `<skills_root>/specpowers/`，如 WorkBuddy `.workbuddy/skills/specpowers/`) — then run the branch selected by the routing rules above:

### 分支 A：状态重置（reset）

```bash
python -m specpowers_cli.bridge.facade reset [--feature <slug>] --root .
```

v2.8.0 multi-active: `--feature <slug>` abandons only that feature (removed from the features map + its auto_base cleaned); with multiple active features the slug is **required** (the command refuses to clear them all at once); single/zero active features = full clear (legacy behavior). This removes any stale lock file. The fallback count is preserved (cannot reset your way around the 1-fallback limit).

Use cases: pipeline stuck mid-stage, lock file left after crash, want to abandon one of several active features (or the only one) and start fresh; archive duplicate error (remote already archived) → `git pull` then reset to sync.

Note: baseline.json is NOT affected.

完成后：stage 回到 `ready`；可调用技能 specpowers-explore / specpowers-propose / specpowers-fast / specpowers-auto 开启新需求。

### 分支 B：基线刷新（baseline）

```bash
python -m specpowers_cli.bridge.facade baseline --root .
```

This re-scans the project and overwrites `.specpowers/baseline.json`. Prompt the user to review and commit the updated baseline for team sharing.

Use cases: team member added new top-level directories, introduced new dependency types, or baseline is stale (long time since the last refresh).

完成后：提示用户检查并提交更新后的 `.specpowers/baseline.json`（团队共享）。
