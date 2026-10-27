# auto-iteration.md — 迭代轮编排（auto 分支 C 详表）

> **加载时机**：`auto-status` 判定 `mode=iterate`（分支 C）时由主契约 `prompts/auto.md` 按需加载；fresh / resume 轮**不加载**本文件。

## 第 1 步：受控轮次切换（确定性层）

```bash
python -m specpowers_cli.bridge.facade auto new-round [--design-doc <路径>] [--instruction "<描述>"] --root .
```

确定性层完成：校验未归档 → `stage` 置回 `propose`、**feature 锁定不变**、`iteration_count += 1`、`execution_mode` 清空；`auto_base.json` 追加本轮 `rounds` 记录（旧格式无 `rounds` 字段时自动按 round 1 迁移）。

**feature slug 首轮锁定，归档前不变**：后续 explore/propose 一律携带 `--feature <锁定slug>` 调用，保证同一需求永远落同一 change 目录。功能名变更只记录裁决、不改 change 目录名（汇总报告「遗留风险」注明）。

## 第 2 步：迭代增量澄清（不回退已跑深度）

迭代轮不重做全量五维（上一轮已跑过的深度不回退），按本轮输入形态做**增量澄清**：

| 本轮输入形态 | 澄清范围 |
|--------------|----------|
| 新文档 / 文档变更 | 增量五维：① 新旧 `parsed` 冲突点自洽性（维度 2）；② 调整是否触碰硬性边界（维度 5）；③ 新增/变更场景可测性（维度 3）。「已定方案」发生变更 → 升级为全量五维 |
| 仅口头指令 | 指令澄清：① 指令能否无歧义映射到现有 scenario 增/删/改（对齐下方深度判定的轻量条件）；② 是否触碰硬性边界（维度 5）。**上一轮停靠在 explore（方案待定）时，指令即方案结论** → ceiling 上调 `full`，按方案变更全量路径在草案基础上收敛 |

增量澄清结论（含 ceiling 维持/上调）以 `### Round <N>` 追加进澄清报告，并调 `facade auto clarify` 刷新登记；发现的新歧义/矛盾按主契约「五维检查清单」对应维度处置。

## 第 3 步：迭代深度判定（裁决规则表扩充）

| 输入情况 | 路径 | 重跑范围 |
|----------|------|----------|
| 新文档/文档变更，且「已定方案」变了 | 全量 | explore 更新设计文档 → propose → apply → review |
| 文档变更但方案不变，场景/范围有调整 | 全量 | propose → apply → review |
| 口头小调整，能无歧义映射到现有 scenario 的增/删/改，不引入新 capability、不碰硬边界 | 轻量 | propose 增量修订三件套 → apply → review |
| 深度判定有疑义 | **保守取全量** | — |

**轻量路径硬底线**：再小的调整也必须修订 spec.md 并过 specpowers-review；轻量只是跳过 explore，不跳过 spec。

## 第 4 步：按深度执行阶段

各阶段调用方式与人工模式完全一致（先调 facade 确定性层，再按对应 `prompts/<stage>.md` 契约执行认知任务），各阶段**迭代轮语义**以对应契约文件的「迭代轮」小节为准（该语义为 auto 与人工模式通用）：

- explore：方案变了才重跑，设计文档覆盖 + 追加「## 迭代历史」。**注意**：这是认知任务直接落盘更新设计文档，**不调 `facade explore`**（其 from_stage 仅 ready，与迭代轮 stage=propose 冲突；stage 保持 propose 即可，更新后重新 `facade record-design-doc` 刷新登记，propose 的前置校验天然满足）
- propose：proposal/spec/tasks 三件套**增量修订**（spec 增量修订场景 + tasks 分轮演进 Round N 小节 + 作废留痕）
- apply：只执行未勾选且未作废的任务
- specpowers-review：范围 = 首轮基点 → 当前（累计审查，编排细则读 `refs/auto-review.md`）

迭代轮**默认不归档**，跑完止于 specpowers-review；`--archive` 显式收口见 `refs/auto-review.md`「归档收口」。

> **人工模式同一语义**：未归档需求要调整时，重入 `/specpowers-propose`（场景/范围调整）或 `/specpowers-explore`（方案变更），经重入识别确认后调同一个 `facade iterate` 完成轮次切换（不要求 auto_base.json）；轮次切换、feature 锁定、各契约迭代轮小节与本文件完全共用。区别仅在人工模式允许与用户交互确认方案是否变更，不适用无人值守裁决规则表。
