"""内置技能资源完整性测试 —— specpowers-explore / specpowers-review 随插件分发的资源校验。

v2.1.0 起 review 审查改用内置 specpowers-review 技能（替代用户级 codex-review 预装），
本用例锁定内置技能的关键资源不被误删，并防止清单重新引入 codex-review 预装依赖：

  - 两个内置技能目录（skills/specpowers-explore、skills/specpowers-review）的 SKILL.md
    存在且 frontmatter name 正确
  - specpowers-review 的审查规则唯一来源、上下文收集脚本及其回归测试齐全
  - SKILL.md 中引用的相对资源目录（scripts/、references/）真实存在
  - 4 份宿主 plugin.json 的 requirements.plugins 不含 codex-review（内置化后无需预装）

作者：SpecPowers Team 2026-09-21（ZCode / GLM-5.3）
"""

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "specpowers"

PLUGIN_MANIFESTS = [
    ".zcode-plugin/plugin.json",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
    ".codebuddy-plugin/plugin.json",
]

# 内置技能 → frontmatter 期望的 name
BUILTIN_SKILLS = {
    "skills/specpowers-explore": "specpowers-explore",
    "skills/specpowers-review": "specpowers-review",
}

# specpowers-review 的关键资源（审查规则 / 收集脚本 / 回归测试 / 使用说明）
REVIEW_RESOURCES = [
    "references/review-guidelines.md",
    "scripts/gather_review_context.py",
    "scripts/tests/test_gather_review_context.py",
    "readme.md",
]


def _frontmatter_field(skill_md_text, field):
    """从 SKILL.md 的 YAML frontmatter 中提取顶层字段值。"""
    match = re.search(rf"^{field}:\s*(.+)$", skill_md_text, re.MULTILINE)
    assert match, f"SKILL.md frontmatter 缺少 {field} 字段"
    return match.group(1).strip()


def test_builtin_skill_frontmatters():
    """两个内置技能的 SKILL.md 必须存在且 frontmatter name 与目录名一致。"""
    for rel_dir, expected_name in BUILTIN_SKILLS.items():
        skill_md = PLUGIN_ROOT / rel_dir / "SKILL.md"
        assert skill_md.is_file(), f"内置技能缺失：{rel_dir}/SKILL.md"
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---"), f"{rel_dir}/SKILL.md 缺少 frontmatter"
        name = _frontmatter_field(content, "name")
        assert name == expected_name, f"{rel_dir}/SKILL.md frontmatter name 应为 {expected_name}，实际 {name}"


def test_specpowers_review_resources_exist():
    """specpowers-review 的审查规则、收集脚本与回归测试必须齐全。"""
    for rel in REVIEW_RESOURCES:
        path = PLUGIN_ROOT / "skills" / "specpowers-review" / rel
        assert path.is_file(), f"specpowers-review 资源缺失：{rel}"
        assert path.stat().st_size > 0, f"specpowers-review 资源为空文件：{rel}"


def test_specpowers_review_refs_resolve():
    """SKILL.md 中引用的相对资源目录（scripts/、references/）必须真实存在。"""
    review_dir = PLUGIN_ROOT / "skills" / "specpowers-review"
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
