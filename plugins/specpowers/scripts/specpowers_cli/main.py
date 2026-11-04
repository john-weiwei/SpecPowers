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
        if (cur / ".zcode-plugin").exists() or (cur / ".claude-plugin").exists() or (cur / ".codex-plugin").exists() or (cur / ".codebuddy-plugin").exists():
            return cur
    # 兜底：上三级（即使没有清单目录也按相对结构定位）
    return Path(__file__).resolve().parent.parent.parent.parent


def _get_assets_dir() -> Path:
    """Get the skill assets directory (SKILL.md, prompts/, templates/).

    新结构下位于 <plugin_root>/skills/specpowers/。
    """
    return _get_plugin_root() / "skills" / "specpowers"


def _get_stage_skills_source() -> Path:
    """Get the stage-skill directories source (<plugin_root>/skills/).

    v2.4.0 起 9 条阶段命令转为独立技能目录（skills/specpowers-<stage>/），
    另含内置审查技能 specpowers-review——pip 安装直接整目录拷贝，
    与插件市场形态的 11 技能集合保持一致。
    """
    return _get_plugin_root() / "skills"


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


def _copy_agent_files(project_dir: Path, integration: dict):
    """Copy skill files to the agent's skills directory.

    Creates:
      <skills_root>/specpowers/             ← main skill (SKILL.md + prompts/ + bin/)
      <skills_root>/specpowers-<stage>/     ← 10 skills (9 阶段技能 + 内置 review)
    """
    assets = _get_assets_dir()
    skills_source = _get_stage_skills_source()
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

    # 2. Stage skills: specpowers-<stage>/ (9 阶段技能 + 内置 review，整目录拷贝)
    #    v2.4.0 命令转技能后源目录已带规范 frontmatter，直接拷贝即可；
    #    旧的"从 commands/*.md 生成技能并注入 name"逻辑随 commands/ 删除而废弃
    #    （v2.5.1 修复：此前安装器仍指向已删除的 commands/，pip 形态 9 个阶段技能从未被安装）
    for skill_source in sorted(skills_source.glob("specpowers-*")):
        if not skill_source.is_dir():
            continue
        _atomic_copytree(skill_source, skills_root / skill_source.name)


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
.specpowers/reports/
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


AGENTS_MD_BEGIN = "<!-- specpowers:begin -->"
AGENTS_MD_END = "<!-- specpowers:end -->"


def _write_agents_md_section(project_dir: Path, skills_root_rel: str) -> None:
    """向项目根 AGENTS.md 写入 SpecPowers 引导段（幂等，标记段整体替换）。

    AGENTS.md 是跨 agent 工具的事实标准引导文件——对不读取 skills 目录
    的规则驱动型工具，这是模型发现 SpecPowers 入口的唯一途径；对已支持
    skills 的工具则提供路径速查。标记段外的用户内容不受影响，删除整段
    后重新执行安装即可恢复。

    Args:
        project_dir: 项目根路径（AGENTS.md 所在目录）。
        skills_root_rel: 技能根目录相对路径（POSIX 风格，如 .workbuddy/skills）。

    作者：SpecPowers Team 2026-11-03（ZCode / GLM-5.3）
    """
    # 引导段正文：11 技能入口表 + 契约位置 + CLI 调用方式（路径保持 POSIX 风格）
    section = f"""{AGENTS_MD_BEGIN}
## SpecPowers 流水线

spec-driven 开发流水线已安装到本项目的 `{skills_root_rel}/`（11 个技能：主技能 specpowers + 9 个阶段技能 + specpowers-review 审查）。**新需求先走探索阶段**。

| 阶段 | 技能入口（SKILL.md） |
|------|---------------------|
| 项目初始化 | `{skills_root_rel}/specpowers-init/SKILL.md` |
| 需求探索（方案对比 + 设计文档落盘） | `{skills_root_rel}/specpowers-explore/SKILL.md` |
| 提案三件套 | `{skills_root_rel}/specpowers-propose/SKILL.md` |
| 执行构建 | `{skills_root_rel}/specpowers-apply/SKILL.md` |
| 归档收尾 | `{skills_root_rel}/specpowers-archive/SKILL.md` |
| 小改动快速通道 | `{skills_root_rel}/specpowers-fast/SKILL.md` |
| 无人值守全流程 | `{skills_root_rel}/specpowers-auto/SKILL.md` |
| 基线刷新 / 状态重置 | `{skills_root_rel}/specpowers-baseline/SKILL.md`、`{skills_root_rel}/specpowers-reset/SKILL.md` |
| 独立审查 | `{skills_root_rel}/specpowers-review/SKILL.md` |

阶段契约与模板位于 `{skills_root_rel}/specpowers/prompts/`（如 `prompts/explore.md`）；主技能总览 `{skills_root_rel}/specpowers/SKILL.md`。

确定性层 CLI：`python -m specpowers_cli.bridge.facade <子命令> --root .`（包不可达时改用包装脚本 `{skills_root_rel}/specpowers/bin/specpowers`，Windows 为 `specpowers.bat`）。

本段由 `specpowers init` 自动维护（重装时整体替换）；删除整段后重新执行安装可恢复。
{AGENTS_MD_END}
"""
    agents_md = project_dir / "AGENTS.md"
    if agents_md.exists():
        content = agents_md.read_text(encoding="utf-8")
        if AGENTS_MD_BEGIN in content:
            # 已有标记段：定位起止整体删除旧段，实现重装幂等替换（段前段后用户内容均保留）
            start = content.index(AGENTS_MD_BEGIN)
            end = content.index(AGENTS_MD_END) + len(AGENTS_MD_END)
            before = content[:start].rstrip("\n")
            after = content[end:].lstrip("\n")
            parts = [p for p in (before, section, after) if p]
            content = "\n\n".join(parts)
        else:
            # 无标记段：纯追加
            content = content.rstrip("\n") + "\n\n" + section
        agents_md.write_text(content, encoding="utf-8", newline="\n")
    else:
        # 不存在：创建最小骨架 + 引导段
        agents_md.write_text("# AGENTS.md\n\n" + section, encoding="utf-8", newline="\n")
    print(f"AGENTS.md 引导段已写入：{agents_md}")


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize SpecPowers in a project directory."""
    target = Path(args.directory or ".").resolve()

    if not target.exists():
        target.mkdir(parents=True)

    # --skills-root 与 --integration 互斥：二选一指定安装位置
    if args.skills_root and args.integration:
        print("Error: --skills-root 与 --integration 互斥，请二选一指定安装位置。")
        return 1

    if args.skills_root:
        # 任意 agent 工具通用接入（v2.6.0）：用户显式指定技能目录，无需改代码加集成
        skills_root_rel = Path(args.skills_root).as_posix()
        integration = {"name": "custom (--skills-root)", "skills_root": skills_root_rel}
        integration_name = "custom"
    else:
        # Detect or use specified integration
        integration_name = args.integration
        if not integration_name:
            integration_name = _detect_agent(target)
            if not integration_name:
                print("╔══════════════════════════════════════════════╗")
                print("║  No AI agent detected in this project.       ║")
                print("║  Use --integration <agent> to specify one,   ║")
                print("║  or --skills-root <path> for any other tool. ║")
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
    print(f"  Skills:  {integration['skills_root']}/  (11 skills: specpowers + 10 specpowers-*)")

    _copy_agent_files(target, integration)
    _copy_runtime_files(target, integration)
    # AGENTS.md 引导段：对规则驱动型工具是发现入口的唯一途径，幂等标记段
    _write_agents_md_section(target, integration["skills_root"])

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
        "--skills-root",
        help="Custom skills directory (relative to project) for any agent tool not in --integration list"
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
