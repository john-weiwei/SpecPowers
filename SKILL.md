---
name: specpowers
description: 桥接编排插件 — 在 OpenSpec / spec-kit / superpowers 之上叠加结构一致性门禁与实时卡转人工，六阶段流水线（constitution→brainstorm→specify→plan→build→archive）+ 优化模式
version: 1.0.0
---

# SpecPowers 桥接插件

> **定位**：薄桥接层（Facade + Adapter + Dispatcher），不重写任何框架引擎。只复用 OpenSpec / spec-kit / superpowers 原生能力，补上两条它们都没有的硬约束：**结构一致性门禁**、**实时卡转人工**。

## 三个概念

| 概念 | 说明 |
|------|------|
| ① 项目原则 | `/specpowers.constitution` — 生成 constitution.md（质量/测试/UX/性能 四类原则）+ 扫描结构基线 |
| ② 特性流水线 | `/specpowers.brainstorm` → `.specify` → `.plan` → `.build` → `.archive` 六阶段 |
| ③ 收尾 | `/specpowers.archive` — delta 合并（常规）或 git commit+stub（优化） |

## 两个开关

| 开关 | 说明 |
|------|------|
| ① 优化模式 | `/specpowers.fast` — 判小跳 spec/plan，直进 build |
| ② 基线刷新 | `/specpowers.baseline` — 手动重扫结构基线 |

---

## 流水线总览

```
constitution ─▶ ready ─┬─(brainstorm)──▶ brainstorm ─▶ specify ─▶ plan ─▶ build ─▶ archive ─▶ ready
                       ├─(specify)─────▶ specify ─▶ plan ─▶ build ─▶ archive ─▶ ready
                       └─(fast)──▶(用户编码)──▶ build ─▶ archive ─▶ ready
```

---

## 命令参考

| 命令 | 参数 | 合法 from_stage | 说明 |
|------|------|----------------|------|
| `/specpowers.constitution` | `[--force]` | constitution / 任意(需确认) | 生成原则 + 扫基线 |
| `/specpowers.brainstorm` | `"<需求>"` | ready | 探索 + 写 brief.md |
| `/specpowers.specify` | `"<需求>"` | brainstorm / ready / build(fallback) | 生成 spec.md |
| `/specpowers.fast` | `"<需求>"` | ready | 声明优化模式 |
| `/specpowers.plan` | — | specify | 生成 plan.md |
| `/specpowers.build` | — | plan / ready(fast) | 执行构建 + 门禁 |
| `/specpowers.archive` | `[--force-merge-check]` | build | 收尾归档 |
| `/specpowers.baseline` | — | 任意 | 手动刷新基线 |
| `/specpowers.reset` | — | 任意 | 重置 state+lock |

---

## 执行方式

所有阶段命令先调用确定性层获取状态/校验，再加载对应 `prompts/` 契约执行认知任务：

```bash
python bridge/facade.py <subcommand> [--root <path>] [options]
```

**自动读取契约强制**：每个阶段开始前，Dispatcher 自动校验本阶段必读上游产物是否存在。缺必读 → 拒绝开工。

---

## 契约文件

| 文件 | 职责 |
|------|------|
| `prompts/constitution.md` | 触发 `/speckit.constitution`；聚焦 4 类原则；不承载结构规则 |
| `prompts/brainstorm.md` | 收口契约：结构化决策摘要 → brief.md 落盘；判小信号映射 |
| `prompts/specify.md` | OpenSpec 场景格式；自动读 brief.md + constitution |
| `prompts/plan.md` | writing-plans 瘦身：合并 spec-kit tasks 进 plan.md |
| `prompts/build.md` | 实时门禁三态 + 能力池调度 + 验收清单消费 |
| `prompts/archive.md` | 四职责收尾；优化 stub；合体后校验 |
| `prompts/fast_mode.md` | 判小 prompt / 确认交互 / 回退 / 清单 |

---

## 安全底线

- 所有用户输入参数化传递，禁止拼入 shell 命令字符串
- git 操作使用参数列表调用 subprocess（bridge/core/git_util.py）
- `.specpowers/state.json` 原子写（临时文件 + rename）
- `.specpowers/.lock` 防重入，含死锁检测

## 团队协作

- `baseline.json` → 提交 git（团队共享基线）
- `state.json` / `audit.log` / `.lock` → `.gitignore`（个人本地）
