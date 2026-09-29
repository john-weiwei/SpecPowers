"""Tests for structure_gate — 结构门禁信号提取（核心门禁逻辑）。

验证 extract_signals 的三类信号 + 去重 + 边界：
1. 新增顶层目录（new_top_dir）
2. 未知依赖文件（new_dep）
3. src/ 下新架构层（new_src_pattern）
4. set 去重（多文件同名信号只报一次）
5. 空 baseline / 空 diff 短路

v2.3.0 追加：任务级修改范围比对（parse_scope_declaration / evaluate_scope）。
"""

from specpowers_cli.bridge.modules.structure_gate import (
    SCOPE_EXEMPT_PREFIXES,
    evaluate_scope,
    extract_signals,
    parse_scope_declaration,
)


def _baseline(top_dirs=None, deps=None, src_patterns=None):
    """构造测试用 baseline dict。

    用 None 显式判断而非 `or`，避免传入空 dict {}（falsy）被误当默认值。
    """
    return {
        "top_dirs": ["src", "docs", "tests"] if top_dirs is None else top_dirs,
        "deps": {"npm": "package.json", "pip": "requirements.txt"} if deps is None else deps,
        "src_patterns": ["controller", "service"] if src_patterns is None else src_patterns,
    }


def test_empty_baseline_returns_empty():
    """空 baseline 直接返回空（无门禁基准）。"""
    assert extract_signals("some diff", {}) == []


def test_empty_diff_returns_empty():
    """空 diff 返回空信号。"""
    assert extract_signals("", _baseline()) == []


def test_none_diff_returns_empty():
    """None diff 返回空信号。"""
    assert extract_signals(None, _baseline()) == []


def test_no_violation_clean():
    """所有文件都在 baseline 内，无信号。"""
    diff = "src/controller/user.py | 10 +++\ndocs/readme.md | 2 +\n"
    # src/controller 在 src_patterns，docs 在 top_dirs
    assert extract_signals(diff, _baseline()) == []


def test_new_top_dir_detected():
    """检测到新的顶层目录。"""
    diff = "new_module/file.py | 5 +\n"
    signals = extract_signals(diff, _baseline(top_dirs=["src", "docs"]))
    assert any("new_top_dir:new_module" in s for s in signals)


def test_dot_dir_not_flagged():
    """以 . 开头的目录（如 .github）不报为 new_top_dir。"""
    diff = ".github/workflows/ci.yml | 10 +++\n"
    signals = extract_signals(diff, _baseline(top_dirs=["src"]))
    assert not any("new_top_dir:.github" in s for s in signals)


def test_new_dep_detected():
    """检测到未知的依赖文件。"""
    # baseline 已知 npm/pip，新增 go.mod
    diff = "go.mod | 5 +\n"
    signals = extract_signals(diff, _baseline(deps={"npm": "package.json"}))
    assert "new_dep:go" in signals


def test_known_dep_no_signal():
    """已知的依赖文件不报信号。"""
    diff = "package.json | 5 +\n"
    signals = extract_signals(diff, _baseline(deps={"npm": "package.json"}))
    assert not any("new_dep:" in s for s in signals)


def test_new_src_pattern_detected():
    """src/ 下出现新的架构层目录。"""
    diff = "src/repository/user.py | 10 +++\n"
    # baseline 只有 controller/service，repository 是新的
    signals = extract_signals(diff, _baseline(src_patterns=["controller", "service"]))
    assert "new_src_pattern:repository" in signals


def test_known_src_pattern_no_signal():
    """src/ 下已知的架构层不报信号。"""
    diff = "src/controller/user.py | 10 +++\n"
    signals = extract_signals(diff, _baseline(src_patterns=["controller"]))
    assert not any("new_src_pattern:" in s for s in signals)


def test_dedup_multiple_files_same_dir():
    """多个文件在同一新目录下，new_top_dir 只报一次（set 去重）。"""
    diff = (
        "newmod/a.py | 1 +\n"
        "newmod/b.py | 1 +\n"
        "newmod/c.py | 1 +\n"
    )
    signals = extract_signals(diff, _baseline(top_dirs=["src"]))
    # 去重后只有一条 new_top_dir:newmod
    assert signals.count("new_top_dir:newmod") == 1


def test_dedup_multiple_dep_files_same_type():
    """同名依赖文件在 diff 中多次出现，new_dep 只报一次（set 去重）。

    场景：git diff --stat 里同一 package.json 被列多次（罕见但去重逻辑需覆盖）。
    """
    diff = "package.json | 1 +\npackage.json | 2 +\n"
    baseline = _baseline(deps={})  # npm 不在已知依赖，会触发 new_dep
    signals = extract_signals(diff, baseline)
    # 同名文件去重后只一条 new_dep:npm
    assert signals.count("new_dep:npm") == 1


def test_multiple_signal_types():
    """一次 diff 可同时触发多种信号类型。"""
    diff = (
        "newdir/x.py | 1 +\n"        # new_top_dir
        "go.mod | 1 +\n"             # new_dep
        "src/repo/y.py | 1 +\n"      # new_src_pattern
    )
    signals = extract_signals(diff, _baseline(
        top_dirs=["src"], deps={"npm": "package.json"}, src_patterns=["controller"]
    ))
    assert any("new_top_dir:newdir" in s for s in signals)
    assert "new_dep:go" in signals
    assert "new_src_pattern:repo" in signals


def test_stat_format_parsing():
    """git diff --stat 格式正确解析（path | N +++---）。"""
    diff = "  src/newlayer/file.py | 15 +++++++++++++++\n"
    signals = extract_signals(diff, _baseline(
        top_dirs=["src"], src_patterns=["controller"]
    ))
    assert "new_src_pattern:newlayer" in signals


def test_summary_line_not_parsed_as_filepath():
    """回归：git diff --stat 末尾汇总行不应被误当文件路径解析。

    汇总行格式如 "3 files changed, 10 insertions(+)" 不含 "|" 分隔符，
    原实现用 split("|") 后取 parts[0]，汇总行被整行当作 filepath，
    产生虚假信号 new_top_dir:"3 files changed, 10 insertions(+)"。

    作者：005819 | 协作：GLM-5.2
    """
    # 模拟真实 git diff --stat 输出（文件行 + 汇总行）
    diff = (
        "src/controller/user.py | 10 +++\n"
        "2 files changed, 10 insertions(+)\n"
    )
    signals = extract_signals(diff, _baseline(
        top_dirs=["src"], src_patterns=["controller"]
    ))
    # 文件行在 baseline 内，无信号；汇总行不应产生任何 new_top_dir
    assert signals == []
    assert not any("changed" in s for s in signals), \
        f"汇总行被误解析为信号: {signals}"


def test_summary_line_with_violation_not_polluted():
    """回归：有真实违规信号时，汇总行不应额外产生虚假信号。

    确保 "files changed" 这样的汇总行文本不会作为 new_top_dir 出现，
    干扰对真实违规信号的判断。
    """
    diff = (
        "newdir/x.py | 1 +\n"                    # 真实 new_top_dir
        "1 file changed, 1 insertion(+)\n"       # 汇总行
    )
    signals = extract_signals(diff, _baseline(top_dirs=["src"]))
    # 只应有真实信号 new_top_dir:newdir，不应有汇总行产生的噪声
    assert signals == ["new_top_dir:newdir"], f"汇总行污染了信号: {signals}"


def test_rename_brace_form_reconstructs_full_path():
    """回归：git rename 折叠写法 src/{old => new}/f.py 必须还原完整新路径。

    原实现取 "=>" 之后丢掉花括号前的公共前缀，"src/{api => controller}/u.py"
    被解析成 "controller/u.py"：
    1. 顶层目录判定为 "controller"（不在 top_dirs）→ 误报 new_top_dir:controller
    2. parts[0] != "src" → src 层信号漏检
    """
    # 前缀 src 在 top_dirs 内、新段 controller 在 src_patterns 内 → 不应有任何信号
    diff = "src/{api => controller}/user.py | 12 ++++\n"
    signals = extract_signals(diff, _baseline(
        top_dirs=["src"], src_patterns=["controller"]
    ))
    assert signals == [], f"rename 折叠路径解析错误: {signals}"

    # 反向：新段是未知架构层 → 应报 new_src_pattern（验证 src 前缀被正确还原后
    # src 层检查生效），且不应产生 new_top_dir
    diff2 = "src/{api => repository}/user.py | 12 ++++\n"
    signals2 = extract_signals(diff2, _baseline(
        top_dirs=["src"], src_patterns=["controller"]
    ))
    assert signals2 == ["new_src_pattern:repository"], \
        f"rename 折叠路径 src 层判定失效: {signals2}"


def test_rename_plain_form_still_works():
    """无公共前后缀的整体 rename（old => new）保持原有解析行为。"""
    diff = "old_dir/file.py => new_dir/file.py | 5 +\n"
    signals = extract_signals(diff, _baseline(top_dirs=["src"]))
    # 新路径 new_dir/file.py：new_dir 不在 top_dirs → 报 new_top_dir:new_dir
    assert "new_top_dir:new_dir" in signals


# ---- 任务级修改范围比对（v2.3.0）----

def test_parse_scope_declaration_basic():
    """注释块内「修改范围:」声明行正确解析（英文冒号 + 尾斜杠归一化）。"""
    md = "<!--\n推荐：conductor\n修改范围：src/order/, tests/order\n-->"
    assert parse_scope_declaration(md) == ["src/order", "tests/order"]


def test_parse_scope_declaration_mixed_separators_and_quotes():
    """逗号/中文逗号/分号/顿号/空白混排 + 引号包裹均正确切分。"""
    md = '<!-- 修改范围:"src/a", src/b；c.txt、d.py e.py -->'
    assert parse_scope_declaration(md) == ["src/a", "src/b", "c.txt", "d.py", "e.py"]


def test_parse_scope_declaration_backslash_normalized():
    """Windows 反斜杠路径归一化为正斜杠（跨平台比对一致）。"""
    md = "<!-- 修改范围：src\\order\\dto -->"
    assert parse_scope_declaration(md) == ["src/order/dto"]


def test_parse_scope_declaration_ignores_body_mentions():
    """回归：正文（注释块外）出现「修改范围：」字样不得误匹配为声明。

    任务描述里常见"修改范围:xx 模块"表述，只在 HTML 注释块内解析。
    """
    md = (
        "<!-- 推荐：conductor -->\n"
        "### Task 1: x\n"
        "- 实现内容：修改范围：src/x（此行在正文，不是声明）\n"
    )
    assert parse_scope_declaration(md) == []


def test_parse_scope_declaration_missing_returns_empty():
    """无注释块 / 注释块内无声明行 → 空列表（对应 gate 输出 undeclared）。"""
    assert parse_scope_declaration("no comment at all") == []
    assert parse_scope_declaration("<!-- 推荐：conductor -->") == []


def test_evaluate_scope_pass():
    """全部改动落在声明范围内 → pass。"""
    r = evaluate_scope(
        ["src/order/a.java", "tests/order/t.py"], ["src/order", "tests/order"]
    )
    assert r["status"] == "pass"
    assert r["out_of_scope"] == []
    assert r["declared"] == ["src/order", "tests/order"]


def test_evaluate_scope_out_of_scope():
    """越界文件被检出并排序去重。"""
    r = evaluate_scope(
        ["src/payment/b.java", "src/order/a.java", "src/payment/a.java"],
        ["src/order"],
    )
    assert r["status"] == "out_of_scope"
    assert r["out_of_scope"] == ["src/payment/a.java", "src/payment/b.java"]


def test_evaluate_scope_prefix_boundary():
    """路径分量边界：声明 src/order 不得吞掉 src/orders_x（前缀误匹配）。"""
    r = evaluate_scope(["src/orders_x/b.java"], ["src/order"])
    assert r["out_of_scope"] == ["src/orders_x/b.java"]


def test_evaluate_scope_exempt_prefixes():
    """流水线工件（openspec/、.specpowers/、docs/specpowers/）永不判越界。"""
    files = [
        "openspec/changes/x/tasks.md",
        ".specpowers/state.json",
        "docs/specpowers/design/a.md",
    ]
    r = evaluate_scope(files, [])
    assert r["status"] == "pass"
    assert set(SCOPE_EXEMPT_PREFIXES) == {"openspec/", ".specpowers/", "docs/specpowers/"}


def test_evaluate_scope_exact_file_declaration():
    """声明为具体文件时精确匹配该文件，其余照常越界。"""
    r = evaluate_scope(["README.md", "src/x.py"], ["README.md"])
    assert r["out_of_scope"] == ["src/x.py"]


def test_evaluate_scope_directory_declaration_matches_children_only():
    """目录声明匹配子路径与目录自身，不匹配同名前缀的他路径。"""
    declared = ["src/a"]
    assert evaluate_scope(["src/a/b.py", "src/a"], declared)["status"] == "pass"
    assert evaluate_scope(["src/ab/c.py"], declared)["status"] == "out_of_scope"
