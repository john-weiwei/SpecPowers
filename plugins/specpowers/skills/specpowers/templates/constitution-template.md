# [PROJECT_NAME] Constitution
<!-- 项目宪章：声明本项目的核心开发原则。由 /specpowers-init 内联生成 -->

## Core Principles
<!-- 核心原则：固定四类（质量/测试/UX/性能），不承载结构规则（目录规范/命名约定由 baseline.json 管理） -->

### I. 质量原则
<!-- 质量原则：代码质量标准、review 要求、可维护性、坏味道容忍度等 -->
[QUALITY_DESCRIPTION]
<!-- 示例：遵循项目既有目录结构与分层；关键逻辑行加行前注释；符合 IDE 代码格式化规范 -->

#### 编码规范
<!-- 编码规范：项目硬性代码风格约束。扫描 CLAUDE.md/AGENTS.md/.cursor/rules 提取，subagent 与 conductor 共用。subagent 模式下由 build 阶段 controller 注入每个 task 的 Context -->
[CODING_CONVENTIONS]
<!-- 示例：禁止行尾注释（改用行前注释）；参数定义禁止默认值；方法行数 ≤ 60 行；超过 2 个枚举值的 if-else 用 switch；多层 if 嵌套用 Early Return；日志格式 [ClassName.methodName]参数信息，异常打印整个异常而非只打印 msg；类/方法须含作者署名（姓名工号(AI工具)）；禁止内部类，统一定义在 dto 包；入参 ≥ 4 用参数对象传递；空集合返回 Collections.emptyList()；try-catch 日志打印整个异常 -->

### II. 测试原则
<!-- 测试原则：测试策略、TDD 偏好、测试分层与覆盖率要求 -->
[TESTING_DESCRIPTION]
<!-- 示例：核心逻辑必须有单测；测试分层（单测/集成/端到端）边界清晰；新增公开 API 须同步补测；优先用真实依赖而非过度 mock -->

### III. UX 原则
<!-- UX 原则：用户体验标准、交互规范、可访问性、错误提示友好度 -->
[UX_DESCRIPTION]
<!-- 示例：错误信息须可定位（含上下文与参数）；交互反馈及时；遵循平台原生交互习惯；关键操作提供撤销或二次确认 -->

### IV. 性能原则
<!-- 性能原则：性能指标、资源占用上限、优化策略、监控要求 -->
[PERFORMANCE_DESCRIPTION]
<!-- 示例：关键接口 P95 响应 ≤ 阈值；避免 N+1 查询与不必要的全量加载；大对象/大集合注意内存占用；核心链路接入监控 -->

## 开发工作流
<!-- 开发工作流：代码审查、提交规范、分支策略、质量门禁等 -->

[WORKFLOW_CONTENT]
<!-- 示例：所有变更须经 review；commit message 遵循约定式提交；结构一致性门禁（build 实时卡 + archive 卡）须通过 -->

## 治理
<!-- 治理：宪章优先级、修订流程、版本语义化规则 -->

[GOVERNANCE_RULES]
<!-- 示例：本宪章优先于其他实践约定；修订须记录理由与迁移计划；版本语义化（MAJOR 破坏性/MINOR 新增/PATCH 措辞） -->

**Version**: [CONSTITUTION_VERSION] | **Ratified**: [RATIFICATION_DATE] | **Last Amended**: [LAST_AMENDED_DATE]
<!-- 示例：Version: 1.0.0 | Ratified: 2026-08-03 | Last Amended: 2026-08-03 -->
