#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""task_brief.py — tasks.md 任务 brief 切分脚本（v3.1.0 落地实现）

apply 阶段 subagent 模式的确定性派发工具：从 tasks.md 切出指定任务的整段
brief 直出给 controller 拼装 subagent Context，替代「主会话读全文 + 手工转写」
的双向 token 浪费（契约见 prompts/apply.md 第五步、prompts/propose.md 任务模板）。

用法
----
  python task_brief.py <tasks.md 路径> <任务号 N> [--spec <delta spec 路径>]

行为
----
  * 输出 tasks.md 顶部「## 推荐执行方式」注释块（含修改范围声明）+ 「### Task N」
    整段（到下一个任务标题或 `## ` 小节边界止）；「## 已作废」小节内的删除线留痕
    不是标题锚点，天然不会被误切；
  * `--spec` 指定 delta spec 时，解析任务「场景引用：」行中的 Scenario 名列表，
    从 spec 抽取对应 `#### Scenario:` 段落附在 brief 末尾「## 关联场景原文」——
    subagent 零上下文也能拿到场景原文，tasks.md 写侧因此只存名字不抄原文；
  * 场景名解析失败或未命中时不阻断（退出码仍为 0），在末尾提示 controller
    手工补充；任务号不存在时非 0 退出并列出可用任务号。

作者: 张威威(005819) / GLM
日期: 2026-11-18
"""
import argparse
import re
import sys

# 任务标题锚点：`### Task N:`（\d+ 边界防 Task 1 误吞 Task 12）
_TASK_TITLE_RE = re.compile(r"^###\s+Task\s+(\d+)(?::|\s|$)")
# 顶部小节标题：从文件头到第一个任务标题之间的内容原样保留
_HEADER_SECTION_RE = re.compile(r"^##\s+推荐执行方式")
# 场景引用行：兼容中文/英文冒号（瘦身后值为纯 Scenario 名列表）
_SCENARIO_REF_RE = re.compile(r"^-\s*场景引用[:：]\s*(.+)$", re.MULTILINE)
# 名列表分隔符：顿号/逗号/分号（中英文均兼容）
_NAME_SPLIT_RE = re.compile(r"[、，,；;]")
# spec 中场景标题：`#### Scenario: <名>`
_SPEC_SCENARIO_RE = re.compile(r"^####\s+Scenario[:：]\s*(.+?)\s*$")
# 无场景占位值（瘦身后契约：无场景引用写「无」）
_NO_SCENARIO_VALUES = {"无", "无场景", "无场景引用", "-"}


def _force_utf8_stdout() -> None:
    """中文 Windows 控制台默认 cp936，显式切 UTF-8 防中文 brief 乱码。"""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def read_text(path: str) -> str:
    """读取 UTF-8 文本；损坏字节替换而非崩溃（防御式，对齐 fs_state 范式）。"""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def extract_header(text: str) -> str:
    """提取 tasks.md 顶部「## 推荐执行方式」小节（含注释块与修改范围声明）。

    边界：从标题行起，到第一个 `### Task` 标题前止；无该标题时返回空串
    （旧格式兼容：brief 只含任务段，controller 自行注入执行方式）。
    """
    lines = text.splitlines()
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        if start is None and _HEADER_SECTION_RE.match(line):
            start = idx
            continue
        if start is not None and _TASK_TITLE_RE.match(line):
            end = idx
            break
    if start is None:
        return ""
    return "\n".join(lines[start:end]).strip()


def extract_task(text: str, number: int) -> str | None:
    """切出 `### Task <number>` 整段；不存在返回 None。

    段边界：下一个任务标题或任意 `## ` 小节标题（如「## 依赖与并行说明」
    「## Round」「## 已作废」）——与 propose.md 契约的 task-brief 切分锚点一致。
    """
    lines = text.splitlines()
    start = None
    end = len(lines)
    for idx, line in enumerate(lines):
        matched = _TASK_TITLE_RE.match(line)
        if matched is None:
            if start is not None and line.startswith("## "):
                end = idx
                break
            continue
        if start is None and int(matched.group(1)) == number:
            start = idx
        elif start is not None:
            end = idx
            break
    if start is None:
        return None
    return "\n".join(lines[start:end]).strip()


def list_task_numbers(text: str) -> list[int]:
    """返回 tasks.md 中全部任务号（含迭代轮各 Round 小节内的任务）。"""
    numbers = []
    for line in text.splitlines():
        matched = _TASK_TITLE_RE.match(line)
        if matched is not None:
            numbers.append(int(matched.group(1)))
    return numbers


def parse_scenario_names(task_section: str) -> list[str]:
    """从任务段「场景引用：」行提取 Scenario 名列表。

    瘦身后契约（v3.1.0）值为纯名列表，按顿号/逗号/分号切分；旧格式
    （含 WHEN-THEN 原文摘录）无法可靠切名时按原样返回切段，未命中场景
    由调用侧降级提示——不猜测、不静默丢弃。
    """
    names: list[str] = []
    for matched in _SCENARIO_REF_RE.finditer(task_section):
        raw = matched.group(1).strip()
        if raw in _NO_SCENARIO_VALUES or not raw:
            continue
        names.extend(part.strip() for part in _NAME_SPLIT_RE.split(raw) if part.strip())
    return names


def extract_scenarios(spec_text: str, names: list[str]) -> tuple[list[str], list[str]]:
    """从 delta spec 抽取指定 Scenario 段落。

    返回 (命中段落列表, 未命中名字列表)；段边界为该场景标题到下一个
    `####`/`###` 标题前，与 OpenSpec delta 格式硬约束对齐。
    """
    lines = spec_text.splitlines()
    # 先建立 名 -> (起, 止) 索引，再按 names 顺序输出（允许重复引用同场景）
    index: dict[str, tuple[int, int]] = {}
    for idx, line in enumerate(lines):
        matched = _SPEC_SCENARIO_RE.match(line)
        if matched is None:
            continue
        start = idx
        end = len(lines)
        for follow in range(idx + 1, len(lines)):
            if lines[follow].startswith("#### ") or lines[follow].startswith("### "):
                end = follow
                break
        index[matched.group(1).strip()] = (start, end)
    sections: list[str] = []
    missing: list[str] = []
    for name in names:
        span = index.get(name)
        if span is None:
            missing.append(name)
            continue
        sections.append("\n".join(lines[span[0]:span[1]]).strip())
    return sections, missing


def build_brief(tasks_path: str, number: int, spec_path: str | None) -> int:
    """组装 brief 并打印；返回进程退出码。"""
    tasks_text = read_text(tasks_path)
    task_section = extract_task(tasks_text, number)
    if task_section is None:
        available = list_task_numbers(tasks_text)
        print(f"错误：tasks.md 中不存在 Task {number}。可用任务号：{available or '无（空清单）'}", file=sys.stderr)
        print("下一步：核对任务号后重试，如 `python task_brief.py <tasks.md> 1`", file=sys.stderr)
        return 1
    header = extract_header(tasks_text)
    if header:
        print(header)
        print()
        print("---")
        print()
    print(task_section)
    # 场景原文附取：--spec 缺省或无场景引用时静默跳过，不产生噪音
    if spec_path is None:
        return 0
    names = parse_scenario_names(task_section)
    if not names:
        return 0
    sections, missing = extract_scenarios(read_text(spec_path), names)
    if sections:
        print()
        print("## 关联场景原文（由 task_brief 从 delta spec 确定性抽取）")
        print()
        for section in sections:
            print(section)
            print()
    if missing:
        print(f"<!-- 场景原文未命中：{ '、'.join(missing) }。请 controller 从 delta spec 手工补充后随 Context 注入 -->")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：参数校验失败给出可执行的下一步指引（对齐 UX 原则）。"""
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="tasks.md 任务 brief 切分（subagent 派发用）")
    parser.add_argument("tasks_md", help="tasks.md 文件路径")
    parser.add_argument("number", type=int, help="任务号 N（### Task N）")
    parser.add_argument("--spec", default=None, help="delta spec 路径，附场景原文（推荐，subagent 零上下文）")
    args = parser.parse_args(argv)
    try:
        return build_brief(args.tasks_md, args.number, args.spec)
    except FileNotFoundError as exc:
        print(f"错误：文件不存在：{exc.filename}", file=sys.stderr)
        print("下一步：确认 tasks.md 路径（openspec/changes/<feature>/tasks.md）后重试", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"错误：读取失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
