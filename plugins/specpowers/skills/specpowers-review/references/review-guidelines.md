# Codex 审查指南（规则唯一来源）

本文件是本技能审查规则的**唯一来源**：判定标准、pass 定义、自检清单、严重度与比例原则均以本文件为准，
SKILL.md 只定义工作流骨架。规则提取自 `codex.app.asar` 的 Codex 审查模式，并在此基础上做了
控制流（§五）、跨文件数据流（§六）与调用链穿透（§七）增强。
英文原文见附录 A（仅溯源用，执行时以下方中文规则为准）。**所有审查结论一律使用中文。**

## 一、六条判定标准（决定"报不报"）

一个问题只有同时满足以下六条才报告，**宁可"没有问题"，也不给推测性或低价值反馈**：

1. 对正确性、性能、安全或可维护性有实质影响；
2. 离散且可操作；
3. 由本次受审改动引入（不是历史遗留）；
4. 作者知情后大概率会修；
5. 不依赖对意图的未声明假设；
6. 明确指出受影响的行为，而非宽泛猜测。

报告时在正文点名文件 / 行 / 函数，说明问题成立的关键场景，保持简洁。

## 二、模式指令

- **基分支模式**：审查相对基准分支「{baseBranch}」的改动，合并基点为 {mergeBaseSha}。
  上下文包由 `gather_review_context.py` 收集：默认只含已提交改动（`合并基点..HEAD`），
  `--include-worktree` 时含工作区未提交改动。
- **未提交模式**：审查当前改动（已暂存 + 未暂存 + 未跟踪）。
- **单方法模式**：审查目标方法及其调用链。无 diff，起点为 `--method` 参数收集的材料
  （定义候选 / 完整方法体 / 兄弟方法 / 调用方清单），审查者按 §七继续穿透。

## 三、严重度定义

| 级别 | 含义 | 典型场景 |
| --- | --- | --- |
| `[P0]` | 数据污染 / 资损 / 安全 | 缓存 key 缺少动态维度导致跨请求数据串用；SQL 注入；越权 |
| `[P1]` | 主流程功能阻断 | 存储层查询范围小于过滤层范围，新类型数据永远匹配不到；早返回阻断兜底致主链路空结果 |
| `[P2]` | 边界条件缺陷 / 确定性隐患 | 取首条时结果集无确定性排序；早返回跳过落库副作用；条件覆盖遗漏枚举值 |
| `[P3]` | 可维护性 | 死代码；复制后未适配；命名与行为不符 |

**拿不准时降一级，并在说明中注明不确定原因。** 与"宁可没有问题"的基调一致：推测性问题最高只给 P3。

## 四、比例原则与算力预算

### 4.1 快速通道

diff ≤ 5 文件 且 ≤ 300 行 且无 §6.1 触发信号时：

- 执行 Pass 1 + 轻量 Pass 2（只对含 `return` / 兜底逻辑的方法做 §5.1）；
- §5.5 / §6.4 自检清单可合并为一行说明（如"§5.5 / §6.4 触发条件未命中，已跳过"）。

### 4.2 大变更分诊

变更 > 30 文件时，先分诊再逐 pass：

- **跳过**：生成代码、`dist/`、`target/`、`*.min.js`、lock 文件、纯测试数据、二进制文件；
- **优先级**：业务逻辑 > 配置 > 测试 > 文档；
- 至少显式执行 Pass 1 + Pass 2，并启用 `--extract-methods`。

### 4.3 调用链穿透深度

默认穿透上限 3 层（入口 → 一层 → 二层 → 三层）；触达缓存 / DB 的节点必须穿透到
SQL / 缓存实现为止。超出 3 层需在报告中说明理由。

## 五、控制流审查规范（Pass 2 核心）

diff 格式仅展示行级补丁，丢失了嵌套条件、早期返回与下游兜底逻辑之间的控制流关系。
以下规则覆盖 diff 驱动审查的结构性盲区：

### 5.1 早期返回阻断检查

对每个含有 `return` 的修改方法，逐 `return` 追踪：

**步骤 A — 识别兜底分支**：扫描方法尾部，识别所有兜底逻辑：

- `if (result == null)` 降级返回默认值；
- "局部结果为空 → 回退到更大范围 / 默认配置"的兜底；
- 方法末尾的默认值返回。
- 若方法无任何兜底分支，跳过本检查。

**步骤 B — 逐 return 路径追踪**：对每个 `return` 语句，假设其触发，追问：

1. 该 `return` 之后的代码是否全部不可达？
2. 不可达代码中是否包含步骤 A 识别的兜底分支？
3. 若包含 → 标记为 P0 / P1 阻断。

**步骤 C — 职责边界判定**：

- 方法名自含完整优先级链语义（如 `matchXxxByPriority` 自含"精确 → 回退"两级语义）→ 阻断兜底的 `return` 即缺陷；
- 方法为单一职责（如仅负责精确匹配）→ `return null` 可能合法（由调用方兜底）。

**触发信号（主动扫描，不依赖被动发现）**：

- `return null` / `return false` 之后 10-40 行存在 `if (result == null)` 条件 → 立即执行步骤 A-C；
- 方法含 ≥ 2 个 `return` → 逐个执行步骤 B。

### 5.2 兄弟方法一致性

同一文件中命名相似（`Xxx` / `XxxNoTag` / `XxxByPriority` 等后缀差异）或调用同一依赖方法的方法对：

**步骤 A — 建立对比矩阵**：兜底由谁负责（调用方 / 方法自身）、关键决策点的处理方式。

**步骤 B — 同类代码的语义差异检测**：相同代码模式在两个方法中的下游后果是否相同？典型陷阱：

- 方法 A 的 `return null` 后调用方还有兜底 → 合法；
- 方法 B 的 `return null` 阻断了方法自身的兜底 → 缺陷。
- **代码模式相同 ≠ 语义正确性相同。**

**步骤 C — 差异归因**：职责边界合理差异 → 放行；复制代码后未适配 → 缺陷。

**触发信号**：后缀差异命名；≥ 2 个方法调用同一依赖方法且后续逻辑结构相似。

### 5.3 diff 片段补充策略

上下文包被截断或方法横跨多个 hunk 时：

- **不要仅根据 diff 片段下结论**，先 Read 完整方法体确认控制流全貌；
- 优先补读：新增方法、嵌套 ≥ 3 层、`return` ≥ 2 个的方法。

### 5.4 多 pass 定义（四 pass）

- **Pass 1 模式匹配**（必须）：条件写错、赋值遗漏、NPE 风险、SQL 字段笔误、死代码、
  集合未判空、资源未关闭。约覆盖 60-70% 缺陷。
- **Pass 2 控制流追踪**（必须）：§5.1-5.3。约覆盖 15-25%。
- **Pass 3 语义验证**（建议）：方法签名变更是否在所有调用方同步；字段新增后序列化 /
  DB 映射是否完整；业务规则是否符合需求。
- **Pass 4 跨文件数据流追踪**（命中 §6.1 触发条件时必须）：见 §六。

### 5.5 Pass 2 自检清单（发布审查结果前必须逐项确认）

**早期返回阻断（§5.1）**：

- [ ] 已扫描方法尾部的兜底分支？（若方法无兜底，填写"无兜底"）
- [ ] 已对每个 `return` 语句追踪其后代码的可达性？
- [ ] 已确认无 `return` 语句阻断了兜底分支？

**兄弟方法一致性（§5.2）**：

- [ ] 已识别同文件中的兄弟方法对？
- [ ] 已对每对兄弟方法建立职责边界对比矩阵？
- [ ] 已检查"代码相同但下游后果不同"的陷阱场景？
- [ ] 已确认每处差异有合理的职责边界解释？

**条件覆盖完整性**：

- [ ] 已检查 `if-else if` 链是否遗漏枚举值 / 状态？
- [ ] 已检查连续 `if`（非 `else if`）是否因缺少空值守卫导致后一个覆盖前一个？

审查报告必须包含此清单的填写结果（勾选或说明跳过原因），不得省略；快速通道按 §4.1 合并说明。

## 六、跨文件数据流追踪（Pass 4）

单文件 / 单方法审查无法发现跨多文件的**数据流断裂**：新字段或新类型在
入口 → 服务层 → 数据源 / 缓存 → 存储查询的链路中，被某一中间环节限制了完整传递，
导致下游永远匹配不到目标数据。

### 6.1 触发条件（命中任一必须执行）

1. 新增枚举值 / 新类型，且服务层有按该值过滤的逻辑；
2. 新增过滤条件（内存 filter 或 SQL `WHERE`）；
3. 新增缓存 / 数据源读取，或修改缓存源；
4. DTO 新增字段且该字段参与下游匹配逻辑。

### 6.2 执行步骤

**步骤 A — 识别数据流链路**：从入口（Controller / Handler / 入口函数）→ 服务层 →
数据源（缓存 / Repository）→ 存储查询（SQL / ORM），显式列出每个环节的代码位置
（文件 + 方法 + 行号）。

**步骤 B — 逐环节检查范围一致性**：

1. 入口层是否正确透传新字段值？
2. 服务层过滤逻辑是否覆盖新值？
3. 数据源 / 缓存返回的数据是否包含新值？
4. 存储查询的 `WHERE` 是否显式排除了新值？

**步骤 C — 定位断裂点**：某环节范围小于上下游时即为瓶颈
（如存储查询范围 < 服务层过滤范围 → 新类型数据永远进不了缓存）→ P1 阻断。

**步骤 D — 兼容性检查**：SQL 用 `OR xxx IS NULL` 兼容旧数据时，应用层的等值过滤
是否也对 `NULL` 做了等价处理？典型陷阱：SQL 放行 `NULL` + 应用层 `equals(x)` 把 `NULL` 过滤掉。

### 6.3 触发信号（主动扫描）

- 新增枚举值 + 服务层 `Objects.equals(...)` / `===` 类过滤；
- 新增 Mapper / ORM 查询方法或修改 `WHERE` 子句；
- 新增缓存方法或修改缓存源；
- DTO 新增字段参与 `.filter()` / `if` 判断；
- SQL 出现 `OR xxx IS NULL` 兼容，且应用层有对应等值过滤。

### 6.4 自检清单（发布审查结果前必须逐项确认）

**数据流链路识别**：

- [ ] 已列出新增字段 / 新值的完整数据流链路（入口 → 服务 → 数据源 → 存储查询）？
- [ ] 已标注链路中每个环节的代码位置（文件 + 方法 + 行号）？

**范围一致性**：

- [ ] 已检查入口层是否正确透传？
- [ ] 已检查服务层过滤是否覆盖新值？
- [ ] 已检查数据源 / 缓存是否包含新值？
- [ ] 已检查存储查询是否排除新值？

**兼容性**：

- [ ] 已检查存储层 `OR IS NULL` 兼容与应用层等值过滤的一致性？
- [ ] 已标注"存储层放行但应用层过滤"的不一致？

**断裂点定位**：

- [ ] 已识别范围瓶颈环节？
- [ ] 已标注瓶颈对功能的影响（P1 / P2）？

## 七、单方法审查 / 调用链穿透

用户点名具体方法时，审查对象不是 diff 而是方法及其调用链。
入口方法体往往"看起来正确"，真实缺陷常在被调用方法中：
缓存 key 缺少动态维度、helper 早返回跳过落库、SQL 缺 `ORDER BY`、跨文件范围瓶颈。

### 7.1 触发与材料收集

- 触发：用户请求形如 `review Class#method`、`审查 XxxSupport#matchXxx`。
- **优先用脚本收集确定性材料**（避免大仓库 grep 超时试错）：
  `python scripts/gather_review_context.py --repo 仓库路径 --method "Class#method"`。
  输出：定义候选（声明目标类的文件优先、测试路径降权）、入口方法完整体、
  同文件兄弟方法清单、一层调用方清单。

### 7.2 执行步骤

**步骤 A — 定位入口**：以 `--method` 输出为准；必要时 `git grep -n "方法签名关键词" -- "*.java"` 等补充定位，
Read 入口方法完整体。

**步骤 B — 构建调用图**：扫描入口方法体，提取直接调用（`this.xxx(`、静态工具、mapper / ORM 调用）；
对每个被调用方法定位定义并 Read 完整体；递归至叶子（框架 / 三方库 / 语言标准库止步）。
默认深度上限 3 层（§4.3）。

**步骤 C — 强制审查触达点**（每个必须 Read 完整体并应用 Pass 1-4）：

1. **缓存 / 记忆化读写**（示例：`redisTemplate.opsForHash`、`putAll`、`expire`、`CacheManager`；
   其他语言为对应缓存客户端）：
   - 缓存 key 是否覆盖输入的**全部动态维度**？遗漏任何随请求 / 配置变化的维度 → 跨请求污染 P0 / P1；
   - helper 早 `return` 是否跳过缓存写入 → 空结果永不缓存、防穿透成死代码 P2。
2. **存储查询**（示例：`xxxMapper.selectXxx`、ORM queryBuilder、SQL 迁移脚本）：
   - 必须定位对应 SQL（Mapper.xml / `@Select` / SQL 文件），检查 `WHERE` / `ORDER BY` / `IN (...)`；
   - 取首条（`get(0)` / `limit 1` / `head`）时结果集必须有确定性排序，否则胜出者依赖存储行序 P2；
   - 动态集合过滤与缓存 key 维度是否一致（范围瓶颈，同 §六）。
3. **跨文件数据流**：DTO / 参数在调用方与 helper 间传递时，逐环节比对范围一致性（§6.2 步骤 A-D）。

**步骤 D — 兄弟 / 同类方法对比**：同文件命名相似方法一并 Read 对比（§5.2）。

**步骤 E — 调用方回溯（建议）**：确认入参是否来自动态生效集合；若是，
缓存 key 必须包含该集合的稳定指纹，否则 P0 / P1。

### 7.3 与既有 pass 的关系

调用链穿透不是新增独立 pass，而是**把 Pass 1-4 施加到调用图每个节点**；
入口方法自身快速过 Pass 1 / 2，重点算力放在触达缓存 / DB 的 helper 节点。

### 7.4 输出要求

- 报告以"调用链穿透"章节开头，列出：入口方法 → 调用图节点清单 → 每个缓存 / DB 触达点的审查结论；
- 不得仅以入口方法体结论收尾；若未穿透，必须在显著位置声明"未执行调用链穿透"。

### 7.5 自检清单（单方法模式发布前必须逐项确认）

- [ ] 已定位入口方法定义并 Read 完整体？
- [ ] 已构建调用图，列出入口的直接 / 间接被调用方法？
- [ ] 已对每个缓存读写触达点 Read 完整 helper 并查缓存 key 维度完整性？
- [ ] 已对每个存储查询触达点定位对应 SQL 并审查 `WHERE` / `ORDER BY` / `IN`？
- [ ] 已对比同文件兄弟 / 同类方法？
- [ ] 已回溯调用方确认入参是否动态变化（缓存 key 是否遗漏该维度）？
- [ ] 报告以"调用链穿透"章节开头，且无仅审入口方法体的结论？

---

## 附录 A — Codex 英文原文（溯源用）

### A.1 Review Guidelines（变量 `xe`，逐字收录）

```
# Review Guidelines

You are acting as a reviewer for a proposed code change made by another engineer.

Review the change and respond in normal Markdown. Do not return JSON, XML, a findings object, or any structured review schema.

Focus on discrete, actionable issues the original author would likely fix if they knew about them. Prefer no issues over speculative or low-signal feedback.

General guidelines for whether to call out an issue:

1. It meaningfully impacts correctness, performance, security, or maintainability.
2. It is discrete and actionable.
3. It was introduced by the change under review.
4. The author would likely fix it once aware.
5. It does not rely on unstated assumptions about intent.
6. It identifies the affected behavior clearly rather than speculating broadly.

When you call out an issue, include the relevant file and line or function in prose, explain the scenario where it matters, and keep the explanation concise. Use priority labels such as `[P1]` or `[P2]` only when helpful to communicate severity.

If there are no actionable issues, say that directly and briefly.
```

### A.2 模式指令（`De` / `Oe`，逐字收录）

```
Review the code changes against the base branch '{baseBranch}'. The merge base commit for this comparison is {mergeBaseSha}. Run `git diff {mergeBaseSha}` to inspect the changes relative to {baseBranch}. Provide concise, actionable feedback in a normal Markdown response.
```

```
Review the current code changes (staged, unstaged, and untracked files) and provide concise, actionable feedback in a normal Markdown response.
```
