#!/usr/bin/env python3
"""SpecPowers Facade — single entry point for deterministic execution layer.

All calls from the cognitive layer (SKILL.md/prompts/) go through this module.
Never call bridge submodules directly.

Usage:
    python -m specpowers_cli.bridge.facade <subcommand> [options]

Subcommands (user-facing, called by skill slash commands):
    constitution [--force]       Generate constitution + baseline scan
    brainstorm "<requirement>"   Start feature with exploration
    specify "<requirement>"      Start/open feature scenario
    fast "<requirement>"         Start feature in fast/optimized mode
    plan                         Generate implementation plan
    build                        Enter build phase with structure gate
    archive [--force-merge-check]  Finalize and archive
    baseline                     Manual baseline refresh
    reset                        Reset state (clear state + lock)

Internal subcommands (for CI / agent direct use):
    scan [--root <path>]         Run baseline scanner
    gate [--base <ref>]          Extract structure gate signals
    status                       Print current state
    version                      Print version
    record-execution-mode <mode> Record build execution mode (conductor|worktree|subagent|tdd)
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


def _cmd_constitution(args: list[str], root: Path) -> int:
    """Handle constitution command."""
    from specpowers_cli.bridge.dispatcher import route
    force = "--force" in args
    # Ensure git repo
    from specpowers_cli.bridge.core.git_util import is_git_repo
    if not is_git_repo(root):
        from specpowers_cli.bridge.core.errors import NotGitRepoError
        raise NotGitRepoError(f"'{root}' is not a git repository.")
    return route("constitution", "full", root, extra={"force": force})


def _cmd_brainstorm(args: list[str], root: Path) -> int:
    """Handle brainstorm command."""
    from specpowers_cli.bridge.dispatcher import route
    req = " ".join(args) if args else ""
    if not req.strip():
        print("Error: brainstorm requires a requirement description.", file=sys.stderr)
        return 2
    return route("brainstorm", "full", root, extra={"requirement": req})


def _cmd_specify(args: list[str], root: Path) -> int:
    """Handle specify command."""
    from specpowers_cli.bridge.dispatcher import route
    req = " ".join(args) if args else ""
    if not req.strip():
        print("Error: specify requires a requirement description.", file=sys.stderr)
        return 2
    return route("specify", "full", root, extra={"requirement": req})


def _cmd_fast(args: list[str], root: Path) -> int:
    """Handle fast command."""
    from specpowers_cli.bridge.dispatcher import route
    req = " ".join(args) if args else ""
    if not req.strip():
        print("Error: fast requires a requirement description.", file=sys.stderr)
        return 2
    return route("fast", "fast", root, extra={"requirement": req})


def _cmd_plan(args: list[str], root: Path) -> int:
    """Handle plan command."""
    from specpowers_cli.bridge.dispatcher import route
    return route("plan", "full", root)


def _cmd_build(args: list[str], root: Path) -> int:
    """Handle build command."""
    from specpowers_cli.bridge.dispatcher import route
    return route("build", "full", root)


def _cmd_archive(args: list[str], root: Path) -> int:
    """Handle archive command."""
    from specpowers_cli.bridge.dispatcher import route
    force_merge = "--force-merge-check" in args
    return route("archive", "full", root, extra={"force_merge_check": force_merge})


def _cmd_baseline(args: list[str], root: Path) -> int:
    """Handle baseline command."""
    from specpowers_cli.bridge.dispatcher import route
    return route("baseline", "full", root)


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
        "constitution": _cmd_constitution,
        "brainstorm": _cmd_brainstorm,
        "specify": _cmd_specify,
        "fast": _cmd_fast,
        "plan": _cmd_plan,
        "build": _cmd_build,
        "archive": _cmd_archive,
        "baseline": _cmd_baseline,
        "reset": _cmd_reset,
        "status": _cmd_status,
        "scan": _cmd_scan,
        "gate": _cmd_gate,
        "record-execution-mode": _cmd_record_execution_mode,
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
