# SpecPowers 多轮迭代方案（定稿）

> **⚠️ v2.0.0 阶段名变更注记**：本文档为 v1.x 定稿方案，文中阶段名 constitution/brainstorm/specify/plan/build 已于 v2.0.0 重命名为 init/explore/propose(合并 specify+plan)/apply，语义不变；ceiling 值 `brainstorm` 相应改为 `explore`。本文按原文保留作历史依据，不再回改。

> 背景：需求期望「一个需求无论修改多少次、执行多少遍 `/specpowers-auto`，没有执行归档之前，所有调整都记录在当前 spec 文件内；执行归档则认为是一个新的需求」。本方案经讨论定稿，作为实现依据。

## 1. 核心语义

**需求身份由归档状态唯一决定，与设计文档解耦**：

- **未归档**（state 有活跃 feature）：无论带什么输入重入 auto——新文档、原文档、还是无文档口头指令——都是**同一需求的新一轮迭代**，一切调整落在当前 change 目录（当前 spec 文件内）
- **已归档**（stage=ready 且 feature 空）：任何输入都视为**全新需求**，新 slug、新 change 目录
- 归档是需求生命周期的唯一终结符；迭代轮数**不设上限**，由归档自然收口

## 2. 重入三分判定（确定性层 `facade auto-status`）

```bash
facade auto-status [--design-doc <path>] [--instruction "<描述>"] [--archive]
```

输出 JSON：`mode`、`iteration_scope 建议`、`feature`、`round`、`reason`。判定逻辑：

```
auto_base.json 残留但 state 已归档 → 清理残留，mode=fresh
state=ready 且 feature 空         → mode=fresh（首轮 auto，文档必填）
有活跃 feature 且未归档：
  无新输入（无文档或文档 hash 未变、无指令、无 --new-round）且存在产物缺口
                                   → mode=resume（断点续跑，现状逻辑）
  有任一新输入                     → mode=iterate（迭代轮）
```

配套 `facade auto new-round`：校验未归档 → stage 置回 specify 前置态、feature 锁定不变、`iteration_count += 1`、落盘本轮输入记录。`fs_state.py` 的 `DEFAULT_STATE` 新增 `iteration_count` 字段；`fallback_count` 语义不动（人工 build→specify 回退仍限 1 次，迭代轮不占额度）。

**人工模式入口形态（实现定稿）**：不设独立 `/specpowers-iterate` 命令。未归档需求要调整时，用户直接重入 `/specpowers-specify`（场景/范围调整）或 `/specpowers-brainstorm`（方案变更），对应契约的「重入识别」小节经**交互确认**后调用同一个 `facade iterate`（轮次切换原语，不要求 auto_base.json）。配套状态机补 specify 自环（from `specify` 重跑幂等放行），保证迭代轮中重跑 `/specpowers-specify` 属续作（轮次不变、不占 fallback 额度）。

## 3. 迭代轮编排

### 3.1 深度分级（裁决规则表扩充）

| 输入情况 | 路径 | 重跑范围 |
|----------|------|----------|
| 新文档/文档变更，且「已定方案」变了 | 全量 | brainstorm 更新 proposal → specify → plan → build → review |
| 文档变更但方案不变，场景/范围有调整 | 全量 | specify → plan → build → review |
| 口头小调整，能无歧义映射到现有 scenario 的增/删/改，不引入新 capability、不碰硬边界 | 轻量 | specify 增量 → plan 增量 → build → review |
| 深度判定有疑义 | **保守取全量** | — |

**轻量路径硬底线**：再小的调整也必须修订 spec.md 并过 specpowers-review；轻量只是跳过 brainstorm，不跳过 spec。

### 3.2 八要素处理

- 有文档（新旧路径均可）→ 整体重解析，替换 `parsed`
- 无文档 → 上一轮 `parsed` 作基线，`--instruction` 作为增量修正叠加，形成本轮有效八要素并落盘
- **feature slug 首轮锁定，归档前不变**；功能名变更只记录裁决、不改 change 目录名，汇总报告「遗留风险」注明

### 3.3 specpowers-review（内置技能）

- `base_commit` 保持**首轮基点**，跨轮不变 → 审查范围 = 首轮基点 → 当前 HEAD + 工作区，天然覆盖多轮累计改动，不漏审
- 复审上限 2 轮是**单轮内**的发现→修复→验证闭环，与需求迭代轮次（`iteration_count`）是两个概念，报告分别呈现
- `--archive` 收口前置检查：存在未收敛的 blocking P1/P2 → **停下报告、不归档**（归档意味着需求终结，带病归档不合理；人工裁决后可手动 `/specpowers-archive`）

## 4. 各产物迭代语义

| 产物 | 多轮语义 |
|------|----------|
| spec.md | **增量修订**：对照本轮有效八要素「必测场景清单」——场景仍存→更新 WHEN/THEN；已删→从 delta 移除；新增→追加。归档前 delta 只在 change 内，修订安全 |
| proposal.md | 覆盖更新，文末追加「## 迭代历史」小节记录每轮变化点 |
| tasks.md | **单文件分轮演进**（任务台账）：按 `## Round N` 分节；已完成 `[x]` 跨轮保留不动；被本轮调整作废的任务移入「已作废」小节（删除线 + 作废依据留痕，不物理删除）；本轮新任务写入新轮小节 |
| build 消费 | **只执行未勾选且未作废的任务**，无需预勾选补丁 |
| archive 校验 | 「任务全部完成」判定**跳过「已作废」小节** |

## 5. 归档收口（双通道，均已确认支持）

| 通道 | 行为 |
|------|------|
| **手动 `/specpowers-archive`** | 迭代轮跑完 stage 停在 build，archive 的合法 from_stage 就是 build，直接可用；归档即宣告新需求 |
| **重入 auto 加 `--archive`** | 本轮（fresh/resume/iterate）跑完 build + review 后追加执行归档步；经 3.3 的 blocking 检查后执行 |
| 默认值 | **任何轮次（fresh/resume/iterate）默认都不归档**，止于 specpowers-review；归档仅经手动 `/specpowers-archive` 或显式 `--archive`（过收口前置检查）；v1.3.0 起移除 `--no-archive`（不再有默认归档需要关闭） |

归档动作统一在确定性层 `_handle_archive` 成功后**清理 `auto_base.json`**（两个通道都生效）；`auto_decisions.md` 演进为 `.specpowers/auto_decisions/<feature>.md`，归档后保留作审计历史。

## 6. 硬阻断与边界

- 硬阻断定义不变（外部依赖不可用且无降级、状态机不一致无法自愈、文档自相矛盾、参数错误：**fresh 模式无文档即参数错误**）
- 续跑兼容：无 `auto_base.json` 且 state 干净 → 走现有全新执行；旧格式 `auto_base.json`（无 `rounds` 字段）读到后按 round 1 兼容迁移

## 7. 改动落点清单

| 层 | 文件 | 改动 |
|----|------|------|
| 确定性层 | `plugins/specpowers/scripts/specpowers_cli/bridge/facade.py` | 新增 `auto-status`、`auto new-round` 子命令；brainstorm/specify 支持 `--feature` 显式锁定 |
| 确定性层 | `plugins/specpowers/scripts/specpowers_cli/bridge/dispatcher.py` | feature 锁定扩展；`_handle_archive` 成功后清理 `auto_base.json`；new-round 受控轮次切换处理器 |
| 确定性层 | `plugins/specpowers/scripts/specpowers_cli/bridge/core/fs_state.py` | `DEFAULT_STATE` 增加 `iteration_count` |
| 契约层 | `plugins/specpowers/skills/specpowers/prompts/auto.md` | 重写重入判定（三分 + 输入形态 + 深度分级）、迭代轮编排表、`--archive`、八要素基线+增量、review 基点策略、收口前置检查 |
| 契约层 | `plugins/specpowers/skills/specpowers/prompts/specify.md` | 迭代轮 spec.md 增量修订规则（保留/更新/删除/新增场景） |
| 契约层 | `plugins/specpowers/skills/specpowers/prompts/brainstorm.md` | 迭代轮 proposal.md 覆盖 + 「## 迭代历史」 |
| 契约层 | `plugins/specpowers/skills/specpowers/prompts/plan.md` | tasks.md 分轮演进规则、差异分析、作废留痕 |
| 契约层 | `plugins/specpowers/skills/specpowers/prompts/build.md` | 只执行未勾选未作废任务 |
| 契约层 | `plugins/specpowers/skills/specpowers/prompts/archive.md` | 完成判定跳过作废小节 |
| 命令/模板 | `plugins/specpowers/commands/specpowers-auto.md`、`plugins/specpowers/skills/specpowers/templates/auto-summary-template.md` | 新参数语义；报告增加需求迭代轮次、本轮输入与调整范围、review 覆盖区间 |
| 测试 | `tests/test_dispatcher.py`、`tests/test_fs_state.py` 等 | 三分判定、迭代跃迁、作废小节跳过、归档清理、旧格式迁移用例 |

## 8. 实现顺序

1. 确定性层：`fs_state.py`（iteration_count）→ `dispatcher.py`（feature 锁定、archive 清理、new-round）→ `facade.py`（auto-status / auto new-round 子命令）+ 对应测试
2. 契约层：`auto.md` 重写 → `specify.md` / `brainstorm.md` / `plan.md` / `build.md` / `archive.md` 迭代语义
3. 命令与模板：`specpowers-auto.md`、`auto-summary-template.md`
4. 全量回归：`python -m pytest tests/ -v`
