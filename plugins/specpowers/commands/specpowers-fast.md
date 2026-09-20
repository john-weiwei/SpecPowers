---
description: Optimized mode for small changes — skip explore/propose, go directly to code
handoffs:
  - label: Build (After Coding)
    agent: specpowers-apply
    prompt: Build and validate the changes. I've completed the coding for...
---

## User Input

```text
$ARGUMENTS
```

## Outline

Load the specpowers skill context, then follow `prompts/fast_mode.md`.

You will:
1. Analyze the requirement against the small-change signal set (bugfix / single-file / no-new-scenario / config-only / text-only / refactor-only)
2. Output structured judgment: `[理由：<signals>，置信度：<高/中/低>]`
3. If small: present confirmation prompt. User confirms → skip to coding.
4. If not small: suggest upgrading to full pipeline (`/specpowers-explore` or `/specpowers-propose`)
5. Generate 3-5 item acceptance checklist
6. User completes their own coding, then runs `/specpowers-apply`
