#!/usr/bin/env python3
"""SpecPowers Facade — single entry point for deterministic execution layer.

All calls from the cognitive layer (SKILL.md/prompts/) go through this module.
Never call bridge submodules directly.

Usage:
    python -m specpowers_cli.bridge.facade <subcommand> [options]

Subcommands (user-facing, called by skill slash commands):
    init [--force]               Generate constitution + baseline scan
    explore "<requirement>"      Start feature with exploration
    propose "<requirement>"      One-shot generate proposal/spec/tasks (OpenSpec change)
    fast "<requirement>"         Start feature in fast/optimized mode
    apply                        Enter apply phase with structure gate
    archive [--force-merge-check]  Finalize and archive
    baseline                     Manual baseline refresh
    reset                        Reset state (clear state + lock)

Auto iteration subcommands (multi-round iteration, see docs/auto-iteration-plan.md):
    auto-status [--design-doc <path>] [--instruction "<desc>"]
                                 三分判定 fresh/resume/iterate（只读；fresh 时顺带清理归档残留）；
                                 响应携带 clarification 视图（上一轮澄清 ceiling + pending_input 停靠保护）
    auto new-round [--design-doc <path>] [--instruction "<desc>"]
                                 受控轮次切换：stage → propose、feature 锁定、rounds 落盘（auto 专用）
    auto clarify --ceiling <full|explore> [--report <路径>]
                                 需求澄清结论登记（写/刷新 auto_base.json 的 clarification 字段，
                                 resume 凭据；见 docs/auto-clarification-plan.md）
    iterate [--design-doc <path>] [--instruction "<desc>"]
                                 人工模式迭代轮切换原语（由 /specpowers-propose、/specpowers-explore
                                 重入识别确认后调用；同 new-round 但不要求 auto_base.json）

Internal subcommands (for CI / agent direct use):
    scan [--root <path>]         Run baseline scanner
    gate [--base <ref>]          Extract structure gate signals
    status                       Print current state
    version                      Print version
    record-execution-mode <mode> Record apply execution mode (conductor|worktree|subagent|tdd)
    record-design-doc <path>     Register explore design doc path (propose 前置校验凭据)

> v2.0.0 起旧子命令名（constitution/brainstorm/specify/plan/build）已移除，无别名。
"""

import json
import os
import sys
from pathlib import Path

from specpowers_cli import __version__


def _find_project_root() -> Path:
    """Find the project root by looking for .git directory."""
    current = Path.cwd()
    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent
    # Fallback to cwd
    return Path.cwd()


def _resolve_root(root_arg: str | None) -> Path:
    """Resolve --root argument or find project root."""
    if root_arg:
        p = Path(root_arg).resolve()
        if not p.exists():
            print(f"Error: path '{root_arg}' does not exist", file=sys.stderr)
            sys.exit(2)
        return p
    return _find_project_root()


def _extract_global_options(rest: list[str]) -> tuple[str | None, list[str]]:
    """从参数列表中提取全局选项 --root，并返回剩余参数。

    支持 --root <path>（空格分隔）与 --root=<path>（等号）两种形式。
    提取后从剩余参数中移除，避免 --root 被拼进各子命令的 requirement。

    作者：005819 | 协作：GLM-5.2
    """
    root_arg = None
    remaining: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        if a == "--root":
            # --root 缺值（位于末尾或下一项是另一选项）直接报错退出，
            # 避免 "--root" 字符串被拼进 requirement 变成 feature 名
            if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
                print("Error: --root requires a path value.", file=sys.stderr)
                sys.exit(2)
            # --root <path> 形式：下一项作为值，跳过两项
            root_arg = rest[i + 1]
            i += 2
            continue
        if a.startswith("--root="):
            # --root=<path> 形式：等号后作为值，跳过当前项
            root_arg = a[len("--root="):]
            i += 1
            continue
        remaining.append(a)
        i += 1
    return root_arg, remaining


def print_help():
    """Print usage help."""
    print(__doc__)
    print("Options:")
    print("  --root <path>     Project root directory (auto-detected if omitted)")
    print("  --base <ref>      Git base ref for comparison (default: HEAD~1)")
    print("  -h, --help        Show this help")


def _cmd_init(args: list[str], root: Path) -> int:
    """Handle init command."""
    from specpowers_cli.bridge.dispatcher import route
    force = "--force" in args
    # Ensure git repo
    from specpowers_cli.bridge.core.git_util import is_git_repo
    if not is_git_repo(root):
        from specpowers_cli.bridge.core.errors import NotGitRepoError
        raise NotGitRepoError(f"'{root}' is not a git repository.")
    return route("init", "full", root, extra={"force": force})


def _cmd_explore(args: list[str], root: Path) -> int:
    """Handle explore command."""
    from specpowers_cli.bridge.dispatcher import route
    opts, positional = _extract_kv_options(args, ("feature",))
    req = " ".join(positional) if positional else ""
    if not req.strip():
        print("Error: explore requires a requirement description.", file=sys.stderr)
        return 2
    return route("explore", "full", root, extra={
        "requirement": req,
        "feature": opts.get("feature", ""),
    })


def _cmd_propose(args: list[str], root: Path) -> int:
    """Handle propose command — 一站式生成 proposal/spec/tasks 三件套（合并原 specify+plan）。"""
    from specpowers_cli.bridge.dispatcher import route
    opts, positional = _extract_kv_options(args, ("feature",))
    req = " ".join(positional) if positional else ""
    if not req.strip():
        print("Error: propose requires a requirement description.", file=sys.stderr)
        return 2
    return route("propose", "full", root, extra={
        "requirement": req,
        "feature": opts.get("feature", ""),
    })


def _cmd_fast(args: list[str], root: Path) -> int:
    """Handle fast command."""
    from specpowers_cli.bridge.dispatcher import route
    req = " ".join(args) if args else ""
    if not req.strip():
        print("Error: fast requires a requirement description.", file=sys.stderr)
        return 2
    return route("fast", "fast", root, extra={"requirement": req})


def _cmd_apply(args: list[str], root: Path) -> int:
    """Handle apply command."""
    from specpowers_cli.bridge.dispatcher import route
    return route("apply", "full", root)


def _cmd_archive(args: list[str], root: Path) -> int:
    """Handle archive command."""
    from specpowers_cli.bridge.dispatcher import route
    force_merge = "--force-merge-check" in args
    return route("archive", "full", root, extra={"force_merge_check": force_merge})


def _cmd_baseline(args: list[str], root: Path) -> int:
    """Handle baseline command."""
    from specpowers_cli.bridge.dispatcher import route
    return route("baseline", "full", root)


def _extract_kv_options(rest: list[str], keys: tuple[str, ...]) -> tuple[dict, list[str]]:
    """从参数列表提取 --key <value> / --key=<value> 形式的命名选项。

    值缺失（位于末尾或下一项以 -- 开头）直接报错退出，避免把 flag 字符串
    当成值拼进后续逻辑。

    Args:
        rest: 待解析的参数列表（已移除全局 --root）。
        keys: 支持的选项名集合（不含 -- 前缀，如 "design-doc"）。

    Returns:
        (选项字典, 剩余位置参数)。

    作者：005819 | 协作：GLM-5.3
    """
    opts: dict = {}
    remaining: list[str] = []
    i = 0
    while i < len(rest):
        a = rest[i]
        matched = False
        for key in keys:
            flag = f"--{key}"
            if a == flag:
                if i + 1 >= len(rest) or rest[i + 1].startswith("--"):
                    print(f"Error: {flag} requires a value.", file=sys.stderr)
                    sys.exit(2)
                opts[key] = rest[i + 1]
                i += 2
                matched = True
                break
            if a.startswith(flag + "="):
                opts[key] = a[len(flag) + 1:]
                i += 1
                matched = True
                break
        if not matched:
            remaining.append(a)
            i += 1
    return opts, remaining


def _cmd_auto_status(args: list[str], root: Path) -> int:
    """Handle auto-status command — 三分判定（只读，fresh 时顺带清理归档残留）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import auto_status
    opts, _ = _extract_kv_options(args, ("design-doc", "instruction"))
    result = auto_status(
        root,
        design_doc=opts.get("design-doc", ""),
        instruction=opts.get("instruction", ""),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_auto_new_round(args: list[str], root: Path) -> int:
    """Handle auto new-round command — 受控轮次切换（stage → propose，feature 锁定）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import route
    opts, _ = _extract_kv_options(args, ("design-doc", "instruction"))
    return route("auto-new-round", "full", root, extra={
        "design_doc": opts.get("design-doc", ""),
        "instruction": opts.get("instruction", ""),
    })


def _cmd_auto_clarify(args: list[str], root: Path) -> int:
    """Handle auto clarify command — 需求澄清结论登记（ceiling 落盘，见 docs/auto-clarification-plan.md）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import route
    opts, _ = _extract_kv_options(args, ("ceiling", "report"))
    ceiling = (opts.get("ceiling") or "").strip()
    # 旧值兼容：v1.x 登记 brainstorm（停靠在原 brainstorm 阶段）读入归一为 explore
    if ceiling == "brainstorm":
        ceiling = "explore"
    if ceiling not in ("full", "explore"):
        print(
            "Error: auto clarify requires --ceiling <full|explore>.",
            file=sys.stderr,
        )
        return 2
    return route("auto-clarify", "full", root, extra={
        "ceiling": ceiling,
        "report": opts.get("report", ""),
    })


def _cmd_iterate(args: list[str], root: Path) -> int:
    """Handle iterate command — 人工模式迭代轮入口（不要求 auto_base.json）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import route
    opts, _ = _extract_kv_options(args, ("design-doc", "instruction"))
    return route("iterate", "full", root, extra={
        "design_doc": opts.get("design-doc", ""),
        "instruction": opts.get("instruction", ""),
    })


def _cmd_record_design_doc(args: list[str], root: Path) -> int:
    """Handle record-design-doc command — 登记探索设计文档路径（propose 前置校验凭据）。

    Usage: record-design-doc <设计文档路径>

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import route
    positional = [a for a in args if not a.startswith("--")]
    if not positional:
        print(
            "Error: record-design-doc requires a design doc path.",
            file=sys.stderr,
        )
        return 2
    return route("record-design-doc", "full", root, extra={
        "design_doc": " ".join(positional),
    })


def _cmd_reset(args: list[str], root: Path) -> int:
    """Handle reset command."""
    from specpowers_cli.bridge.dispatcher import route
    return route("reset", "full", root)


def _cmd_status(args: list[str], root: Path) -> int:
    """Handle status command."""
    from specpowers_cli.bridge.core.fs_state import load_state
    state = load_state(root)
    print(json.dumps(state, indent=2))
    return 0


def _cmd_scan(args: list[str], root: Path) -> int:
    """Handle internal scan command."""
    from specpowers_cli.bridge.modules.baseline_scanner import scan
    scan(root)
    print(f"Baseline scanned successfully: {root / '.specpowers' / 'baseline.json'}")
    return 0


def _cmd_gate(args: list[str], root: Path) -> int:
    """Handle internal gate command."""
    import json
    import re

    base = "HEAD~1"
    for i, a in enumerate(args):
        if a == "--base" and i + 1 < len(args):
            candidate = args[i + 1]
            # 校验 ref 合法性：必须以字母/数字开头，仅含 ref 合法字符。
            # 防止以 "-" 开头的值（如 --output=xxx）被 git 当作选项执行（参数注入）
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/@^~-]*", candidate):
                print(
                    f"Error: invalid --base value '{candidate}' "
                    "(must be a git ref, cannot start with '-').",
                    file=sys.stderr,
                )
                return 2
            base = candidate

    from specpowers_cli.bridge.core.git_util import diff_stat
    from specpowers_cli.bridge.modules.baseline_scanner import load_baseline
    from specpowers_cli.bridge.modules.structure_gate import extract_signals

    diff = diff_stat(root, base)
    baseline = load_baseline(root)
    signals = extract_signals(diff, baseline)
    print(json.dumps({"signals": signals, "base": base, "diff_lines": len(diff.splitlines()) if diff else 0}))
    return 0


def _cmd_version(args: list[str], root: Path) -> int:
    """Handle version command."""
    print(f"SpecPowers bridge v{__version__}")
    return 0


def _cmd_record_execution_mode(args: list[str], root: Path) -> int:
    """记录 build 阶段用户选择的执行方式到 state.json。

    落地 build.md 第二步的承诺：执行方式持久化到 state（execution_mode 字段），
    并对 fast 模式做 worktree/subagent 禁用校验（确定性层纵深防御）。

    Usage: record-execution-mode <conductor|worktree|subagent|tdd>

    作者：005819 | 协作：GLM-5.2
    """
    if not args:
        print(
            "Error: record-execution-mode requires an execution mode "
            "(conductor|worktree|subagent|tdd).",
            file=sys.stderr,
        )
        return 2
    mode = args[0]
    from specpowers_cli.bridge.core.fs_state import load_state
    from specpowers_cli.bridge.core.lock import acquire_lock, release_lock
    from specpowers_cli.bridge.modules.mode_controller import set_execution_mode
    # 写 state 需获取锁，防止并发 stage 操作交叉写入
    acquire_lock(root, timeout=0)
    try:
        state = load_state(root)
        state = set_execution_mode(root, state, mode)
    finally:
        release_lock(root)
    print(f"执行方式已记录：{state['execution_mode']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    subcommand = argv[0]
    rest = argv[1:]

    # "auto status" / "auto new-round" 空格形式归一化为连字符子命令（auto-status / auto-new-round）
    # 作者：005819 | 协作：GLM-5.3
    if subcommand == "auto" and rest:
        subcommand = f"auto-{rest[0]}"
        rest = rest[1:]

    # 提取全局选项 --root 并从 rest 中移除，防止其被拼进 requirement
    root_arg, rest = _extract_global_options(rest)

    # Subcommands that don't need project root
    if subcommand in ("--help", "-h", "help"):
        print_help()
        return 0
    if subcommand in ("version", "--version", "-V"):
        return _cmd_version(rest, Path.cwd())

    # Resolve project root
    try:
        root = _resolve_root(root_arg)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Dispatch subcommand
    handlers = {
        "init": _cmd_init,
        "explore": _cmd_explore,
        "propose": _cmd_propose,
        "fast": _cmd_fast,
        "apply": _cmd_apply,
        "archive": _cmd_archive,
        "baseline": _cmd_baseline,
        "reset": _cmd_reset,
        "status": _cmd_status,
        "scan": _cmd_scan,
        "gate": _cmd_gate,
        "record-execution-mode": _cmd_record_execution_mode,
        "record-design-doc": _cmd_record_design_doc,
        "auto-status": _cmd_auto_status,
        "auto-new-round": _cmd_auto_new_round,
        "auto-clarify": _cmd_auto_clarify,
        "iterate": _cmd_iterate,
    }

    handler = handlers.get(subcommand)
    if handler is None:
        print(f"Error: unknown subcommand '{subcommand}'", file=sys.stderr)
        print_help()
        return 2

    try:
        return handler(rest, root)
    except Exception as e:
        # Unified error handling
        exit_code = getattr(e, "exit_code", 1)
        detail = getattr(e, "detail", None)
        print(f"Error: {e}", file=sys.stderr)
        if detail:
            print(f"  Detail: {detail}", file=sys.stderr)
        # Check for verbose mode
        if os.environ.get("SPECPOWERS_VERBOSE"):
            import traceback
            traceback.print_exc(file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
