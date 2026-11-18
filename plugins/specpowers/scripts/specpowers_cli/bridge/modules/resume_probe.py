"""Ambient resume — SessionStart 只读探测活跃需求状态（v2.3.0；v3.0 全推导）。

v2.7.0 增补 sticky_note：UserPromptSubmit 逐轮注入的会话粘滞锚点行
（有活跃需求才输出 feature/stage/Round + capability + 修改范围锚点，
供模型做消息相关性判定；零活跃零输出，与 probe_resume 同只读口径）。

v2.8.0 多活跃需求化：probe 与 sticky 均枚举全部活跃需求，
每需求一行、前台标注——「当前在做什么」活在对话上下文里，锚点的作用是
把全部活跃需求摆在模型眼前供消息归属判定（与 OpenSpec「agent 上下文
指名、工具不做隐式当前」同哲学），而非维护单一「当前需求」。

v3.0.0 状态机推导化：活跃清单（active_slugs 目录扫描）、阶段（derive_stage）、
轮次（iteration_count_of）、前台（foreground_slug meta 推导）全部从工件推导，
本模块零 state 读取；「工件存在但状态未接管」的跨机分支随双真相源消失
（目录即活跃，天然跨机一致）。

借鉴 Comet resume-probe 的低噪声理念（文章数据分级 B/C 级，机制以本仓库
实测为准）：会话启动时只读探测未完成的特性流水线，确有活跃状态才输出
提示，零活跃零噪音。探测绝不写状态、绝不抛异常阻断——所有异常由调用方
（facade resume-probe 子命令）吞掉降级为空提示。

probe_resume 判定分支（按序短路）：
1. active_slugs 有活跃需求 → 每需求一行：auto_base（.specpowers/auto_base/
   <slug>.json）存在按 auto 断点提示（重入 /specpowers-auto 续跑）；否则按
   推导阶段给续跑指引；fast 态需求（meta.mode=fast）给验收提示
2. 其余（含全新项目）→ 空串，零噪音

作者：005819 | 协作：GLM-5.3
"""

from pathlib import Path

from specpowers_cli.bridge.core.fs_state import auto_base_path
from specpowers_cli.bridge.modules.state_derivation import (
    active_slugs, foreground_slug, derive_stage, iteration_count_of, read_meta,
    change_dir_of, STAGE_FAST,
)

# 阶段 → 续跑指引。与 dispatcher 工件判定对齐：
# - explore 重入 explore 非法（仅新需求），指引 propose 直达或重新探索
# - propose 自环合法（迭代续作：已有产物校验后复用，只补缺失）
STAGE_NEXT = {
    "explore": "/specpowers-propose（直接提案）或 /specpowers-explore（重新探索）",
    "propose": "/specpowers-propose（断点续作：已有产物校验后复用，只补缺失）",
    "apply": "/specpowers-apply",
}
ACTIVE_STAGES = ("explore", "propose", "apply", "fast")

# sticky_note 多需求展示上限：≤3 全列；>3 时前台 + 后台一行汇总（控 token）
STICKY_MAX_LINES = 3


def active_changes(root: Path) -> list[str]:
    """活跃 change 目录名（v3.0 起即 active_slugs 的别名，保持旧调用方兼容）。"""
    return active_slugs(root)


def probe_resume(root: Path) -> str:
    """只读探测，返回多行提示文本；空串 = 无活跃状态（零噪音）。

    多活跃需求：每需求一行（auto 断点优先于阶段指引），前台标注。
    全推导拼装（stage/Round/mode 来自工件与 meta），异常由调用方降级。
    """
    features = active_slugs(root)
    fg = foreground_slug(root) or ""

    lines: list[str] = []
    # 前台永远排第一行（与 sticky_note 同序：模型对未指名语境的默认归属参考）
    ordered = [fg] + [slug for slug in features if slug != fg] if fg else features
    for slug in ordered:
        change_dir = change_dir_of(root, slug)
        stage = derive_stage(change_dir)
        meta = read_meta(change_dir) or {}
        mode = str(meta.get("mode") or "full")
        rounds = iteration_count_of(change_dir)
        fg_note = "（前台）" if slug == fg else ""

        # 1. 流水线活跃：按推导 stage 给续跑指引（auto 断点优先；fast 态除外——
        # auto 流程不为 fast 需求建基线，迁移残留的 fast+auto_base 按 fast 提示）
        if stage != STAGE_FAST and auto_base_path(root, slug).exists():
            lines.append(
                f"📌 检测到 auto 无人值守任务中断：{slug}{fg_note}，断点阶段 {stage}。"
                f"重入 /specpowers-auto 续跑（三分判定 resume/iterate）。"
            )
            continue
        round_note = f"（Round {rounds}）" if rounds >= 1 else ""
        if stage == STAGE_FAST:
            # fast 态需求（meta.mode=fast）：编码由用户完成，提示验收入口
            lines.append(
                f"📌 fast 优化模式进行中：{slug}{fg_note}。"
                f"编码完成后运行 /specpowers-apply 验收。"
            )
        else:
            lines.append(
                f"📌 检测到未完成的特性流水线：{slug}{round_note}{fg_note}，"
                f"当前阶段 {stage}。续跑：{STAGE_NEXT[stage]}"
            )

    return "\n".join(lines) if lines else ""


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


def _sticky_line(root: Path, slug: str, fg: bool) -> str:
    """拼装单个活跃需求的粘滞锚点行（stage/Round/mode 全推导，capability/修改范围逐项降级）。

    作者：005819 | 协作：GLM-5.3
    """
    change_dir = change_dir_of(root, slug)
    stage = derive_stage(change_dir)
    meta = read_meta(change_dir) or {}
    mode = str(meta.get("mode") or "full")
    rounds = iteration_count_of(change_dir)
    fg_note = "（前台）" if fg else ""

    # fast 态需求：编码由用户完成，仅提示验收入口
    if stage == STAGE_FAST:
        return (
            f"fast 优化模式进行中：{slug}{fg_note}。编码完成后 /specpowers-apply 验收；"
            f"放弃该需求请 /specpowers-maintain reset --feature {slug}"
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
        f"脱离该需求请先 /specpowers-archive --feature {slug} 或 /specpowers-maintain reset --feature {slug}"
    )


def sticky_note(root: Path) -> str:
    """会话粘滞锚点行（v2.7.0，UserPromptSubmit hook 消费；v2.8.0 多需求多行）。

    每个活跃需求一行锚点（feature/stage/Round + capability + 修改范围
    前缀，前台行加「（前台）」标注），供模型对每条用户消息做相关性匹配
    （软粘滞，判定规则见主技能 SKILL.md「会话粘滞」）；无活跃状态返回
    空串零注入。展示上限：≤3 个全列，>3 时前台 + 一行后台汇总（控 token）。
    只读、绝不写状态；stage/Round/meta 全推导，capability/修改范围取自
    本地文件 IO（零 LLM token），文件缺失逐项降级。异常由调用方
    （facade sticky-note）吞掉降级为空输出。

    作者：005819 | 协作：GLM-5.3
    """
    features = active_slugs(root)
    if not features:
        return ""
    fg = foreground_slug(root) or ""

    lines: list[str] = []
    # 前台永远排第一行（模型对未指名语境的默认归属参考）
    ordered = [fg] + [slug for slug in features if slug != fg] if fg else features
    shown = ordered[:STICKY_MAX_LINES]
    for slug in shown:
        lines.append(_sticky_line(root, slug, slug == fg))
    rest = ordered[STICKY_MAX_LINES:]
    if rest:
        lines.append(
            f"另有 {len(rest)} 个后台活跃需求：{'、'.join(rest)}——"
            "相关消息处理时命令须显式 --feature 指定目标"
        )
    return "\n".join(lines)
