# auto-summary-template.md — /specpowers-auto 汇总报告模板

> `/specpowers-auto` 结束时（正常收尾或硬阻断停下）按本模板输出汇总报告。全部中文；
> 方括号为占位符，按实际情况填写；无对应内容的段落写「无」并说明原因，不得删除段落。

# /specpowers-auto 执行汇总：<功能名>

- **执行模式**：无人值守直通（constitution → brainstorm → specify → plan → build → codex-review → archive）
- **执行结果**：正常收尾 / 硬阻断停下（第 <N> 步）
- **设计文档**：<路径>
- **审查基点**：<base_commit SHA>（记录于 `.specpowers/auto_base.json`）
- **审查方式**：codex-review 技能 / 降级自审 checklist（二选一，降级时注明原因）

## 一、各阶段产物路径

| 阶段 | 产物 | 路径 |
|------|------|------|
| constitution | constitution.md | `.specpowers/constitution.md` |
| brainstorm | proposal.md | `openspec/changes/<feature>/proposal.md` |
| specify | spec.md | `openspec/changes/<feature>/specs/.../spec.md` |
| plan | tasks.md | `openspec/changes/<feature>/tasks.md` |
| build | 代码 + 测试 | <涉及目录> |
| codex-review | 审查记录 | <落盘路径，如有> |
| archive | 归档结果 | `openspec/specs/<capability>/spec.md`（归档后） |

## 二、实际修改 / 新增文件清单

**修改（<N> 处）**：

- <文件路径> — <一句话改动说明>

**新增（<N> 个）**：

- <文件路径> — <一句话用途说明>

## 三、review 结论与修复清单

- **迭代轮次**：<N> 轮（上限 2 轮）
- **最终结论**：<无本次改动引入的 P1/P2 遗留 / 仍有遗留见「遗留风险」>

### 修复清单

| 轮次 | 问题 | 严重度 | 修复方式 | 涉及文件 |
|------|------|--------|----------|----------|
| 1 | <问题描述> | [P1]/[P2] | <修复方式> | <文件> |

### 只记录不修改的问题

| 问题 | 严重度 | 不修改原因（历史遗留 / nit 级） |
|------|--------|--------------------------------|
| <问题描述> | [P1]/[P2] | <原因> |

### Strengths（做得好的点）

- <本次改动中值得肯定的设计或实现，1–3 条，供人工回看时快速建立信心>

## 四、编译与测试结果

- **编译**：<命令，如 `mvn clean package -DskipTests`> → <通过/失败>
- **单测**：<全部通过 / 跳过（原因：本地 MySQL/Redis 等依赖不可达）/ 失败（详见输出）>
- **其他验证**：<门禁校验、归档校验等结果>

## 五、裁决日志摘要

> 完整裁决记录见 `.specpowers/auto_decisions.md`（如落盘）。

| 阶段 | 交互节点 | 裁决结果 | 依据 |
|------|----------|----------|------|
| <brainstorm> | <方案取舍确认> | <按文档结论执行> | <文档章节号> |
| <build> | <门禁转人工信号> | <自愈/硬阻断> | <信号内容与处置> |

## 六、遗留风险

- **外部依赖未就绪项**：<未就绪的外部接口及采用的降级策略（如 Remote 降级：返回空 + warn 日志 + 完整异常堆栈），接口就绪后仅需替换的层次>
- **降级审查标注**：<若 codex-review 不可用，此处标注「本次为降级审查」及原因>
- **2 轮后仍遗留问题**：<轮次上限内未收敛的 blocking 问题，交人工裁决>
- **其他**：<归档校验「只转人工、不打回」记录的问题等>
