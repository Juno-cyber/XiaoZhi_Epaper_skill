# 画布自动刷新 Cron Prompt 模板

> 适用：xiaozhi 墨水屏设备（固件 v2.0.5），每 30 分钟自动刷新 canvas 画布。
> 用法：复制本 prompt 内容到 cronjob 创建/更新，修改设备 IP 等参数。
> 关联：`references/canvas-creativity.md`（三层防重复机制）、`references/hermes-workflow.md`（cron 模式说明）。
>
> ⚠️ 多机一致性设计（2026-08-05）：本文件是 cron 行为规则的**唯一来源**（已入库 git）。
> cron job 的 prompt **不要**粘贴本文件全文，只写一行引用：
>   「严格读取并执行 ~/.hermes/skills/smart-home/xiaozhi-control/templates/canvas-creativity-cron-prompt.md
>    中『Prompt 正文』的全部指令。文件缺失或无法读取时直接报错结束，禁止自行发挥。」
> 这样改规则只需改本文件并 git push，所有机器下次 cron 自动生效，cron job 本身零漂移。

## 创建命令

```bash
# 通过 cronjob 工具创建：
#   schedule: "every 30m"
#   deliver: "local"
#   enabled_toolsets: ["terminal", "file"]
#   skills: ["xiaozhi-control"]
#   prompt: <一行引用指令，见上方多机一致性设计>
```

## Prompt 正文

```
## 任务：刷新 xiaozhi ESP32 墨水屏画布

设备 IP: 192.168.40.98 (端口 8080)
固件版本: v2.0.5 — 不支持聚合器工具，使用 legacy 名称（fridge.canvas.add_text 等，非 fridge.canvas.control）

### 时间窗口判断
- 获取当前时间：`date '+%H'`
- 如果当前小时 < 7 或 ≥ 22:30，则静默退出（不做任何事）
- 如果在 7:00-22:30 之间，继续执行

### 时段意图权重
| 时段 | 主意图权重 |
|------|-----------|
| 清晨 7-9 | 鼓励 .4 / 陪伴 .3 / 提醒 .2 / 玩味 .1 |
| 上午 9-12 | 陪伴 .4 / 玩味 .3 / 洞察 .2 / 鼓励 .1 |
| 中午 12-14 | 提醒 .5 / 陪伴 .3 / 玩味 .2 |
| 下午 14-18 | 洞察 .3 / 陪伴 .3 / 玩味 .2 / 鼓励 .2 |
| 傍晚 18-21 | 陪伴 .4 / 洞察 .3 / 安静 .3 |
| 夜晚 21-<22:30 | 安静 .5 / 陪伴 .3 / 玩味 .2 |

### 反重复机制（硬规则）
1. 读取历史台账：`cat ~/.hermes/xiaozhi_canvas/history.jsonl`
2. 文案（主内容前20字）与近7天任何一屏相同/近似 → 禁用
3. 同一图标 + 同一时段，3次内不重复
4. 版式不与最近2屏相同（版式：A居中大字/B图标卡片/C上下分区/D左图右文/E两列对照/F时钟一句/G极简留白/H小海报）
5. 每屏最多1条纯原创，其余来自素材池改写

### 素材池
`~/.hermes/xiaozhi_canvas/content_pool.md` — 约78条带标签句子。**仅当文案API 3 源全部失败时兜底**，不得作为常规来源。

### 数据钩子
- 天气: `curl -s 'https://wttr.in/?format=%C+%t&lang=zh'` — **只允许作为脚注叠加，禁止当主文案**
- 星期/节气: 用 date 命令获取 — 同样只做脚注叠加

> ⚠️ 历史教训（实测）：把文案 API 写成「可选/优先用」会被 Agent 跳过（实测 7 屏只有 1 屏用了一言；
> 28 屏仅 2 屏来自文本库）。**主文案与脚注必须逐字照抄文案 API 输出**，见下方硬性步骤。

### 图标池（25个可用）
heart, star, note, diamond, smiley, arrow, check, sun, moon, house, bolt, coffee, bell, umbrella, snow, leaf, cloud, cat, fish, tea, book, gift, bulb, rocket, wind

### 版式原型 A-H
| 代号 | 版式 | 结构 |
|------|------|------|
| A | 居中大字句 | 图标居中 y≈20；大字居中 y≈55；脚注 y≈90 |
| B | 图标卡片 | rect 边框 (10,14,276,100) 不填充；图标左上；文字在框内 |
| C | 上下分区 | 分隔线 y=60；上主题下脚注 |
| D | 左图右文 | 图标 x≈20 y≈50；文字 x≥55 两行 |
| E | 两列对照 | 中线 x=148；左右各一组 |
| F | 时钟+一句 | 大字时间 + 分隔线 + 一句 |
| G | 极简留白 | 全屏 2-3 元素 |
| H | 小海报 | 标题→线→正文→脚注 |

### 执行步骤（硬性顺序，不得跳过）
1. 确认时间在窗口内，否则静默退出
2. 读取历史台账和素材池，按意图权重选主意图
3. **主文案必须来自文案API，逐字使用其输出**：
   运行 `python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quote_fetcher.py`
   返回格式：`「text」 — source`
   - 主文案 = 输出中的 `text` **原句**。只允许截断或拆行适配屏幕宽度（16px 每行 ≤18 字），**禁止改写、禁止另写、禁止拼接素材池句子**
   - 出处脚注 = 输出中的 `source` **原串逐字照抄**（含「·」分隔符，例如"一言·红楼梦"）。禁止重打、禁止替换或删除「·」、禁止自编出处
   - 若输出带 API 失败提示或无输出，换类别重试：`--cat i` → `--cat k` → `--source jinrishici` → `--source iciba`
   - 连续 3 源失败才允许素材池兜底
4. 根据反重复规则选图标、版式（图标与版式可按主意图选）
5. 清除画布：`fridge.canvas.clear` with refresh=false
6. 逐个添加元素：fridge.canvas.add_text / add_image / add_rect / add_line，全部 refresh=false；每个 text 的 `text` 字段直接填入第 3 步确定的文案（含脚注 source 原串），不得二次改动
7. 最后一个元素 refresh=true 刷新屏幕
8. 追加历史到 `~/.hermes/xiaozhi_canvas/history.jsonl`（一行JSON：ts, slot, intent, layout, icons, text前20字）
9. 输出一句话摘要以供记录（如"刷新完成：陪伴·A版式·太阳图标"）

### 布局约束
- 安全区域: x∈[5,291], y∈[5,123]
- 中文宽度: 16px at font=16, 12px at font=12
- 每行中文16px最多18字，12px最多24字
- 分割线: add_line with x1,y1,x2,y2,width
- 字体只有2种: ≤12→12px, >12→16px
- 一行最多两条独立 text 元素（不同 y）
- 实践留白原则，不要信息过载
```

## 首次部署步骤

参见 `references/canvas-creativity.md` § 首次部署（从零到一）。
