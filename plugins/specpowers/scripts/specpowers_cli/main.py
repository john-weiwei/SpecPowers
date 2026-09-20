"""SpecPowers CLI — install the specpowers plugin into any project.

Usage:
    specpowers init [directory] [--integration <agent>] [--force]
    specpowers version
    specpowers --help

Examples:
    specpowers init                         # Init current dir, auto-detect agent
    specpowers init my-project              # Init new directory
    specpowers init --integration workbuddy  # Force WorkBuddy integration
    specpowers init --integration claude     # Claude Code integration
    specpowers init --integration cursor     # Cursor integration
"""

import argparse
import os
import shutil
import sys
from pathlib import Path

from specpowers_cli import __version__

# ── Supported integrations ────────────────────────────────────────────

INTEGRATIONS = {
    "workbuddy": {
        "name": "WorkBuddy",
        "skills_root": ".workbuddy/skills",
    },
    "claude": {
        "name": "Claude Code",
        "skills_root": ".claude/skills",
    },
    "cursor": {
        "name": "Cursor",
        "skills_root": ".cursor/skills",
    },
    "copilot": {
        "name": "GitHub Copilot",
        "skills_root": ".github/skills",
    },
    "windsurf": {
        "name": "Windsurf",
        "skills_root": ".windsurf/skills",
    },
    "codex": {
        "name": "OpenAI Codex CLI",
        "skills_root": ".codex/skills",
    },
    "zcode": {
        "name": "ZCode",
        "skills_root": ".zcode/skills",
    },
}


def _detect_agent(project_dir: Path) -> str | None:
    """Auto-detect which AI agent is used in this project."""
    signals = {
        "workbuddy": [".workbuddy"],
        "claude": [".claude", "CLAUDE.md"],
        "cursor": [".cursor", ".cursorrules"],
        "copilot": [".github/copilot-instructions.md"],
        "windsurf": [".windsurfrules"],
        "zcode": [".zcode", "ZCODE.md"],
    }
    for agent, paths in signals.items():
        for p in paths:
            if (project_dir / p).exists():
                return agent
    return None


def _get_plugin_root() -> Path:
    """定位插件根目录（含 .zcode-plugin/ 等清单目录的标志）。

    新插件布局：
        <plugin_root>/
        ├── .zcode-plugin/  (等清单目录)
        ├── commands/
        ├── skills/specpowers/  (SKILL.md + prompts/ + templates/)
        └── scripts/specpowers_cli/  ← 本文件在此
    """
    cur = Path(__file__).resolve().parent
    # scripts/specpowers_cli/ → 上三级到插件根
    for _ in range(4):
        cur = cur.parent
        if (cur / ".zcode-plugin").exists() or (cur / ".claude-plugin").exists() or (cur / ".codex-plugin").exists():
            return cur
    # 兜底：上三级（即使没有清单目录也按相对结构定位）
    return Path(__file__).resolve().parent.parent.parent.parent


def _get_assets_dir() -> Path:
    """Get the skill assets directory (SKILL.md, prompts/, templates/).

    新结构下位于 <plugin_root>/skills/specpowers/。
    """
    return _get_plugin_root() / "skills" / "specpowers"


def _get_commands_dir() -> Path:
    """Get the commands directory (<plugin_root>/commands/)."""
    return _get_plugin_root() / "commands"


def _atomic_copytree(src: Path, dst: Path, ignore=None) -> None:
    """原子拷贝目录树：先拷到临时目录，成功后替换目标。

    避免 --force 重装时 rmtree 后 copytree 中途失败留下半拷贝损坏态。
    失败时清理临时目录，保持目标原样不变。
    """
    dst_parent = dst.parent
    tmp_dst = dst_parent / f".{dst.name}.tmp-{os.getpid()}"
    if tmp_dst.exists():
        shutil.rmtree(tmp_dst)
    try:
        shutil.copytree(src, tmp_dst, ignore=ignore)
        # 原子替换：先删目标再 rename（dst 存在时 os.replace 跨目录不保证原子）
        if dst.exists():
            old_backup = dst_parent / f".{dst.name}.bak-{os.getpid()}"
            if old_backup.exists():
                shutil.rmtree(old_backup)
            os.replace(dst, old_backup)
            try:
                os.replace(tmp_dst, dst)
            except Exception:
                # 第二步失败：把旧数据移回原位，避免目标缺失、旧数据滞留 .bak
                os.replace(old_backup, dst)
                raise
            shutil.rmtree(old_backup, ignore_errors=True)
        else:
            os.replace(tmp_dst, dst)
    except Exception:
        if tmp_dst.exists():
            shutil.rmtree(tmp_dst, ignore_errors=True)
        raise


def _with_skill_name(content: str, skill_name: str) -> str:
    """为生成的 SKILL.md frontmatter 注入 name 属性（已有则覆盖）。

    skill 规范要求 frontmatter 声明 name 且与目录名一致；
    command 源文件只有 description，复制时在此补齐。
    """
    if not content.startswith("---"):
        # 无 frontmatter：包一层只含 name 的头
        return f"---\nname: {skill_name}\n---\n{content}"
    lines = content.splitlines(keepends=True)
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        # 只有起始 --- 无闭合，视为格式损坏，同样补标准头
        return f"---\nname: {skill_name}\n---\n{content}"
    body = lines[1:end]
    for idx, line in enumerate(body):
        if line.strip().startswith("name:"):
            body[idx] = f"name: {skill_name}\n"
            return "---\n" + "".join(body) + "".join(lines[end:])
    return lines[0] + f"name: {skill_name}\n" + "".join(body) + "".join(lines[end:])


def _copy_agent_files(project_dir: Path, integration: dict):
    """Copy skill files to the agent's skills directory.

    Creates:
      <skills_root>/specpowers/             ← main skill (SKILL.md + prompts/ + bin/)
      <skills_root>/specpowers-<stage>/     ← 9 individual skills (SKILL.md each)
    """
    assets = _get_assets_dir()
    commands_dir = _get_commands_dir()
    skills_root = project_dir / integration["skills_root"]

    # 1. Main skill: specpowers/ (SKILL.md + prompts + bin)
    main_skill = skills_root / "specpowers"
    main_skill.mkdir(parents=True, exist_ok=True)

    src_skill = assets / "SKILL.md"
    if src_skill.exists():
        shutil.copy2(src_skill, main_skill / "SKILL.md")

    src_prompts = assets / "prompts"
    if src_prompts.exists():
        prompts_target = main_skill / "prompts"
        _atomic_copytree(src_prompts, prompts_target)

    # 拷贝 templates/ 目录（constitution 等内联生成模板）
    src_templates = assets / "templates"
    if src_templates.exists():
        templates_target = main_skill / "templates"
        _atomic_copytree(src_templates, templates_target)

    bin_target = main_skill / "bin"
    bin_source = Path(__file__).resolve().parent / "bin"
    if bin_source.exists():
        _atomic_copytree(bin_source, bin_target)

    # 2. Individual skills: specpowers-<stage>/SKILL.md (9 skills)
    #    命令文件已去 specpowers. 前缀（init.md 等），这里恢复成独立 skill
    if commands_dir.exists():
        for cmd_file in commands_dir.glob("*.md"):
            # init.md → specpowers-init/SKILL.md
            skill_name = f"specpowers-{cmd_file.stem}"
            skill_dir = skills_root / skill_name
            skill_dir.mkdir(parents=True, exist_ok=True)
            # skill 规范要求 frontmatter 带 name 属性，command 源文件不带，复制时注入
            content = cmd_file.read_text(encoding="utf-8")
            with open(skill_dir / "SKILL.md", "w", encoding="utf-8", newline="") as f:
                f.write(_with_skill_name(content, skill_name))


def _copy_runtime_files(project_dir: Path, integration: dict):
    """Copy the bridge Python package + create .specpowers/ runtime dir.

    拷贝策略（本地 fallback，兑现设计承诺）：
    - 把 specpowers_cli 包完整拷到 <skills_root>/specpowers/specpowers_cli/，
      与 bin/ 同级。这样即使未 pip install，bin 脚本也能通过 PYTHONPATH
      指向本地包运行（见 bin/specpowers 的 fallback 分支）。
    - 同时创建 .specpowers/ 运行时目录 + 更新 .gitignore。

    Args:
        project_dir: 项目根目录。
        integration: 集成配置（提供 skills_root 路径）。
    """
    skills_root = project_dir / integration["skills_root"]
    main_skill = skills_root / "specpowers"

    # 1. 拷贝 specpowers_cli 包（本地 fallback，与 bin/ 同级）
    #    排除 assets/bin —— 它们已由 _copy_agent_files 拷到 skill 根，避免重复
    pkg_source = Path(__file__).resolve().parent
    pkg_target = main_skill / "specpowers_cli"
    _atomic_copytree(
        pkg_source, pkg_target,
        ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "tests", "assets", "bin",
        ),
    )

    # 2. Create .specpowers/ runtime directory
    runtime_dir = project_dir / ".specpowers"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    # 3. Copy .gitignore template
    #    state.json/.lock 个人本地（gitignore）；
    #    openspec change 产物团队可见（提交，归档时移入 openspec/changes/archive/）
    gitignore_path = project_dir / ".gitignore"
    gitignore_entry = """
# SpecPowers personal runtime (do not commit)
.specpowers/state.json
.specpowers/.lock
"""
    if gitignore_path.exists():
        # 显式 UTF-8：Windows 默认用 locale 编码（中文系统为 GBK），
        # 而 .gitignore 通常是 UTF-8，直接 read_text() 会因含非 ASCII 字符报 UnicodeDecodeError
        content = gitignore_path.read_text(encoding="utf-8")
        if ".specpowers/state.json" not in content:
            with open(gitignore_path, "a", encoding="utf-8") as f:
                f.write(gitignore_entry)
    else:
        gitignore_path.write_text(gitignore_entry.strip() + "\n", encoding="utf-8")


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize SpecPowers in a project directory."""
    target = Path(args.directory or ".").resolve()

    if not target.exists():
        target.mkdir(parents=True)

    # Detect or use specified integration
    integration_name = args.integration
    if not integration_name:
        integration_name = _detect_agent(target)
        if not integration_name:
            print("╔══════════════════════════════════════════════╗")
            print("║  No AI agent detected in this project.       ║")
            print("║  Use --integration <agent> to specify one.   ║")
            print("║                                              ║")
            print("║  Supported agents:                           ║")
            for key, info in INTEGRATIONS.items():
                print(f"║    {key:<12} → {info['name']:<25} ║")
            print("╚══════════════════════════════════════════════╝")
            return 1
    elif integration_name not in INTEGRATIONS:
        print(f"Unknown integration: {integration_name}")
        print(f"Supported: {', '.join(INTEGRATIONS.keys())}")
        return 1

    integration = INTEGRATIONS[integration_name]
    skills_root = target / integration["skills_root"]
    main_skill = skills_root / "specpowers"

    # Check if already initialized
    if main_skill.exists() and not args.force:
        print(f"SpecPowers already initialized in {target}")
        print(f"  Skills root: {skills_root}")
        print(f"  Use --force to re-initialize.")
        return 0

    # Copy agent files
    print(f"Initializing SpecPowers v{__version__}")
    print(f"  Project: {target}")
    print(f"  Agent:   {integration['name']} ({integration_name})")
    print(f"  Skills:  {integration['skills_root']}/  (10 skills: specpowers + 9 specpowers-*)")

    _copy_agent_files(target, integration)
    _copy_runtime_files(target, integration)

    print()
    print("Done! SpecPowers is ready.")
    print()
    print("Next steps:")
    print("  1. cd " + (args.directory or "."))
    print("  2. $specpowers-init    ← generate project principles + baseline")
    print("  3. $specpowers-explore \"<requirement>\"   ← start a feature")
    print("     or $specpowers-fast \"<requirement>\"      ← quick fix mode")
    print()
    print("All skills: $specpowers-init $specpowers-explore $specpowers-propose")
    print("            $specpowers-apply $specpowers-archive")
    print("            $specpowers-fast $specpowers-auto $specpowers-baseline $specpowers-reset")
    return 0


def cmd_version(args: argparse.Namespace) -> int:
    """Print version."""
    print(f"SpecPowers CLI v{__version__}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """SpecPowers CLI entry point."""
    if argv is None:
        argv = sys.argv[1:]

    parser = argparse.ArgumentParser(
        prog="specpowers",
        description="Install SpecPowers — a bridging plugin for spec-driven development",
    )
    parser.add_argument(
        "--version", "-V", action="store_true", help="Print version and exit"
    )

    subparsers = parser.add_subparsers(dest="command")

    # ── init ──
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize SpecPowers in a project directory",
        description="Create .specpowers/ runtime dir and install agent skill files (SKILL.md + prompts/)",
    )
    init_parser.add_argument(
        "directory", nargs="?", default=".",
        help="Project directory (default: current)"
    )
    init_parser.add_argument(
        "--integration", "-i",
        choices=list(INTEGRATIONS.keys()),
        help="AI agent to integrate with (auto-detected if omitted)"
    )
    init_parser.add_argument(
        "--force", "-f", action="store_true",
        help="Force re-initialization even if already set up"
    )

    # ── version ──
    subparsers.add_parser("version", help="Print version")

    args = parser.parse_args(argv)

    if args.version or (not argv and not args.command):
        return cmd_version(args)

    if args.command == "init":
        return cmd_init(args)
    elif args.command == "version":
        return cmd_version(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
