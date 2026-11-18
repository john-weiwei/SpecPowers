"""Tests for facade — 全局选项解析、子命令分发与 v3.0 推导式命令。

回归覆盖：
- --root <path> 与 --root=<path> 两种形式都能被正确解析，不得被
  " ".join(args) 拼进 feature 名（原 bug：explore "需求" --root . 导致
  feature 变成「洗护到家黄牛充值限制---root」一类的脏数据）
- gate --base 参数注入拒绝与 scope 修改范围比对
- resume-probe / sticky-note 子命令（v3.0 现场从 state 换 openspec/changes/
  工件构造，helper 见 tests/helpers_v3.py）
- reconcile（v3.0 收缩为工件推导核对报告，不再修复 state）
- status（v3.0 全推导拼装，无 schema / reconcile_warnings 键）
- iterate 子命令已删除（unknown subcommand 回归）

作者：005819 | 协作：GLM-5.2（v3.0 推导化适配：GLM-5.3）
"""

import subprocess
from pathlib import Path

import pytest

from specpowers_cli.bridge.facade import _extract_global_options, main
from tests.helpers_v3 import make_change, make_triple, read_meta_of, write_runtime

# meta last_touched 时间戳（前台推导的确定性现场；最大者为前台）
_T_EARLY = "2026-11-17T00:00:01+00:00"
_T_LATE = "2026-11-17T00:00:02+00:00"


def _create_temp_git_repo(tmp_path: Path) -> Path:
    """在 pytest tmp_path 下创建带提交的临时 git 仓库（会话级模板复制，约 10ms）。"""
    from tests._gitrepo import create_git_repo

    return create_git_repo(tmp_path / "facade-repo")


def _write_corrupt_legacy_state(root: Path) -> None:
    """落盘一份损坏的遗留 state.json（v3.0 应被推导逻辑/迁移钩子安全处理）。"""
    (root / ".specpowers").mkdir(parents=True, exist_ok=True)
    (root / ".specpowers" / "state.json").write_text("{broken", encoding="utf-8")


def _seed_init_artifacts(root: Path) -> None:
    """补齐 init 产物（constitution.md + baseline.json），通过未初始化兜底检查。

    v3.0 无 state.json 可写——route 入口的 _check_initialized 仍要求这两份
    初始化产物存在（与 v2.5.0 起的语义一致）。
    """
    specpowers_dir = root / ".specpowers"
    specpowers_dir.mkdir(parents=True, exist_ok=True)
    (specpowers_dir / "constitution.md").write_text("# Constitution", encoding="utf-8")
    (specpowers_dir / "baseline.json").write_text("{}", encoding="utf-8")


# ---------- _extract_global_options 单元测试 ----------

def test_extract_root_space_form_removes_both_tokens():
    """--root <path> 形式：root 与 path 都从剩余参数移除。"""
    root_arg, remaining = _extract_global_options(["需求", "--root", "."])
    assert root_arg == "."
    assert remaining == ["需求"]


def test_extract_root_equals_form():
    """--root=<path> 形式：等号后作为值。"""
    root_arg, remaining = _extract_global_options(["需求", "--root=./repo"])
    assert root_arg == "./repo"
    assert remaining == ["需求"]


def test_extract_no_root_returns_none_and_unchanged():
    """没有 --root 时，root_arg 为 None 且剩余参数不变。"""
    root_arg, remaining = _extract_global_options(["需求", "更多", "描述"])
    assert root_arg is None
    assert remaining == ["需求", "更多", "描述"]


def test_extract_root_without_value_rejected(capsys):
    """--root 出现在末尾无值时：直接报错退出，不得把 "--root" 拼进 requirement。"""
    with pytest.raises(SystemExit) as exc_info:
        _extract_global_options(["需求", "--root"])
    assert exc_info.value.code == 2
    assert "--root requires a path value" in capsys.readouterr().err


def test_extract_root_value_cannot_be_next_option(capsys):
    """--root 后紧跟另一选项时视为缺值：报错退出而非吞参。"""
    with pytest.raises(SystemExit) as exc_info:
        _extract_global_options(["--root", "--force", "需求"])
    assert exc_info.value.code == 2
    assert "--root requires a path value" in capsys.readouterr().err


# ---------- 通过 main() 的回归测试 ----------

def test_explore_root_not_merged_into_feature(tmp_path: Path, capsys):
    """回归：explore 带正确参数时 --root 不得污染 feature 名（v3.0 续作拒绝路径）。

    v3.0 explore 对新需求因 registry 遗留 state.json 必需项而无法完成
    （生产缺陷，另行报告），回归改走「requirement normalize 后命中活跃
    清单 → explore 续作拒绝」路径：命中的前提是 feature 名等于纯需求
    normalize 结果，--root 污染即不命中、错误信息不会出现该精确句式。
    """
    root = _create_temp_git_repo(tmp_path)
    _seed_init_artifacts(root)
    make_change(root, "洗护到家黄牛充值限制", meta={"design_doc": "docs/specpowers/design/x.md"})

    rc = main(["explore", "洗护到家黄牛充值限制", "--root", str(root)])
    err = capsys.readouterr().err
    assert rc == 2  # 续作拒绝（explore 仅对新需求执行）
    # feature 应等于纯需求 normalize 结果并命中活跃清单，绝不含 root/--root 字符
    assert "feature '洗护到家黄牛充值限制' 已在活跃清单中" in err


def test_explore_root_equals_form_not_merged_into_feature(tmp_path: Path, capsys):
    """回归：--root=<path> 形式同样不得污染 feature 名（v3.0 续作拒绝路径）。"""
    root = _create_temp_git_repo(tmp_path)
    _seed_init_artifacts(root)
    make_change(root, "登录模块重构", meta={"design_doc": "docs/specpowers/design/x.md"})

    rc = main(["explore", "--root=" + str(root), "登录模块重构"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "feature '登录模块重构' 已在活跃清单中" in err


# ---- gate --base 参数注入拒绝（安全修复回归）----

def test_gate_rejects_option_like_base(tmp_path, capsys):
    """--base 值以 '-' 开头（git 选项注入，如 --output=）必须被拒绝。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["gate", "--root", str(root), "--base", "--output=/tmp/evil"])
    assert rc == 2
    assert "invalid --base value" in capsys.readouterr().err


def test_gate_rejects_metachar_base(tmp_path, capsys):
    """--base 值含空格等非法字符时被拒绝。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["gate", "--root", str(root), "--base", "HEAD; rm -rf /"])
    assert rc == 2


def test_gate_accepts_normal_ref_base(tmp_path):
    """--base 正常 git ref（如 HEAD~1）照常放行。"""
    root = _create_temp_git_repo(tmp_path)
    # HEAD~1 需要仓库至少 2 个提交，补一个
    (root / "CHANGE.md").write_text("# Change", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "second"],
        cwd=str(root), capture_output=True, check=True,
    )
    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0


# ---- gate scope 修改范围比对（v2.3.0；v3.0 前台改由工件推导）----

def _seed_tasks_with_scope(root: Path, feature: str, scope_decl: str | None) -> None:
    """构造活跃 change 目录与 tasks.md（scope_decl=None 表示不写声明行）。

    v3.0 前台推导：tasks.md 即活跃工件 → 该需求为唯一活跃、自动成为前台。
    """
    change_dir = root / "openspec" / "changes" / feature
    change_dir.mkdir(parents=True, exist_ok=True)
    comment = "<!--\n推荐：conductor\n修改范围：%s\n-->" % scope_decl if scope_decl else "<!--\n推荐：conductor\n-->"
    (change_dir / "tasks.md").write_text(comment, encoding="utf-8")


def test_gate_scope_out_of_scope(tmp_path, capsys):
    """声明 README.md 而实际改动含 placeholder → scope=out_of_scope 列出越界文件。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_tasks_with_scope(root, "demo", "README.md")
    (root / "placeholder_0.md").write_text("out of scope change", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"]["status"] == "out_of_scope"
    assert "placeholder_0.md" in out["scope"]["out_of_scope"]
    assert out["scope"]["declared"] == ["README.md"]


def test_gate_caps_long_lists_with_total(tmp_path, capsys):
    """v3.1.0 输出封顶：越界文件超 20 条时 stdout 截断附 total（完整明细落盘 report）。

    无界列表（∝ 越界文件数）在大项目上随规模线性膨胀进 LLM 上下文；
    stdout 封顶后明细由 report 句柄承载（转人工时人机按路径回查）。
    """
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_tasks_with_scope(root, "demo", "README.md")
    for i in range(25):
        (root / f"placeholder_{i}.md").write_text("out of scope change", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # stdout 截断：前 20 条 + total 计数；status 判定不受截断影响
    assert len(out["scope"]["out_of_scope"]) == 20
    assert out["scope"]["out_of_scope_total"] == 25
    assert out["scope"]["status"] == "out_of_scope"
    assert "report" in out
    # 落盘 report 为完整明细（人机按句柄回查）
    report = json.loads((root / out["report"]).read_text(encoding="utf-8"))
    assert len(report["scope"]["out_of_scope"]) == 25


def test_gate_scope_pass(tmp_path, capsys):
    """改动全部落在声明范围内 → scope=pass。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_tasks_with_scope(root, "demo", "placeholder_0.md, openspec/, .specpowers/")
    (root / "placeholder_0.md").write_text("in scope change", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"]["status"] == "pass"


def test_gate_scope_undeclared(tmp_path, capsys):
    """tasks.md 存在但缺修改范围声明 → scope=undeclared（旧产物兼容）。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_tasks_with_scope(root, "demo", None)
    (root / "placeholder_0.md").write_text("changed", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["scope"]["status"] == "undeclared"
    assert out["scope"]["out_of_scope"] == []


def test_gate_scope_omitted_without_tasks_md(tmp_path, capsys):
    """无 tasks.md（fast/CI 场景）→ 输出 JSON 不带 scope 键（旧消费者兼容）。"""
    import json

    root = _create_temp_git_repo(tmp_path)
    (root / "CHANGE.md").write_text("# x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "second"],
        cwd=str(root), capture_output=True, check=True,
    )

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "scope" not in out


def test_gate_report_written_on_signals_or_out_of_scope(tmp_path, capsys):
    """有结构信号或越界改动时落盘完整判定报告，输出附 report 句柄（RTK recall 式）。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_tasks_with_scope(root, "demo", "README.md")
    (root / "placeholder_0.md").write_text("out of scope change", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    # 报告句柄存在且指向真实文件
    assert "report" in out
    report_file = root / out["report"]
    assert report_file.exists()
    # 报告内容 = 完整判定 JSON（含 scope），相对路径固定在 .specpowers/reports/ 下
    assert out["report"].startswith(".specpowers/reports/gate-")
    report = json.loads(report_file.read_text(encoding="utf-8"))
    assert report["scope"]["status"] == "out_of_scope"
    assert report["signals"] == out["signals"]


def test_gate_report_omitted_when_clean(tmp_path, capsys):
    """无结构信号且 scope=pass 时不落盘报告（输出 JSON 不带 report 键）。"""
    import json

    from tests._gitrepo import commit_all

    root = _create_temp_git_repo(tmp_path)
    _seed_tasks_with_scope(root, "demo", "placeholder_0.md")
    (root / "placeholder_0.md").write_text("in scope change", encoding="utf-8")
    commit_all(root, "apply change")

    rc = main(["gate", "--root", str(root), "--base", "HEAD~1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert "report" not in out
    assert out["signals"] == []
    assert out["scope"]["status"] == "pass"


# ---- iterate 子命令已删除（v3.0 重入迭代由目录推导识别）----

def test_iterate_subcommand_removed(tmp_path, capsys):
    """v3.0 facade iterate 已删除 → unknown subcommand（exit 2）。"""
    rc = main(["iterate", "--root", str(tmp_path)])
    assert rc == 2
    assert "unknown subcommand 'iterate'" in capsys.readouterr().err


# ---- resume-probe 子命令（v2.3.0 引入；v3.0 全推导，现场换工件构造）----

def test_resume_probe_subcommand_silent_on_fresh(tmp_path, capsys):
    """resume-probe 在无活跃需求的项目 exit 0 且输出空（零噪音）。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["resume-probe", "--root", str(root)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_resume_probe_subcommand_reports_active_pipeline(tmp_path, capsys):
    """resume-probe 在活跃流水线输出续跑提示（hook 注入的内容源）。"""
    # 三件套齐且无勾选 → 推导 propose（断点续作指引）
    make_triple(tmp_path, "demo")
    rc = main(["resume-probe", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "demo" in out
    assert "当前阶段 propose" in out
    assert "/specpowers-propose" in out


def test_resume_probe_subcommand_ignores_corrupt_legacy_state(tmp_path, capsys):
    """遗留 state.json 损坏时 resume-probe 仍 exit 0 且推导照常（探测绝不阻断）。

    v3.0 探测零 state 读取；入口迁移钩子将损坏文件留底（可追溯），
    活跃需求从工件推导不受影响。
    """
    root = tmp_path
    _write_corrupt_legacy_state(root)
    make_triple(root, "demo")
    rc = main(["resume-probe", "--root", str(root)])
    assert rc == 0
    assert "demo" in capsys.readouterr().out


# ---------- sticky-note 会话粘滞锚点行子命令（v2.7.0） ----------

def test_sticky_note_subcommand_silent_on_fresh(tmp_path, capsys):
    """sticky-note 在无活跃需求的项目 exit 0 且输出空（零注入零 token）。"""
    root = _create_temp_git_repo(tmp_path)
    rc = main(["sticky-note", "--root", str(root)])
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_sticky_note_subcommand_reports_anchor_line(tmp_path, capsys):
    """sticky-note 在活跃流水线输出锚点行（hook 注入的内容源）。"""
    change = make_triple(
        tmp_path, "demo",
        tasks_text="<!-- 修改范围：src/order/** -->\n### T: x\n\n- [ ] a\n",
    )
    (change / "specs" / "order").mkdir(parents=True, exist_ok=True)
    rc = main(["sticky-note", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "demo" in out
    assert "propose" in out
    assert "（前台）" in out
    assert "capability=order" in out
    assert "修改范围=src/order/**" in out
    assert "/specpowers-archive" in out


def test_sticky_note_subcommand_ignores_corrupt_legacy_state(tmp_path, capsys):
    """遗留 state.json 损坏时 sticky-note 仍 exit 0 且锚点照常推导（绝不阻断用户消息）。"""
    root = tmp_path
    _write_corrupt_legacy_state(root)
    make_triple(root, "demo")
    rc = main(["sticky-note", "--root", str(root)])
    assert rc == 0
    assert "活跃需求 demo" in capsys.readouterr().out


# ---------- locate 自描述命令（v2.6.0） ----------

def test_locate_reports_source_tree_installation(capsys):
    """locate 在源码树/插件市场形态下报告 plugin_root 候选与契约存在性。

    pytest 的 sys.path 指向仓库源码树（conftest 注入），locate 应探测出
    plugins/specpowers 的 skills 目录与 explore 契约、bin 包装脚本。
    """
    import json
    rc = main(["locate"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cli_package"], "应报告 CLI 包绝对路径"
    plugin_roots = [c for c in payload["candidates"] if c["kind"] == "plugin_root"]
    assert plugin_roots, "源码树形态应探测出 plugin_root 候选"
    candidate = plugin_roots[0]
    assert candidate["explore_contract_exists"], "explore 契约应真实存在"
    assert "specpowers-explore" in candidate["skills"], "技能清单应含阶段技能"
    assert payload["bin_wrapper"] and payload["bin_wrapper"]["exists"], "应报告 bin 包装脚本"


def test_locate_requires_no_project_root(tmp_path, capsys):
    """locate 不依赖项目状态：空目录（非 git、未初始化）也能执行。"""
    import json
    rc = main(["locate", "--root", str(tmp_path)])
    assert rc == 0
    json.loads(capsys.readouterr().out)


# ---- reconcile 子命令（v3.0 收缩为工件推导核对报告，不再修复 state）----

def test_reconcile_derives_round_and_pointer_from_artifacts(tmp_path, capsys):
    """reconcile 从工件推导活跃清单/阶段/轮次（state.json 退役后的正常态）。

    v2.12 旧语义「从 meta+三件套重建 state 条目」随 state 退役收缩为
    「推导核对报告」：design-round-2.md 轮次痕迹推导 Round 2，design_doc
    指针由 change 目录 meta 保全。
    """
    import json

    root = tmp_path
    change = make_triple(root, "rebuild-me",
                         meta={"design_doc": "docs/specpowers/design/x.md"})
    (change / "design-round-2.md").write_text("x", encoding="utf-8")

    assert main(["reconcile", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    data, _ = json.JSONDecoder().raw_decode(out)  # 输出 = JSON 报告 + 摘要行
    assert data["active"] == ["rebuild-me"]
    assert data["foreground"] == "rebuild-me"
    assert data["stages"]["rebuild-me"] == "propose"
    assert data["rounds"]["rebuild-me"] == 2
    assert read_meta_of(root, "rebuild-me")["design_doc"] == "docs/specpowers/design/x.md"


def test_reconcile_explore_stage_for_meta_only_change(tmp_path, capsys):
    """仅 meta 的 change（explore 完成待 propose）→ 推导为 explore 态。"""
    import json

    root = tmp_path
    make_change(root, "explore-done",
                meta={"design_doc": "docs/specpowers/design/e.md"})

    assert main(["reconcile", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    data, _ = json.JSONDecoder().raw_decode(out)
    assert data["stages"]["explore-done"] == "explore"
    assert data["foreground"] == "explore-done"
    assert read_meta_of(root, "explore-done")["design_doc"] == "docs/specpowers/design/e.md"


def test_reconcile_audits_corrupted_meta(tmp_path, capsys):
    """meta 损坏（非法 JSON）→ 推导按缺失降级继续 + audit 警告行（异常可追溯）。"""
    import json

    root = tmp_path
    change = make_triple(root, "legacy-change")
    (change / ".specpowers-meta.json").write_text("{corrupted!!", encoding="utf-8")

    assert main(["reconcile", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    data, _ = json.JSONDecoder().raw_decode(out)
    assert data["stages"]["legacy-change"] == "propose", "meta 损坏不应阻断工件推导"
    assert data["audit"]["legacy-change"], "损坏 meta 应产出审计警告"
    assert any("meta 损坏" in w for w in data["warnings"])


def test_reconcile_self_heals_corrupted_legacy_state(tmp_path, capsys):
    """冒烟回归：遗留 state.json 损坏 → 迁移钩子留底自愈，推导从工件照常进行。"""
    import json

    root = tmp_path
    make_triple(root, "heal-me")
    _write_corrupt_legacy_state(root)

    assert main(["reconcile", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "heal-me" in out
    # 损坏文件改名留底（现场可追溯），活跃需求由工件推导重建
    assert list((root / ".specpowers").glob("state.json.corrupted-*"))
    assert not (root / ".specpowers" / "state.json").exists()
    data, _ = json.JSONDecoder().raw_decode(out)
    assert data["stages"]["heal-me"] == "propose"


# ---------- status 全推导拼装（v3.0） ----------

def test_status_fully_derived_without_schema_or_reconcile_keys(tmp_path, capsys):
    """status 全推导：runtime 全局字段 + 工件推导概览；无 schema/reconcile_warnings 键。"""
    import json

    root = tmp_path
    write_runtime(root, fallback_count=1, last_archive_ref="abc1234")
    make_triple(root, "window-feat",
                meta={"mode": "full", "execution_mode": "conductor",
                      "design_doc": "docs/specpowers/design/x.md",
                      "last_touched": _T_EARLY})
    make_change(root, "beta", meta={"design_doc": "docs/specpowers/design/b.md",
                                    "last_touched": _T_LATE})

    rc = main(["status", "--root", str(root)])
    data = json.loads(capsys.readouterr().out)
    assert rc == 0
    # runtime.json 承接的跨需求全局过程字段
    assert data["fallback_count"] == 1
    assert data["last_archive_ref"] == "abc1234"
    # 前台 = meta last_touched 最大者（beta 仅 meta 登记 → 推导 explore）
    assert data["foreground"] == "beta"
    assert data["feature"] == "beta"
    assert data["stage"] == "explore"
    assert data["mode"] == "full"
    assert data["execution_mode"] == ""
    assert data["iteration_count"] == 0
    assert data["design_doc"] == "docs/specpowers/design/b.md"
    # features 概览键：slug → stage/mode/iteration_count 全推导
    assert data["features"]["window-feat"] == {
        "stage": "propose", "mode": "full", "iteration_count": 0,
    }
    assert data["features"]["beta"]["stage"] == "explore"
    # schema 键随 state 退役删除；推导式下无对账警告出口
    assert "schema" not in data
    assert "reconcile_warnings" not in data
