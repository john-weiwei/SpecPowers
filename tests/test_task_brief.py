"""Tests for task_brief — subagent 派发的任务 brief 切分脚本（v3.1.0）。

apply.md 第五步承诺的 `scripts/task_brief.py` 落地实现（v3.1.0 契约缺口修复）：
subagent 模式 brief 由脚本直出，替代「主会话读全文 + 手工转写」的双向 token 浪费。

验证面：
1. extract_header — 顶部「## 推荐执行方式」注释块提取（含修改范围声明）
2. extract_task — 切段边界（下一任务标题 / `## ` 小节标题止）
3. 已作废小节删除线留痕（`~~### Task N~~`）非标题锚点，不被误切
4. parse_scenario_names — Scenario 名列表解析（顿号/逗号/分号、「无」占位）
5. extract_scenarios — 从 delta spec 抽取场景原文（命中/未命中降级）
6. build_brief 端到端 — header + 任务段 + 关联场景原文
7. 任务号不存在 — 非 0 退出 + 可用任务号指引（报错即指引，UX 原则）

作者：005819 | 协作：GLM
"""

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TASK_BRIEF_PATH = (
    REPO_ROOT / "plugins" / "specpowers" / "skills" / "specpowers"
    / "scripts" / "task_brief.py"
)

# 从脚本路径加载模块（scripts/ 非包，无包内相对导入）
_spec = importlib.util.spec_from_file_location("task_brief", TASK_BRIEF_PATH)
task_brief = importlib.util.module_from_spec(_spec)
sys.modules["task_brief"] = task_brief
_spec.loader.exec_module(task_brief)


TASKS_MD = """## 推荐执行方式

<!--
推荐：subagent
修改范围：src/order/, tests/order/
-->

### Task 1: 创建 DTO

- [ ] 实现内容：新建 OrderDTO
- 场景引用：下单成功、库存不足
- 依赖：无
- 并行：否

### Task 2: 实现 Service

- [ ] 实现内容：编写 OrderService
- 场景引用：下单成功
- 依赖：Task 1
- 并行：否

## 依赖与并行说明

- Task 1 → Task 2

## Round 2（场景调整）

### Task 3: 新增取消接口

- [ ] 实现内容：编写 CancelService
- 场景引用：无
- 依赖：Task 2
- 并行：否

## 已作废

- ~~### Task 4: 旧任务~~ — Round 2 作废，依据：spec 场景删除
"""

SPEC_MD = """## 订单 Delta

### Requirement: 下单流程

#### Scenario: 下单成功

- **WHEN** 库存充足且下单请求合法
- **THEN** 订单创建成功

#### Scenario: 库存不足

- **WHEN** 库存小于购买量
- **THEN** 返回库存不足错误

### Requirement: 支付

#### Scenario: 支付成功

- **WHEN** 支付回调到达
- **THEN** 订单状态更新
"""


def test_extract_header_contains_scope_declaration():
    """顶部注释块整段保留：修改范围声明是 controller 拼装 Context 与门禁声明的依据。"""
    header = task_brief.extract_header(TASKS_MD)
    assert "推荐：subagent" in header
    assert "修改范围：src/order/, tests/order/" in header


def test_extract_header_absent_returns_empty():
    """无「## 推荐执行方式」标题的旧格式文件返回空串（brief 只含任务段）。"""
    assert task_brief.extract_header("### Task 1: x\n- [ ] y\n") == ""


def test_extract_task_section_boundaries():
    """切段边界：到下一任务标题或 `## ` 小节标题止，不吞后续小节。"""
    section = task_brief.extract_task(TASKS_MD, 1)
    assert "### Task 1: 创建 DTO" in section
    assert "场景引用：下单成功、库存不足" in section
    assert "### Task 2" not in section
    assert "## 依赖与并行说明" not in section
    # Task 2 段止于「## 依赖与并行说明」
    section2 = task_brief.extract_task(TASKS_MD, 2)
    assert "### Task 2: 实现 Service" in section2
    assert "依赖与并行说明" not in section2


def test_extract_task_number_boundary_no_prefix_swallow():
    """任务号边界：Task 1 不得被 `### Task 12` 之类前缀误匹配（\\d 边界）。"""
    text = "### Task 12: 多号任务\n- [ ] x\n\n### Task 2: 另一任务\n- [ ] y\n"
    assert task_brief.extract_task(text, 1) is None
    assert "### Task 12" in task_brief.extract_task(text, 12)
    assert "### Task 2" in task_brief.extract_task(text, 2)


def test_retired_section_strikethrough_not_matched():
    """已作废小节的删除线留痕（`~~### Task 4~~`）非标题锚点，不被误切。"""
    numbers = task_brief.list_task_numbers(TASKS_MD)
    assert numbers == [1, 2, 3]
    assert task_brief.extract_task(TASKS_MD, 4) is None


def test_parse_scenario_names_split_and_placeholder():
    """名列表解析：顿号/逗号/分号切分；「无」占位与空值过滤。"""
    names = task_brief.parse_scenario_names("- 场景引用：下单成功、库存不足\n")
    assert names == ["下单成功", "库存不足"]
    names = task_brief.parse_scenario_names("- 场景引用: A,B；C\n")
    assert names == ["A", "B", "C"]
    assert task_brief.parse_scenario_names("- 场景引用：无\n") == []
    assert task_brief.parse_scenario_names("- 依赖：Task 1\n") == []


def test_extract_scenarios_hit_and_missing():
    """场景抽取：命中段落按名输出；未命中名单独返回（降级提示的依据）。"""
    sections, missing = task_brief.extract_scenarios(
        SPEC_MD, ["下单成功", "库存不足", "不存在的场景"]
    )
    assert len(sections) == 2
    assert "#### Scenario: 下单成功" in sections[0]
    assert "**WHEN** 库存充足且下单请求合法" in sections[0]
    assert "#### Scenario: 库存不足" in sections[1]
    assert missing == ["不存在的场景"]


def test_extract_scenarios_section_boundary_at_requirement():
    """场景段止于下一 `####`/`###` 标题：同 requirement 多场景互不吞并。"""
    sections, _ = task_brief.extract_scenarios(SPEC_MD, ["支付成功"])
    assert len(sections) == 1
    assert "#### Scenario: 支付成功" in sections[0]
    assert "**THEN** 订单状态更新" in sections[0]


def test_build_brief_end_to_end(tmp_path, capsys):
    """端到端：header + 任务段 + 关联场景原文一次输出，退出码 0。"""
    tasks = tmp_path / "tasks.md"
    spec = tmp_path / "spec.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    spec.write_text(SPEC_MD, encoding="utf-8")
    code = task_brief.build_brief(str(tasks), 1, str(spec))
    out = capsys.readouterr().out
    assert code == 0
    assert "修改范围：src/order/, tests/order/" in out
    assert "### Task 1: 创建 DTO" in out
    assert "## 关联场景原文（由 task_brief 从 delta spec 确定性抽取）" in out
    assert "#### Scenario: 下单成功" in out
    assert "#### Scenario: 库存不足" in out


def test_build_brief_no_scenario_ref_skips_spec(tmp_path, capsys):
    """场景引用为「无」时不附场景章节（零噪音），退出码 0。"""
    tasks = tmp_path / "tasks.md"
    spec = tmp_path / "spec.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    spec.write_text(SPEC_MD, encoding="utf-8")
    code = task_brief.build_brief(str(tasks), 3, str(spec))
    out = capsys.readouterr().out
    assert code == 0
    assert "### Task 3: 新增取消接口" in out
    assert "关联场景原文" not in out


def test_build_brief_missing_scenario_degrades(tmp_path, capsys):
    """场景名未命中：退出码仍 0，末尾降级提示 controller 手工补充（不阻断派发）。"""
    tasks = tmp_path / "tasks.md"
    spec = tmp_path / "spec.md"
    tasks.write_text(
        TASKS_MD.replace("场景引用：下单成功、库存不足", "场景引用：幽灵场景"),
        encoding="utf-8",
    )
    spec.write_text(SPEC_MD, encoding="utf-8")
    code = task_brief.build_brief(str(tasks), 1, str(spec))
    out = capsys.readouterr().out
    assert code == 0
    assert "未命中" in out
    assert "幽灵场景" in out


def test_build_brief_missing_task_errors_with_guidance(tmp_path, capsys):
    """任务号不存在：非 0 退出 + 列出可用任务号（报错即指引，不猜测）。"""
    tasks = tmp_path / "tasks.md"
    tasks.write_text(TASKS_MD, encoding="utf-8")
    code = task_brief.build_brief(str(tasks), 99, None)
    err = capsys.readouterr().err
    assert code == 1
    assert "不存在 Task 99" in err
    assert "[1, 2, 3]" in err


def test_main_missing_file_exits_with_guidance(tmp_path, capsys):
    """tasks.md 路径不存在：非 0 退出 + 路径核对指引（防御式，不崩溃）。"""
    code = task_brief.main([str(tmp_path / "nope.md"), "1"])
    err = capsys.readouterr().err
    assert code == 1
    assert "文件不存在" in err


def test_module_has_no_third_party_imports():
    """仅标准库（项目原则：Python ≥3.11 仅标准库，运行时禁止 pip 依赖）。"""
    import ast
    tree = ast.parse(TASK_BRIEF_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"argparse", "re", "sys", "ast"}, f"引入了非标准库依赖：{imported}"
