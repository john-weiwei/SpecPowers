---
name: specpowers-baseline
description: 刷新结构基线——重扫顶层目录、依赖清单与源码规律，覆盖 baseline.json
---

# specpowers-baseline — 基线刷新

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数；本技能无额外参数）。

## Outline

Load the specpowers skill context, then run:

```bash
python -m specpowers_cli.bridge.facade baseline --root .
```

This re-scans the project and overwrites `.specpowers/baseline.json`. Prompt the user to review and commit the updated baseline for team sharing.

Use cases: team member added new top-level directories, introduced new dependency types, or baseline is stale (long time since the last refresh).

完成后：提示用户检查并提交更新后的 `.specpowers/baseline.json`（团队共享）。
