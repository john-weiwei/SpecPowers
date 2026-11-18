# 状态机推导化statejson-事实状态迁移为工件目录推导确定性层校验依据 Specification

## Purpose
TBD - created by archiving change 状态机推导化statejson-事实状态迁移为工件目录推导确定性层校验依据. Update Purpose after archive.
## Requirements
### Requirement: 状态机推导化statejson-事实状态迁移为工件目录推导确定性层校验依据

需求级事实状态（活跃性 / 迭代轮次 / 设计文档指针）SHALL 以 openspec/changes/ 工件目录推导为权威信源，state.json 仅作可重建缓存；读取路径 SHALL 内嵌对账（僵尸条目自动清理），并提供 `facade reconcile` 从工件重建状态。

#### Scenario: 僵尸条目自动清理

- **WHEN** state.json features 映射存在某需求条目，而 openspec/changes/ 下对应目录已消失（手动归档或删除），且该条目 stage 不属于 explore/fast（change 目录合法缺席的态）
- **THEN** 读取路径自动清理该条目并在输出中给出警告行（含被清理 slug），后续推进类命令不再路由到该需求

#### Scenario: explore 与 fast 态豁免对账

- **WHEN** 条目 stage 为 explore（产物在 docs/specpowers/design/，change 目录尚未创建）或 fast（无三件套工件）
- **THEN** 对账豁免目录缺席检查，条目不被清理

#### Scenario: 迭代轮次从工件推导

- **WHEN** change 目录内存在 design-round-3.md 且 tasks.md 含「## Round 5」小节
- **THEN** 该需求的迭代轮次推导值为 5（取两者最大值），与 state 缓存不一致时以推导为准并回写缓存

#### Scenario: 设计文档指针自包含落盘

- **WHEN** explore 收口执行 record-design-doc 登记设计文档
- **THEN** change 目录被确保创建并落 .specpowers-meta.json（含 design_doc 相对路径与 created_at），state 损坏后可据此重建指针

#### Scenario: reconcile 从工件重建状态

- **WHEN** state.json 损坏或丢失，而 change 目录含 .specpowers-meta.json 与三件套（proposal/specs/tasks）
- **THEN** facade reconcile 从工件重建该需求条目并输出对账报告；无 meta 且无三件套的 slug 报告为「无法重建，需重走入口」

#### Scenario: meta 损坏降级不阻断

- **WHEN** .specpowers-meta.json 内容非法（JSON 解析失败）
- **THEN** design_doc 推导返回 None 并输出警告，主流程不中断（视同缺失降级）

#### Scenario: 活跃判定扩展 meta 文件

- **WHEN** openspec/changes/ 下某目录仅含 .specpowers-meta.json（尚无三件套）
- **THEN** active_changes 将其视为活跃 change（explore 已完成、待 propose 的需求不被遗漏）

#### Scenario: 推导值与缓存不一致以推导为准

- **WHEN** 同一需求的迭代轮次推导值与 state.json 缓存值不一致
- **THEN** 消费方读到的值以推导为准，且缓存被回写为推导值，对账报告记录差异行

