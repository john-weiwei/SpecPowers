# constitution.md — 项目原则生成契约

## 触发

当用户调用 `/specpowers-constitution [--force]` 时加载本契约。

## 前置校验

1. 确认当前目录是 git 仓库
2. 运行 `python -m specpowers_cli.bridge.facade constitution [--force] --root .` 完成状态机校验
3. 检查返回：若 stage 非 constitution 且无 --force → 提示用户确认（会丢弃当前 feature 流水线）

> 确定性层在此次调用中会自动完成 baseline 扫描，产物写入 `.specpowers/baseline.json`。但此时 `.specpowers/constitution.md` 尚未生成，baseline 中的 `constitution_hash` 为空字符串——这是预期行为，将在第三步补扫刷新。

## 执行步骤

### 第一步：读取模板

读取 constitution 生成模板：

```
templates/constitution-template.md
```

（插件安装后位于 skill 目录内，即 `${PLUGIN_ROOT}/skills/specpowers/templates/constitution-template.md`）

该模板采用四类原则骨架（`# Constitution → Core Principles → 开发工作流 → 治理 → 版本脚注行`），Core Principles 固定为四类原则占位。

若模板文件缺失（init 时未拷贝），可退化为内联结构：`# <项目名> Constitution` + 四个 `###` 原则小节 + `## 开发工作流` + `## 治理` + 版本脚注行。

### 第二步：扫描项目信号，填充原则

扫描项目上下文，按以下优先级取值填充占位符：

- **用户输入**（`$ARGUMENTS`）优先级最高
- **编码规范载体**（高优先级，专供 `[CODING_CONVENTIONS]`）：扫描项目根的 `CLAUDE.md`、`AGENTS.md`、`.cursor/rules`、`.codeiumignore` 同级规范文件，提取其中的硬性编码约束（禁止项、格式、署名、行数上限等）。逐条转写为声明式条目。
- 否则从项目上下文推断：`README`、依赖清单（`package.json` / `pom.xml` / `pyproject.toml` 等）、既有目录结构
- 治理日期：`RATIFICATION_DATE` 用今天日期，`LAST_AMENDED_DATE` 同 `RATIFICATION_DATE`（首次生成）
- `CONSTITUTION_VERSION` 首次生成固定为 `1.0.0`

**仅聚焦以下四类原则**（中文描述，不承载结构规则）：

1. **质量原则**（`[QUALITY_DESCRIPTION]`）— 代码质量标准、review 要求、可维护性、坏味道容忍度
   - 含 `[CODING_CONVENTIONS]` 子占位符：从 `CLAUDE.md`/`AGENTS.md`/`.cursor/rules` 等载体提取的**可执行编码约束清单**（每条一行，声明式，如「禁止行尾注释」「方法行数 ≤ 60 行」「日志格式 [ClassName.methodName]」）。无此类载体或载体无硬性约束时，填「本项目无显式编码规范载体」。此小节是 subagent 模式下 build 阶段 Context 注入的硬依赖。
2. **测试原则**（`[TESTING_DESCRIPTION]`）— 测试策略、TDD 偏好、测试分层与覆盖率
3. **UX 原则**（`[UX_DESCRIPTION]`）— 用户体验标准、交互规范、可访问性、错误提示友好度
4. **性能原则**（`[PERFORMANCE_DESCRIPTION]`）— 性能指标、资源占用上限、优化策略、监控要求

同时填充：

- `[PROJECT_NAME]` — 项目名（从目录名或 README 推断）
- `[WORKFLOW_CONTENT]` — 开发工作流（review、提交规范、门禁要求等）
- `[GOVERNANCE_RULES]` — 治理规则（宪章优先级、修订流程、版本语义化规则）。填充时参考措辞：本宪章优先于其他实践约定；所有 PR/code review 须校验是否符合宪章原则（尤其编码规范小节）；修订须记录理由与迁移计划。

填充规则：
- 替换所有 `[ALL_CAPS]` 占位符为具体文本，不残留未解释的括号 token
- 保留标题层级（`#` / `##` / `###`）与模板一致
- **占位符层级独立性**：`[QUALITY_DESCRIPTION]` 与 `[CODING_CONVENTIONS]` 是**两个独立占位符**，分别填充，互不包含——`[QUALITY_DESCRIPTION]` 只填质量原则正文（停留在 `### I. 质量原则` 下、`#### 编码规范` 之前）；`[CODING_CONVENTIONS]` 单独填入 `#### 编码规范` 子小节。不要把编码规范内容塞进 `[QUALITY_DESCRIPTION]`，也不要让 `[QUALITY_DESCRIPTION]` 覆盖到 `#### 编码规范` 小节。
- 原则描述须是**声明式、可检验**的（避免「应该」「尽量」等模糊措辞）
- `<!-- -->` HTML 注释在填充后可删除，除非仍有澄清价值

### 第三步：落盘并刷新 baseline

1. **直接写入** `.specpowers/constitution.md`（覆盖）。constitution 由本插件内联生成，不依赖任何外部技能，不产生 `.specify/memory/constitution.md` 副本。
2. **刷新 baseline**（修复时序问题：首次 scan 时 constitution.md 不存在导致 hash 为空）：

```bash
python -m specpowers_cli.bridge.facade baseline --root .
```

刷新后验证 `.specpowers/baseline.json` 的 `constitution_hash` 字段**非空**（为 constitution.md 的 SHA-256）。

### 第四步：确认产物

提示用户：

```
✅ .specpowers/constitution.md 已生成（项目原则：质量/测试/UX/性能）
✅ .specpowers/baseline.json 已刷新（constitution_hash 已填充）
请 review 后提交到 git 供团队共享。
```

## --force 标志

`--force` 时：无视已有产物，强制删除重建 constitution.md + 重扫 baseline.json。版本号按语义化递增：

- MAJOR：删除或重新定义原则（不兼容）
- MINOR：新增原则或实质性扩写
- PATCH：措辞、typo、非语义调整

## 基线产物说明

`baseline.json` 包含：
- `git_ref` — 扫描时的 HEAD commit
- `scanned_at` — 扫描时间戳
- `top_dirs` — 顶层目录列表
- `deps` — 识别的依赖清单
- `src_patterns` — src/ 二级目录命名规律
- `constitution_hash` — constitution.md 的 SHA-256（第三步刷新后填充）

## 后续步骤

完成后 stage 跃迁到 `ready`，可执行：
- `/specpowers-brainstorm "<需求>"` — 启动特性探索
- `/specpowers-specify "<需求>"` — 直接进入场景定义
- `/specpowers-fast "<需求>"` — 优化模式
