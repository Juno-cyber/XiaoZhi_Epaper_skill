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
**⚠️ 自 2026-08-04 起降级为兜底**：主文案 **90%+ 必须来自文本库 API**（quote_fetcher.py）。
素材池仅用于：① API 连续 3 源失败时兜底；② 与 API 句拼接做改写（主体仍是 API 句）。
附录含 8 种版式原型结构速查 + 2026 常用节气表（前后 1 天算）。

### 2b. 文本库 API（主文案来源，90%+ 强制）

`scripts/quote_fetcher.py` — 聚合 4 个免费无 key 文案 API，自动去重（14 天台账）+ 审计日志（`~/.hermes/xiaozhi_canvas/quote_log.jsonl`，每次调用留痕，可核对出处）：

| 源 | 命令 | 分类 |
|----|------|------|
| 一言 hitokoto | `--cat d` 文学 / `--cat i` 诗词 / `--cat k` 哲学 / 默认顺序 | 文学/诗词/哲学/动漫 |
| 今日诗词 jinrishici | `--source jinrishici` | 带季节标签 |
| 金山词霸每日一句 | `--source iciba` | 中英对照 |
| 素材池（兜底） | `--source pool` | 仅 API 全挂时 |

**规则**（cron prompt 强制执行）：
1. 主体文案必须来自 quote_fetcher 输出 `text` 原句（可截断/拆行适配屏幕），脚注**原样照抄** `source`（格式 `一言・出处` / `诗词・朝代 作者`，中间必有 `・`（U+30FB）中点分隔符——⚠️ 固件 u8g2 wqy gb2312 字库无 U+00B7（·）字形会静默丢弃，必须用 U+30FB ・）——禁止重拼来源、禁止去掉分隔符写成「一言红楼梦」式连写
2. 失败则换类别重试（`--cat i` → `--cat k` → `--source jinrishici` → `--source iciba`）
3. 连续 3 源失败才允许数据钩子/素材池
4. 禁止不调用 quote_fetcher 就自称"一言来源"；台账 text 必须带真实出处
5. 数据脚注各项之间也用 `·` 分隔（如「晴 31°C · 距立秋 2 天 · 冰箱空」）；上屏前逐字检查无连写

### 3. 数据层：真实世界钩子

| 钩子 | 命令 | 产出 |
|------|------|------|
| 文案 API | `quote_fetcher.py` | 一言(文学/诗词/哲学)、今日诗词、每日一句 — 自动去重 |
| 冰箱 | `fridge.stats.summary` | 件数/临期/品类 → 洞察文案 |
| 天气 | `curl -s 'https://wttr.in/?format=%C+%t&lang=zh'` | 带伞/加衣/听雨 |
| 时间 | `date` + 节气表 | 星期几/月初月末/节气 |

规则：**90%+ 主体文案来自文本库 API**（quote_fetcher.py，见 §2b）；数据钩子（冰箱/天气）只做脚注叠加；素材池仅 API 全挂时兜底。

## 视觉丰富度：禅绕画 (Zentangle)

24x24 图标之外的第二级视觉：**程序化生成角落装饰图案**（`scripts/zentangle_generator.py`）。
- 24 种图案模块；**方案A（2026-08-04 起）**：禅绕画只作**角落小区域点缀**（带 1px 边框的"画框"），图文分区，不再全屏背景
- 角落区域预设：右上(196,6,92,62) / 右下(196,66,92,56) / 左上(6,6,92,62) / 中上横幅(102,8,92,62)
- 生成命令：`zentangle_generator.py --upload <IP> --pattern <名字> --name zp --region 196,6,92,62 --seed $RANDOM`
- 适合角落：mandala paradox rose aster spiral concentric lissajous stipple printemps crescent waves flux betweed scale weave grid knightsbridge
- 适配时段：安静/夜晚/冥想场景；文字与禅绕区保持 8px+ 间距

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

## 手动单屏刷新（验证/演示用，与 cron 同机制）

需要当场刷一屏时（调试、演示、手动测试 skill 更新），按 cron 同款规则走一遍：

1. **取文案（90% 强制）**：`quote_fetcher.py` 必调，输出即主文案与脚注出处
2. **查台账去重**：`tail -10 ~/.hermes/xiaozhi_canvas/history.jsonl` → 文案不与近 7 天同；版式不与最近 2 屏同；图标同时段 3 次内不重复
3. **禅绕画角落（可选）**：`zentangle_generator.py --upload <IP> --pattern <名> --name zp --region <x,y,w,h> --seed $RANDOM`（角落区域见上方案A；与正文保持不重叠：正文/分隔线右端 < region.x）
4. **推送（固件 v2.0.5）**：clear → legacy `fridge.canvas.*` 批量 add 全部 `refresh=false` → 最后一条 `refresh=true`；逐条确认 `"status":"success"`，串行执行不并发
5. **台账**：quote_log 由 quote_fetcher 自动留痕；history.jsonl **测试屏可跳过**（不占用 cron 去重额度，避免测试文案污染后续自动屏）；正式屏必写

完整可复用布局（小海报+角落禅绕画）与推屏命令：`references/page-templates.md` §8。
