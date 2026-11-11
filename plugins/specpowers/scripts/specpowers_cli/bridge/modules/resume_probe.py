"""Ambient resume — SessionStart 只读探测活跃需求状态（v2.3.0）。

v2.7.0 增补 sticky_note：UserPromptSubmit 逐轮注入的会话粘滞锚点行
（有活跃需求才输出单行 feature/stage/Round + capability + 修改范围锚点，
供模型做消息相关性判定；零活跃零输出，与 probe_resume 同只读口径）。

借鉴 Comet resume-probe 的低噪声理念（文章数据分级 B/C 级，机制以本仓库
实测为准）：会话启动时只读探测未完成的特性流水线，确有活跃状态才输出
提示，零活跃零噪音。探测绝不写状态、绝不抛异常阻断——所有异常由调用方
（facade resume-probe 子命令）吞掉降级为空提示。

判定分支（按序短路）：
1. state 阶段活跃（explore/propose/apply/archive）+ feature 非空
   → auto_base.json 存在按 auto 断点提示（重入 /specpowers-auto 续跑）；
     否则按阶段给续跑指引（与状态机 VALID_TRANSITIONS 对齐）
2. stage=ready + mode=fast → fast 验收提示（编码完成后 /specpowers-apply）
3. 工件存在但流水线状态未接管（本机 state 缺失/已回 ready——团队协作时
   state.json 每人独立而 openspec/changes/ 工件共享，跨机接管靠此提示）
   → 列出活跃 change，建议重入 propose 确认或 reset 放弃
4. 其余（含全新项目）→ 空串，零噪音

作者：005819 | 协作：GLM-5.3
"""

from pathlib import Path

from specpowers_cli.bridge.core.fs_state import DEFAULT_STATE, load_state

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


def _auto_base_path(root: Path) -> Path:
    """auto_base.json 路径（与 dispatcher._auto_base_path 保持一致）。"""
    return root / ".specpowers" / "auto_base.json"


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

    state.json 缺失/损坏时按默认状态继续（探测不阻断、不引导 reset——
    修复指引属于各阶段命令的前置校验职责，不在探测里越位）。
    """
    try:
        state = load_state(root)
    except Exception:
        state = dict(DEFAULT_STATE)
    stage = str(state.get("stage", "init"))
    mode = str(state.get("mode", "full"))
    feature = str(state.get("feature") or "").strip()
    rounds = int(state.get("iteration_count", 0) or 0)

    # 1. 流水线活跃：按 stage 给续跑指引（auto 断点优先）
    if stage in ACTIVE_STAGES and feature:
        if _auto_base_path(root).exists():
            return (
                f"📌 检测到 auto 无人值守任务中断：{feature}，断点阶段 {stage}。"
                "重入 /specpowers-auto 续跑（三分判定 resume/iterate）。"
            )
        round_note = f"（Round {rounds}）" if rounds >= 1 else ""
        return (
            f"📌 检测到未完成的特性流水线：{feature}{round_note}，"
            f"当前阶段 {stage}。续跑：{STAGE_NEXT[stage]}"
        )
    # 2. fast 优化模式进行中
    if stage == "ready" and mode == "fast" and feature:
        return f"📌 fast 优化模式进行中：{feature}。编码完成后运行 /specpowers-apply 验收。"
    # 3. 工件存在但流水线状态未接管（state 每人独立而工件共享的跨机场景）
    changes = active_changes(root)
    if changes and not (stage in ACTIVE_STAGES and feature):
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


def sticky_note(root: Path) -> str:
    """会话粘滞锚点行（v2.7.0，UserPromptSubmit hook 消费）。

    有活跃需求时输出单行锚点（feature/stage/Round + capability + 修改范围
    前缀），供模型对每条用户消息做相关性匹配（软粘滞，判定规则见主技能
    SKILL.md「会话粘滞」小节）；无活跃状态返回空串零注入。只读、绝不写
    状态；capability/修改范围取自本地文件 IO（零 LLM token），文件缺失
    逐项降级。异常由调用方（facade sticky-note）吞掉降级为空输出。

    作者：005819 | 协作：GLM-5.3
    """
    try:
        state = load_state(root)
    except Exception:
        state = dict(DEFAULT_STATE)
    stage = str(state.get("stage", "init"))
    mode = str(state.get("mode", "full"))
    feature = str(state.get("feature") or "").strip()
    rounds = int(state.get("iteration_count", 0) or 0)

    # 1. 流水线活跃：拼装锚点行（capability / 修改范围逐项可选，缺失即降级）
    if stage in ACTIVE_STAGES and feature:
        round_note = f"，Round {rounds}" if rounds >= 1 else ""
        anchors = ""
        caps = _capability_names(root, feature)
        if caps:
            anchors += f"：capability={','.join(caps)}"
        scope = _scope_prefixes(root, feature)
        if scope:
            anchors += f"，修改范围={scope}"
        return (
            f"活跃需求 {feature}（{stage}{round_note}）{anchors} —— "
            "相关消息按 specpowers 流程处理（判定规则见主技能 SKILL.md「会话粘滞」），"
            "脱离流程请先 /specpowers-archive 或 /specpowers-reset"
        )
    # 2. fast 优化模式进行中：编码由用户完成，仅提示验收入口
    if stage == "ready" and mode == "fast" and feature:
        return (
            f"fast 优化模式进行中：{feature}。编码完成后 /specpowers-apply 验收；"
            "放弃请 /specpowers-reset"
        )
    return ""
