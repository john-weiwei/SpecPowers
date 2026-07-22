#!/usr/bin/env python3
"""SpecPowers Facade — single entry point for deterministic execution layer.

All calls from the cognitive layer (SKILL.md/prompts/) go through this module.
Never call bridge submodules directly.

Usage:
    python bridge/facade.py <subcommand> [options]

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
"""

import os
import sys
from pathlib import Path


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


def print_help():
    """Print usage help."""
    print(__doc__)
    print("Options:")
    print("  --root <path>     Project root directory (auto-detected if omitted)")
    print("  --base <ref>      Git base ref for comparison (default: HEAD~1)")
    print("  -h, --help        Show this help")


def _cmd_constitution(args: list[str], root: Path) -> int:
    """Handle constitution command."""
    from bridge.dispatcher import route
    force = "--force" in args
    # Ensure git repo
    from bridge.core.git_util import is_git_repo
    if not is_git_repo(root):
        from bridge.core.errors import NotGitRepoError
        raise NotGitRepoError(f"'{root}' is not a git repository.")
    return route("constitution", "full", root, extra={"force": force})


def _cmd_brainstorm(args: list[str], root: Path) -> int:
    """Handle brainstorm command."""
    from bridge.dispatcher import route
    req = " ".join(args) if args else ""
    if not req.strip():
        print("Error: brainstorm requires a requirement description.", file=sys.stderr)
        return 2
    return route("brainstorm", "full", root, extra={"requirement": req})


def _cmd_specify(args: list[str], root: Path) -> int:
    """Handle specify command."""
    from bridge.dispatcher import route
    req = " ".join(args) if args else ""
    if not req.strip():
        print("Error: specify requires a requirement description.", file=sys.stderr)
        return 2
    return route("specify", "full", root, extra={"requirement": req})


def _cmd_fast(args: list[str], root: Path) -> int:
    """Handle fast command."""
    from bridge.dispatcher import route
    req = " ".join(args) if args else ""
    if not req.strip():
        print("Error: fast requires a requirement description.", file=sys.stderr)
        return 2
    return route("fast", "fast", root, extra={"requirement": req})


def _cmd_plan(args: list[str], root: Path) -> int:
    """Handle plan command."""
    from bridge.dispatcher import route
    return route("plan", "full", root)


def _cmd_build(args: list[str], root: Path) -> int:
    """Handle build command."""
    from bridge.dispatcher import route
    return route("build", "full", root)


def _cmd_archive(args: list[str], root: Path) -> int:
    """Handle archive command."""
    from bridge.dispatcher import route
    force_merge = "--force-merge-check" in args
    return route("archive", "full", root, extra={"force_merge_check": force_merge})


def _cmd_baseline(args: list[str], root: Path) -> int:
    """Handle baseline command."""
    from bridge.dispatcher import route
    return route("baseline", "full", root)


def _cmd_reset(args: list[str], root: Path) -> int:
    """Handle reset command."""
    from bridge.dispatcher import route
    return route("reset", "full", root)


def _cmd_status(args: list[str], root: Path) -> int:
    """Handle status command."""
    from bridge.core.fs_state import load_state
    state = load_state(root)
    print(json.dumps(state, indent=2))
    return 0


def _cmd_scan(args: list[str], root: Path) -> int:
    """Handle internal scan command."""
    from bridge.modules.baseline_scanner import scan
    scan(root)
    print(f"Baseline scanned successfully: {root / '.specpowers' / 'baseline.json'}")
    return 0


def _cmd_gate(args: list[str], root: Path) -> int:
    """Handle internal gate command."""
    import json

    base = "HEAD~1"
    for i, a in enumerate(args):
        if a == "--base" and i + 1 < len(args):
            base = args[i + 1]

    from bridge.core.git_util import diff_stat
    from bridge.modules.baseline_scanner import load_baseline
    from bridge.modules.structure_gate import extract_signals

    diff = diff_stat(root, base)
    baseline = load_baseline(root)
    signals = extract_signals(diff, baseline)
    print(json.dumps({"signals": signals, "base": base, "diff_lines": len(diff.splitlines()) if diff else 0}))
    return 0


def _cmd_version(args: list[str], root: Path) -> int:
    """Handle version command."""
    from bridge import __version__
    print(f"SpecPowers bridge v{__version__}")
    return 0


import json  # noqa: E402 (used by _cmd_status)


def main(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] in ("-h", "--help", "help"):
        print_help()
        return 0

    subcommand = argv[0]
    rest = argv[1:]

    # Extract --root if present
    root_arg = None
    for i, a in enumerate(rest):
        if a == "--root" and i + 1 < len(rest):
            root_arg = rest[i + 1]
            break

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
