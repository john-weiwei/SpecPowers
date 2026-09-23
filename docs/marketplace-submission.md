# 官方插件市场收录指南（Claude / OpenAI）

> 作者：SpecPowers Team 2026-09-23（ZCode / GLM-5.3）
> 状态：材料已备齐，待 push + tag 后人工提交（提交需登录各自账号，无法代办）

## 一、为什么收录

当前安装方式要求用户先知道本仓库地址再手动 `marketplace add`。收录后的差别：

- **Claude** → `claude-plugins-official` 官方市场：用户在 `/plugin` 面板直接搜索一键安装
- **OpenAI** → universal plugin directory（**ChatGPT + Codex 共享**）：插件面板搜索即装，附带平台可信度背书

## 二、前置条件（提交前必须完成）

1. `git push origin main` 推送全部 v2.2.0 提交
2. 打 tag 并推送（本仓库发版惯例，pip 安装命令也引用 tag）：

   ```bash
   git tag -a v2.2.0 -m "v2.2.0：Claude Code / Codex 插件市场安装修复 + portable 根清单 + 收录准备"
   git push origin v2.2.0
   ```

3. 提交前自检（任一环境跑一次即可）：
   - Claude CLI：仓库根 `claude plugin validate .`
   - Codex CLI：`codex plugin marketplace add <仓库本地路径>` 后 `codex plugin marketplace list` 冒烟
4. 本地全量测试通过：`python -m pytest tests/`（当前 206 用例）

## 三、Claude 官方市场（claude-plugins-official）

**提交入口**：表单 <https://clau.de/plugin-directory-submission>（官方 README 明确"Use the plugin directory submission form"，不走 PR）。

**审核口径**：官方仅笼统要求"meet quality and security standards"；插件含 hooks 会进入人工安全审核（见第五节答复要点）。

**关键约束**：marketplace 条目的 `name` 是 **immutable slug**——收录后不可改名（改名需 `renames` 迁移映射）。我们的 `specpowers` 已在 4 份宿主清单 + 4 份市场清单锁定，无改名风险。

**表单填写材料（直接复制）**：

- 插件名：`specpowers`
- 仓库：<https://github.com/john-weiwei/SpecPowers>
- 市场清单：仓库根 `.claude-plugin/marketplace.json`（含 owner/strict，source 指向 `./plugins/specpowers`）
- 英文简介（short）：`A bridging plugin that layers structure-consistency gates and real-time human-handoff on top of OpenSpec and superpowers, with a five-stage pipeline (init→explore→propose→apply→archive) and an unattended auto mode.`
- 英文长描述：`SpecPowers orchestrates OpenSpec and superpowers without rewriting their engines, adding two hard constraints they both lack: a structure-consistency gate that rejects unsanctioned directories/dependencies in AI-generated code, and real-time human-handoff that pauses on uncertainty instead of silently skipping. It ships 9 slash commands covering a five-stage pipeline (init, explore, propose, apply, archive), a fast mode for small changes, and an unattended auto mode driven by a design document. Requires OpenSpec CLI (archive stage) and the superpowers plugin (propose/apply); both are auto-detected at session start.`
- 分类：`developer-tools`
- 关键词：`spec-driven, pipeline, openspec, structure-gate, superpowers`

## 四、OpenAI universal directory（ChatGPT + Codex 共享）

**文档入口**：developers.openai.com → Plugins → **Test and publish**（子页：Connect and test your plugin → **Submit and publish** → Submission error reference）。

**流程**（官方工作流）：

1. **本地测试**：ChatGPT 桌面端添加本仓库为市场源（读 `.agents/plugins/marketplace.json`），安装 specpowers 验证 skills 加载与 SessionStart 依赖提示
2. **提交完整插件**：经 Submit and publish 入口提交（skills 全量 + 声明组件；本插件无 MCP 服务器，审核面更小）
3. **审核发布**：通过后进入 universal plugin directory，ChatGPT 与 Codex 双端可见

**已就绪的格式资产**：

| 资产 | 位置 | 作用 |
|------|------|------|
| portable 根清单 | `plugins/specpowers/plugin.json` | agent-plugins.org 1.0.0 schema；`skills/` 与 `hooks/hooks.json` 自动发现；`extensions.com.openai.interface` 内含英文展示元数据（displayName/shortDescription/category） |
| Codex 兼容回退 | `plugins/specpowers/.codex-plugin/plugin.json` | 旧版工具识别；根清单含 inline 扩展时被整体忽略（依赖声明已随迁至根清单扩展内） |
| Codex 市场清单 | `.agents/plugins/marketplace.json` | policy/category 齐备 |

官方另提供「Submit your Claude Code plugin to OpenAI」转换指南——本仓库已是双格式原生，无需转换。

## 五、安全审核答复要点（两家通用，提前备好）

- **零网络行为**：插件不含 MCP 服务器、不发起任何网络请求、不外传数据；纯本地 Markdown 指令 + Python 标准库（≥3.11，零第三方依赖）
- **SessionStart hook 行为**（`hooks/hooks.json` → `run-hook.cmd check-deps`）：检测 `openspec` CLI 与 superpowers 插件是否安装（`command -v` + 本地插件缓存目录探测），结果以 JSON additionalContext 注入会话提示用户；**永远 exit 0，不阻断会话**；未通过信任审核时宿主自动跳过
- **确定性层能力边界**：仅本地文件读写（`.specpowers/`、`openspec/`、`docs/specpowers/`）、git 只读操作（diff/log/status）与文件锁；无删除仓库外文件、无修改 git 配置、无凭据访问
- **来源可审计**：全部脚本在仓库内明文可查，MIT 协议

## 六、提交后跟踪

- Claude：表单提交后等待 Anthropic 审核（无公开 SLA）；期间用户始终可用市场源直装（README 方式一）
- OpenAI：若收到 Submission error，对照官方 Submission error reference 页修订后重提；发布后在 ChatGPT 桌面端 / Codex 插件面板搜索 `SpecPowers` 验收
- 两端收录成功后：README「支持平台」表补注官方市场条目，`docs/claude-codex-marketplace-plan.md` P2 状态收口
