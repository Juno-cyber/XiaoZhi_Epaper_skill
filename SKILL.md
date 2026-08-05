---
name: xiaozhi-control
description: "Discover and control xiaozhi ESP32 voice-AI devices on the LAN. Use when user wants to find, health-check, or call MCP tools (fridge management, e-paper page switch, canvas drawing, custom pages, recipes) on a xiaozhi-esp32 device over HTTP."
version: 1.9.0
author: Juno-cyber
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [xiaozhi, esp32, smart-home, iot, lan-control, mcp]
  hermes:
    tags: [xiaozhi, esp32, smart-home, iot, lan-control, mcp]
    related_skills: [openhue]
prerequisites:
  commands: [python3]
---

# xiaozhi LAN Control

Discover and control xiaozhi-esp32 devices on the local network via HTTP (port 8080).

> **Path note**: This skill runs from `~/.hermes/skills/smart-home/xiaozhi-control/` (Hermes install dir) or the repo root. Command examples below use the Hermes path — if running from the repo, replace it with the repo path (e.g. `scripts/quick_page_builder.py`).

## When to Use

- Find xiaozhi devices on LAN → `python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/xiaozhi_discovery.py`
- Call MCP tools (fridge, e-paper, canvas, custom pages, recipes)
- Health check, device scanner UI (`/ui`)

**Don't use for**:
- Flashing/building firmware → `references/firmware-development.md`
- Cloud/MQTT control (this skill is LAN-only)
- Web console UI dev / browser canvas interaction → `references/web-console.md`, `references/canvas-web-interaction.md`
- Custom page architecture & layout audits → `references/custom-pages.md`
- Page layout design philosophy & ready-made templates → `references/display-philosophy.md`, `references/page-templates.md`

## Quick Start

```bash
# 1. Discover (mDNS xiaozhi.local → cache → UDP → port scan, in priority order)
IP=$(python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/xiaozhi_discovery.py)

# 2. Health check
curl http://$IP:8080/

# 3. Call any tool (always use /api/call, never /mcp for curl)
curl -X POST http://$IP:8080/api/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"fridge.stats.summary","args":{}}'
```

Discovery variants: `--health` (discover + check), `--save` (cache to `~/.hermes/xiaozhi_ip.txt`), `-v` (verbose).
Prerequisite: device + host on same WiFi, LocalControl enabled (HTTP :8080 + mDNS `xiaozhi.local`).

## Quick Page Builder (preferred for ALL layouts)

Use `scripts/quick_page_builder.py` — one command deploys an entire canvas/page layout from a DSL file
or inline text. Always prefer this over hand-curling individual API calls.

```bash
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quick_page_builder.py <IP> 6 my_layout.layout

# Inline DSL:
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quick_page_builder.py <IP> 6 - << 'EOF'
clear
switch 6
text id=title text="标题" x=12 y=2 font_size=16
pixart id=img1 art=heart x=40 y=62 w=24 h=24
text id=lbl1 text="爱心" x=40 y=88 font_size=12
refresh
EOF
```

**DSL commands** (`#` = comment, `---` = separator):
| Command | Format |
|---------|--------|
| `clear` | Clear all elements |
| `switch N` | Switch to page N |
| `text` | `id=.. text=".." x=.. y=.. font_size=.. align=..` |
| `rect` | `id=.. x=.. y=.. w=.. h=.. filled=..` |
| `line` | `id=.. x1=.. y1=.. x2=.. y2=.. width=..` |
| `image` | `id=.. name=.. x=.. y=.. w=.. h=..` |
| `pixart` | `id=.. art=<name> x=.. y=.. w=24 h=24` (auto-generate + upload, cached) |
| `refresh` | Flush to screen (always last) |

**Pixel art** (25 built-in): heart, star, note, diamond, smiley, arrow, check, sun, moon, house, bolt, coffee, bell, umbrella, snow, leaf, cloud, cat, fish, tea, book, gift, bulb, rocket, wind.
```bash
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/pixel_art_generator.py --list        # list available
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/pixel_art_generator.py --upload <IP>  # upload all
```

**Zentangle (禅绕画) generator** — procedural full-screen 296x128 line art, infinite variety via seed:
```bash
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/zentangle_generator.py --list     # 24 patterns: waves concentric spiral grid vine honeycomb mandala meander ripple + classic tangle set (knightsbridge paradox printemps crescent flux mooka fescu betweed hollibaugh weave scale rose lissajous aster stipple)
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/zentangle_generator.py --preview  # render 9-sample PNG grid
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/zentangle_generator.py --upload <IP> --pattern mandala --name z1 --seed 42   # upload to LittleFS
# then: fridge.canvas.clear → fridge.canvas.add_image {id:"z1", name:"z1", x:0, y:0, w:296, h:128} → refresh
# Best-looking: mandala, vine, waves, meander, paradox, rose, printemps, stipple. Dense patterns (honeycomb/grid/knightsbridge) may ghost on e-paper.
```

**Quote fetcher** — daily-quote APIs for fresh copy (free, no key; dedups against history; audit log):
```bash
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quote_fetcher.py              # 一言·文学 (90%+ 主文案来源)
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quote_fetcher.py --cat i     # 诗词
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quote_fetcher.py --cat k     # 哲学
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quote_fetcher.py --source jinrishici   # 今日诗词
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quote_fetcher.py --source iciba        # 每日一句
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/quote_fetcher.py --source pool         # 本地素材池 (仅 API 全挂兜底)
# Sources: hitokoto (c=d文学/i诗词/k哲学), jinrishici, iciba, local pool. Output: 「text」 — source
# ⚠️ source 已保证「一言·出处」中点分隔（fmt_source）；屏上脚注必须原样照抄，禁止去掉 · 连写成「一言红楼梦」
# ⚠️ 画布 cron 主文案 90%+ 必须来自此脚本输出；审计日志 ~/.hermes/xiaozhi_canvas/quote_log.jsonl
```

## MCP Tools Overview (14 total)

All called via `POST /api/call` → `{"tool":"...","args":{...}}`. Two endpoints exist:
`/api/call` (simplified, always use this) and `/mcp` (JSON-RPC). Never mix formats.
Full signatures: `references/api-reference.md`.

### Fridge Core (10 tools)
`fridge.item.{get,add,remove,clear_all,list,update}` — CRUD for fridge items.
`fridge.stats.{summary,query}` — `query` takes `category`, `filter`(all/expired/expiring_soon), `expiring_days`(default 7).
`fridge.pagemanager` — switch e-paper page (1-15).
`fridge.recipe.recommend` — AI recipe + display. `fridge_only` rejects if ingredients missing; `mixed_purchase` auto-fills `extra_ingredients`.

### UI Aggregators (3 tools — dispatch via `action` parameter)
| Tool | Scope | Actions |
|------|-------|---------|
| `fridge.canvas.control` | Canvas page 6 | `add_text`, `add_rect`, `add_line`, `add_image`, `list`, `remove`, `clear`, `refresh` |
| `fridge.page.control` | Custom pages 7-15 | `create`, `delete`, `list`, `rename`, `clear` |
| `fridge.page.element.control` | Elements on pages 7-15 | `add`, `update`, `remove`, `list` |

**Element add params** (flat, never nested): `page`, `id`, `type`(text/rect/line/image), `x`, `y`, `text`, `font_size`, `align`, `w`, `h`, `filled`, `x1`, `y1`, `x2`, `y2`, `width`, `max_width`(default 276), `dynamic`, `dynamic_type`, `refresh`.
For `line` type, `x`/`y` required by schema but ignored — pass `x:0, y:0`.

### Network (1 tool)
`device.network.info` → `{"wifi_ssid":"...","ip":"...","http_url":"..."}`.

### Legacy Names
Old tool names (e.g. `fridge.canvas.add_text`) auto-map via `/api/call` but **use aggregator names for new code**. `/mcp` JSON-RPC endpoint only supports new names.

## E-Paper Pages

| Page | Name | Purpose |
|------|------|---------|
| 1 | CHAT | Status bar + voice chat hints (auto-switched on config/startup) |
| 2 | FRIDGE_STATS | Clock + fridge statistics |
| 3 | FOOD_LIST | Item list (max 4 rows) |
| 4 | RECIPE | AI recipe display |
| 5 | HOME_PIC | Memorial image |
| 6 | CANVAS | Free-form canvas (Agent-controlled) |
| 7-15 | CUSTOM | User-created pages (persist across reboots) |

## Canvas API (Page 6) — `fridge.canvas.control`

> ⚠️ **Firmware v2.0.5 note**: the flashed firmware does NOT register the aggregator
> `fridge.canvas.control` / `fridge.page.control` — call the **legacy names** directly
> (`fridge.canvas.add_text`, `fridge.canvas.add_line`, `fridge.canvas.add_rect`,
> `fridge.canvas.add_image`, `fridge.canvas.remove`, `fridge.canvas.clear`,
> `fridge.canvas.refresh`, `fridge.canvas.list`). `quick_page_builder.py` uses the
> aggregator and **fails silently** on this firmware — hand-curl instead (pitfall #53).
> Aggregator names apply only to newer firmware builds.

```bash
curl -X POST http://<IP>:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.canvas.add_text","args":{"id":"t1","text":"Hello","x":10,"y":5,"font_size":16}}'
```

| Action | Required params |
|--------|----------------|
| `add_text` | `id`, `text`, `x`, `y`, `font_size`(12/16), `align`(left/center/right), `max_width`(opt, default 276) |
| `add_rect` | `id`, `x`, `y`, `w`, `h`, `filled`(bool) |
| `add_line` | `id`, `x1`, `y1`, `x2`, `y2`, `width` |
| `add_image` | `id`, `name`(LittleFS image), `x`, `y`, `w`, `h` |
| `list` / `remove`(`id`) / `clear` | — |
| `refresh` | Force display refresh |

**Batch pattern**: set `refresh=false` on all adds, then `action=refresh` on last call.
Canvas elements auto-saved to `/canvas/layout.json`, restored on boot. **Max 30 labels** — always `clear` before a new layout.

**Images**: 1-bpp raw bitmap (MSB first, row-padded), size = `ceil(w/8) × h` bytes. Upload via `POST /api/canvas_image?name=<n>` with `Content-Type: application/octet-stream`. Use widths that are multiples of 8 (device reads `w*h/8` bytes). Bit=1 = foreground (black) — invert if image appears inverted.

## Custom Pages API (7-15)

Two tools: `fridge.page.control` (manage pages) + `fridge.page.element.control` (manage elements).

```bash
# Create page
curl -X POST ... -d '{"tool":"fridge.page.control","args":{"action":"create","name":"My Page"}}'
# Add element
curl -X POST ... -d '{"tool":"fridge.page.element.control","args":{"action":"add","page":7,"id":"t1","type":"text","text":"Hello","x":8,"y":2,"font_size":12}}'
# Update dynamic element (cron push)
curl -X POST ... -d '{"tool":"fridge.page.element.control","args":{"action":"update","page":7,"id":"gold","text":"¥892.6/g","refresh":true}}'
```

**CRITICAL**: All params (`page`, `id`, `type`, `text`, ...) are **flat** in `args`, never nested under `element`.

**Persistence**: pages at `/canvas/custom_pages.json`, layouts at `/canvas/page_N.json` (N=7-15).
`element.update` text changes persist via `SavePageLayout()` — they survive reboots.

**Device-side dynamic elements** (`dynamic_type`, no Agent needed): `clock` (HH:MM), `date` (YYYY-MM-DD 周X), `datetime` (MM-DD HH:MM), `cpu_temp` (XX.X°C), `heap` (Heap: XXKB), `uptime` (Up: Xd Xh Xm). Device self-updates every 1s via clock_timer + partial refresh. Persisted in `page_N.json`.

**Agent-pushed dynamic elements**: `dynamic: true` + `element.update` via cron jobs (weather, prices, counts). See `references/custom-pages.md` for architecture, `references/hermes-workflow.md` for the cron pattern.

## Layout Rules (296×128 screen)

### Width Budget — MUST VERIFY for EVERY text element

Each Chinese char: **16px at font_size=16**, **12px at font_size=12**. English/digit ≈ half.

**RULE**: Before placing any text, verify: `x + (char_count × char_width) ≤ 291`

| font_size | char width | max chars at x=0 | max chars at x=200 |
|-----------|-----------|-------------------|--------------------|
| 16 | 16px | 18 chars | 5 chars |
| 12 | 12px | 24 chars | 7 chars |

Wrong (will overflow): `x=200, text="今天天气真好适合出去散步", font=16` → ends at 392 ✗
Right: `x=0,   text="今天天气真好适合出去散步", font=16` → ends at 192 ✓

### Split-Screen Width Constraints

Vertical divider at **x=185**. Each zone has a HARD width limit:

| Zone | x range | Width | max chars (16px) | max chars (12px) |
|------|---------|-------|-------------------|--------------------|
| Left | 0-185 | 185px | 11 chars | 15 chars |
| Right | 186-296 | 110px | **6 chars** | 9 chars |

If content exceeds the zone width, **shorten the text** or **reflow to full-width (start at x=0)**.

### Text Alignment & `x` Semantics (ESP32 vs HTML Canvas)

**ESP32 `align=center`**: `x` is the **LEFT EDGE** of the centering region, NOT the text center point. Text is centered within `[x, x+max_width]`, where `max_width` defaults to 276. Effective text center = `x + max_width/2`.

- To truly center on the 296px screen: use `x=0` or `x=10` with `align=center` (NOT `x=148`)
- `x=148, align=center` → centers within [148, 424] → text appears **far right** ⚠️
- `align=right`: `x` is the right edge. Left edge = `x - text_width` (must be ≥ 5)

**HTML Canvas discrepancy**: `ctx.textAlign='center'` treats `x` as the text's center point — opposite of ESP32. Web console preview must compensate: `drawX = elem.x + (elem.max_width || 276) / 2` for center, `drawX = elem.x + (elem.max_width || 276)` for right.

### Font

Only 2 sizes: `≤12` → 12px, `>12` → 16px. `font_size=10` renders 12px; `font_size=14` renders 16px.

### Y-Axis & Spacing

- Start from y=0 (or y=2 for safety). Bottom safe margin: y=126.
- Text row spacing: font_size + 2px (16px font → 18px to next row). After separator line: +4px.
- Pixel art (24×24) + label: art at y, label at y+26. Icons: min 33px center-to-center.
- Text auto-wrap: split Chinese text > ~8 chars (16px) into separate elements on different y positions.

## Page Templates

`templates/todo-list-page.sh` — ready-made todo layout (clears page, adds 9 elements, switches to it):
```bash
bash ~/.hermes/skills/smart-home/xiaozhi-control/templates/todo-list-page.sh <IP> <page>
# Then update item texts: fridge.page.element.control {action:"update", page, id:"item1..3", text:"..", refresh:true}
```
More templates in `references/page-templates.md`.

## Serial Debugging

```bash
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/crash_log.py              # /dev/ttyUSB0, 20s
python3 ~/.hermes/skills/smart-home/xiaozhi-control/scripts/crash_log.py /dev/ttyUSB0 30
```
**Baud = 115200** (NOT 921600 — garbage otherwise). Verify: `grep MONITOR_BAUD sdkconfig`.
`pyserial` is only in the IDF venv (`$HOME/.espressif/python_env/idf5.4_py3.10_env/bin/python3`), NOT system python3 — always use the IDF venv for serial scripts.

## Agent Pitfalls (TOP 10 — full 52 in `references/pitfalls.md`)

1. **Text overflow right boundary** (#1 layout bug) → verify `x + chars×char_width ≤ 291` before placing ANY text (16px/char at font=16, 12px/char at font=12). Split-screen right zone fits only 6 chars at 16px.
2. **`align=center` x is region left edge, not text center** → centers within `[x, x+max_width]` (default 276). Use `x=0`/`x=10` to truly center; `x=148` pushes text far right.
3. **Custom page params are FLAT** → `page`, `id`, `type`, `text` at top level of `args`, never `{"element":{...}}`.
4. **Line elements still need x/y** → schema requires `x`/`y` in every `add`; for lines pass `x:0, y:0` (ignored, actual coords from x1/y1).
5. **Canvas: clear before new layout** → max 30 labels; `action=clear` deletes `layout.json` (not empty array). Stale labels accumulate invisibly.
6. **Canvas: batch with refresh=false** → set `refresh=false` on all adds, `refresh=true` on last call. Reduces flicker and screen wear (each refresh wears e-paper).
7. **Recipe `fridge_only` rejects missing ingredients** → use `mixed_purchase` to auto-fill `extra_ingredients`.
8. **Two API formats** → `/api/call` = `{"tool":"...","args":{}}`; `/mcp` = JSON-RPC. Mixing = `Missing 'tool' field`. Always `/api/call`.
9. **5s MCP timeout + one request at a time** → device processes sequentially; retry or simplify complex calls. Never fire concurrent requests.
10. **No auth** → any device on same LAN can call the API. Use only on trusted networks.

Firmware-development pitfalls (partition table, CORS, persistence bugs, crash diagnosis):
→ `references/firmware-development.md` + `references/pitfalls.md` (52 entries).

## References

| File | Content | Read when |
|------|---------|-----------|
| `references/api-reference.md` | Full HTTP API + MCP tool signatures | Any tool call needs exact params |
| `references/pitfalls.md` | All 52 field-tested pitfalls | Anything fails or behaves unexpectedly |
| `references/custom-pages.md` | Custom page architecture, dynamic elements, layout audits | Building/auditing pages 7-15 |
| `references/page-templates.md` | 7 ready-made layout templates | Building a common page layout |
| `references/display-philosophy.md` | 10 design principles + 5 pre-refresh questions | Designing what to show on screen |
| `references/canvas-creativity.md` | Anti-repeat system: history ledger, content pool, layout rotation, data hooks | Cron auto-refresh keeps every screen different |
| `references/web-console.md` | Web console setup, CORS, frontend API client | Web console dev/testing |
| `references/canvas-web-interaction.md` | Canvas interaction patterns (events, brush, dragging) | Browser canvas features |
| `references/firmware-development.md` | Build/flash/debug, source structure | Firmware changes |
| `references/hermes-workflow.md` | Hermes workflows: web design delegation, cron data push | Hermes-specific automation |

## Verification Checklist

- [ ] Discovery script outputs an IP (`xiaozhi_discovery.py --save`)
- [ ] `curl http://<IP>:8080/` → `{"status":"ok",...}`
- [ ] At least one MCP tool call succeeds (e.g. `fridge.stats.summary`)
- [ ] Canvas: `pagemanager target_page=6` → batch-add with `refresh=false` → final `refresh` works
- [ ] Canvas persistence: layout survives reboot; `clear` before new layout
- [ ] Custom page: `page.create` → `element.add` → `element.update` → `pagemanager` → reboot → all persists
- [ ] Dynamic element: `dynamic_type:"clock"` updates every second without Agent
- [ ] No text element violates width budget (`x + chars×char_width ≤ 291`)
