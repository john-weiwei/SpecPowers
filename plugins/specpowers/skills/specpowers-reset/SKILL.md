---
name: specpowers-reset
description: 重置流水线状态——清除 state.json 与 lock 回到 ready，不动 baseline
---

# specpowers-reset — 状态重置

用户输入经技能 args 参数传入（用户直接 `/` 调用时为原文，模型经 Skill 工具调用时为编排参数；本技能无额外参数）。

## Outline

Load the specpowers skill context, then run:

```bash
python -m specpowers_cli.bridge.facade reset --root .
```

This clears the pipeline state (stage/feature/mode) and removes any stale lock file. The fallback count is preserved (cannot reset your way around the 1-fallback limit).

Use cases: pipeline stuck mid-stage, lock file left after crash, want to abandon current feature and start fresh.

Note: baseline.json is NOT affected.

完成后：stage 回到 `ready`；可调用技能 specpowers-explore / specpowers-propose / specpowers-fast / specpowers-auto 开启新需求。
