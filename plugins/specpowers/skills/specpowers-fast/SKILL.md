---
name: specpowers-fast
description: 判定小改动走快速通道——跳过探索与提案直接编码，完成后进 apply 收尾
---

# specpowers-fast — 快速通道

用户输入经技能 args 参数传入（用户直接 `/` 调用时为需求原文，模型经 Skill 工具调用时为编排参数）。

## Outline

Load the specpowers skill context, then follow `prompts/fast_mode.md`.

You will:
1. Analyze the requirement against the small-change signal set (bugfix / single-file / no-new-scenario / config-only / text-only / refactor-only)
2. Output structured judgment: `[理由：<signals>，置信度：<高/中/低>]`
3. If small: present confirmation prompt. User confirms → skip to coding.
4. If not small: suggest upgrading to full pipeline (`/specpowers-explore` or `/specpowers-propose`)
5. Generate 3-5 item acceptance checklist
6. User completes their own coding, then runs `/specpowers-apply`

完成后：用户自行编码，然后建议调用技能 specpowers-apply（用户直接 `/specpowers-apply` 调用，auto 模式下模型直接经 Skill 工具调用）。
