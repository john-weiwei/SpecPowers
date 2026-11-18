#!/usr/bin/env python3
"""SpecPowers Facade — single entry point for deterministic execution layer.

All calls from the cognitive layer (SKILL.md/prompts/) go through this module.
Never call bridge submodules directly.

Usage:
    python -m specpowers_cli.bridge.facade <subcommand> [options]

Subcommands (user-facing, called by skill slash commands):
    init [--force]               Generate constitution + baseline scan
    explore "<requirement>" [--feature <slug>]
                                 Start feature with exploration
    propose "<requirement>" [--feature <slug>]
                                 One-shot generate proposal/spec/tasks (OpenSpec change)
    fast "<requirement>" [--feature <slug>]
                                 Start feature in fast/optimized mode
    apply [--feature <slug>]     Enter apply phase with structure gate
    archive [--force-merge-check] [--feature <slug>]
                                 Finalize and archive
    baseline                     Manual baseline refresh
    reset [--feature <slug>] [--force]
                                 Abandon a feature（v3.0 删 change 目录 + auto_base 分片，--force 确认）
    switch <slug>                Switch foreground feature（touch meta last_touched）

v2.8.0 multi-active features（v3.0 起活跃权威 = openspec/changes/ 目录推导）:
- 单活跃需求：命令缺省作用于前台（meta last_touched 最大者），体验与旧版完全一致
- 多活跃 + 推进/破坏性命令（apply/archive/reset/auto 系列/record-*）
  未指名 → 拒绝并列出活跃需求与推导阶段，须带 --feature 重试（防错需求）
- 多活跃 + 只读命令（status/auto-status/sticky）→ 全部活跃需求输出，无需指名
- 归档仅终结该需求（features 移除 + auto_base/<slug>.json 清理），
  其余活跃不受影响，前台自动切到剩余 last_touched 最大者

Auto iteration subcommands (multi-round iteration, see docs/auto-iteration-plan.md):
    auto-status [--design-doc <path>] [--instruction "<desc>"] [--feature <slug>]
                                 三分判定 fresh/resume/iterate（只读；fresh 时顺带清理归档残留）；
                                 响应携带 clarification 视图（上一轮澄清 ceiling + pending_input 停靠保护）
    auto new-round [--design-doc <path>] [--instruction "<desc>"] [--feature <slug>]
                                 auto 迭代轮 rounds 记录（v3.0 起纯 auto_base 落盘，轮次由工件推导）
    auto clarify --ceiling <full|explore> [--report <路径>] [--feature <slug>]
                                 需求澄清结论登记（写/刷新该需求 auto_base 的 clarification 字段，
                                 resume 凭据；见 docs/auto-clarification-plan.md）
    reconcile [--feature <slug>] 工件对账报告（v3.0）：活跃清单/阶段/轮次全推导核对 +
                                 meta 审计警告；不再修复 state（state 已退役）

Internal subcommands (for CI / agent direct use):
    scan [--root <path>]         Run baseline scanner
    gate [--base <ref>]          Extract structure gate signals（v2.3.0 起附 scope 修改范围比对）
    status                       Print current state（v3.0 全推导：前台平铺 + 活跃需求概览）
    version                      Print version
    record-execution-mode <mode> [--feature <slug>]
                                 Record apply execution mode (conductor|worktree|subagent|tdd)
    record-design-doc <path> [--feature <slug>]
                                 Register explore design doc (change 目录 meta，propose 前置凭据)
    resume-probe                 Ambient resume 只读探测（SessionStart hook 消费）：
                                 活跃需求才输出续跑提示，零活跃零噪音，异常降级为空
    sticky-note                  会话粘滞锚点行（UserPromptSubmit hook 消费，v2.7.0）：
                                 每个活跃需求一行锚点（feature/stage/Round + capability +
                                 修改范围，前台标注），零活跃零输出，异常降级为空
    locate                       安装位置自描述（v2.6.0）：输出 CLI 包路径、候选
                                 skills 目录（插件市场/源码树与 pip 两形态）、契约文件
                                 与 bin 包装脚本的实际路径——任意 agent 工具执行一次
                                 即完成自定位，不依赖宿主特性、不需要 --root

v3.0.0 状态机推导化：
- state.json 退役：活跃权威 = openspec/changes/ 目录扫描；阶段/轮次/前台全推导
- 需求级登记（design_doc/mode/execution_mode/last_touched）落 change 目录 meta
- facade iterate 已删除（重入 propose/explore 由目录推导识别为迭代轮）
- reset 语义重定义：删除 change 目录 + auto_base 分片（--force 确认）
- fallback_count/last_archive_ref 迁 .specpowers/runtime.json

> v2.0.0 起旧子命令名（constitution/brainstorm/specify/plan/build）已移除，无别名。
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime, timezone

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
    return route("init", root, extra={"force": force})


def _cmd_explore(args: list[str], root: Path) -> int:
    """Handle explore command."""
    from specpowers_cli.bridge.dispatcher import route
    opts, positional = _extract_kv_options(args, ("feature",))
    req = " ".join(positional) if positional else ""
    if not req.strip():
        print("Error: explore requires a requirement description.", file=sys.stderr)
        return 2
    return route("explore", root, extra={
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
    return route("propose", root, extra={
        "requirement": req,
        "feature": opts.get("feature", ""),
    })


def _cmd_fast(args: list[str], root: Path) -> int:
    """Handle fast command."""
    from specpowers_cli.bridge.dispatcher import route
    opts, positional = _extract_kv_options(args, ("feature",))
    req = " ".join(positional) if positional else ""
    if not req.strip():
        print("Error: fast requires a requirement description.", file=sys.stderr)
        return 2
    return route("fast", root, extra={
        "requirement": req,
        "feature": opts.get("feature", ""),
    })


def _cmd_apply(args: list[str], root: Path) -> int:
    """Handle apply command."""
    from specpowers_cli.bridge.dispatcher import route
    opts, _ = _extract_kv_options(args, ("feature",))
    return route("apply", root, extra={"feature": opts.get("feature", "")})


def _cmd_archive(args: list[str], root: Path) -> int:
    """Handle archive command."""
    from specpowers_cli.bridge.dispatcher import route
    opts, positional = _extract_kv_options(args, ("feature",))
    force_merge = "--force-merge-check" in args
    return route("archive", root, extra={
        "force_merge_check": force_merge,
        "feature": opts.get("feature", "") or (" ".join(positional) if positional else ""),
    })


def _cmd_baseline(args: list[str], root: Path) -> int:
    """Handle baseline command."""
    from specpowers_cli.bridge.dispatcher import route
    return route("baseline", root)


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
    opts, _ = _extract_kv_options(args, ("design-doc", "instruction", "feature"))
    result = auto_status(
        root,
        design_doc=opts.get("design-doc", ""),
        instruction=opts.get("instruction", ""),
        feature=opts.get("feature", ""),
    )
    # 紧凑单行 JSON（v3.1.0）：输出进 LLM 上下文，去 indent 换行省 token
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_auto_new_round(args: list[str], root: Path) -> int:
    """Handle auto new-round command — 受控轮次切换（stage → propose，feature 锁定）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import route
    opts, _ = _extract_kv_options(args, ("design-doc", "instruction", "feature"))
    return route("auto-new-round", root, extra={
        "design_doc": opts.get("design-doc", ""),
        "instruction": opts.get("instruction", ""),
        "feature": opts.get("feature", ""),
    })


def _cmd_auto_clarify(args: list[str], root: Path) -> int:
    """Handle auto clarify command — 需求澄清结论登记（ceiling 落盘，见 docs/auto-clarification-plan.md）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import route
    opts, _ = _extract_kv_options(args, ("ceiling", "report", "feature"))
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
    return route("auto-clarify", root, extra={
        "ceiling": ceiling,
        "report": opts.get("report", ""),
        "feature": opts.get("feature", ""),
    })


def _cmd_record_design_doc(args: list[str], root: Path) -> int:
    """Handle record-design-doc command — 登记探索设计文档路径（propose 前置校验凭据）。

    Usage: record-design-doc <设计文档路径> [--feature <slug>]

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.dispatcher import route
    opts, positional = _extract_kv_options(args, ("feature",))
    if not positional:
        print(
            "Error: record-design-doc requires a design doc path.",
            file=sys.stderr,
        )
        return 2
    return route("record-design-doc", root, extra={
        "design_doc": " ".join(positional),
        "feature": opts.get("feature", ""),
    })


def _cmd_reconcile(args: list[str], root: Path) -> int:
    """Handle reconcile command — 工件对账报告（v3.0：推导核对，不再修复 state）。

    state.json 已退役（v3.0），本命令职责收缩为：
    ① 旧 state 迁移兜底（残留 state.json 的项目顺手迁移）；
    ② 全量推导核对报告——活跃清单/阶段/轮次/前台/meta 审计警告，机器可读。
    锁内执行（迁移含 meta/runtime 写盘）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.core.lock import acquire_lock, release_lock
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, foreground_slug, derive_stage, iteration_count_of,
        audit_artifacts, change_dir_of, migrate_legacy_state,
    )

    opts, _ = _extract_kv_options(args, ("feature",))
    only = (opts.get("feature") or "").strip()

    report: dict = {"migration": {}, "active": [], "foreground": "",
                    "stages": {}, "rounds": {}, "audit": {}, "warnings": []}
    acquire_lock(root, timeout=0)
    try:
        # ① 旧 state 迁移兜底（幂等；无旧 state 零副作用）
        migration = migrate_legacy_state(root)
        if migration.get("migrated"):
            report["migration"] = migration
            report["warnings"].extend(migration.get("warnings", []))

        # ② 全量推导核对
        slugs = active_slugs(root)
        if only:
            slugs = [s for s in slugs if s == only]
        report["active"] = slugs
        report["foreground"] = foreground_slug(root) or ""
        for slug in slugs:
            report["stages"][slug] = derive_stage(change_dir_of(root, slug))
            report["rounds"][slug] = iteration_count_of(change_dir_of(root, slug))
            audit = audit_artifacts(root, slug)
            if audit:
                report["audit"][slug] = audit
                report["warnings"].extend(audit)
    finally:
        release_lock(root)

    # 紧凑单行 JSON + warnings 封顶（v3.1.0）：warnings ∝ 损坏 meta 数无理论上限，
    # 超限截断附计数；audit 明细同源已含于 warnings，报告体量可控
    capped_warnings, warnings_total = _capped_str_list(report["warnings"])
    print(json.dumps(report, ensure_ascii=False) if warnings_total <= len(capped_warnings)
          else json.dumps({**report, "warnings": capped_warnings,
                           "warnings_total": warnings_total}, ensure_ascii=False))
    print(f"对账完成：{len(report['active'])} 个活跃需求"
          f"{'（--feature ' + only + '）' if only else ''}；"
          f"状态唯一权威 = openspec/changes/ 工件推导（state.json 已退役）")
    return 0


def _cmd_switch(args: list[str], root: Path) -> int:
    """Handle switch command — 切换前台需求（v2.8.0 多活跃；v3.0 写 meta）。

    touch 目标需求 meta 的 last_touched（推导式前台的唯一写入口）：
    纯切前台，不开工不推进。锁内执行（meta 原子写）。

    作者：005819 | 协作：GLM-5.3
    """
    from datetime import datetime, timezone as _tz
    from specpowers_cli.bridge.core.lock import acquire_lock, release_lock
    from specpowers_cli.bridge.modules.state_derivation import active_slugs, update_meta
    opts, positional = _extract_kv_options(args, ("feature",))
    slug = (opts.get("feature", "") or " ".join(positional)).strip()
    if not slug:
        print("Error: switch requires a feature slug. Usage: facade switch <slug> --root .", file=sys.stderr)
        return 2
    if slug not in active_slugs(root):
        print(
            f"Error: '{slug}' 不是活跃需求。当前活跃：{', '.join(active_slugs(root)) or '（无）'}。",
            file=sys.stderr,
        )
        return 2
    acquire_lock(root, timeout=0)
    try:
        update_meta(root, slug, {
            "last_touched": datetime.now(_tz.utc).isoformat(timespec="microseconds"),
        })
    finally:
        release_lock(root)
    print(f"前台已切换：{slug}（前台 = 最近操作的需求，其余活跃需求转后台不受影响）")
    return 0


def _cmd_reset(args: list[str], root: Path) -> int:
    """Handle reset command（v3.0：--force 兼任删除确认跳过）。"""
    from specpowers_cli.bridge.dispatcher import route
    opts, _ = _extract_kv_options(args, ("feature",))
    return route("reset", root, extra={
        "feature": opts.get("feature", ""),
        "force": "--force" in args,
    })


def _cmd_status(args: list[str], root: Path) -> int:
    """Handle status command — 全推导拼装（v3.0：零 state 读写）。

    顶层字段与旧扁平视图同名同义（前台需求展开），旧消费者不破坏；
    features 概览键（slug → stage/mode/iteration_count）与 foreground 键
    （前台推导结果）保留；schema 键随 state 退役删除。
    """
    from specpowers_cli.bridge.core.fs_state import load_runtime
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, foreground_slug, derive_stage, iteration_count_of,
        read_meta, design_doc_of, change_dir_of,
    )
    runtime = load_runtime(root)
    fg = foreground_slug(root) or ""
    result = {
        "fallback_count": runtime["fallback_count"],
        "last_archive_ref": runtime["last_archive_ref"],
        "feature": fg,
        "stage": derive_stage(change_dir_of(root, fg)) if fg else "ready",
    }
    if fg:
        cdir = change_dir_of(root, fg)
        meta = read_meta(cdir) or {}
        result["mode"] = str(meta.get("mode") or "full")
        result["execution_mode"] = str(meta.get("execution_mode") or "")
        result["iteration_count"] = iteration_count_of(cdir)
        result["design_doc"] = design_doc_of(root, fg) or ""
    else:
        result.update({"mode": "full", "execution_mode": "", "iteration_count": 0, "design_doc": ""})
    features_overview = {}
    for slug in active_slugs(root):
        cdir = change_dir_of(root, slug)
        meta = read_meta(cdir) or {}
        features_overview[slug] = {
            "stage": derive_stage(cdir),
            "mode": str(meta.get("mode") or "full"),
            "iteration_count": iteration_count_of(cdir),
        }
    result["features"] = features_overview
    result["foreground"] = fg
    # 紧凑单行 JSON（v3.1.0）：indent 换行只增 token 不增信息，LLM 消费方单行可读
    print(json.dumps(result, ensure_ascii=False))
    return 0


def _cmd_scan(args: list[str], root: Path) -> int:
    """Handle internal scan command."""
    from specpowers_cli.bridge.modules.baseline_scanner import scan
    scan(root)
    print(f"Baseline scanned successfully: {root / '.specpowers' / 'baseline.json'}")
    return 0


def _cmd_locate(args: list[str], root: Path) -> int:
    """Handle locate command — 安装位置自描述（任意 agent 工具运行时探测，v2.6.0）。

    输出 JSON：CLI 包绝对路径、候选 skills 目录清单（源码树/插件市场形态
    与 pip 安装形态各自动探测）、每个候选下的技能集合与探索契约存在性、
    bin 包装脚本路径。模型在任何工具里执行一次即完成自定位——不依赖宿主
    环境变量，不需要项目已初始化。

    作者：005819 | 协作：GLM-5.3
    """
    import specpowers_cli
    pkg_dir = Path(specpowers_cli.__file__).resolve().parent
    result = {"cli_package": str(pkg_dir), "candidates": [], "bin_wrapper": None}

    def _record_bin(bin_dir: Path) -> None:
        # 记录包装脚本候选（首次命中即保留：越早的祖先越接近实际安装位置）
        if result["bin_wrapper"] is None and bin_dir.is_dir():
            result["bin_wrapper"] = {
                "posix": str(bin_dir / "specpowers"),
                "windows": str(bin_dir / "specpowers.bat"),
                "exists": (bin_dir / "specpowers").exists() or (bin_dir / "specpowers.bat").exists(),
            }

    for ancestor in pkg_dir.parents:
        # 形态一：源码树/插件市场——包在 <plugin_root>/scripts/specpowers_cli 下
        skills_dir = ancestor / "skills"
        explore_contract = skills_dir / "specpowers" / "prompts" / "explore.md"
        if (skills_dir / "specpowers" / "SKILL.md").is_file():
            result["candidates"].append({
                "kind": "plugin_root",
                "path": str(ancestor),
                "skills_dir": str(skills_dir),
                "skills": sorted(p.name for p in skills_dir.iterdir() if p.is_dir()),
                "explore_contract": str(explore_contract),
                "explore_contract_exists": explore_contract.is_file(),
            })
            _record_bin(ancestor / "scripts" / "specpowers_cli" / "bin")
        # 形态二：pip 安装——包拷贝于 <skills_root>/specpowers/specpowers_cli 下，
        # 名为 specpowers 且含 SKILL.md 的祖先即主技能目录，其父即 skills 根
        if ancestor.name == "specpowers" and (ancestor / "SKILL.md").is_file():
            pip_skills_root = ancestor.parent
            pip_contract = ancestor / "prompts" / "explore.md"
            result["candidates"].append({
                "kind": "pip_skills_root",
                "path": str(pip_skills_root),
                "skills_dir": str(pip_skills_root),
                "skills": sorted(p.name for p in pip_skills_root.iterdir() if p.is_dir()),
                "explore_contract": str(pip_contract),
                "explore_contract_exists": pip_contract.is_file(),
            })
            _record_bin(ancestor / "bin")

    print(json.dumps(result, indent=2))
    return 0


def _scope_assessment(root: Path, base: str) -> dict | None:
    """评估任务级修改范围比对；不适用场景返回 None（输出 JSON 不带 scope 键）。

    适用前提：有前台活跃需求（fast/CI 场景不比对——fast 无 tasks.md 自然
    返回 None）且该 feature 的 tasks.md 存在。声明缺失 → status=undeclared
    （提示 propose 补声明，非硬阻断，兼容 v2.2 旧产物）。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.core.git_util import diff_name_only
    from specpowers_cli.bridge.modules.structure_gate import (
        evaluate_scope,
        parse_scope_declaration,
    )
    from specpowers_cli.bridge.modules.state_derivation import foreground_slug
    feature = foreground_slug(root) or ""
    if not feature:
        return None
    tasks_path = root / "openspec" / "changes" / feature / "tasks.md"
    if not tasks_path.exists():
        return None
    declared = parse_scope_declaration(tasks_path.read_text(encoding="utf-8"))
    if not declared:
        return {"declared": [], "out_of_scope": [], "status": "undeclared"}
    return evaluate_scope(diff_name_only(root, base), declared)


_LIST_OUTPUT_CAP = 20  # stdout 列表输出封顶（v3.1.0）：超限截断附计数，完整明细走落盘报告


def _capped_str_list(items: list, cap: int = _LIST_OUTPUT_CAP) -> tuple[list, int]:
    """字符串列表输出封顶：超限截取前 cap 条。

    返回 (截断后列表, 总条数)；未超限返回原列表与长度（消费方据 total 与
    长度是否一致判断截断）。输出会进 LLM 上下文，无界列表（越界文件/警告）
    在大项目上随规模线性膨胀，封顶后明细由落盘报告承载。

    作者：005819 | 协作：GLM
    """
    total = len(items)
    if total <= cap:
        return items, total
    return list(items[:cap]), total


def _cmd_gate(args: list[str], root: Path) -> int:
    """Handle internal gate command."""
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
    result = {"signals": signals, "base": base, "diff_lines": len(diff.splitlines()) if diff else 0}
    # 任务级修改范围比对（v2.3.0）：不适用时不带 scope 键，保持旧消费者兼容
    scope = _scope_assessment(root, base)
    if scope is not None:
        result["scope"] = scope
    # 判定留痕（借鉴 RTK 的 recall 句柄模式）：有结构信号或越界改动时把完整
    # 判定 JSON 落盘到 .specpowers/reports/，输出只附 report 句柄路径——
    # apply 契约与人工裁决按路径回查完整报告，不必把全部明细塞进拒绝消息
    if signals or (scope is not None and scope.get("status") == "out_of_scope"):
        from datetime import datetime
        reports_dir = root / ".specpowers" / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        report_path = reports_dir / f"gate-{datetime.now():%Y%m%d-%H%M%S}.json"
        # 落盘完整明细（人机按 report 句柄回查），stdout 只出封顶版
        report_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        result["report"] = report_path.relative_to(root).as_posix()
    # stdout 输出封顶（v3.1.0）：信号/越界列表超 20 条截断 + total 计数，
    # 截断标记由 total 与列表长度差表达，明细指向 report 句柄
    capped = dict(result)
    capped_signals, signals_total = _capped_str_list(result.get("signals", []))
    if signals_total > len(capped_signals):
        capped["signals"] = capped_signals
        capped["signals_total"] = signals_total
    scope = result.get("scope")
    if scope:
        capped_scope = dict(scope)
        for key in ("out_of_scope", "declared"):
            items, total = _capped_str_list(scope.get(key, []))
            if total > len(items):
                capped_scope[key] = items
                capped_scope[f"{key}_total"] = total
        capped["scope"] = capped_scope
    print(json.dumps(capped))
    return 0


def _cmd_resume_probe(args: list[str], root: Path) -> int:
    """Handle resume-probe command — SessionStart 只读探测活跃需求（零噪音）。

    探测绝不阻断会话启动：任何异常静默降级为空输出（exit 0）。
    空输出 = 无活跃状态，hook 侧零注入。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.modules.resume_probe import probe_resume
    try:
        print(probe_resume(root))
    except Exception:
        return 0
    return 0


def _cmd_sticky_note(args: list[str], root: Path) -> int:
    """Handle sticky-note command — 会话粘滞锚点行（UserPromptSubmit hook 消费，v2.7.0）。

    有活跃需求才输出单行锚点（feature/stage/Round + capability + 修改范围），
    零活跃零输出；任何异常静默降级为空输出（exit 0），绝不阻断用户消息。

    作者：005819 | 协作：GLM-5.3
    """
    from specpowers_cli.bridge.modules.resume_probe import sticky_note
    try:
        print(sticky_note(root))
    except Exception:
        return 0
    return 0


def _cmd_version(args: list[str], root: Path) -> int:
    """Handle version command."""
    print(f"SpecPowers bridge v{__version__}")
    return 0


def _cmd_record_execution_mode(args: list[str], root: Path) -> int:
    """记录 apply 阶段用户选择的执行方式到目标需求的状态（v2.8.0 起支持 --feature）。

    落地 apply.md 第二步的承诺：执行方式持久化（execution_mode 字段），
    并对 fast 模式做 worktree/subagent 禁用校验（确定性层纵深防御）。
    多活跃未指名时拒绝（防记错需求），单活跃缺省前台。

    Usage: record-execution-mode <conductor|worktree|subagent|tdd> [--feature <slug>]

    作者：005819 | 协作：GLM-5.2（v2.8.0 多需求化：GLM-5.3）
    """
    opts, positional = _extract_kv_options(args, ("feature",))
    if not positional:
        print(
            "Error: record-execution-mode requires an execution mode "
            "(conductor|worktree|subagent|tdd).",
            file=sys.stderr,
        )
        return 2
    mode = positional[0]
    from specpowers_cli.bridge.core.lock import acquire_lock, release_lock
    from specpowers_cli.bridge.modules.mode_controller import set_execution_mode
    from specpowers_cli.bridge.modules.state_derivation import (
        active_slugs, foreground_slug,
    )
    # 写 meta 需获取锁，防止并发 stage 操作交叉写入
    acquire_lock(root, timeout=0)
    try:
        feature = (opts.get("feature") or "").strip()
        if not feature:
            active = active_slugs(root)
            if not active:
                from specpowers_cli.bridge.core.errors import StateError
                print("Error: no active feature. Run a stage that sets feature first.", file=sys.stderr)
                return 2
            if len(active) > 1:
                from specpowers_cli.bridge.core.errors import StateError
                print(
                    f"Error: multiple active features, --feature required: "
                    f"{', '.join(active)}.",
                    file=sys.stderr,
                )
                return 2
            feature = foreground_slug(root) or ""
        normalized = set_execution_mode(root, feature, mode)
    finally:
        release_lock(root)
    print(f"执行方式已记录（feature '{feature}'）：{normalized}")
    return 0


def _configure_output_streams() -> None:
    """输出编码兜底：errors="replace" 保证任意字符都不会让流程崩溃。

    管道/agent 捕获场景下 stdout/stderr 按系统 locale（Windows 为 cp936）编码，
    输出 ⚠/✓ 等非 GBK 字符会抛 UnicodeEncodeError 且发生在状态已落盘之后，
    调用方会误判失败。bin 包装脚本已设 PYTHONUTF8=1（整体切 UTF-8），
    此处仅兜 errors，不改 encoding（避免交互 GBK 控制台中文乱码）。
    作者：005819 | 协作：GLM-5.3
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (ValueError, OSError):
                # 已关闭的流或底层缓冲不支持时静默跳过（不影响主流程）
                pass


def main(argv: list[str] | None = None) -> int:
    """Main entry point. Returns exit code."""
    _configure_output_streams()
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

    if subcommand in ("version", "--version", "-V"):
        return _cmd_version(rest, Path.cwd())

    # locate 自描述：不依赖项目状态，提前分发（root 解析前即可执行）
    if subcommand == "locate":
        return _cmd_locate(rest, Path.cwd())

    # Resolve project root
    try:
        root = _resolve_root(root_arg)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # v3.0 旧 state 迁移钩子（所有子命令统一入口，幂等）：首次命令探测
    # state.json → meta 齐全化 + runtime.json + 改名 .bak；无旧 state 零副作用
    try:
        from specpowers_cli.bridge.modules.state_derivation import migrate_legacy_state
        migrate_legacy_state(root)
    except Exception:
        # 迁移失败不阻断命令（report 可经 reconcile 查看）；推导式命令本身
        # 不依赖 state，失败仅影响旧字段保全
        pass

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
        "reconcile": _cmd_reconcile,
        "switch": _cmd_switch,
        "status": _cmd_status,
        "scan": _cmd_scan,
        "gate": _cmd_gate,
        "record-execution-mode": _cmd_record_execution_mode,
        "record-design-doc": _cmd_record_design_doc,
        "resume-probe": _cmd_resume_probe,
        "sticky-note": _cmd_sticky_note,
        "auto-status": _cmd_auto_status,
        "auto-new-round": _cmd_auto_new_round,
        "auto-clarify": _cmd_auto_clarify,
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
        # Verbose 模式口径与 dispatcher.is_verbose 一致（仅 "1" 生效）
        if os.environ.get("SPECPOWERS_VERBOSE", "").strip() == "1":
            import traceback
            traceback.print_exc(file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    sys.exit(main())
