# Custom Page Layout Templates

Ready-made page designs for common use cases. Each template specifies elements
as MCP `fridge.page.element.add` calls with exact coordinates.

Screen: 296×128 pixels. Safe area: x∈[5,291], y∈[5,123].

## Template Index

| # | Page Name | Dynamic (device) | Dynamic (Hermes) | Static |
|---|-----------|------------------|-------------------|--------|
| 1 | Clock + Weather | `clock`, `date` | weather text | title, frame |
| 2 | Daily Quote | — | quote text | title, separator |
| 3 | Pixel Art | — | — | bitmap image |
| 4 | CPU Dashboard | `cpu_temp`, `heap`, `uptime` | — | labels, frame |
| 5 | Holiday Countdown | — | days remaining | title, frame |
| 6 | Today's Focus | — | focus text | title, frame |
| 7 | Todo List (compact) | — | item text | title, checkboxes |

## 1. Clock + Weather Page

```
 y=0  ┌──────────────────────────────────────────┐
 y=4  │           14:31                          │  clock (dynamic_type, font=16, center, x=148,y=4)
 y=22 │         2026-07-09 周三                  │  date (dynamic_type, font=12, center, x=148,y=22)
 y=40 ══════════════════════════════════════════════  separator line (x:10→286, y=40)
 y=48 │  ☀ 晴 28°C                              │  weather (Agent-pushed, font=12, x=20,y=48)
 y=68 │  湿度 45% · 风 3级                       │  weather detail (Agent-pushed, font=12, x=20,y=68)
 y=90 │  更新于 14:30                            │  weather update time (Agent-pushed, font=12, x=20,y=90)
 y=128└──────────────────────────────────────────┘
```

Elements:
- `clock`: text, dynamic_type="clock", x=148, y=4, font_size=16, align=center
- `date`: text, dynamic_type="date", x=148, y=22, font_size=12, align=center
- `sep`: line, x1=10, y1=40, x2=286, y2=40, width=1
- `weather_main`: text, x=20, y=48, font_size=12 (Agent cron pushes "☀ 晴 28°C")
- `weather_detail`: text, x=20, y=68, font_size=12 (Agent cron pushes "湿度 45%")
- `weather_time`: text, x=20, y=90, font_size=12 (Agent cron pushes "更新于 14:30")

## 2. Daily Quote + Random Knowledge Page

```
 y=0  ┌──────────────────────────────────────────┐
 y=2  │ 每日一句                                 │  title (font=12, x=8, y=2)
 y=18 ══════════════════════════════════════════════  separator
 y=26 │ 不积跬步，无以至千里。                   │  quote (font=12, x=10, y=26, max_width=276)
 y=44 │                          —— 荀子《劝学》  │  author (font=12, x=200, y=44, align=right)
 y=64 ══════════════════════════════════════════════  separator
 y=72 │ 💡 知识：蜂鸟是唯一能倒退飞行的鸟       │  knowledge (font=12, x=10, y=72)
 y=90 │                                          │
 y=110│ 说"换一句"刷新                           │  hint (font=12, x=8, y=110)
 y=128└──────────────────────────────────────────┘
```

All text elements are Agent-pushed (cron every 6h or on voice command).

## 3. Pixel Art / Fun Image Page

```
 y=0  ┌──────────────────────────────────────────┐
      │                                          │
      │         [128×96 pixel art bitmap]        │  image (x=84, y=16, w=128, h=96)
      │                                          │
      │                                          │
 y=128└──────────────────────────────────────────┘
```

Single image element. Upload 1-bpp bitmap via `POST /api/canvas_image?name=pixel_art_1`,
then `element.add { type:"image", name:"pixel_art_1", x:84, y:16, w:128, h:96 }`.
Use `fridge.page.clear` + re-add to swap images.

## 4. CPU Dashboard Page

```
 y=0  ┌──────────────────────────────────────────┐
 y=2  │ CPU Dashboard                            │  title (font=12, x=8, y=2)
 y=18 ══════════════════════════════════════════════  separator
 y=26 │ Chip Temp:    52.3°C                     │  cpu_temp (dynamic_type, font=12, x=10, y=26)
 y=44 │ Free Heap:   Heap: 128KB                 │  heap (dynamic_type, font=12, x=10, y=44)
 y=62 │ Uptime:      Up: 1d 3h 42m               │  uptime (dynamic_type, font=12, x=10, y=62)
 y=80 │                                          │
 y=96 │ WiFi: <IP>                               │  ip (static, font=12, x=10, y=96)
 y=112│ Flash: 16MB · PSRAM: 8MB                 │  hw info (static, font=12, x=10, y=112)
 y=128└──────────────────────────────────────────┘
```

Device-side dynamic: `cpu_temp`, `heap`, `uptime` all use `dynamic_type`.
Static: IP and hardware info set once at page creation.

## 5. Holiday Countdown Page

```
 y=0  ┌──────────────────────────────────────────┐
 y=4  │ 距 下个假期                              │  title (font=12, center, x=148, y=4)
 y=24 │                                          │
 y=32 │         42                               │  days number (large text, font=16, center, x=148, y=32)
 y=52 │          天                              │  unit (font=12, center, x=148, y=52)
 y=72 │ 中秋节 09-29                             │  holiday name (Agent-pushed, font=12, center, x=148, y=72)
 y=90 ══════════════════════════════════════════════  separator
 y=100│ 下一个: 国庆节 10-01 (54天)              │  next holiday (Agent-pushed, font=12, x=10, y=100)
 y=128└──────────────────────────────────────────┘
```

Agent cron (daily) calculates days to next Chinese legal holiday and pushes text.

## 6. Today's Focus Page

```
 y=0  ┌──────────────────────────────────────────┐
 y=4  │ 🎯 今日 Focus                            │  title (font=16, center, x=148, y=4)
 y=28 ══════════════════════════════════════════════  separator
 y=40 │                                          │
 y=48 │     完成自定义页面验证                   │  focus text (font=16, center, x=148, y=48)
 y=72 │                                          │
 y=90 ══════════════════════════════════════════════  separator
 y=100│ 说"设置Focus..."修改                    │  hint (font=12, center, x=148, y=100)
 y=128└──────────────────────────────────────────┘
```

Simple single-focus page. Agent pushes focus text via voice command or daily cron.

## 7. Todo List Page (Compact 12px)

```
 y=0  ┌──────────────────────────────────────────┐
 y=2  │ 待办事项                                 │  title (font=12, x=8, y=2)
 y=18 ══════════════════════════════════════════════  separator
 y=22  ☐ 买菜                                   │  box1(6×6,x=6,y=24) + item1(font=12, x=16, y=22)
 y=36  ☐ 做饭                                   │  box2 + item2
 y=50  ☐ 写日记                                 │  box3 + item3
 y=64  ☐ ...                                    │  box4 + item4 (optional)
 y=112 说"提醒我..."添加待办                    │  hint (font=12, x=8, y=112)
 y=128└──────────────────────────────────────────┘
```

- Row spacing: 14px (12px font + 2px gap)
- Checkbox: 6×6 rect at x=6, text at x=16 (10px gap)
- Max ~5 rows before hitting hint at y=112
- Mark done: remove box, re-add with `filled: true`
- Item text: Agent-pushed via `element.update`

## Split-Screen Variant (Todo + Gold Price)

Add a vertical divider at x=185 and place gold price elements on the right:

```
 ┌────────────────────────────────┬───────────────┐
 │ 待办事项                       │ 黄金¥/g       │
 ════════════════════════════════╪═══════════════
 │  ☐ 买菜                        │  ¥892.6/g    │
 │  ☐ 做饭                        │  08:39更新   │
 │  ☐ 写日记                      │               │
 │  说"提醒我..."添加待办         │               │
 └────────────────────────────────┴───────────────┘
```

- `vsep`: line, x1=185, y1=2, x2=185, y2=108, width=1
- Right zone: x=192, width ~100px (~5 chars at 16px, ~7 at 12px)
- Gold price pushed by cron (`gold_price_update.sh`, every 60m)
