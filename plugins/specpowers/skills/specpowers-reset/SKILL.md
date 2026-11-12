---
name: specpowers-reset
description: 重置流水线状态——清除 state.json 与 lock 回到 ready，不动 baseline
---

# specpowers-reset — 状态重置

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数；本技能无额外参数）。

## Outline

Load the specpowers skill context (`SKILL.md`) — it lives in the **main skill directory `specpowers/`**, a sibling of this stage skill (插件市场 `${PLUGIN_ROOT}/skills/specpowers/`；pip 安装 `<skills_root>/specpowers/`，如 WorkBuddy `.workbuddy/skills/specpowers/`) — then run:

```bash
python -m specpowers_cli.bridge.facade reset [--feature <slug>] --root .
```

v2.8.0 multi-active: `--feature <slug>` abandons only that feature (removed from the features map + its auto_base cleaned); with multiple active features the slug is **required** (the command refuses to clear them all at once); single/zero active features = full clear (legacy behavior). This removes any stale lock file. The fallback count is preserved (cannot reset your way around the 1-fallback limit).

Use cases: pipeline stuck mid-stage, lock file left after crash, want to abandon one of several active features (or the only one) and start fresh.

Note: baseline.json is NOT affected.

完成后：stage 回到 `ready`；可调用技能 specpowers-explore / specpowers-propose / specpowers-fast / specpowers-auto 开启新需求。
