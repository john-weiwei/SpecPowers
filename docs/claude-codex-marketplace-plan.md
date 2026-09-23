# Claude Code / Codex 插件市场安装支持优化方案

> 作者：SpecPowers Team 2026-09-23（ZCode / GLM-5.3）
> 状态：P0 + P1 + P2 已实施（v2.2.0，2026-09-23）。P2 官方收录的表单提交需人工完成，材料见 docs/marketplace-submission.md；P2 第 10 项（commands 包装 skills）维持缓办

## 一、结论摘要

**当前 README 声称的 Claude Code / Codex 市场安装命令实际不可用**——两家都不识别仓库根的裸 `marketplace.json`：

- **Claude Code** 只认仓库根的 **`.claude-plugin/marketplace.json`**（本仓库没有这份）
- **Codex / ChatGPT** 只认仓库根的 **`.agents/plugins/marketplace.json`**，或 legacy 兼容的 `.claude-plugin/marketplace.json`（两份都没有）

现有的根 `marketplace.json` 是 ZCode 约定，`.codebuddy-plugin/marketplace.json` 是 WorkBuddy 约定，对这两家无效。修复成本低（新增 2 份市场清单 + 同步测试/文档），另附 2 项能力补齐（Codex hooks 依赖检测已过时）与可选演进（portable plugin.json、官方市场收录）。

## 二、官方要求速览（事实来源）

### Claude Code（来源：code.claude.com/docs/en/plugin-marketplaces）

| 要点 | 要求 |
|------|------|
| 清单位置 | 仓库根 `.claude-plugin/marketplace.json`，路径相对市场根解析 |
| 市场级必需字段 | `name`（kebab-case，避开 npm/github/gh/claude-code-marketplace 等保留名）、`owner`（必含 `name`，可选 `email`/`url`）、`plugins[]` |
| 插件条目必需 | `name`、`source`（相对路径必须 `./` 开头，不允许 `../`） |
| 条目可选字段 | `displayName`/`description`/`author`/`category`/`keywords`/`tags`/`strict`/`homepage`/`license` 等；**不建议写 `version`**（Claude 总以插件内 `plugin.json` 的值为准，双写易漂移且不告警） |
| strict 模式 | 默认 `true`：组件以插件内 `plugin.json` 为权威，条目只补充合并 |
| 校验工具 | `claude plugin validate .`（或会话内 `/plugin validate .`） |
| 安装 | `/plugin marketplace add <git-url>` → `/plugin install specpowers@specpowers-marketplace` |

### Codex / ChatGPT（来源：developers.openai.com/plugins/build/plugins）

| 要点 | 要求 |
|------|------|
| 清单位置 | 仓库根 `.agents/plugins/marketplace.json`（repo 级）；也会读 legacy 兼容的 `.claude-plugin/marketplace.json` |
| 市场顶层字段 | `name`、`interface.displayName`（ChatGPT 桌面端市场标题）、`plugins[]` |
| 插件条目 | `name`、`source`（本地条目可用纯字符串 `"./plugins/xxx"` 或 `{source:"local", path:"./..."}`）、**必带 `policy.installation` + `policy.authentication` + `category`** |
| source 解析 | `source.path` 相对**市场根**（不是相对 `.agents/plugins/`），`./` 开头，不得逃出根 |
| CLI 命令 | `codex plugin marketplace add owner/repo`（支持 GitHub 简写、git URL、本地路径；`--ref` 可 pin） |
| 安装位置 | `~/.codex/plugins/cache/$MARKETPLACE/$PLUGIN/$VERSION/`，启停在 `~/.codex/config.toml` |
| 插件清单 | 新推荐 portable 布局：插件根 `plugin.json`（`$schema: agent-plugins.org/schemas/1.0.0/plugin.schema.json`），`skills/` 自动发现；OpenAI 专属配置放 `extensions.com.openai`。现有 `.codex-plugin/plugin.json` 仍作为兼容回退受支持 |
| hooks | **Codex 已支持插件 hooks**（与 Claude 同一事件 schema；默认发现 `hooks/hooks.json`；hook 命令收 `PLUGIN_ROOT`/`PLUGIN_DATA`，且**兼容 `CLAUDE_PLUGIN_ROOT`/`CLAUDE_PLUGIN_DATA`**；需用户信任审核后才执行，未信任自动跳过） |
| 公开发布 | 通过 plugin submission portal 提交，收录进 ChatGPT + Codex 共享的 universal directory |

## 三、差距清单

| # | 差距 | 后果 | 优先级 |
|---|------|------|--------|
| G1 | 缺 `.claude-plugin/marketplace.json` | Claude 市场添加失败，README 安装命令失实 | **P0** |
| G2 | 缺 `.agents/plugins/marketplace.json` | Codex 市场添加失败，README 安装命令失实 | **P0** |
| G3 | Claude 市场清单必需的 `owner` 未准备 | 新清单必须补齐 | P0（随 G1） |
| G4 | `.codex-plugin/plugin.json` 写死「Codex 暂不支持 hooks」，未注册 hooks | Codex 端缺 SessionStart 依赖自动检测（官方现已支持且兼容 `${CLAUDE_PLUGIN_ROOT}`） | P1 |
| G5 | 无 `claude plugin validate` / Codex 本地冒烟的校验闭环 | 清单错误只能靠用户反馈发现 | P1 |
| G6 | 清单一致性测试只锁 6 份清单 | 新增 2 份市场清单后测试需同步，防版本漂移 | P1 |
| G7 | 无 portable 根 `plugin.json`（仅 `.codex-plugin/` 兼容布局） | 非阻断（官方仍支持），属推荐演进方向 | P2 |
| G8 | 市场条目 `version` 双写（现 2 份市场清单均写） | Claude 官方明确建议避免；新清单单源化 | P2 |

## 四、改动方案

### P0：让两家安装命令真正可用

**1. 新增 `.claude-plugin/marketplace.json`（仓库根，Claude 标准格式）**

```json
{
  "name": "specpowers-marketplace",
  "owner": {
    "name": "SpecPowers Team",
    "url": "https://github.com/john-weiwei/SpecPowers"
  },
  "description": "SpecPowers — spec 驱动开发桥接编排插件市场",
  "plugins": [
    {
      "name": "specpowers",
      "source": "./plugins/specpowers",
      "description": "在 OpenSpec + superpowers 之上叠加结构一致性门禁与实时卡转人工的五阶段流水线编排插件（init→explore→propose→apply→archive），含无人值守 auto 模式。",
      "author": { "name": "SpecPowers Team" },
      "category": "developer-tools",
      "keywords": ["spec-driven", "pipeline", "openspec", "structure-gate", "superpowers"],
      "strict": true
    }
  ]
}
```

要点：**不写 `version`**（以插件内 `plugin.json` 为准）；**不放 Codex 专属 `policy` 字段**（避免 Claude 校验未知字段的风险）。

**2. 新增 `.agents/plugins/marketplace.json`（仓库根，Codex 标准格式）**

```json
{
  "name": "specpowers-marketplace",
  "interface": {
    "displayName": "SpecPowers"
  },
  "plugins": [
    {
      "name": "specpowers",
      "source": {
        "source": "local",
        "path": "./plugins/specpowers"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Developer Tools"
    }
  ]
}
```

要点：`source.path` 相对市场根解析（不是相对 `.agents/plugins/`）；`policy`/`category` 为官方必带字段；无 MCP/auth 需求，`authentication: "ON_INSTALL"` 取默认即可。

**3. README 安装命令校正**

```bash
# Claude Code
/plugin marketplace add https://github.com/john-weiwei/SpecPowers
/plugin install specpowers@specpowers-marketplace

# Codex CLI（GitHub 简写）
codex plugin marketplace add john-weiwei/SpecPowers
# 安装后在插件面板 / config.toml 启用；升级用 codex plugin marketplace upgrade
```

注意：**不要建议 `--sparse .agents/plugins`**——稀疏克隆会丢掉 `plugins/` 插件目录，导致条目解析失败。

**4. 清单一致性测试同步（`tests/test_manifest_consistency.py`）**

- 市场清单列表从 2 份扩到 4 份（根 `marketplace.json`、`.claude-plugin/marketplace.json`、`.agents/plugins/marketplace.json`、`.codebuddy-plugin/marketplace.json`）
- 新增断言：Claude 清单必须带 `owner`；Codex 清单条目必须带 `policy.installation`/`policy.authentication`/`category`
- 版本一致性策略调整：新市场清单**不写 version**，断言改为「写了就必须与 `plugin.json` 一致」（兼容 ZCode/WorkBuddy 旧约定）

### P1：能力补齐 + 校验闭环

**5. `.codex-plugin/plugin.json` 启用 hooks 依赖检测**

- 修正 `_detect` 说明文字（「Codex 暂不支持 hooks」已过时）
- 增加 `"hooks": "./hooks/hooks.json"`（legacy 布局显式声明；现有 hooks.json 用 `${CLAUDE_PLUGIN_ROOT}`，Codex 官方兼容该变量）
- 行为兜底：插件 hooks 需用户信任审核，未信任时 Codex 静默跳过——注册本身无副作用
- 实测项：SessionStart matcher `startup|clear|compact` 与 Codex 事件 schema 兼容性；Windows 下 `.cmd` hook 命令执行

**6. 校验闭环**

- 本地：在仓库根跑 `claude plugin validate .`；Codex 侧 `codex plugin marketplace add <仓库本地路径>` + `codex plugin marketplace list` 冒烟
- 可选：CI 增加「清单 JSON 结构 + 一致性」pytest（已有测试基础，扩用例即可；外部 CLI 校验不强依赖）

**7. 版本与文档**

- 实施时版本升级 v2.2.0（8 份清单 + pyproject + `__version__` + SKILL.md + README 徽章同步，沿用现有流程）
- README「支持平台」表、项目结构图补两份新市场清单

### P2：可选演进（非阻断）

**8. portable 根 `plugin.json`（Agent Plugins 跨生态标准）**

在 `plugins/specpowers/` 根新增 `plugin.json`（`$schema: https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`），OpenAI 专属配置（`interface`/`hooks`）放 `extensions.com.openai`；`.codex-plugin/plugin.json` 保留为兼容回退。收益：`skills/` 与 `hooks/hooks.json` 自动发现、贴合 agent-plugins.org 开放标准；注意 inline `extensions.com.openai` 存在时**整体取代** `.codex-plugin` overlay（不合并）。

**9. 官方市场收录**

- Claude：向 `anthropics/claude-plugins-official` 提交收录（获得官方分发曝光）
- Codex：通过 plugin submission portal 提交，收录进 ChatGPT + Codex 共享 universal directory（需准备 interface 展示元数据：displayName/shortDescription/category/brandColor/图标）

**10. （低优先）commands 包装为 skills 供 Codex 显式触发**

Codex 不支持自定义 slash 命令（组件仅 skills/MCP/hooks/apps）。如需 Codex 用户显式调用 9 个命令的等价物，可将其包装为轻量 skills；主 SKILL.md 已承载编排入口，边际价值中等，暂缓。

## 五、风险与注意事项

| 事项 | 说明 |
|------|------|
| 市场名保留字 | `specpowers-marketplace` 不在 Claude 保留名列表（npm/github/gh/claude-code-marketplace 等），可用 |
| 双清单内容漂移 | 4 份市场清单高度重复，靠扩展后的一致性测试锁定 name/description/category 关键字段 |
| version 单源化 | 新市场清单不写 version；Claude 明确总用插件内 plugin.json 的值 |
| `--sparse` 陷阱 | sparse 只含 `.agents/plugins` 会丢 `plugins/` 目录，不要使用或需 repeat 两个 sparse 路径 |
| Codex hooks 信任机制 | 未信任自动跳过，注册无副作用；Windows `.cmd` 执行需实测后再写进文档承诺 |
| 现有平台零回归 | 根 `marketplace.json`（ZCode）与 `.codebuddy-plugin/`（WorkBuddy）不动；新增文件对现有四家宿主无影响 |

## 六、实施顺序建议

1. P0 四项一次提交（两份新清单 + README + 测试扩展），跑全量 pytest
2. P1 hooks 启用单独提交（便于出问题时回退），实测 Codex trust 流程后更新 README 依赖检测说明
3. P2 按需排期（官方收录建议在 GitHub 开源仓库稳定、README/英文描述就绪后进行）
