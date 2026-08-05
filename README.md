# XiaoZhi E-Paper Skill

> 一个让 AI Agent 通过局域网 HTTP 控制 ESP32 电子墨水屏的技能包。
> 支持页面管理、画布绘制、动态元素、自定义页面持久化，以及 Web 控制台。

## 这是什么

这个仓库是一个 **Agent Skill** — 一套让 AI 助手（如 Hermes Agent 或其他支持 MCP/工具调用的 Agent）控制小智 ESP32 设备电子墨水屏的知识包。

它包含：
- **SKILL.md** — Agent 可读的技能定义（触发条件、API 参考、工作流）
- **references/** — 详细的参考文档（API、固件、Web、模板、设计哲学、坑清单）
- **scripts/** — 可直接运行的 Python 工具脚本
- **templates/** — 即用型页面布局模板

## 部署到 Hermes

仓库是唯一事实源（有 Git 历史与协作），Hermes 运行的是部署副本。修改后一键部署：

```bash
bash deploy.sh          # 部署到 ~/.hermes/skills/smart-home/xiaozhi-control/
bash deploy.sh --push   # 部署 + git commit + push
```

> 注意：`deploy.sh` 的方向是 **仓库 → Hermes**（旧 `sync.sh` 已删除）。只改仓库，不要直接改 Hermes 目录——否则下次部署会被覆盖。

## 多机一致性（Multi-Machine Sync）

要让多台机器上的 skill **和它的 cron 行为**完全一致，遵循"单一来源 + 引用"架构：

1. **skill 文件**：仓库是唯一事实源。每台机器执行：
   ```bash
   git clone https://github.com/Juno-cyber/XiaoZhi_Epaper_skill.git
   cd XiaoZhi_Epaper_skill && bash deploy.sh
   # 以后更新：git pull && bash deploy.sh
   ```
2. **cron 规则**：`templates/canvas-creativity-cron-prompt.md` 是 cron 行为规则的唯一来源（已入库）。
   cron job 的 prompt **不要**粘贴全文，只写一行引用指令：
   > 严格读取并执行 ~/.hermes/skills/smart-home/xiaozhi-control/templates/canvas-creativity-cron-prompt.md 中『Prompt 正文』的全部指令（含时间窗口判断、时段意图权重、反重复硬规则、文案API逐字照抄硬性步骤、legacy 推送与布局约束）。该模板文件是规则的唯一来源，随 skill 仓库 git 同步；若文件缺失或无法读取，直接报错结束，不要自行发挥或凭记忆执行。
   
   创建 cron job 参数：`schedule: "every 30m"`、`deliver: "local"`、`enabled_toolsets: ["terminal","file"]`、`skills: ["xiaozhi-control"]`。
3. **改规则** = 改模板文件 + `git push` → 各机器 `git pull && bash deploy.sh` → 下次 cron 自动生效。
   各机器的 cron job 配置零漂移（prompt 永远是那一行引用），不会再出现"某台机器还是旧措辞"。

> ⚠️ 本机历史遗留：旧版 cron job 把规则全文内嵌在 prompt 里（无引用），会导致机器间不一致。
> 已按上述设计更新为引用模式。若其他机器上有旧式内嵌 prompt，请同样改为引用。

## 设备要求

- ESP32-S3 开发板，运行 [xiaozhi-esp32](https://github.com/78/xiaozhi-esp32) 固件
- 启用 LocalControl（HTTP 服务器，端口 8080 + mDNS）
- 带电子墨水屏（默认 296×128 像素）
- 与控制端在同一局域网

## 快速开始

### 1. 发现设备

```bash
python3 scripts/xiaozhi_discovery.py --health --save
```

### 2. 健康检查

```bash
curl http://<IP>:8080/
# → {"status":"ok","board":"...","version":"..."}
```

### 3. 调用 MCP 工具

```bash
# 切换到画布页面
curl -X POST http://<IP>:8080/api/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"fridge.pagemanager","args":{"target_page":6}}'

# 在画布上添加文字（聚合工具 + action 分发）
curl -X POST http://<IP>:8080/api/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"fridge.canvas.control","args":{"action":"add_text","id":"hello","text":"Hello!","x":10,"y":10,"font_size":16,"align":"left","refresh":true}}'
```

### 4. 使用布局 DSL 一键部署

```bash
python3 scripts/quick_page_builder.py <IP> 6 - << 'EOF'
clear
text id=title text="今日待办" x=8 y=2 font_size=12 align=left
line id=sep x1=0 y1=18 x2=296 y2=18 width=1
text id=item1 text="写论文" x=20 y=24 font_size=12
text id=item2 text="训模型" x=20 y=42 font_size=12
text id=item3 text="做饭" x=20 y=60 font_size=12
refresh
EOF
```
元素默认 `refresh=false` 批量添加，最后一行 `refresh` 统一刷新。

## 功能概览

| 功能 | 说明 |
|------|------|
| 设备发现 | mDNS / 缓存 IP / 端口扫描，自动发现局域网内设备 |
| 页面切换 | 6 个内置页面 + 最多 9 个自定义页面 (7-15) |
| 画布绘制 | 文字、线条、矩形、图片，支持 LittleFS 持久化 |
| 自定义页面 | 创建/删除/重命名，元素持久化到 Flash，重启不丢失 |
| 动态元素 | 设备端时钟/温度/内存（无需 Agent）+ Agent 推送（天气/股价等）|
| 像素画 | 13 种内置 24×24 像素画素材，自动生成并上传 |
| Web 控制台 | 浏览器端管理界面，支持手绘、拖拽、预览 |
| 屏幕设计哲学 | 10 条原则 + 5 个刷新前问题，让屏幕成为 Agent 的"生活画布" |

## 文档索引

| 文档 | 内容 |
|------|------|
| [SKILL.md](SKILL.md) | Agent 技能定义 — 触发条件、API 参考、工作流 |
| [references/api-reference.md](references/api-reference.md) | HTTP API + MCP 工具完整参考 |
| [references/pitfalls.md](references/pitfalls.md) | 52 条实战踩坑清单 |
| [references/custom-pages.md](references/custom-pages.md) | 自定义页面架构、动态元素、持久化 |
| [references/page-templates.md](references/page-templates.md) | 7 种即用型页面布局模板 |
| [references/firmware-development.md](references/firmware-development.md) | 固件编译、烧录、调试、源码结构 |
| [references/web-console.md](references/web-console.md) | Web 控制台搭建、CORS 配置、前端 API |
| [references/canvas-web-interaction.md](references/canvas-web-interaction.md) | 画布交互模式：统一事件、离屏画笔、拖拽 |
| [references/display-philosophy.md](references/display-philosophy.md) | 屏幕设计哲学：10 原则 + 5 问题 |
| [references/hermes-workflow.md](references/hermes-workflow.md) | Hermes 工作流：Web 设计委托、cron 数据推送 |

## 屏幕设计哲学

这个 Skill 不仅仅是一个技术工具。它包含一套设计哲学——把电子墨水屏当作 AI Agent 在现实世界的"生活画布"，而非简单的信息显示器。

> 你的目标不是"把屏幕填满"，而是"让朋友觉得这一眼值得看"。

详见 [references/display-philosophy.md](references/display-philosophy.md)。

## 技术栈

- **设备端**: ESP32-S3, ESP-IDF v5.4, xiaozhi-esp32 固件
- **通信**: HTTP (局域网), MCP (Model Context Protocol)
- **存储**: LittleFS (2MB 分区, 存储图片和页面布局)
- **屏幕**: 296×128 电子墨水屏 (GxEPD2)
- **控制端**: Python 3, curl, 任何支持 HTTP 的 Agent

## License

MIT
