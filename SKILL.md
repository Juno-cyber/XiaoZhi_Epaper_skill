---
name: xiaozhi-control
description: "Discover and control xiaozhi ESP32 voice-AI devices on the LAN. Use when user wants to find, health-check, or call MCP tools (fridge management, e-paper page switch, canvas drawing, custom pages, recipes) on a xiaozhi-esp32 device over HTTP."
version: 1.7.0
author: Juno-cyber
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [xiaozhi, esp32, smart-home, iot, lan-control, mcp]
prerequisites:
  commands: [python3]
---

# xiaozhi LAN Control

Discover and control xiaozhi-esp32 devices on the local network via HTTP (port 8080).

## When to Use

- Find xiaozhi devices on LAN → `python3 scripts/xiaozhi_discovery.py`
- Call MCP tools (fridge, e-paper, canvas, custom pages, recipes)
- Health check, device scanner UI (`/ui`)

**Don't use for**: flashing/building firmware, cloud/MQTT control, web console UI dev.
Reference docs: `docs/api-reference.md` (full API), `docs/firmware-development.md` (build/flash),
`docs/custom-pages.md` (custom page architecture), `docs/display-philosophy.md` (design),
`docs/page-templates.md` (ready-made layouts), `docs/canvas-web-interaction.md` (browser).

## Quick Start

```bash
# 1. Discover (mDNS → cache → UDP → port scan, in priority order)
IP=$(python3 scripts/xiaozhi_discovery.py)

# 2. Health check
curl http://$IP:8080/

# 3. Call any tool (always use /api/call, never /mcp for curl)
curl -X POST http://$IP:8080/api/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"fridge.stats.summary","args":{}}'
```

Discovery variants: `--health` (discover + check), `--save` (cache to `~/.cache/xiaozhi_ip.txt`), `-v` (verbose).
Device hostname: `xiaozhi-<MAC>.local`. Prerequisite: device + host on same WiFi, LocalControl enabled.

## Quick Page Builder (preferred for ALL layouts)

Use `scripts/quick_page_builder.py` — one command deploys an entire canvas/page layout from a DSL file
or inline text. Always prefer this over hand-curling individual API calls.

```bash
python3 scripts/quick_page_builder.py <IP> 6 my_layout.layout

# Inline DSL:
python3 scripts/quick_page_builder.py <IP> 6 - << 'EOF'
clear
switch 6
text id=title text="标题" x=12 y=2 font_size=16
pixart id=img1 art=heart x=40 y=62 w=24 h=24
text id=lbl1 text="爱心" x=40 y=88 font_size=12
refresh
EOF
```

**DSL commands** (`#` = comment):
| Command | Format |
|---------|--------|
| `clear` | Clear all elements |
| `switch N` | Switch to page N |
| `text` | `id=.. text=".." x=.. y=.. font_size=.. align=..` |
| `rect` | `id=.. x=.. y=.. w=.. h=.. filled=..` |
| `line` | `id=.. x1=.. y1=.. x2=.. y2=.. width=..` |
| `image` | `id=.. name=.. x=.. y=.. w=.. h=..` |
| `pixart` | `id=.. art=<name> x=.. y=.. w=24 h=24` (auto-generate + upload) |
| `refresh` | Flush to screen (always last) |

**Pixel art** (13 built-in): heart, star, note, diamond, smiley, arrow, check, sun, moon, house, bolt, coffee, bell.
```bash
python3 scripts/pixel_art_generator.py --list       # list available
python3 scripts/pixel_art_generator.py --upload <IP>  # upload all to device
```

## MCP Tools Overview (14 total)

All called via `POST /api/call` → `{"tool":"...","args":{...}}`. Two endpoints exist:
`/api/call` (simplified, always use this) and `/mcp` (JSON-RPC). Never mix formats.
Full signatures: `docs/api-reference.md`.

### Fridge Core (10 tools)
`fridge.item.{get,add,remove,clear_all,list,update}` — CRUD for fridge items.
`fridge.stats.{summary,query}` — statistics, filtered queries.
`fridge.pagemanager` — switch e-paper page (1-15).
`fridge.recipe.recommend` — AI recipe recommendation + display.

### UI Aggregators (3 tools — dispatch via `action` parameter)
| Tool | Scope | Actions |
|------|-------|---------|
| `fridge.canvas.control` | Canvas page 6 | `add_text`, `add_rect`, `add_line`, `add_image`, `list`, `remove`, `clear`, `refresh` |
| `fridge.page.control` | Custom pages 7-15 | `create`, `delete`, `list`, `rename`, `clear` |
| `fridge.page.element.control` | Elements on pages 7-15 | `add`, `update`, `remove`, `list` |

### Network (1 tool)
`device.network.info` → `{"wifi_ssid":"...","ip":"...","http_url":"..."}`.

### Legacy Names
Old tool names (e.g. `fridge.canvas.add_text`) auto-map via `/api/call` but **use aggregator names for new code**.
`/mcp` JSON-RPC endpoint only supports new names.

## E-Paper Pages

| Page | Name | Purpose |
|------|------|---------|
| 1 | CHAT | Status bar + voice chat hints |
| 2 | FRIDGE_STATS | Clock + fridge statistics |
| 3 | FOOD_LIST | Item list (max 4 rows) |
| 4 | RECIPE | AI recipe display |
| 5 | HOME_PIC | Memorial image |
| 6 | CANVAS | Free-form canvas (Agent-controlled) |
| 7-15 | CUSTOM | User-created pages (persist across reboots) |

## Canvas API (Page 6) — `fridge.canvas.control`

```bash
# Single element:
curl -X POST http://<IP>:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.canvas.control","args":{"action":"add_text","id":"t1","text":"Hello","x":10,"y":5,"font_size":16}}'
```

| Action | Required params |
|--------|----------------|
| `add_text` | `id`, `text`, `x`, `y`, `font_size`(12/16), `align`(left/center/right) |
| `add_rect` | `id`, `x`, `y`, `w`, `h`, `filled`(bool) |
| `add_line` | `id`, `x1`, `y1`, `x2`, `y2`, `width` |
| `add_image` | `id`, `name`(LittleFS image), `x`, `y`, `w`, `h` |
| `list` / `remove`(`id`) / `clear` | — |
| `refresh` | Force display refresh |

**Batch pattern**: set `refresh=false` on all adds, then `action=refresh` on last call.
Canvas elements auto-saved to `/canvas/layout.json`, restored on boot.

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

**Page management** (`fridge.page.control`): `create`(name), `delete`(page), `list`, `rename`(page,name), `clear`(page).

**Element types for `action=add`**:
- `text`: `text`, `x`, `y`, `font_size`(12/16), `align`(left/center/right), `dynamic`, `dynamic_type`
- `rect`: `x`, `y`, `w`, `h`, `filled`
- `line`: `x1`, `y1`, `x2`, `y2`, `width` (+ pass `x:0, y:0` — required by schema but ignored)
- `image`: `name`, `x`, `y`, `w`, `h`

**CRITICAL**: All params (`page`, `id`, `type`, `text`, etc.) are **flat** in `args`, never nested.
See `docs/custom-pages.md` for full architecture and dynamic element patterns.

## Layout Rules (296×128 screen)

### Width Budget — MUST VERIFY for EVERY text element

Each Chinese char: **16px at font_size=16**, **12px at font_size=12**.
English/digit: roughly half width (use char count as upper bound for safety).

**RULE**: Before placing any text, verify:  `x + (char_count × char_width) ≤ 291`

| font_size | char width | max chars at x=0 | max chars at x=200 |
|-----------|-----------|-------------------|--------------------|
| 16 | 16px | 18 chars | 5 chars |
| 12 | 12px | 24 chars | 7 chars |

Wrong (will overflow):  `x=200, text="今天天气真好适合出去散步", font=16` → ends at 392 ✗
Right:  `x=0,   text="今天天气真好适合出去散步", font=16` → ends at 192 ✓

### Split-Screen Width Constraints

Vertical divider at **x=185**. Each zone has a HARD width limit:

| Zone | x range | Width | max chars (16px) | max chars (12px) |
|------|---------|-------|-------------------|--------------------|
| Left | 0-185 | 185px | 11 chars | 15 chars |
| Right | 186-296 | 110px | **6 chars** | 9 chars |

If content exceeds the zone width, **shorten the text** or **reflow to full-width (start at x=0)**.

### Text Alignment & `x` Semantics (ESP32 vs HTML Canvas)

**ESP32 `align=center`**: `x` is the **LEFT EDGE** of the centering region, NOT the text center point. Text is centered within `[x, x+max_width]`, where `max_width` defaults to 276 (full screen width). Effective text center = `x + max_width/2`.

- To truly center on the 296px screen: use `x=0` or `x=10` with `align=center` (NOT `x=148`)
- `x=148, align=center` → centers within [148, 424] → text appears **far right** ⚠️
- `align=right`: `x` is the right edge. Left edge = `x - text_width`.

**HTML Canvas discrepancy**: `ctx.textAlign='center'` treats `x` as the text's center point — opposite of ESP32. Web console preview must compensate: `drawX = elem.x + (elem.max_width || 276) / 2` for center, `drawX = elem.x + (elem.max_width || 276)` for right. Without this, preview looks correct but physical screen shows text shifted right.

### Font

Only 2 sizes: `≤12` = 12px, `>12` = 16px. Passing `font_size=10` → 12px; `font_size=14` → 16px.

### Y-Axis & Spacing

- Start from y=0 (or y=2 for safety). Bottom safe margin: y=126.
- Text row spacing: font_size + 2px (e.g. 16px font → 18px gap to next row).
- After separator line: +4px before next element.
- Pixel art (24×24) + label: art at y, label at y+26.
- Icons: min 33px center-to-center horizontally.

## Page Templates

`templates/todo-list-page.sh` — ready-made todo layout:
```bash
bash templates/todo-list-page.sh <IP> <page> [item1] [item2] [item3]
```
7 more templates in `docs/page-templates.md`.

## Serial Debugging

```bash
python3 scripts/crash_log.py              # /dev/ttyUSB0, 20s
python3 scripts/crash_log.py /dev/ttyUSB0 30
```
Baud = **115200** (NOT 921600). Prerequisites: `pip install pyserial`, port permissions.

## Agent Pitfalls

1. **Discovery fails** → `python3 scripts/xiaozhi_discovery.py -v` (some networks block mDNS; port scan fallback works).
2. **Known IP** → skip discovery, curl directly to `http://<IP>:8080/`.
3. **5s MCP timeout** → device times out after 5s. Retry or simplify complex calls.
4. **One request at a time** → device processes sequentially. Never fire concurrent requests.
5. **Two API formats** → `/api/call` = `{"tool":"...","args":{}}`; `/mcp` = JSON-RPC. Mixing = error. Always `/api/call`.
6. **Use quick_page_builder, not hand-curl** → the script handles batching, error recovery, pixel art generation. Check `templates/` first for ready-made layouts.
7. **Canvas: clear before new layout** → `action=clear` deletes `layout.json`. Stale labels persist otherwise. Max 30 canvas elements.
8. **Canvas: batch with refresh=false** → set `refresh=false` on all adds, then `action=refresh` on last call. Prevents flicker and screen wear.
9. **Custom page params are FLAT** → `page`, `id`, `type`, `text` at top level of `args`, never `{"element":{...}}`.
10. **Line elements still need x/y** → schema requires `x`/`y` in every `add`; for lines pass `x:0, y:0` (ignored, actual coords from x1/y1).
11. **Recipe `fridge_only` rejects missing ingredients** → use `mixed_purchase` mode to auto-fill `extra_ingredients`.
12. **MCP tool consolidation** → use aggregator names (`fridge.canvas.control` + `action`). Legacy names auto-map but `/mcp` endpoint doesn't support them.
13. **Text auto-wrap** → split Chinese text > ~8 chars (16px) into separate elements on different y positions.
14. **No auth** → any device on same LAN can call API. Use only on trusted networks.
15. **Text overflow right boundary** → the #1 layout bug. Before placing ANY text, compute: `x + chars×char_width ≤ 291`. Font 16 = 16px/char, font 12 = 12px/char. Split-screen right zone (110px) fits only 6 chars at 16px. If text won't fit at current x, either: (a) start at x=0 for full width, (b) shorten the text, or (c) split into multiple shorter lines at different y.
16. **`align=center` x is region left edge, not text center** → ESP32 centers text within `[x, x+max_width]` (max_width defaults to 276). `x=148, align=center` does NOT center at pixel 148 — it centers within [148,424], making text appear far right. To truly center: use `x=0` or `x=10` with `align=center`. HTML Canvas `textAlign='center'` is the opposite (x = text center), so web preview must compensate: `drawX = elem.x + (elem.max_width || 276) / 2`.

Firmware development pitfalls (partition table, serial, crashes, CORS, persistence bugs):
→ `docs/firmware-development.md`.
