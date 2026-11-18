"""内置技能资源完整性测试 —— 10 个技能（主技能 + review + 8 个阶段技能）随插件分发的资源校验。

v2.1.0 起 review 审查改用内置 specpowers-review 技能（替代用户级 codex-review 预装），
本用例锁定内置技能的关键资源不被误删，并防止清单重新引入 codex-review 预装依赖。

v2.3.1 起契约分层按需加载（省 token），追加锁定：

  - 主技能 prompts/refs/ 四份 auto 低频细则与 review references/ 三份细则文件存在且非空
  - 主契约 auto.md / review-guidelines.md 中引用的细则文件名必须真实存在（防引用失效）

v2.4.0 起 9 条阶段命令转为阶段技能（命令目录删除，slash 名不变），追加锁定：

  - 10 个技能目录的 SKILL.md 存在且 frontmatter name 与目录名一致
  - 阶段技能完整性：正文引用对应 prompts/<stage>.md 契约不断链、
    无命令时代残留（$ARGUMENTS 占位符 / handoffs / allowed-tools）
  - 防回潮：commands/ 目录不存在、三端清单（zcode/claude/codebuddy）无顶层 "commands" 键
  - 探索引擎并入防断链：skills/ 目录集合恰为 10 个（无 -engine 残留目录）、
    prompts/explore.md 含探索引擎细则章节与三模板锚点、
    插件本体与两份用户文档无「内置 specpowers-explore 技能」残留表述
    （README 版本变更记录表中的历史条目除外）

v2.5.0 起初始化前置（用户不 init 直接开工不再静默劣化），追加锁定：

  - 5 个流水线薄入口（explore/propose/apply/archive/fast）含第 0 步
    「Init check first」：constitution/baseline 任一缺失 = 未初始化，
    自动补跑 specpowers-init 后继续原技能（auto 编排内置 init 不需要，
    maintain/init 为维护或初始化动作不适用）

v2.5.1 起跨端契约遵从（WorkBuddy 读不到契约文件导致 explore 不守约），追加锁定：

  - 9 个阶段技能正文必须写明主技能目录真实位置（兄弟目录定位句 +
    双安装形态路径含 WorkBuddy .workbuddy/skills 示例），防裸相对路径回潮
  - 7 个契约引用技能必须含契约文件 Glob 兜底搜索句（变量不可用时的最后定位手段）
  - specpowers-explore 必须前置「硬性产出契约」节：契约文件不可读时
    静默探索/方案对比展示/设计文档落盘登记四条底线仍成立

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

# 全部 10 个技能 → frontmatter 期望的 name（v2.9.0 起 baseline/reset 合并为 maintain）
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
    "specpowers-maintain": "specpowers-maintain",
}

# 8 个阶段技能 → 对应 prompts/ 契约（maintain 为确定性命令薄入口，无独立契约）
STAGE_SKILL_CONTRACTS = {
    "specpowers-init": "prompts/init.md",
    "specpowers-explore": "prompts/explore.md",
    "specpowers-propose": "prompts/propose.md",
    "specpowers-apply": "prompts/apply.md",
    "specpowers-archive": "prompts/archive.md",
    "specpowers-fast": "prompts/fast_mode.md",
    "specpowers-auto": "prompts/auto.md",
}

# 全部 8 个阶段技能（转换规则统一适用，含无独立契约的 maintain）
STAGE_SKILLS = {
    "specpowers-init",
    "specpowers-explore",
    "specpowers-propose",
    "specpowers-apply",
    "specpowers-archive",
    "specpowers-fast",
    "specpowers-auto",
    "specpowers-maintain",
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

# v2.10.0 设计文档瘦身：模板必须含的 5 章锚点 + 精简纪律锚点
DESIGN_DOC_SLIM_ANCHORS = [
    "## 决策摘要",
    "## 方案对比",
    "## 相关既有模式",
    "## 修改范围",
    "精简纪律",
    "唯一事实源",
    "禁止复述",
]

# v2.10.0 设计文档瘦身防回潮：旧复述章节标题不得再出现在设计文档模板中
# （「项目上下文」「需求分析」「组件划分」是 baseline/constitution 复述或重叠章节，
#  删除后由「相关既有模式」≤6 行与「架构（含组件职责）」承接）
DESIGN_DOC_SLIM_REGRESSION_MARKERS = [
    "## 项目上下文",
    "## 需求分析",
    "### 组件划分",
]

# v2.5.0 初始化前置：5 个流水线薄入口必须含第 0 步检测
# （auto 编排内置 init 步骤不需要；maintain/init 为维护或初始化动作不适用）
INIT_CHECK_SKILLS = {
    "specpowers-explore",
    "specpowers-propose",
    "specpowers-apply",
    "specpowers-archive",
    "specpowers-fast",
}

# v2.5.1 跨端契约定位：阶段技能必须写明主技能目录真实位置
# （兄弟目录定位句 + pip 形态 WorkBuddy 示例路径——跨端断链修复的直接证据）
STAGE_SKILL_LOCATION_ANCHORS = [
    "sibling of this stage skill",
    ".workbuddy/skills/specpowers",
]

# v2.6.0 变量模式锚点：仅 7 个契约引用技能适用（完整版定位句）——
# `*_PLUGIN_ROOT` 模式化表述让新工具零改动覆盖，防止回潮成封闭端枚举清单
CONTRACT_VARIABLE_PATTERN_ANCHOR = "*_PLUGIN_ROOT"

# 契约引用技能必须含 Glob 兜底搜索句（PLUGIN_ROOT 变量不可用时的最后定位手段）
CONTRACT_GLOB_ANCHOR = "**/specpowers/prompts/"

# v2.7.0 迭代轮简易设计文档：基线冻结 + design-round-<N>.md 增量文档
# （防回潮为「覆盖重写基线 + 重新登记」的旧语义——token 消耗大头）
ITERATION_DESIGN_ROUND_ANCHORS = {
    "specpowers/prompts/explore.md": [
        "design-round-<N>",
        "基线设计文档冻结不动",
    ],
    "specpowers/prompts/propose.md": [
        "design-round-<N>.md",
        "禁止整份重读",
    ],
    "specpowers/prompts/refs/auto-iteration.md": [
        "design-round-<N>",
    ],
    "specpowers-explore/SKILL.md": [
        "design-round-<N>.md",
    ],
}

# 迭代轮旧覆盖语义的防回潮标记（只扫设计文档相关契约；proposal 三件套的
# 「覆盖更新」是有意保留的规则，不在扫描范围）
ITERATION_OVERWRITE_REGRESSION_MARKERS = ["设计文档覆盖", "更新后须重新"]

# v2.11.0 迭代轮 token 收敛：proposal 迭代历史表格化封顶滚动（消 O(N) 增长）+
# spec/tasks 骨架两级读取 + Edit 化修订（降常数）+ apply 侧按模式分流边界声明
# （v3.1.0 精化：apply 侧原「不局部化」改为按「谁执行」分流，见 TOKEN_SLIM_V31_ANCHORS）
ITERATION_TOKEN_SLIM_ANCHORS = {
    "specpowers/prompts/propose.md": [
        "| 轮次 | 日期 | 输入 | 变化点 |",
        "封顶滚动",
        "旧格式自动收敛",
        "骨架两级读取",
        "^### Requirement:|^#### Scenario:",
        "^### Task|^## Round|^## 已作废",
        "修订用 Edit 而非整份重写",
        "回退全文读取",
    ],
    "specpowers/prompts/apply.md": [
        "按「谁执行」分流",
    ],
    "specpowers/prompts/refs/auto-iteration.md": [
        "propose.md 迭代轮小节为准",
    ],
}

# v3.1.0 读写 token 降耗：apply 分流读取 + task_brief 脚本直出 + 场景引用瘦身 +
# proposal 迭代轮骨架 Edit 化 + explore 一次成型/收口 Edit + baseline 退出必读 +
# archive grep 证据 + 确定性层输出封顶 + auto 汇总封顶
TOKEN_SLIM_V31_ANCHORS = {
    "specpowers/prompts/apply.md": [
        "scripts/task_brief.py",
        "禁止手工转写",
        "骨架读取",
        "baseline.json 不再读取",
        "编码规范对每个 task 都必带",
        "conductor/TDD/worktree 主会话亲自执行",
    ],
    "specpowers/prompts/propose.md": [
        "场景引用：<关联 delta spec 的 Scenario 名列表，顿号分隔",
        "^## |^### 字段：",
        "禁止抄录 WHEN-THEN 原文",
    ],
    "specpowers/prompts/explore.md": [
        "一次成型",
        "Edit 增量补正",
        "baseline.json 不再读取",
    ],
    "specpowers/prompts/archive.md": [
        "不整份读取 constitution.md",
    ],
    "specpowers/templates/auto-summary-template.md": [
        "≤60 行",
    ],
    "specpowers/SKILL.md": [
        "v3.1.0 读写 token 降耗",
        "task_brief.py",
    ],
}

# v3.1.0 防回潮：tasks.md 旧场景引用模板（抄录 WHEN-THEN 原文）与 explore 收口
# 旧覆盖语义不得回潮（原文抄录 = 任务数 × 场景长度的重复输出）
SCENARIO_REF_REGRESSION_MARKERS = ["WHEN-THEN 原文摘录"]
EXPLORE_OVERWRITE_REGRESSION_MARKERS = ["覆盖写入同一文件", "若文件已存在则覆盖更新"]

# v2.11.0 防回潮：proposal 迭代历史旧多行小节模板不得回潮
# （每轮 5-8 行的 ### Round 小节随轮次线性变长，是迭代轮 token 增长点）
ITERATION_HISTORY_REGRESSION_MARKER = "### Round <N>（<日期>）"

# v2.7.0 会话粘滞：主技能六级判定锚点 + 薄入口粘滞行（auto 单会话直通不适用）
SESSION_STICKY_MAIN_ANCHORS = ["会话粘滞", "拿不准 → 一律按相关", "UserPromptSubmit"]

# v2.9.0 维护技能合并（reset + baseline → maintain）：两分支命令 + 三层分流 +
# 用户零学习成本表述，防止合并后能力丢失或分流规则被简化掉
MAINTAIN_SKILL_ANCHORS = [
    "facade reset",
    "facade baseline",
    "分流规则（三层判定）",
    "意图不明 → 必问",
    "用户无需记忆任何参数",
]

SESSION_STICKY_SKILLS = {
    "specpowers-explore",
    "specpowers-propose",
    "specpowers-apply",
    "specpowers-archive",
    "specpowers-fast",
}

# v2.5.1 explore 硬性产出契约锚点（WorkBuddy 等宿主读不到 prompts/explore.md 时底线仍成立）
EXPLORE_HARD_DELIVERABLES_ANCHORS = [
    "硬性产出契约",
    "逐个提问",
    "docs/specpowers/design/",
    "不只在对话中展示",
    "record-design-doc",
]

# v2.8.0 多活跃需求：主技能多需求契约锚点（前台推导/--feature 硬条款/per-feature 解除/归档语义）
# （v3.0 起「features 映射」表述被工件推导取代——目录即需求身份，锚点同步换代）
MULTI_FEATURE_MAIN_ANCHORS = [
    "多活跃硬条款",
    "必须显式 `--feature",
    "命中哪个需求就按哪个需求的阶段契约处理",
    "解除条件（per-feature）",
    "归档即**该需求**完结",
    "目录即需求身份",
]
# v2.8.0 多活跃需求：四份阶段契约的 feature 来源句锚点（防回潮成单需求 state.feature 表述）
MULTI_FEATURE_PROMPT_ANCHORS = [
    "`--feature` 参数或前台推导确定",
    "slug 即身份",
]
MULTI_FEATURE_PROMPTS = ("explore.md", "propose.md", "apply.md", "archive.md")

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
    """10 个技能的 SKILL.md 必须存在且 frontmatter name 与目录名一致。"""
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


def test_stage_skills_init_check_first():
    """5 个流水线薄入口必须含第 0 步「Init check first」（v2.5.0 初始化前置）。

    未初始化项目直接开工的场景下，薄入口是模型实际遵循的步骤清单——
    第 0 步缺失会让 propose 读不到 constitution 时自行编原则静默劣化。
    """
    for rel_dir in INIT_CHECK_SKILLS:
        content = (SKILLS_ROOT / rel_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "**Init check first**" in content, (
            f"skills/{rel_dir}/SKILL.md 缺少第 0 步初始化前置检查——"
            "未初始化项目将静默劣化（自动补跑 specpowers-init 的锚点被误删）"
        )
        assert ".specpowers/constitution.md" in content, (
            f"skills/{rel_dir}/SKILL.md 第 0 步未检查 constitution.md 存在性"
        )
        assert ".specpowers/baseline.json" in content, (
            f"skills/{rel_dir}/SKILL.md 第 0 步未检查 baseline.json 存在性"
        )


def test_stage_skills_locate_main_skill_directory():
    """v2.5.1 跨端契约定位：9 个阶段技能必须写明主技能目录真实位置。

    裸相对路径（follow prompts/<stage>.md）在不级联加载主技能上下文的宿主
    （如 WorkBuddy）上解析不到真实文件——阶段技能只拿到自身薄入口正文，
    方案对比/落盘登记等硬规则全部丢失。定位句锚点缺失即断链回潮。
    """
    # 基础锚点对全部 8 个阶段技能适用（maintain 为缩短版定位句）
    for rel_dir in STAGE_SKILLS:
        content = (SKILLS_ROOT / rel_dir / "SKILL.md").read_text(encoding="utf-8")
        for anchor in STAGE_SKILL_LOCATION_ANCHORS:
            assert anchor in content, (
                f"skills/{rel_dir}/SKILL.md 缺少主技能目录定位锚点「{anchor}」——"
                "裸相对路径在 WorkBuddy 等宿主上断链（v2.5.1 跨端修复回潮）"
            )
    # 变量模式锚点仅对 7 个契约引用技能适用（完整版定位句）
    for rel_dir in STAGE_SKILL_CONTRACTS:
        content = (SKILLS_ROOT / rel_dir / "SKILL.md").read_text(encoding="utf-8")
        assert CONTRACT_VARIABLE_PATTERN_ANCHOR in content, (
            f"skills/{rel_dir}/SKILL.md 变量表述缺少「{CONTRACT_VARIABLE_PATTERN_ANCHOR}」模式——"
            "必须是模式 + 举例（新工具零改动覆盖），不得回潮成封闭端枚举（v2.6.0）"
        )
        assert CONTRACT_GLOB_ANCHOR in content, (
            f"skills/{rel_dir}/SKILL.md 缺少契约文件 Glob 兜底搜索句"
            f"（{CONTRACT_GLOB_ANCHOR}）——宿主变量不可用时模型无最后定位手段"
        )


def test_explore_skill_hard_deliverables():
    """v2.5.1 explore 硬性产出契约前置：契约文件不可读时四条底线仍成立。

    WorkBuddy 事故根因：薄入口正文只有一行英文摘要且反向鼓励提问，
    契约文件读不到时静默探索/方案对比/落盘登记全部丢失。
    """
    content = (SKILLS_ROOT / "specpowers-explore" / "SKILL.md").read_text(
        encoding="utf-8"
    )
    for anchor in EXPLORE_HARD_DELIVERABLES_ANCHORS:
        assert anchor in content, (
            f"skills/specpowers-explore/SKILL.md 缺少硬性产出锚点「{anchor}」——"
            "宿主读不到 prompts/explore.md 时产出物契约丢失（v2.5.1 修复回潮）"
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
    """探索引擎并入防断链：skills/ 目录集合恰为 10 个（无 -engine 残留、无多余目录）。"""
    actual = {p.name for p in SKILLS_ROOT.iterdir() if p.is_dir()}
    expected = set(ALL_SKILLS)
    assert actual == expected, (
        f"skills/ 目录集合漂移：多余 {sorted(actual - expected)}，缺失 {sorted(expected - actual)}"
    )
    assert not any(name.endswith("-engine") for name in actual), (
        "skills/ 下存在 -engine 结尾目录——内部引擎不以技能身份暴露（v2.4.0 方案 C）"
    )


def test_maintain_skill_branches():
    """v2.9.0 维护合并防回潮：maintain 技能必须保留两分支命令与三层分流规则。

    reset + baseline 合并后，分支命令（facade reset / facade baseline）、
    三层分流（意图判断 → 显式子动作词 → 拿不准必问）与「用户无需记忆参数」
    的零学习成本表述任一缺失，都会让模型在维护场景下失去可执行指引。
    """
    content = (SKILLS_ROOT / "specpowers-maintain" / "SKILL.md").read_text(encoding="utf-8")
    for anchor in MAINTAIN_SKILL_ANCHORS:
        assert anchor in content, (
            f"skills/specpowers-maintain/SKILL.md 缺少维护合并锚点「{anchor}」——"
            "合并后能力丢失或分流规则被简化（v2.9.0 防回潮）"
        )
    # 旧技能目录不得回潮（slash 名已移除，统一入口为 specpowers-maintain）
    assert not (SKILLS_ROOT / "specpowers-reset").exists(), (
        "skills/specpowers-reset/ 仍存在——v2.9.0 已合并入 specpowers-maintain"
    )
    assert not (SKILLS_ROOT / "specpowers-baseline").exists(), (
        "skills/specpowers-baseline/ 仍存在——v2.9.0 已合并入 specpowers-maintain"
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


def test_design_doc_slim_template_anchors():
    """v2.10.0 设计文档瘦身防断链：5 章模板 + 精简纪律锚点必须在契约中。

    「项目上下文」「需求分析」「组件划分」是 baseline/constitution 复述或
    相互重叠的冗余章节（写侧 token 大头），删除后由「相关既有模式」≤6 行
    与「架构（含组件职责）」承接；锚点缺失即瘦身语义断链。
    """
    content = (SKILLS_ROOT / "specpowers" / "prompts" / "explore.md").read_text(
        encoding="utf-8"
    )
    for anchor in DESIGN_DOC_SLIM_ANCHORS:
        assert anchor in content, (
            f"prompts/explore.md 缺少设计文档瘦身锚点「{anchor}」——"
            "5 章模板或精简纪律被误删（v2.10.0 修复回潮）"
        )
    for marker in DESIGN_DOC_SLIM_REGRESSION_MARKERS:
        assert marker not in content, (
            f"prompts/explore.md 残留旧复述章节「{marker}」——"
            "该章节是 baseline/constitution 的纯复述或重叠内容，已由瘦身模板"
            "「相关既有模式」/「架构（含组件职责）」承接（v2.10.0）"
        )


def test_propose_design_doc_partial_read():
    """v2.10.0 propose 读侧纪律：人工模式局部读取设计文档，禁止默认整份重读。

    与 auto 模式路径（auto_base 分片八要素 + Grep 局部回查）对齐——
    人工模式若整份重读，写侧瘦身的读侧收益全部落空。
    """
    content = (SKILLS_ROOT / "specpowers" / "prompts" / "propose.md").read_text(
        encoding="utf-8"
    )
    for anchor in ("局部读取 meta `design_doc` 登记的设计文档", "禁止默认整份重读"):
        assert anchor in content, (
            f"prompts/propose.md 缺少读侧纪律锚点「{anchor}」——"
            "人工模式退回整份重读设计文档，读侧 token 收益落空（v2.10.0 修复回潮）"
        )


def test_iteration_design_round_anchors():
    """v2.7.0 迭代轮简易设计文档防断链：契约与薄入口必须写明 design-round 语义。

    基线冻结 + change 目录内增量文档是迭代轮 token 节省的核心；锚点缺失
    意味着模型会被引导回「重读重写整份基线」的旧行为。
    """
    for rel_path, anchors in ITERATION_DESIGN_ROUND_ANCHORS.items():
        content = (SKILLS_ROOT / rel_path).read_text(encoding="utf-8")
        for anchor in anchors:
            assert anchor in content, (
                f"skills/{rel_path} 缺少迭代轮 design-round 锚点「{anchor}」——"
                "简易设计文档语义断链（v2.7.0 修复回潮）"
            )


def test_iteration_no_overwrite_regression():
    """防回潮：设计文档相关契约不得残留旧的「覆盖重写基线 + 重新登记」语义。

    proposal.md 的「覆盖更新」是三件套有意保留的规则，不在扫描范围。
    """
    scan_paths = [
        "specpowers/prompts/explore.md",
        "specpowers/prompts/refs/auto-iteration.md",
    ]
    for rel_path in scan_paths:
        content = (SKILLS_ROOT / rel_path).read_text(encoding="utf-8")
        for marker in ITERATION_OVERWRITE_REGRESSION_MARKERS:
            assert marker not in content, (
                f"skills/{rel_path} 残留旧覆盖语义标记「{marker}」——"
                "迭代轮应新落 design-round-<N>.md，不再覆盖重写基线设计文档（v2.7.0）"
            )


def test_iteration_token_slim_anchors():
    """v2.11.0 迭代轮 token 收敛防断链：历史表格封顶 + 骨架两级读取 + Edit 化锚点。

    迭代轮 IO 从「三件套全读全写」收敛为「spec/tasks 骨架 + 命中项 Edit」；
    apply 侧按「谁执行」分流（v3.1.0 精化，原「不局部化」由分流表述取代）。
    锚点缺失意味着模型被引导回全读全写旧行为。
    """
    for rel_path, anchors in ITERATION_TOKEN_SLIM_ANCHORS.items():
        content = (SKILLS_ROOT / rel_path).read_text(encoding="utf-8")
        for anchor in anchors:
            assert anchor in content, (
                f"skills/{rel_path} 缺少 v2.11.0 迭代轮 token 收敛锚点「{anchor}」——"
                "历史表格封顶/骨架两级读取/Edit 化语义断链（v2.11.0 修复回潮）"
            )


def test_token_slim_v31_anchors():
    """v3.1.0 读写 token 降耗防断链：分流读取 + 脚本直出 + 骨架 Edit 化锚点。

    ① apply 按执行模式分流（subagent 骨架读取 + task_brief 脚本直出，
    conductor/TDD/worktree 保持全文读）；② 场景引用瘦身为 Scenario 名列表；
    ③ proposal 迭代轮骨架 Edit 化；④ explore 一次成型 + 收口 Edit；
    ⑤ baseline.json 退出认知层必读；⑥ archive grep 证据；⑦ auto 汇总封顶。
    锚点缺失意味着对应降耗语义断链，模型回退全读全写旧行为。
    """
    for rel_path, anchors in TOKEN_SLIM_V31_ANCHORS.items():
        content = (SKILLS_ROOT / rel_path).read_text(encoding="utf-8")
        for anchor in anchors:
            assert anchor in content, (
                f"skills/{rel_path} 缺少 v3.1.0 token 降耗锚点「{anchor}」——"
                "读写降耗语义断链（v3.1.0 修复回潮）"
            )
    # task_brief.py 脚本本体必须存在（契约引用的脚本缺失 = 契约缺口）
    script = SKILLS_ROOT / "specpowers" / "scripts" / "task_brief.py"
    assert script.is_file(), (
        "skills/specpowers/scripts/task_brief.py 缺失——apply.md/propose.md 引用的"
        "brief 切分脚本不存在，subagent 派发退回手工转写（v3.1.0 修复回潮）"
    )


def test_token_slim_v31_regression():
    """防回潮：旧场景引用模板（抄 WHEN-THEN 原文）与 explore 收口覆盖语义不得回潮。

    原文抄录 = 任务数 × 场景长度的重复输出；收口覆盖重写 = 设计文档双倍输出。
    """
    tasks_contract = (SKILLS_ROOT / "specpowers" / "prompts" / "propose.md").read_text(
        encoding="utf-8"
    )
    for marker in SCENARIO_REF_REGRESSION_MARKERS:
        assert marker not in tasks_contract, (
            f"prompts/propose.md 残留旧场景引用模板标记「{marker}」——"
            "场景原文由 task_brief 脚本确定性附上，tasks.md 只存 Scenario 名（v3.1.0）"
        )
    explore_contract = (SKILLS_ROOT / "specpowers" / "prompts" / "explore.md").read_text(
        encoding="utf-8"
    )
    for marker in EXPLORE_OVERWRITE_REGRESSION_MARKERS:
        assert marker not in explore_contract, (
            f"prompts/explore.md 残留旧覆盖语义标记「{marker}」——"
            "设计文档一次成型，收口只做 Edit 增量补正（v3.1.0）"
        )


def test_iteration_history_multiline_regression():
    """防回潮：propose 契约不得残留旧的多行迭代历史小节模板。

    每轮 5-8 行的 ### Round 小节使 proposal 随轮次线性变长，v2.11.0 起由
    单行表格 + 封顶滚动替代（明细事实源：design-round-N.md 与 spec/tasks 轮次痕迹）。
    """
    content = (SKILLS_ROOT / "specpowers" / "prompts" / "propose.md").read_text(
        encoding="utf-8"
    )
    assert ITERATION_HISTORY_REGRESSION_MARKER not in content, (
        "prompts/propose.md 残留旧多行迭代历史模板「"
        + ITERATION_HISTORY_REGRESSION_MARKER
        + "」——应使用单行表格 + 封顶滚动格式（v2.11.0）"
    )


def test_session_sticky_main_skill_anchors():
    """v2.7.0 会话粘滞防断链：主技能必须含六级判定规则与 hook 说明。"""
    content = (SKILLS_ROOT / "specpowers" / "SKILL.md").read_text(encoding="utf-8")
    for anchor in SESSION_STICKY_MAIN_ANCHORS:
        assert anchor in content, (
            f"skills/specpowers/SKILL.md 缺少会话粘滞锚点「{anchor}」——"
            "粘滞三级处理/六级判定/hook 注入说明断链（v2.7.0 修复回潮）"
        )


def test_session_sticky_stage_skill_lines():
    """v2.7.0 五个流水线薄入口必须含粘滞行（auto 单会话直通不适用）。"""
    for rel_dir in SESSION_STICKY_SKILLS:
        content = (SKILLS_ROOT / rel_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "会话粘滞" in content, (
            f"skills/{rel_dir}/SKILL.md 缺少会话粘滞行——宿主不级联加载主技能时"
            "粘滞语义对薄入口不可见（v2.7.0）"
        )


def test_hooks_register_user_prompt_submit():
    """v2.7.0 hooks.json 必须注册 UserPromptSubmit 且脚本落位（逐轮锚点行）。"""
    hooks = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    assert "UserPromptSubmit" in hooks.get("hooks", {}), (
        "hooks.json 未注册 UserPromptSubmit——逐轮粘滞锚点行注入断链（v2.7.0）"
    )
    assert (PLUGIN_ROOT / "hooks" / "session-sticky").is_file(), (
        "hooks/session-sticky 脚本缺失——UserPromptSubmit 注册指向不存在的脚本"
    )


def test_multi_feature_main_skill_anchors():
    """v2.8.0 多活跃需求防回潮：主技能必须含前台推导/--feature 硬条款/per-feature 解除锚点。"""
    content = (SKILLS_ROOT / "specpowers" / "SKILL.md").read_text(encoding="utf-8")
    for anchor in MULTI_FEATURE_MAIN_ANCHORS:
        assert anchor in content, (
            f"skills/specpowers/SKILL.md 缺少多活跃需求锚点「{anchor}」——"
            "多需求路由规则/前台推导/归档语义断链（v2.8.0）"
        )


def test_multi_feature_prompt_anchors():
    """v2.8.0 四份阶段契约的 feature 来源句必须为多需求表述（防回潮成单需求 state.feature）。"""
    for name in MULTI_FEATURE_PROMPTS:
        content = (SKILLS_ROOT / "specpowers" / "prompts" / name).read_text(encoding="utf-8")
        for anchor in MULTI_FEATURE_PROMPT_ANCHORS:
            assert anchor in content, (
                f"prompts/{name} 缺少多活跃需求锚点「{anchor}」——"
                "feature 来源句回潮成单需求 state.json 字段表述（v2.8.0）"
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


def test_state_derivation_contract_anchors():
    """v3.0 状态机推导化契约锚点（防回潮）：meta 自包含登记 + 工件推导 + reconcile 入口。

    - explore.md：登记即建目录语义含 .specpowers-meta.json 自包含登记，
      旧「不创建 changes/ 目录」定位表述不得回潮（v3.0 起 change 目录
      自探索收口即建立，仅三件套仍归 propose）
    - SKILL.md：工件推导小节（derive_stage / runtime.json / state.json.bak 迁移留底）
      + reconcile 入口
    - propose.md：迭代轮轮次即工件推导值（design-round-N / tasks Round 小节），
      重入识别为目录推导（无 state 可读），回退额度计次在 runtime.json
    - fast_mode.md：fast 自包含（入口建 change 目录 + meta(mode=fast) + checklist.md 骨架）
    """
    explore_md = (PLUGIN_ROOT / "skills/specpowers/prompts/explore.md").read_text(encoding="utf-8")
    assert ".specpowers-meta.json" in explore_md, "explore.md 缺自包含登记锚点"
    assert "自包含" in explore_md, "explore.md 缺自包含登记语义说明"
    assert "不创建" not in explore_md, "explore.md 残留旧定位表述「不创建 changes/ 目录」（v2.12 已解除）"
    assert "登记即建目录" in explore_md, "explore.md 缺 v3.0 收口建目录锚点"
    assert "自动识别为迭代轮" in explore_md, (
        "explore.md 重入识别缺目录推导自动识别锚点（v3.0 无 facade iterate，重入即迭代轮）"
    )

    skill_md = (PLUGIN_ROOT / "skills/specpowers/SKILL.md").read_text(encoding="utf-8")
    assert "工件推导" in skill_md, "SKILL.md 缺工件推导小节"
    assert "derive_stage" in skill_md, "SKILL.md 缺 derive_stage 工件判定锚点"
    assert "runtime.json" in skill_md, "SKILL.md 缺项目级 runtime.json 锚点"
    assert "state.json.bak" in skill_md, "SKILL.md 缺旧 state 迁移留底锚点"
    assert "facade reconcile" in skill_md, "SKILL.md 缺 reconcile 入口"

    propose_md = (PLUGIN_ROOT / "skills/specpowers/prompts/propose.md").read_text(encoding="utf-8")
    assert "轮次即工件推导值" in propose_md, "propose.md 迭代轮缺推导值语义锚点"
    assert "自动识别为迭代轮" in propose_md, (
        "propose.md 重入识别缺目录推导自动识别锚点（v3.0 重入即迭代轮，无需确认命令开轮）"
    )
    assert "runtime.json" in propose_md, "propose.md 回退场景缺 runtime.json 计次锚点"

    fast_md = (PLUGIN_ROOT / "skills/specpowers/prompts/fast_mode.md").read_text(encoding="utf-8")
    assert "checklist.md" in fast_md, "fast_mode.md 缺 checklist.md 验收清单锚点"
    assert "mode=fast" in fast_md, "fast_mode.md 缺 meta(mode=fast) 自包含登记锚点"

    auto_md = (PLUGIN_ROOT / "skills/specpowers/prompts/auto.md").read_text(encoding="utf-8")
    assert "facade reconcile" in auto_md, "auto.md 断点定位缺 reconcile 恢复入口"
    assert "工件推导" in auto_md, "auto.md 缺工件推导口径锚点（v3.0 阶段由工件推导）"


def test_reconcile_command_registered():
    """facade reconcile 子命令已注册且与 record-design-doc 的 meta 落盘联动（防子命令遗漏）。"""
    from specpowers_cli.bridge.facade import main

    facade_py = (PLUGIN_ROOT / "scripts/specpowers_cli/bridge/facade.py").read_text(encoding="utf-8")
    assert '"reconcile": _cmd_reconcile' in facade_py, "facade 分发表未注册 reconcile"
    dispatcher_py = (PLUGIN_ROOT / "scripts/specpowers_cli/bridge/dispatcher.py").read_text(
        encoding="utf-8")
    assert "update_meta" in dispatcher_py, "record-design-doc 未落自包含登记（update_meta，v3.0 起唯一写点为 change 目录 meta）"
