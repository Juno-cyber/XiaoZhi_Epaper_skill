# 画布自主创作：防重复机制 (Canvas Creativity System)

> 适用：cron 自动刷新画布（每 30 分钟，7:00-22:30）。本文档解释"如何让每屏不重样"的完整机制。
> 相关：`display-philosophy.md`（设计哲学）、`hermes-workflow.md`（cron 模式）。

## 问题根源

早期每 30 分钟一刷，但每次运行都是**全新会话**：
- 无记忆 → 不知道上一屏显示过什么 → 重复无法避免
- 时段→内容硬模板（早安/晚安/休息提醒…）→ 同一时段每天同款
- 图标池只有 13 个，模型只认太阳/月亮/咖啡 → 傍晚永远月亮
- 无数据钩子 → 只能写泛泛的心情文案

## 三层机制

### 1. 记忆层：历史台账 `~/.hermes/xiaozhi_canvas/history.jsonl`

每次成功刷新后追加一行 JSON（UTF-8，一行一条）：

```json
{"ts":"2026-08-04 08-00-12","slot":"morning","intent":"encourage","layout":"C","icons":["sun"],"text":"把今天过成自己喜欢的样子"}
```

字段：`ts`(YYYY-MM-DD HH-MM-SS)、`slot`(morning/forenoon/noon/afternoon/evening/night)、`intent`(encourage/company/remind/quiet/playful/insight)、`layout`(A-H)、`icons`(数组)、`text`(主文案前 20 字)。

**反重复硬规则**（cron prompt 内执行）：
1. 文案与近 7 天任何一屏相同/近似 → 禁用
2. 同一图标 + 同一时段，3 次内不重复
3. 版式原型（A-H）不与最近 2 屏相同
4. 每日清晨首屏换新（周一 ≠ 周二）
5. 每屏最多 1 条纯原创，其余来自素材池改写

### 2. 素材层：内容池 `~/.hermes/xiaozhi_canvas/content_pool.md`

约 80 条带标签句子（`鼓励/安静/陪伴/玩味/洞察/提醒/食物/时节/天气/自指`）。
Agent 按主意图挑 2-3 条 → 重组/改写/拼接 → 最多加 10 字原创。
附录含 8 种版式原型结构速查 + 2026 常用节气表（前后 1 天算）。

### 3. 数据层：真实世界钩子

| 钩子 | 命令 | 产出 |
|------|------|------|
| 冰箱 | `fridge.stats.summary` | 件数/临期/品类 → 洞察文案 |
| 天气 | `curl -s 'https://wttr.in/?format=%C+%t&lang=zh'` | 带伞/加衣/听雨 |
| 时间 | `date` + 节气表 | 星期几/月初月末/节气 |

规则：有数据变化 → 讲数据；没变化 → 素材池。

## 意图权重（代替固定内容模板）

| 时段 | 主意图权重 |
|------|-----------|
| 清晨 7-9 | 鼓励 .4 / 陪伴 .3 / 提醒 .2 / 玩味 .1 |
| 上午 9-12 | 陪伴 .4 / 玩味 .3 / 洞察 .2 / 鼓励 .1 |
| 中午 12-14 | 提醒 .5 / 陪伴 .3 / 玩味 .2 |
| 下午 14-18 | 洞察 .3 / 陪伴 .3 / 玩味 .2 / 鼓励 .2 |
| 傍晚 18-21 | 总结 .4 / 陪伴 .3 / 安静 .3 |
| 夜晚 21-23 | 安静 .5 / 陪伴 .3 / 玩味 .2 |

掷骰子选主意图，同一时段不同天应不同。

## 版式原型 A-H（不许连续 2 屏同款）

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

## 图标池（25 个）

`heart star note diamond smiley arrow check sun moon house bolt coffee bell umbrella snow leaf cloud cat fish tea book gift bulb rocket wind`
（v1.9 新增 12 个：umbrella/snow/leaf/cloud/cat/fish/tea/book/gift/bulb/rocket/wind，见 `scripts/pixel_art_generator.py`）
