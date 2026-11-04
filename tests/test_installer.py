"""pip 安装器（specpowers init --integration）产物完整性测试。

v2.5.1 修复 pip 形态 9 个阶段技能从未被安装的断链：安装器第 2 段仍指向
v2.4.0 已删除的 commands/ 目录（commands_dir.exists() 恒为 False，静默跳过），
pip 安装的项目里只有主技能、没有任何阶段入口。本用例锁定安装产物与插件
市场形态的 11 技能集合一致、阶段技能定位链闭合，并锁 bin 包装脚本
ASCII-only——cmd 按当前代码页解码 bat，非 ASCII 注释在 cp936（中文
Windows 默认）下导致整个脚本解析失败，WorkBuddy 上 CLI fallback 直接崩。

作者：SpecPowers Team 2026-11-02（ZCode / GLM-5.3）
"""

from pathlib import Path

from specpowers_cli.main import main as installer_main

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_ROOT = REPO_ROOT / "plugins" / "specpowers"

# 安装产物必须覆盖的全部 11 个技能（与插件市场形态 skills/ 集合一致）
EXPECTED_INSTALLED_SKILLS = {
    "specpowers",
    "specpowers-review",
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


def _run_workbuddy_install(tmp_path):
    """在临时目录执行 workbuddy 形态安装，返回安装后的 skills 根目录路径。"""
    project = tmp_path / "wbproj"
    rc = installer_main(["init", str(project), "--integration", "workbuddy"])
    assert rc == 0, "workbuddy 形态安装应成功返回 0"
    return project / ".workbuddy" / "skills"


def test_installer_copies_all_eleven_skills(tmp_path):
    """pip 安装必须落齐 11 个技能目录（v2.5.1 前阶段技能从未被安装）。"""
    skills_root = _run_workbuddy_install(tmp_path)
    installed = {p.name for p in skills_root.iterdir() if p.is_dir()}
    assert installed == EXPECTED_INSTALLED_SKILLS, (
        f"pip 安装技能集合漂移：多余 {sorted(installed - EXPECTED_INSTALLED_SKILLS)}，"
        f"缺失 {sorted(EXPECTED_INSTALLED_SKILLS - installed)}——"
        "v2.5.1 前安装器指向已删除的 commands/，阶段技能静默漏装"
    )


def test_installer_stage_contract_resolvable(tmp_path):
    """安装后阶段技能正文指向的契约文件必须真实存在（跨端定位链闭合）。"""
    skills_root = _run_workbuddy_install(tmp_path)
    explore_md = skills_root / "specpowers-explore" / "SKILL.md"
    assert explore_md.is_file(), "安装产物缺 specpowers-explore/SKILL.md"
    content = explore_md.read_text(encoding="utf-8")
    # 阶段技能正文按「兄弟目录 specpowers/」定位主技能契约——该路径必须真实可达
    assert "sibling of this stage skill" in content, "阶段技能主技能目录定位句缺失"
    assert (skills_root / "specpowers" / "prompts" / "explore.md").is_file(), (
        "安装产物缺 specpowers/prompts/explore.md——阶段技能定位链断裂"
    )


def test_bin_wrapper_ascii_only():
    """Windows bin 包装脚本必须 ASCII-only（cp936 代码页下 cmd 解码非 ASCII 即崩）。"""
    bat = PLUGIN_ROOT / "scripts" / "specpowers_cli" / "bin" / "specpowers.bat"
    content = bat.read_text(encoding="utf-8")
    assert content.isascii(), (
        "specpowers.bat 含非 ASCII 字符——cmd 按当前代码页解码 bat 文件，"
        "中文注释在 cp936 下导致命令拆分错乱、整个脚本无法执行"
    )


# ---------- v2.6.0 任意工具通用接入 ----------

def test_installer_custom_skills_root(tmp_path):
    """--skills-root 任意工具一步接入：自定义目录落齐 11 技能 + AGENTS.md 引导段。"""
    project = tmp_path / "customproj"
    rc = installer_main(["init", str(project), "--skills-root", ".foocode/skills"])
    assert rc == 0, "--skills-root 安装应成功"
    skills_root = project / ".foocode" / "skills"
    installed = {p.name for p in skills_root.iterdir() if p.is_dir()}
    assert installed == EXPECTED_INSTALLED_SKILLS, (
        f"自定义 skills_root 技能集合漂移：{sorted(installed ^ EXPECTED_INSTALLED_SKILLS)}"
    )
    # AGENTS.md 引导段应写入并引用自定义路径
    agents_md = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- specpowers:begin -->" in agents_md, "引导段标记缺失"
    assert ".foocode/skills/specpowers-explore/SKILL.md" in agents_md, (
        "引导段应引用自定义 skills_root 下的技能路径"
    )


def test_installer_agents_md_idempotent(tmp_path):
    """AGENTS.md 幂等：重装整段替换，标记段外用户内容保留。"""
    project = tmp_path / "agentsproj"
    installer_main(["init", str(project), "--skills-root", ".foocode/skills"])
    agents_md = project / "AGENTS.md"
    # 模拟用户在标记段外追加自己的内容
    content = agents_md.read_text(encoding="utf-8")
    agents_md.write_text("# 用户自定义标题\n\n" + content + "\n用户尾部内容\n", encoding="utf-8")
    # 重装（--force）：标记段整体替换为同一份新段，不重复不丢用户内容
    installer_main(["init", str(project), "--skills-root", ".foocode/skills", "--force"])
    refreshed = agents_md.read_text(encoding="utf-8")
    assert refreshed.count("<!-- specpowers:begin -->") == 1, "重装后标记段应恰有一份"
    assert "# 用户自定义标题" in refreshed and "用户尾部内容" in refreshed, (
        "标记段外用户内容必须保留"
    )


def test_installer_rejects_integration_with_skills_root(tmp_path):
    """--integration 与 --skills-root 互斥：同时给出报错返回 1。"""
    project = tmp_path / "conflictproj"
    rc = installer_main([
        "init", str(project), "--integration", "claude", "--skills-root", ".x/skills",
    ])
    assert rc == 1, "互斥参数同时给出应返回 1"
    assert not (project / ".claude").exists(), "互斥报错时不应产生安装动作"
