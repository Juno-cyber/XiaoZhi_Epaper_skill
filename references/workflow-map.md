# Workflow Map —— 定时任务 × 屏幕 总览图

> 回答一个问题：**用户用这个 skill 建了哪些定时任务（cron），它们又怎样改变了墨水屏的显示。**
> 用一张图（SVG）概括，随数据自动更新。生成器：`scripts/workflow_map.py`（纯标准库，无第三方依赖）。

## 目标

skill 现在的定时能力是「建 cron →（Agent 或 shell 脚本）取数据 → 推一屏/更新元素」。时间一长，会有很多 cron 任务和页面，人工很难一眼看清「谁在改哪块屏、改得对不对」。本图把三处事实合成一张总览：

1. 有哪些 cron 任务、每个的调度/状态/上次下次运行。
2. 每个写屏任务在一天 24 小时里什么时候触发。
3. 设备当前每页是什么、元素摆在哪、哪些是动态元素、由哪个任务驱动（同色）。

它同时天然暴露「漂移」：比如某 cron 还在每日更新页 7 的排班，但页 7 现在其实变成了待办清单——一图就能看到任务自称的目标与屏幕实际内容对不上。

## 数据来源（均已实测）

| 来源 | 路径 / 端点 | 提供什么 |
|---|---|---|
| cron 注册表 | `~/.hermes/cron/jobs.json` | 每个 job：`id/name/prompt\|script/no_agent/schedule{expr,display}/enabled/last_status/next_run_at/last_run_at/deliver/skills` |
| 画布历史台账 | `~/.hermes/xiaozhi_canvas/history.jsonl` | 每 30 分钟一屏：`{ts, slot, intent, layout, icons[], text}` |
| 文案审计（可选） | `~/.hermes/xiaozhi_canvas/quote_log.jsonl` | 每次 quote_fetcher 调用的 `{ts, source, category, text前40}` |
| 设备页面/元素 | `GET http://<IP>:8080/` + `/api/call`（`fridge.page.control action=list`、`fridge.page.element.control action=list`、`fridge.canvas.control action=list`） | 页列表 + 每页元素（坐标/字体/dtype 动态标记/图片名） |
| 任务执行产出（可选） | `~/.hermes/cron/output/<job_id>/<ts>.md` | 每次运行的 Agent 摘要 |

## 一张图的结构（4 区 + 图例）

1. **头部** —— 设备名/IP/固件版本、生成时间、汇总 chips（cron 总数 / 写屏任务数 / 页面数 / 最近刷新时间）。
2. **① 定时任务面板** —— 每个 cron 一行：调度表达式（+ 人性化）、状态（ok/error/skipped/disabled）、上次/下次运行、写屏目标（page N，按 prompt 里的 `页N`/`page N` 启发式识别）、执行方式（Agent 模型 / shell 脚本）。
3. **② 24 小时触发视图** —— 横轴 0–24 点，写屏任务用同色圆点标出每次触发时点；画布任务的活动窗口（7:00–22:30）用淡色底标出。
4. **③ 当前屏幕面板** —— 设备每页画成 296×128 缩略图（元素按真实坐标、字体、对齐摆放；`dtype` 动态元素高亮并标 ⚡），页名横幅用「驱动它的任务」的颜色。
5. **④ 最近画布刷新** —— 历史台账最近 16 屏（时间/意图/版式/文案前 15 字），一眼看出每 30 分钟刷一屏的节奏。
6. **图例** —— 颜色 = 写屏任务，标注 job id → 目标页。

## 呈现方式（推荐与取舍）

| 方式 | 依赖 | 中文渲染 | 可移植 | 适用 |
|---|---|---|---|---|
| **纯 Python 生成 SVG**（默认） | 无（标准库） | 浏览器系统 CJK 字体 | ✅ 跨平台 | 首选「一张图」：可提交、可浏览器打开、可贴进聊天/文档 |
| **Pillow 生成 PNG** | Pillow + 可用的 CJK 字体 | 可接近固件字号与布局 | 依赖本机字体 | 需要逐页 296×128 位图预览时 |
| Mermaid（markdown） | 无（渲染器在 GitHub/编辑器） | 中英均可 | ✅ | 静态拓扑图，贴 README；不是「数据驱动的一张图」 |
| HTML 仪表盘 | 无（浏览器） | ✅ | ✅ | 交互版（hover 高亮、点页看详情），可作第二阶段增强 |

**推荐**：SVG-first（本 skill 零依赖、跨平台）。SVG 在任何浏览器即可看；若要 PNG，可用 Pillow、`chromium --headless --screenshot` 或 `rsvg-convert` 转换。

## 用法

```bash
cd ~/.hermes/skills/smart-home/xiaozhi-control
python3 scripts/workflow_map.py \
    --ip 192.168.1.10 \
    --jobs ~/.hermes/cron/jobs.json \
    --history ~/.hermes/xiaozhi_canvas/history.jsonl \
    --out workflow_map.svg
# → workflow_map.svg，浏览器打开即可
```

- `--ip` 缺省则不连设备（只画 cron + 历史，不画页面缩略图）。
- 提交样例见 `templates/workflow-map.example.svg`（真实数据快照，2026-09-01）。
- 若要转 PNG：`chromium --headless --screenshot=workflow_map.png workflow_map.svg`（或使用 `rsvg-convert`）。

## 已知数据坑（本图会暴露，但请勿擅自改运行时状态）

1. **cron 内嵌旧 prompt 未随 skill 更新**：`jobs.json` 里画布任务（`2170a15386cd`）仍内嵌「固件 v2.0.5 只支持旧工具名 + `·` 分隔符」的旧 prompt，与 skill 现行的「引用模式 + ASCII `-` 分隔」不同。改法是让该 job 只留一行引用 `templates/canvas-creativity-cron-prompt.md`（见 skill README「多机一致性」），**不要**动手改 `jobs.json` 里的运行中 prompt——留待用户确认。
2. **排班任务目标页漂移**：`580778dcba43`（每日 06:30）自称更新「页 7 排班月历」，但设备页 7 当前是「待办事项」；排班位图未在页 7 元素里出现。这正是本图要暴露的「任务意图 ≠ 屏幕实际」。
3. 场景识别是启发式的（根据 prompt 里的 `页N`/`page N`/`画布`/`canvas`），自定义 cron 若用其他措辞可能识别不到——可把目标页写进 job 名（如「… · page 7」）以提高准确度。

## 路线图

- 阶段 1（本实现）：静态 SVG 总览（cron + 24h 触发 + 屏幕 + 历史 + 图例）。
- 阶段 2：HTML 交互版——hover 高亮任务→页面→元素链路、点页展开元素详情、时间轴可缩放。
- 阶段 3：接入 `executions.db`/`quote_log.jsonl` 做「内容多样性」「时段意图分布」分析小面板。
