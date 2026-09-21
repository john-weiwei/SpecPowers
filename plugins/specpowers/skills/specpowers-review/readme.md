# specpowers-review 技能使用说明（SpecPowers 内置）

复刻 OpenAI Codex 代码审查逻辑的技能，随 SpecPowers 插件内置分发（`skills/specpowers-review/`，无需预装）。
它收集与 Codex 同等完整的 git 上下文，
套用 Codex 的六条判定标准 + 本技能增强的控制流审查规范，输出 Codex 同款格式（普通 Markdown 审查正文）。
**所有审查结论以中文呈现。**

审查规则的唯一来源是 `references/review-guidelines.md`（判定标准 / pass 定义 / 自检清单 / 严重度 / 比例原则）。

## 目录结构

```
specpowers-review/
├── SKILL.md                       # 技能定义与工作流骨架
├── readme.md                      # 本文档（使用说明 + 设计动机 + 历史复盘）
├── references/
│   └── review-guidelines.md       # 审查规则唯一来源（含 Codex 英文原文附录）
└── scripts/
    ├── gather_review_context.py   # git 上下文收集（基分支 / 未提交 / 单方法）
    └── tests/
        └── test_gather_review_context.py  # 回归测试（unittest，无第三方依赖）
```

## 触发方式

满足以下任一情形时，调用本技能：

- 用户说"审查我的改动""review 这个 PR""代码审查""按 codex 规则审查""Codex review"等。
- 用户提供 PR / 分支名 / 基准分支，要求审查。
- 用户要求审查未提交的工作区改动。
- 用户点名某个具体方法（如 `Class#method`）要求审查。

## 使用前准备

- 本机需要安装 `git` 与 `python3`。
- 目标必须是 git 仓库。

## 使用步骤

### 模式一：基分支对比（审查相对某分支的改动）

```bash
# 推荐：默认只对比已提交改动（合并基点..HEAD），并启用方法体提取
python scripts/gather_review_context.py --repo /path/to/repo --base main --extract-methods --out 上下文.md

# 纳入工作区未提交改动（旧版行为）
python scripts/gather_review_context.py --repo /path/to/repo --base main --include-worktree --out 上下文.md
```

随后按 `references/review-guidelines.md` 执行多 pass 审查（Pass 1-4），产出中文审查。

### 模式二：未提交改动（审查工作区）

```bash
python scripts/gather_review_context.py --repo /path/to/repo --extract-methods --out 上下文.md
```

### 模式三：单方法调用链穿透（审查指定方法）

```bash
python scripts/gather_review_context.py --repo /path/to/repo --method "Class#method" --out 上下文.md
```

脚本自动完成机械性工作：`git grep` 定位定义候选（声明目标类的文件优先、测试路径降权、
兼容 `meth<...>(` 泛型签名）、导出入口方法完整体、列出同文件兄弟方法、列出一层调用方。
调用图的递归展开与缓存 / DB 触达点穿透仍由审查者按指南 §七执行（默认深度上限 3 层）。

### v5 变更摘要（本次重构）

1. **Windows 编码修复**：git 输出统一 utf-8 解码并关闭 `core.quotepath`，
   中文提交信息 / 中文路径不再乱码。
2. **成员表算法**：方法边界识别改用"花括号深度跳变 + 容器排除"，替代 v2 的
   "签名行同深度匹配"——修复嵌套块内变更（恰是该功能的目标场景）静默提取失败；
   兼容大括号换行（Allman）风格、多行签名、注解行；识别忽略字符串 / 注释中的花括号。
3. **按 diff 版本提取**：方法体提取读 diff 对应版本（基分支取 HEAD、staged 取 index、
   unstaged 取工作区），已删除文件跳过提取并在上下文包注明。
4. **统一截断策略**：未提交模式同样受 `--max-bytes` 约束；所有模式按文件粒度截断
   （不做字节级砍断），超预算文件列入"未包含文件清单"，提示用 Read 工具补读。
5. **基分支语义明确化**：默认 `合并基点..HEAD`（纯已提交，符合审 PR 心智），
   `--include-worktree` 保留旧行为；上下文包头注明对比范围。
6. **多语言提取**：Java / TS / JS / TSX / JSX（花括号成员表）、Python（缩进 def）、
   Mapper XML（完整 SQL 语句块）。
7. **`--method` 单方法模式**：见模式三。

## 验证

```bash
cd <插件目录>/skills/specpowers-review
python -m unittest discover -s scripts/tests -v
```

测试在临时 git 仓库与合成源码上运行（无第三方依赖），覆盖：深层嵌套方法提取（回归）、
大括号换行风格、多行签名与注解、字符串内花括号、Python 函数提取、Mapper XML 语句块提取、
含空格与中文路径、中文提交信息、已删除文件跳过、staged 基于 index / unstaged 基于工作区的
提取基准、预算截断与未包含清单、基分支默认范围与 `--include-worktree`、
`--method` 单方法模式与互斥参数校验。

---

## 设计动机与历史复盘

以下为各版本增强的设计动机与真实漏检事故复盘（事故专名仅在此归档，规则正文已通用化）。

### v2：diff 片段的控制流盲区（`--extract-methods`）

diff 格式仅展示行级补丁，丢失了嵌套条件、早期返回与下游兜底逻辑之间的控制流关系。
典型案例：`matchConfigByFormulateAreaNoTag` 的 `return null` 短路了 NATIONAL 兜底——
该问题在 diff 片段中不可见。`--extract-methods` 在 diff 后追加"变更方法完整上下文"章节，
供 Pass 2 控制流追踪使用。

### v3：跨文件数据流断裂（Pass 4）

一次审查中遗漏了 P1：SQL 层 `WHERE popup_type = 1` 导致 `popup_type=2` 的配置永远进不了
C 端缓存，而 Java 层 `.filter(item -> Objects.equals(item.getPopupType(), 2))` 永远匹配不到。
根因是单文件审查无法发现跨 4 个文件的范围瓶颈。Pass 4 要求显式追踪
入口 → 服务层 → 缓存 → SQL 链路的范围一致性（指南 §六）。

### v4：单方法漏检与调用链穿透

用户点名 `CabinetPaymentPageSaleEntranceSupport#matchConfigByFormulateAreaNoTag` 时，
首轮仅审入口方法体，漏掉 1 个 P1 + 2 个 P2，穿透调用链后才发现：

- **P1**：缓存 key 遗漏动态 `configBizIds`（随生效配置变化却未进 key）→ 跨请求污染，新配置最长 1 天不生效；
- **P2**：helper 早 `return` 跳过 `putAll` → 空结果永不缓存、防穿透成死代码；
- **P2**：SQL 无 `ORDER BY` → `get(0)` 取首条的胜出者依赖 DB 行序。

由此确立规则：单方法模式必须调用链穿透，严禁只审入口方法体（指南 §七）。

### v5：脚本正确性与上下文保真重构

v2 的方法提取实现存在一个与设计目标相悖的缺陷：方法定位要求"签名行与变更行花括号深度相等"，
而变更一旦落在嵌套块内（深度更深），提取就静默失败——变更越嵌套越提不出方法体。
另有：未提交模式的 staged 提取读错基准（工作区而非 index）、基分支模式混入工作区未提交改动、
未提交模式完全没有截断、Windows 中文乱码。v5 逐项修复（见上文"v5 变更摘要"），
并以 24 个回归测试固化行为。

## 与 Codex 的对应关系

| Codex 概念 | 本技能实现 |
| --- | --- |
| `review_model` git 查询 | `scripts/gather_review_context.py`（基分支 / 未提交 / 单方法三模式） |
| Review Guidelines（`xe`） | `references/review-guidelines.md` §一（中文）+ 附录 A（英文原文） |
| 模式指令 `De` / `Oe` | 指南 §二 + 附录 A.2 |
| `Ce()` 提示词组装 | 指南 §二 + SKILL.md 工作流 |
| （Codex 没有）控制流审查 | 指南 §五 + `--extract-methods` |
| （Codex 没有）跨文件数据流 | 指南 §六（Pass 4） |
| （Codex 没有）调用链穿透 | 指南 §七 + `--method` 模式 |

## 常见问题

- **Q：差异太大被截断了怎么办？**
  A：上下文包末尾的"未包含文件清单"列出所有未纳入的文件与字节数。**必须用 Read 工具
  补读这些文件后再审查**，不得仅基于截断片段下结论。
- **Q：什么情况下必须启用 `--extract-methods`？**
  A：变更 ≥ 30 个文件、或方法嵌套 ≥ 3 层、或方法含 ≥ 2 个 `return` 时强烈建议启用；
  所有分支审查建议默认启用。
- **Q：提取没覆盖我要审的方法怎么办？**
  A：提取基于花括号 / 缩进 / 标签边界的启发式解析，个别极端格式可能漏提。
  此时直接用 Read 工具读取源文件完整方法体，不要依赖 diff 片段评判控制流。
- **Q：兄弟方法一致性检查的作用是什么？**
  A：当两个命名相似的方法在相同判断点采用不同策略时（如一个 `return null`、另一个落入兜底），
  可能意味着一方有拷贝遗漏。这种缺陷在单方法 diff 中无法发现，必须通过比较审查暴露。
- **Q：审查语言可以切换吗？**
  A：本技能固定输出中文。如确需英文，请参照 `references/review-guidelines.md` 附录 A 的原文规则自行调整。
