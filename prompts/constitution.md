# constitution.md — 项目原则生成契约

## 触发

当用户调用 `/specpowers.constitution [--force]` 时加载本契约。

## 前置校验

1. 确认当前目录是 git 仓库
2. 运行 `python bridge/facade.py constitution [--force] --root .` 完成状态机校验
3. 检查返回：若 stage 非 constitution 且无 --force → 提示用户确认（会丢弃当前 feature 流水线）

## 执行步骤

### 第一步：生成 constitution.md

调用 `/speckit.constitution` 生成项目原则文档，**仅聚焦以下四类原则**：

1. **质量原则** — 代码质量标准、review 要求、测试覆盖率
2. **测试原则** — 测试策略、TDD 偏好、测试分层
3. **UX 原则** — 用户体验标准、交互规范、可访问性
4. **性能原则** — 性能指标、优化策略、监控要求

**不承载结构规则**（目录规范、命名约定等由 baseline.json 管理）。

### 第二步：扫描结构基线

确定性层已自动完成基线扫描（`baseline_scanner.scan()`），产物写入 `.specpowers/baseline.json`。

验证基线产物：
```bash
python bridge/facade.py scan --root .
```

### 第三步：确认产物

提示用户：

```
constitution.md 已生成（项目原则：质量/测试/UX/性能）
baseline.json 已生成（结构基线：top_dirs/deps/src_patterns）
请 review 后提交到 git 供团队共享。
```

## --force 标志

`--force` 时：无视已有产物，强制删除重建 constitution.md + 重扫 baseline.json。

## 基线产物说明

`baseline.json` 包含：
- `git_ref` — 扫描时的 HEAD commit
- `scanned_at` — 扫描时间戳
- `top_dirs` — 顶层目录列表
- `deps` — 识别的依赖清单
- `src_patterns` — src/ 二级目录命名规律
- `constitution_hash` — constitution.md 的 SHA-256

## 后续步骤

完成后 stage 跃迁到 `ready`，可执行：
- `/specpowers.brainstorm "<需求>"` — 启动特性探索
- `/specpowers.specify "<需求>"` — 直接进入场景定义
- `/specpowers.fast "<需求>"` — 优化模式
