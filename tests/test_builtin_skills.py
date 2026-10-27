"""内置技能资源完整性测试 —— 11 个技能（主技能 + review + 9 个阶段技能）随插件分发的资源校验。

v2.1.0 起 review 审查改用内置 specpowers-review 技能（替代用户级 codex-review 预装），
本用例锁定内置技能的关键资源不被误删，并防止清单重新引入 codex-review 预装依赖。

v2.3.1 起契约分层按需加载（省 token），追加锁定：

  - 主技能 prompts/refs/ 四份 auto 低频细则与 review references/ 三份细则文件存在且非空
  - 主契约 auto.md / review-guidelines.md 中引用的细则文件名必须真实存在（防引用失效）

v2.4.0 起 9 条阶段命令转为阶段技能（命令目录删除，slash 名不变），追加锁定：

  - 11 个技能目录的 SKILL.md 存在且 frontmatter name 与目录名一致
  - 阶段技能完整性：正文引用对应 prompts/<stage>.md 契约不断链、
    无命令时代残留（$ARGUMENTS 占位符 / handoffs / allowed-tools）
  - 防回潮：commands/ 目录不存在、三端清单（zcode/claude/codebuddy）无顶层 "commands" 键
  - 探索引擎并入防断链：skills/ 目录集合恰为 11 个（无 -engine 残留目录）、
    prompts/explore.md 含探索引擎细则章节与三模板锚点、
    插件本体与两份用户文档无「内置 specpowers-explore 技能」残留表述
    （README 版本变更记录表中的历史条目除外）

作者：SpecPowers Team 2026-10-23（ZCode / GLM-5.3）
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "specpowers"
SKILLS_ROOT = PLUGIN_ROOT / "skills"

PLUGIN_MANIFESTS = [
    ".zcode-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".codebuddy-plugin/plugin.json",
]

# 全部 11 个技能 → frontmatter 期望的 name（v2.4.0 起 9 条命令转为阶段技能）
ALL_SKILLS = {
    "specpowers": "specpowers",
    "specpowers-review": "specpowers-review",
    "specpowers-init": "specpowers-init",
    "specpowers-explore": "specpowers-explore",
    "specpowers-propose": "specpowers-propose",
    "specpowers-apply": "specpowers-apply",
    "specpowers-archive": "specpowers-archive",
    "specpowers-fast": "specpowers-fast",
    "specpowers-auto": "specpowers-auto",
    "specpowers-baseline": "specpowers-baseline",
    "specpowers-reset": "specpowers-reset",
}

# 9 个阶段技能 → 对应 prompts/ 契约（baseline/reset 为确定性命令薄入口，无独立契约）
STAGE_SKILL_CONTRACTS = {
    "specpowers-init": "prompts/init.md",
    "specpowers-explore": "prompts/explore.md",
    "specpowers-propose": "prompts/propose.md",
    "specpowers-apply": "prompts/apply.md",
    "specpowers-archive": "prompts/archive.md",
    "specpowers-fast": "prompts/fast_mode.md",
    "specpowers-auto": "prompts/auto.md",
}

# 全部 9 个阶段技能（转换规则统一适用，含无独立契约的 baseline/reset）
STAGE_SKILLS = {
    "specpowers-init",
    "specpowers-explore",
    "specpowers-propose",
    "specpowers-apply",
    "specpowers-archive",
    "specpowers-fast",
    "specpowers-auto",
    "specpowers-baseline",
    "specpowers-reset",
}

# specpowers-review 的关键资源（审查规则 / 收集脚本 / 回归测试 / 使用说明）
REVIEW_RESOURCES = [
    "references/review-guidelines.md",
    "scripts/gather_review_context.py",
    "scripts/tests/test_gather_review_context.py",
    "readme.md",
]

# v2.3.1 契约分层按需加载：主技能 auto 细则 + review 细则（缺一则按需加载断链）
ON_DEMAND_CONTRACT_RESOURCES = {
    "skills/specpowers": [
        "prompts/refs/auto-iteration.md",
        "prompts/refs/auto-review.md",
        "prompts/refs/auto-adjudication.md",
        "prompts/refs/auto-explore-halt.md",
    ],
    "skills/specpowers-review": [
        "references/dataflow-tracking.md",
        "references/method-review.md",
        "references/codex-origin.md",
    ],
}

# 探索引擎细则并入 explore 契约的防断链锚点（细则章节 + 三模板 + HARD-GATE 措辞）
EXPLORE_ENGINE_ANCHORS = [
    "探索引擎细则",
    "必须完整执行",
    "方案对比表模板",
    "设计文档模板",
    "探索结论输出模板",
]

# 引擎技能身份的残留表述（防回潮；README 版本变更记录历史条目除外）
BUILTIN_EXPLORE_SKILL_PHRASES = [
    "内置 specpowers-explore 技能",
    "built-in specpowers-explore skill",
]


def _frontmatter_field(skill_md_text, field):
    """从 SKILL.md 的 YAML frontmatter 中提取顶层字段值。"""
    match = re.search(rf"^{field}:\s*(.+)$", skill_md_text, re.MULTILINE)
    assert match, f"SKILL.md frontmatter 缺少 {field} 字段"
    return match.group(1).strip()


def test_builtin_skill_frontmatters():
    """11 个技能的 SKILL.md 必须存在且 frontmatter name 与目录名一致。"""
    for rel_dir, expected_name in ALL_SKILLS.items():
        skill_md = SKILLS_ROOT / rel_dir / "SKILL.md"
        assert skill_md.is_file(), f"技能缺失：skills/{rel_dir}/SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---"), f"skills/{rel_dir}/SKILL.md 缺少 frontmatter"
        name = _frontmatter_field(content, "name")
        assert name == expected_name, (
            f"skills/{rel_dir}/SKILL.md frontmatter name 应为 {expected_name}，实际 {name}"
        )


def test_stage_skills_reference_contract():
    """阶段技能正文必须引用对应 prompts/<stage>.md 契约（薄入口不断链）。"""
    main_skill_prompts = SKILLS_ROOT / "specpowers" / "prompts"
    for rel_dir, contract in STAGE_SKILL_CONTRACTS.items():
        content = (SKILLS_ROOT / rel_dir / "SKILL.md").read_text(encoding="utf-8")
        assert contract in content, (
            f"skills/{rel_dir}/SKILL.md 未引用 {contract}（阶段技能与契约断链）"
        )
        assert (main_skill_prompts / Path(contract).name).is_file(), (
            f"阶段技能引用的契约不存在：skills/specpowers/{contract}"
        )


def test_stage_skills_no_command_artifacts():
    """阶段技能不得残留命令时代的 frontmatter/占位符约定（9 份统一适用）。"""
    for rel_dir in STAGE_SKILLS:
        content = (SKILLS_ROOT / rel_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "$ARGUMENTS" not in content, (
            f"skills/{rel_dir}/SKILL.md 残留命令占位符 $ARGUMENTS——技能输入经 args 参数传入"
        )
        assert not re.search(r"^handoffs:", content, re.MULTILINE), (
            f"skills/{rel_dir}/SKILL.md 残留 handoffs frontmatter（技能无此约定）"
        )
        assert not re.search(r"^allowed-tools:", content, re.MULTILINE), (
            f"skills/{rel_dir}/SKILL.md 声明了 allowed-tools——阶段技能是编排单元应继承全部工具"
        )


def test_stage_skills_description_verb_first():
    """阶段技能 description 必须动词开头（9 份统一适用，生命周期语义立即可见）。"""
    verb_first_prefixes = (
        "生成", "探索", "执行", "归档", "刷新", "重置", "驱动", "判定",
    )
    for rel_dir in STAGE_SKILLS:
        content = (SKILLS_ROOT / rel_dir / "SKILL.md").read_text(encoding="utf-8")
        description = _frontmatter_field(content, "description")
        assert description.startswith(verb_first_prefixes), (
            f"skills/{rel_dir}/SKILL.md description 应动词开头，实际：{description[:20]}…"
        )


def test_commands_dir_removed():
    """防回潮：commands/ 目录必须已删除（9 条命令全部转为阶段技能）。"""
    commands_dir = PLUGIN_ROOT / "commands"
    assert not commands_dir.exists(), (
        "plugins/specpowers/commands/ 仍存在——阶段入口已是技能，命令目录不得回潮"
    )


def test_manifests_have_no_commands_key():
    """防回潮：三端清单（zcode/claude/codebuddy）不得再注册顶层 "commands" 键。"""
    for rel in (".zcode-plugin/plugin.json", ".claude-plugin/plugin.json",
                ".codebuddy-plugin/plugin.json"):
        manifest = json.loads((PLUGIN_ROOT / rel).read_text(encoding="utf-8"))
        assert "commands" not in manifest, (
            f"{rel} 仍注册顶层 commands 键——命令目录已删除，注册会指向不存在的目录"
        )


def test_skills_dir_exact_set():
    """探索引擎并入防断链：skills/ 目录集合恰为 11 个（无 -engine 残留、无多余目录）。"""
    actual = {p.name for p in SKILLS_ROOT.iterdir() if p.is_dir()}
    expected = set(ALL_SKILLS)
    assert actual == expected, (
        f"skills/ 目录集合漂移：多余 {sorted(actual - expected)}，缺失 {sorted(expected - actual)}"
    )
    assert not any(name.endswith("-engine") for name in actual), (
        "skills/ 下存在 -engine 结尾目录——内部引擎不以技能身份暴露（v2.4.0 方案 C）"
    )


def test_explore_contract_contains_engine_details():
    """探索引擎细则必须完整内联于 prompts/explore.md（防细则被误删断链）。"""
    content = (SKILLS_ROOT / "specpowers" / "prompts" / "explore.md").read_text(
        encoding="utf-8"
    )
    for anchor in EXPLORE_ENGINE_ANCHORS:
        assert anchor in content, (
            f"prompts/explore.md 缺少探索引擎细则锚点「{anchor}」——引擎细则被误删即断链"
        )


def test_no_builtin_explore_skill_references():
    """插件本体与两份用户文档不得残留「内置 specpowers-explore 技能」表述（引擎已并入契约）。

    README 版本变更记录表的行（`| v` 开头）除外——历史版本的变更描述允许引用该表述。
    """
    scan_targets = [PLUGIN_ROOT / "skills", PLUGIN_ROOT / "scripts", PLUGIN_ROOT / "hooks"]
    doc_targets = [REPO_ROOT / "README.md", REPO_ROOT / "docs" / "GETTING-STARTED.md"]
    for target in scan_targets + doc_targets:
        files = target.rglob("*.md") if target.is_dir() else (
            [target] if target.is_file() else []
        )
        for file in files:
            for line_no, line in enumerate(
                file.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if line.lstrip().startswith("| v"):
                    continue
                for phrase in BUILTIN_EXPLORE_SKILL_PHRASES:
                    assert phrase not in line, (
                        f"{file.relative_to(REPO_ROOT)}:{line_no} 残留引擎技能表述「{phrase}」"
                        "——探索引擎已内联于 prompts/explore.md，不以技能身份存在"
                    )


def test_specpowers_review_resources_exist():
    """specpowers-review 的审查规则、收集脚本与回归测试必须齐全。"""
    for rel in REVIEW_RESOURCES:
        path = SKILLS_ROOT / "specpowers-review" / rel
        assert path.is_file(), f"specpowers-review 资源缺失：{rel}"
        assert path.stat().st_size > 0, f"specpowers-review 资源为空文件：{rel}"


def test_specpowers_review_refs_resolve():
    """SKILL.md 中引用的相对资源目录（scripts/、references/）必须真实存在。"""
    review_dir = SKILLS_ROOT / "specpowers-review"
    content = (review_dir / "SKILL.md").read_text(encoding="utf-8")
    for ref_dir in ("scripts", "references"):
        assert ref_dir in content, f"SKILL.md 未引用 {ref_dir}/ 资源"
        assert (review_dir / ref_dir).is_dir(), f"SKILL.md 引用的 {ref_dir}/ 目录不存在"


def test_manifests_do_not_require_codex_review():
    """内置化后 4 份清单不得再把 codex-review 列为预装插件依赖。"""
    for rel in PLUGIN_MANIFESTS:
        manifest = json.loads((PLUGIN_ROOT / rel).read_text(encoding="utf-8"))
        plugins = manifest.get("requirements", {}).get("plugins", [])
        names = [entry.get("name") for entry in plugins]
        assert "codex-review" not in names, (
            f"{rel} 仍将 codex-review 列为预装依赖——review 已内置为 specpowers-review，应移除该条目"
        )


def test_on_demand_contract_resources_exist():
    """契约分层按需加载：主技能 refs/ 与 review references/ 细则文件必须存在且非空（防误删断链）。"""
    for skill_dir, rels in ON_DEMAND_CONTRACT_RESOURCES.items():
        for rel in rels:
            path = PLUGIN_ROOT / skill_dir / rel
            assert path.is_file(), f"按需加载细则缺失：{skill_dir}/{rel}"
            assert path.stat().st_size > 0, f"按需加载细则为空文件：{skill_dir}/{rel}"


def test_on_demand_refs_are_linked_from_contracts():
    """主契约中引用的细则文件名必须真实存在——拆分重构后防引用失效（agent 读不到细则即断链）。"""
    # auto.md 主契约引用的 refs/auto-*.md 必须都能在 prompts/refs/ 下找到
    auto_md = (PLUGIN_ROOT / "skills/specpowers/prompts/auto.md").read_text(encoding="utf-8")
    refs_dir = PLUGIN_ROOT / "skills/specpowers/prompts/refs"
    referenced = set(re.findall(r"refs/(auto-[\w-]+\.md)", auto_md))
    assert referenced, "auto.md 未引用任何 refs/ 细则（按需加载索引缺失）"
    for name in referenced:
        assert (refs_dir / name).is_file(), f"auto.md 引用的 refs/{name} 不存在"

    # review-guidelines.md 主指南引用的 references/*.md 细则必须真实存在
    guidelines = (
        PLUGIN_ROOT / "skills/specpowers-review/references/review-guidelines.md"
    ).read_text(encoding="utf-8")
    review_refs_dir = PLUGIN_ROOT / "skills/specpowers-review/references"
    referenced_review = set(
        name for name in re.findall(r"references/([\w-]+\.md)", guidelines)
        if name != "review-guidelines.md"
    )
    assert referenced_review, "review-guidelines.md 未引用任何细则（按需加载指引缺失）"
    for name in referenced_review:
        assert (review_refs_dir / name).is_file(), f"review-guidelines.md 引用的 references/{name} 不存在"
