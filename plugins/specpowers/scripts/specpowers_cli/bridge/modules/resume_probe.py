"""Ambient resume — SessionStart 只读探测活跃需求状态（v2.3.0）。

v2.7.0 增补 sticky_note：UserPromptSubmit 逐轮注入的会话粘滞锚点行
（有活跃需求才输出 feature/stage/Round + capability + 修改范围锚点，
供模型做消息相关性判定；零活跃零输出，与 probe_resume 同只读口径）。

v2.8.0 多活跃需求化：probe 与 sticky 均枚举全部活跃需求（features 映射），
每需求一行、前台标注——「当前在做什么」活在对话上下文里，锚点的作用是
把全部活跃需求摆在模型眼前供消息归属判定（与 OpenSpec「agent 上下文
指名、工具不做隐式当前」同哲学），而非维护单一「当前需求」。

借鉴 Comet resume-probe 的低噪声理念（文章数据分级 B/C 级，机制以本仓库
实测为准）：会话启动时只读探测未完成的特性流水线，确有活跃状态才输出
提示，零活跃零噪音。探测绝不写状态、绝不抛异常阻断——所有异常由调用方
（facade resume-probe 子命令）吞掉降级为空提示。

probe_resume 判定分支（按序短路）：
1. features 映射有活跃需求（stage ∈ explore/propose/apply/archive）
   → 每需求一行：auto_base（.specpowers/auto_base/<slug>.json）存在按
     auto 断点提示（重入 /specpowers-auto 续跑）；否则按阶段给续跑指引
     （与状态机 VALID_TRANSITIONS 对齐）；fast 态需求（stage=ready+mode=fast）
     给验收提示
2. 工件存在但流水线状态未接管（本机 state 缺失/已回 ready——团队协作时
   state.json 每人独立而 openspec/changes/ 工件共享，跨机接管靠此提示）
   → 列出活跃 change，建议重入 propose 确认或 reset 放弃
3. 其余（含全新项目）→ 空串，零噪音

作者：005819 | 协作：GLM-5.3
"""

from pathlib import Path

from specpowers_cli.bridge.core.fs_state import (
    list_features, load_feature, foreground_feature, auto_base_path,
)

# 阶段 → 续跑指引。与 dispatcher.VALID_TRANSITIONS 对齐：
# - explore 重入 explore 非法（from 仅 ready），指引 propose 直达或重新探索
# - propose 自环合法（迭代续作：已有产物校验后复用，只补缺失）
STAGE_NEXT = {
    "explore": "/specpowers-propose（直接提案）或 /specpowers-explore（重新探索）",
    "propose": "/specpowers-propose（断点续作：已有产物校验后复用，只补缺失）",
    "apply": "/specpowers-apply",
    "archive": "/specpowers-archive",
}
ACTIVE_STAGES = ("explore", "propose", "apply", "archive")

# sticky_note 多需求展示上限：≤3 全列；>3 时前台 + 后台一行汇总（控 token）
STICKY_MAX_LINES = 3


def active_changes(root: Path) -> list[str]:
    """扫描 openspec/changes/ 下活跃（未归档）change 目录名，按名字排序。

    活跃判定与 Comet resume-probe 同口径：目录含任一三件套工件
    （proposal.md / tasks.md / specs/）即视为活跃，archive 快照目录排除。
    """
    base = root / "openspec" / "changes"
    if not base.is_dir():
        return []
    names: list[str] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name == "archive":
            continue
        has_artifact = (
            (child / "proposal.md").exists()
            or (child / "tasks.md").exists()
            or (child / "specs").is_dir()
        )
        if has_artifact:
            names.append(child.name)
    return names


def probe_resume(root: Path) -> str:
    """只读探测，返回多行提示文本；空串 = 无活跃状态（零噪音）。

    多活跃需求：每需求一行（auto 断点优先于阶段指引），前台标注。
    state.json 缺失/损坏时按默认状态继续（探测不阻断、不引导 reset——
    修复指引属于各阶段命令的前置校验职责，不在探测里越位）。
    """
    try:
        features = list_features(root)
    except Exception:
        features = []
    fg = ""
    try:
        fg = foreground_feature(root)
    except Exception:
        fg = ""

    lines: list[str] = []
    # 前台永远排第一行（与 sticky_note 同序：模型对未指名语境的默认归属参考）
    ordered = [fg] + [slug for slug in features if slug != fg]
    for slug in ordered:
        try:
            fs = load_feature(root, slug) or {}
        except Exception:
            continue
        stage = str(fs.get("stage", ""))
        mode = str(fs.get("mode", "full"))
        rounds = int(fs.get("iteration_count", 0) or 0)
        fg_note = "（前台）" if slug == fg else ""

        # 1. 流水线活跃：按 stage 给续跑指引（auto 断点优先）
        if stage in ACTIVE_STAGES:
            if auto_base_path(root, slug).exists():
                lines.append(
                    f"📌 检测到 auto 无人值守任务中断：{slug}{fg_note}，断点阶段 {stage}。"
                    f"重入 /specpowers-auto 续跑（三分判定 resume/iterate）。"
                )
                continue
            round_note = f"（Round {rounds}）" if rounds >= 1 else ""
            lines.append(
                f"📌 检测到未完成的特性流水线：{slug}{round_note}{fg_note}，"
                f"当前阶段 {stage}。续跑：{STAGE_NEXT[stage]}"
            )
            continue
        # fast 态需求（stage=ready + mode=fast）：编码由用户完成，提示验收入口
        if stage == "ready" and mode == "fast":
            lines.append(
                f"📌 fast 优化模式进行中：{slug}{fg_note}。"
                f"编码完成后运行 /specpowers-apply 验收。"
            )

    if lines:
        return "\n".join(lines)

    # 2. 工件存在但流水线状态未接管（state 每人独立而工件共享的跨机场景）
    changes = active_changes(root)
    if changes:
        names = ", ".join(changes)
        return (
            f"📌 检测到未归档的 change：{names}（本机流水线状态未接管）。"
            "继续该需求：/specpowers-propose（重入确认为迭代轮）；放弃：/specpowers-reset。"
        )
    return ""


def _capability_names(root: Path, feature: str) -> list[str]:
    """列出当前 change 的 capability 目录名（specs/ 下一级目录，排序）。

    供 sticky_note 拼装锚点行（本地文件 IO，零 LLM token）；目录不存在返回空。

    作者：005819 | 协作：GLM-5.3
    """
    specs = root / "openspec" / "changes" / feature / "specs"
    if not specs.is_dir():
        return []
    return sorted(child.name for child in specs.iterdir() if child.is_dir())


def _scope_prefixes(root: Path, feature: str, limit: int = 120) -> str:
    """提取 tasks.md「修改范围：」声明行内容，超长截断。

    多轮迭代取并集后可能很长，超 limit 字符截断加省略号；文件缺失或无
    声明行返回空串（sticky_note 降级为不含修改范围的简版锚点行）。

    作者：005819 | 协作：GLM-5.3
    """
    tasks = root / "openspec" / "changes" / feature / "tasks.md"
    if not tasks.is_file():
        return ""
    for line in tasks.read_text(encoding="utf-8", errors="replace").splitlines():
        # 匹配 tasks.md 顶部注释块中的「修改范围：」声明行
        if "修改范围" in line and "：" in line:
            raw = line.split("：", 1)[1].strip()
            # 声明行位于 HTML 注释块内，剥掉行尾注释闭合符再截断
            if raw.endswith("-->"):
                raw = raw[:-3].rstrip()
            return raw if len(raw) <= limit else raw[: limit - 1] + "…"
    return ""


def _sticky_line(root: Path, slug: str, fs: dict, fg: bool) -> str:
    """拼装单个活跃需求的粘滞锚点行（capability/修改范围逐项可选，缺失降级）。

    作者：005819 | 协作：GLM-5.3
    """
    stage = str(fs.get("stage", ""))
    mode = str(fs.get("mode", "full"))
    rounds = int(fs.get("iteration_count", 0) or 0)
    fg_note = "（前台）" if fg else ""

    # fast 态需求：编码由用户完成，仅提示验收入口
    if stage == "ready" and mode == "fast":
        return (
            f"fast 优化模式进行中：{slug}{fg_note}。编码完成后 /specpowers-apply 验收；"
            f"放弃该需求请 /specpowers-reset --feature {slug}"
        )

    round_note = f"，Round {rounds}" if rounds >= 1 else ""
    anchors = ""
    caps = _capability_names(root, slug)
    if caps:
        anchors += f"：capability={','.join(caps)}"
    scope = _scope_prefixes(root, slug)
    if scope:
        anchors += f"，修改范围={scope}"
    return (
        f"活跃需求 {slug}{fg_note}（{stage}{round_note}）{anchors} —— "
        "相关消息按 specpowers 流程处理（判定规则见主技能 SKILL.md「会话粘滞」，"
        "命中哪个需求就按哪个需求的阶段契约处理），"
        f"脱离该需求请先 /specpowers-archive --feature {slug} 或 /specpowers-reset --feature {slug}"
    )


def sticky_note(root: Path) -> str:
    """会话粘滞锚点行（v2.7.0，UserPromptSubmit hook 消费；v2.8.0 多需求多行）。

    每个活跃需求一行锚点（feature/stage/Round + capability + 修改范围
    前缀，前台行加「（前台）」标注），供模型对每条用户消息做相关性匹配
    （软粘滞，判定规则见主技能 SKILL.md「会话粘滞」）；无活跃状态返回
    空串零注入。展示上限：≤3 个全列，>3 时前台 + 一行后台汇总（控 token）。
    只读、绝不写状态；capability/修改范围取自本地文件 IO（零 LLM token），
    文件缺失逐项降级。异常由调用方（facade sticky-note）吞掉降级为空输出。

    作者：005819 | 协作：GLM-5.3
    """
    try:
        features = list_features(root)
        fg = foreground_feature(root)
    except Exception:
        return ""

    if not features:
        # state 未接管但工件存在（跨机场景）：保持零噪音原则，锚点不输出
        # （接管提示由 SessionStart 的 probe_resume 分支 2 承担）
        return ""

    lines: list[str] = []
    # 前台永远排第一行（模型对未指名语境的默认归属参考）
    ordered = [fg] + [slug for slug in features if slug != fg]
    shown = ordered[:STICKY_MAX_LINES]
    for slug in shown:
        try:
            fs = load_feature(root, slug) or {}
        except Exception:
            continue
        lines.append(_sticky_line(root, slug, fs, slug == fg))
    rest = ordered[STICKY_MAX_LINES:]
    if rest:
        lines.append(
            f"另有 {len(rest)} 个后台活跃需求：{'、'.join(rest)}——"
            "相关消息处理时命令须显式 --feature 指定目标"
        )
    return "\n".join(lines)
