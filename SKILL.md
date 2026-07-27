---
name: xiaozhi-control
description: "Discover and control xiaozhi ESP32 voice-AI devices on the LAN. Use when user wants to find, health-check, or call MCP tools (fridge management, e-paper page switch, recipes) on a xiaozhi-esp32 device over HTTP."
version: 1.5.0
author: Juno-cyber
license: MIT
platforms: [linux, macos, windows]
metadata:
  tags: [xiaozhi, esp32, smart-home, iot, lan-control, mcp]
prerequisites:
  commands: [python3]
---

# xiaozhi LAN Control

Discover and control xiaozhi-esp32 devices on the local network via HTTP.

## When to Use

- User wants to find xiaozhi devices on the LAN
- User wants to call MCP tools on a xiaozhi device (fridge, e-paper, recipes)
- User wants a health check on their xiaozhi device

Don't use for:
- Flashing firmware or building (use ESP-IDF directly; see `docs/firmware-development.md`)
- Cloud/MQTT control (this skill is LAN-only)
- Building web console UI (see `docs/web-console.md`)
- Canvas interaction patterns (see `docs/canvas-web-interaction.md`)
- Custom page architecture (see `docs/custom-pages.md`)
- Display Design Philosophy (see `docs/display-philosophy.md`)
- Ready-made page templates (see `docs/page-templates.md`)

## Quick Page Builder (FAST — use this for all canvas/page layouts)

**Scripts** (in `scripts/`):
- `quick_page_builder.py` — Layout DSL → device. Reads a text layout file, deploys all elements in one pass.
- `pixel_art_generator.py` — 13 built-in 24×24 pixel arts. Auto-uploads to device LittleFS on first use.

**Usage**:
```bash
# Write a .layout file, then deploy in ONE command:
python3 scripts/quick_page_builder.py <IP> 6 my_layout.layout

# Or pipe inline:
python3 scripts/quick_page_builder.py <IP> 6 - << 'EOF'
clear
switch 6
text id=title text="标题" x=12 y=2 font_size=16 align=left
pixart id=img1 art=heart x=40 y=62 w=24 h=24
text id=lbl1 text="爱心" x=40 y=88 font_size=12
refresh
EOF
```

**Layout DSL commands** (one per line, # = comment, --- = separator):
```
clear                           # Clear page
switch 6                        # Switch to target page
text   id=.. text=".." x=.. y=.. font_size=.. align=..    # Add text
rect   id=.. x=.. y=.. w=.. h=.. filled=..                 # Add rectangle
line   id=.. x1=.. y1=.. x2=.. y2=.. width=..              # Add line
image  id=.. name=.. x=.. y=.. w=.. h=..                   # Add uploaded image
pixart id=.. art=heart x=.. y=.. w=24 h=24                 # Auto-generate+upload+display
refresh                        # Refresh display (do LAST)
```

**Available pixel arts**: heart, star, note, diamond, smiley, arrow, check, sun, moon, house, bolt, coffee, bell
```bash
python3 scripts/pixel_art_generator.py --list
python3 scripts/pixel_art_generator.py --upload <IP>  # upload all
python3 scripts/pixel_art_generator.py --dump heart /tmp/heart.bin  # export one
```

## Device Prerequisites

The xiaozhi-esp32 device must have **LocalControl** enabled (HTTP server on port 8080 + mDNS registration `xiaozhi.local`). The device and this machine must be on the same WiFi.

## Serial Debugging

When HTTP/LAN control isn't working (device won't boot, WiFi won't connect, crash loop), use the bundled serial script:

```bash
python3 scripts/crash_log.py              # Default: /dev/ttyUSB0, 20 seconds
python3 scripts/crash_log.py /dev/ttyUSB0 30  # Custom port and duration
```

Prerequisites: `pip install pyserial`, serial port permissions (`sudo chmod 666 /dev/ttyUSB0`).

### ⚠️ Serial baud rate = 115200 (NOT 921600)

The device console UART runs at **115200 baud**. Using 921600 produces garbage data. Verify from sdkconfig:
```bash
grep MONITOR_BAUD sdkconfig  # → CONFIG_ESPTOOLPY_MONITOR_BAUD=115200
```

## Discovery

Run the bundled discovery script. It tries 4 strategies in priority order:

| # | Strategy | Speed | Notes |
|---|----------|-------|-------|
| 1 | mDNS resolve `xiaozhi.local` | <100ms | Best if mDNS works on your network |
| 2 | Cached IP (`~/.cache/xiaozhi_ip.txt`) | instant | Last successful discovery |
| 3 | UDP broadcast | 3s | Requires device-side UDP responder |
| 4 | Port scan subnet for :8080 | 2-5s | Most reliable fallback |

```bash
python3 scripts/xiaozhi_discovery.py            # Discover and print IP
python3 scripts/xiaozhi_discovery.py --health   # Discover + health check
python3 scripts/xiaozhi_discovery.py --save     # Discover + save IP to cache
python3 scripts/xiaozhi_discovery.py -v         # Verbose
```

Output: IP address to stdout (exit 0), errors to stderr (exit 1).

## HTTP API

Once you have the IP (port `8080`):

```bash
# Health check
curl http://<IP>:8080/
# → {"status":"ok","board":"bread-compact-wifi-epaperx","version":"2.0.3",...}

# Call MCP tool (simplified format — recommended)
curl -X POST http://<IP>:8080/api/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"fridge.stats.summary","args":{}}'

# Raw JSON-RPC (alternative)
curl -X POST http://<IP>:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"fridge.stats.summary","arguments":{}}}'
```

Two endpoints: `/api/call` uses `{"tool":"...","args":{}}` (simplified); `/mcp`
uses JSON-RPC. Mixing returns `{"error":"Missing 'tool' field"}`. For curl
testing, always use `/api/call`. See `docs/api-reference.md` for full details.

## Available MCP Tools

| Tool | Description | Key Args |
|------|-------------|----------|
| `fridge.pagemanager` | Switch e-paper page | `target_page`: 1-15 |
| `fridge.stats.summary` | Fridge statistics | `{}` |
| `fridge.stats.query` | Query items by filter | `category`, `expire_within_days` |
| `fridge.item.list` | List all items | `sort_by`: name/expiry/quantity |
| `fridge.item.get` | Get single item | `item_id` |
| `fridge.item.add` | Add item | `name`, `category`, `quantity`, `unit`, `expire_time` |
| `fridge.item.update` | Update item | `item_id` + fields to change |
| `fridge.item.remove` | Remove item | `item_id` |
| `fridge.item.clear_all` | Clear all items | `{}` |
| `fridge.recipe.recommend` | Recommend recipe + display | `dish_name`, `required_ingredients`, `recommendation_mode` |
| `fridge.canvas.add_text` | Place text on canvas (page 6) | `id`, `text`, `x`, `y`, `font_size`, `align`, `refresh` |
| `fridge.canvas.add_rect` | Place rectangle (page 6) | `id`, `x`, `y`, `w`, `h`, `filled`, `refresh` |
| `fridge.canvas.add_line` | Place line (page 6) | `id`, `x1`, `y1`, `x2`, `y2`, `width`, `refresh` |
| `fridge.canvas.add_image` | Load image from LittleFS (page 6) | `id`, `name`, `x`, `y`, `w`, `h`, `refresh` |
| `fridge.canvas.clear` | Clear canvas (or single by `id`) | `refresh`, optional `id` |
| `fridge.page.create` | Create custom page (7-15) | `name` |
| `fridge.page.delete` | Delete custom page | `page` (7-15) |
| `fridge.page.list` | List all pages | `{}` |
| `fridge.page.rename` | Rename custom page | `page`, `name` |
| `fridge.page.element.add` | Add element to custom page | `page`, `id`, `type`, `x`, `y`, `text`, `font_size`, `align`, `dynamic_type`, `refresh` |
| `fridge.page.element.update` | Update element text (cron push) | `page`, `id`, `text`, `refresh` |
| `fridge.page.element.remove` | Remove element | `page`, `id`, `refresh` |
| `fridge.page.element.list` | List elements on page | `page` |
| `fridge.page.clear` | Clear page elements | `page`, `refresh` |

## E-Paper Pages

| target_page | Name | Content |
|-------------|------|---------|
| 1 | CHAT | Status bar + chat (connection hints) |
| 2 | FRIDGE_STATS | Clock + fridge stats |
| 3 | FOOD_LIST | Item list (max 4 rows) |
| 4 | RECIPE | AI recipe |
| 5 | HOME_PIC | Memorial image |
| 6 | CANVAS | Free-form canvas (Agent-controlled) |
| 7-15 | CUSTOM | User-created pages with static + dynamic elements |

Custom pages persist across reboots. Each page holds static elements
(text/rect/line) and **dynamic elements** whose text is updated via
`fridge.page.element.update`. See `docs/custom-pages.md` for full architecture.

## Canvas API (Page 6)

The canvas page lets the Agent freely place text, lines, and rectangles on the
296×128 e-paper display. Use `refresh=false` to batch multiple operations, then
flush with `refresh=true` on the last call.

### Canvas Coordinate System

- Screen: 296 (W) × 128 (H) pixels
- Origin: top-left (0,0)
- Safe area: x ∈ [5, 291], y ∈ [5, 123]

### Canvas Image Format

1-bpp (black/white) raw bitmap, MSB first, each row padded to byte boundary.
Size = `ceil(w/8) * h` bytes. 1 = black, 0 = white. Images persist in LittleFS.
See `docs/api-reference.md` § Canvas Image Storage for upload + display workflow
and color-inversion pitfalls.

## E-Paper Layout Rules (296×128)

### Text Auto-Wrap Problem
Chinese text longer than ~8 characters at 16px (or ~12 at 12px) may auto-wrap
and get cut off. **Always split long text into multiple independent text elements
on separate y coordinates**.

Rule of thumb: 1 Chinese char ≈ 16px at font_size=16, ≈ 12px at font_size=12.

### Y-Axis: Start from 0
Don't add unnecessary top margin. Start elements from y=0 (or y=2 for visual
safety). Bottom safe margin is y=126.

### Element Spacing (Minimum Gaps)
- Text row height: font_size + 2px gap (e.g. 16px font → 18px row spacing)
- After separator line: leave 4px before next element
- Pixel art (24×24) + label below: art at y, label at y+26
- Between pixel art icons horizontally: minimum 33px center-to-center

### Section Layout Template
```
 y=0    Title (font=16, y=0-2)
 y=18   ── separator line ──
 y=22   Content row 1
 y=40   Content row 2  (18px spacing for font=16)
 y=58   Content row 3
 y=70   ── separator line ──
 y=74   Pixel art row (24×24 icons)
 y=100  Labels under icons (font=12)
 y=114  Footer text (font=12)
 y=128  (bottom edge)
```

## Split-Screen Layout Pattern

For pages showing two independent data zones (e.g. todo list + live price),
use a vertical divider line at x=185:

```
┌────────────────────────────────┬───────────────┐
│ Left zone (x: 0-184)           │ Right (186-295)│
│ ~185px wide                    │ ~110px wide    │
└────────────────────────────────┴───────────────┘
```

- Left: 185px = ~9 Chinese chars at 16px, ~12 at 12px
- Right: 110px = ~5 Chinese chars at 16px, ~7 at 12px
- Vertical line: `element.add { type:"line", x1:185, y1:2, x2:185, y2:108, width:1 }`

## Font Size Selection

The device supports only TWO font sizes:
- `font_size <= 12` → `u8g2_font_wqy12_t_gb2312` (12px)
- `font_size > 12` → `u8g2_font_wqy16_t_gb2312` (16px)

Passing `font_size=10` renders at 12px. Passing `font_size=14` renders at 16px.

## Common Pitfalls

1. **mDNS not resolving**: Some networks block mDNS. Fall back to port scan: `python3 scripts/xiaozhi_discovery.py -v`.
2. **Port scan slow**: 254 IPs at 0.5s timeout each, parallelized 50-way. Takes 2-5s. If you know the IP, curl directly.
3. **5s response timeout**: The device waits 5s for MCP tool completion. Complex tools may time out — retry or simplify.
4. **No auth**: Any device on the same LAN can call the API. Only use on trusted networks.
5. **One request at a time**: The device processes MCP calls sequentially. Don't fire concurrent requests.
6. **Browser CORS — "connected but operations fail" = OPTIONS 405**: The #1 symptom of missing CORS support. Health check (GET /) succeeds and shows "已连接", but ALL subsequent operations fail with "获取失败". Root cause: browser sends an `OPTIONS` preflight before POST, and ESP32 httpd returns `405` because no `HTTP_OPTIONS` handler is registered. Fix: register OPTIONS handlers for each URI and set `config.max_uri_handlers = 16`. See `docs/web-console.md`.
7. **Recipe `extra_ingredients` was unreliable (now fixed)**: As of v2.0.3+ the device auto-checks fridge inventory. In `fridge_only` mode, if any required ingredient is missing, the call is rejected. In `mixed_purchase` mode, missing ingredients auto-fill into `extra_ingredients`.
8. **Canvas layout persistence & label management**: Canvas elements auto-saved to `/canvas/layout.json` in LittleFS, restored on boot. Max 30 canvas labels. Same-ID `add` is a replacement. `canvas.clear` **deletes** `layout.json` (not writes empty array). Always call `fridge.canvas.clear` before drawing a new layout to avoid stale labels.
9. **Canvas label accumulation (max 30)**: Each `add` that creates a *new* ID increments the label count. Exceeding 30 returns `"Canvas label limit reached (30). Call fridge.canvas.clear first."`. Always `clear` before new layouts.
10. **`fridge.pagemanager` supports pages 1-15**: Pages 1-5 system, 6 canvas, 7-15 custom. Update both Property max and HandlePageManager range check when adding pages.
11. **Partition table change for LittleFS**: Adding `canvas_data` requires changing `partitions/v2/16m.csv`. Do a full clean (`idf.py fullclean`) and flash all partitions.
12. **LoadCanvasLayout timing**: Must NOT be called in `Initialize()` — LittleFS isn't mounted yet. Call from `MountCanvasStorage()` after `esp_vfs_littlefs_register()`.
13. **JSON field parsing offset**: When parsing `"font_size":`, offset is `pos + 12` (not `pos + 13`). Off-by-one causes wrong font selection after reboot.
14. **`fridge.page.element.add` requires `x`/`y` even for `line` type**: `x`/`y` are required by the schema. For lines, actual coords are `x1/y1/x2/y2` — pass `x:0, y:0`.
15. **`fridge.page.element.add` parameters are FLAT**: `page`, `id`, `type`, `text`, etc. are top-level keys in `args`. Never nest under `element`. Correct: `{"page":7, "id":"title", "type":"text", "text":"待办事项", ...}`.
16. **Use templates or quick_page_builder, don't hand-curl**: The skill ships `templates/todo-list-page.sh` (ready-made todo layout) and `scripts/quick_page_builder.py` (DSL-driven batch deployment). Hand-curling 9+ curl commands is slow and error-prone. Always check if a template exists first.
17. **Two API formats**: `/api/call` uses `{"tool":"...","args":{}}`; `/mcp` uses JSON-RPC. Mixing returns `{"error":"Missing 'tool' field"}`. Always use `/api/call` for curl testing.
18. **Device reboot via HTTP**: No `/api/reboot` endpoint. Use `esp_restart()` via custom MCP tool or power-cycle.
19. **CustomPageManager singleton — must define `GetInstance()` in `.cc`**: Declaring `static CustomPageManager& GetInstance();` in `.h` is NOT enough. Define in `.cc`: `CustomPageManager& CustomPageManager::GetInstance() { static CustomPageManager instance; return instance; }`.
20. **`esptool` flash via `@flash_args` must run from `build/` dir**: `cd build && python3 -m esptool --chip esp32s3 -b 460800 --before default_reset --after hard_reset -p /dev/ttyUSB0 write_flash @flash_args`.
21. **Serial port busy after `idf.py monitor` or `cat`**: `fuser -k /dev/ttyUSB0`, wait 1-2s, then retry.
22. **`idf.py flash`/`monitor` timeout in non-TTY shell**: Use `esptool` directly (see pitfall #20) for flashing, and `crash_log.py` for serial capture.
23. **Debugging ESP32 crashes with addr2line**: Capture serial log via `crash_log.py`, then: `xtensa-esp32s3-elf-addr2line -pfiaC -e build/xiaozhi.elf 0x<addr1> 0x<addr2> ...`. See `docs/firmware-development.md`.
24. **`SetDeviceState(kDeviceStateStarting)` crash — do NOT call `audio_service_` methods**: Early states run before `audio_service_.Initialize()`. Only call `display_epaper->SetPage(CHAT_PAGE)` in `kDeviceStateStarting`/`kDeviceStateWifiConfiguring`.
25. **Hiding e-paper UI elements via `visible=false`**: Cleaner than commenting out `AddLabel()` lines. See `docs/firmware-development.md` § E-Paper Chat Page Layout.
26. **Custom page persistence — three bugs must ALL be fixed**: (A) `UpdateElementText()` doesn't call `SavePageLayout()` → text updates lost; (B) `LoadPageLayout()` parser matches outer JSON wrapper → only 0-1 elements restored; (C) `RestoreCanvasLayout()` called from WiFi pthread → stack overflow crash loop. All three must be fixed.
27. **MCP tool count limit — xiaozhi server caps at 32 tools**: Current count is 32 = exactly the limit (3 common + 2 user-only + 3 lamp + 24 fridge). Canvas tools reduced from 8 to 5 by merging `list`/`refresh`/`remove` into other tools.

## Page Templates

### Todo List Page (`templates/todo-list-page.sh`)

A ready-made "待办事项" layout for custom pages (7-15). Screen 296×128.
Creates 9 elements: title text, separator line, 3× (checkbox rect + item text), bottom hint.

Layout:
```
 y=0  待办事项                                    (title, font=12, x=8,y=2)
 y=18 ════════════ full-width separator line ════════════
 y=24  ☐ 写专利                                   (box1 6×6 @ x=6,y=24; item1 font=12 @ x=20,y=24)
 y=42  ☐ 改论文                                   (box2; item2)
 y=60  ☐ 运动小智开发                             (box3; item3)
 y=112 说"提醒我..."添加待办                      (hint, font=12)
```

Usage:
```bash
bash templates/todo-list-page.sh <IP> 7
# Args: $1=IP, $2=page, $3-5=custom item text
```

**Customizing item text**: After running the template, update each item's text via `fridge.page.element.update` with `refresh=false` on all but the last, then `refresh=true` on the last to flush all changes to the screen at once.

See `docs/page-templates.md` for 7 ready-made layouts (clock+weather, daily quote, pixel art, CPU dashboard, countdown, focus, todo).

## Verification Checklist

- [ ] Discovery script runs and outputs an IP
- [ ] `curl http://<IP>:8080/` returns `{"status":"ok",...}`
- [ ] At least one MCP tool call succeeds (e.g. `fridge.stats.summary`)
- [ ] `--save` flag writes cache to `~/.cache/xiaozhi_ip.txt`
- [ ] Canvas: `fridge.pagemanager target_page=6` succeeds (page 6 = CANVAS)
- [ ] Canvas: batch-add elements with `refresh=false` then `refresh=true` works
- [ ] Image storage: `POST /api/canvas_image?name=test` returns `{"status":"success"}`
- [ ] Image display: `fridge.canvas.add_image` loads uploaded image and displays it
- [ ] Persistence: uploaded image survives device reboot (stored in LittleFS)
- [ ] Canvas layout persistence: text/lines/rects auto-saved to layout.json, restored on boot
- [ ] Custom pages: `page.create` → `element.add` → `element.update` → `pagemanager` → reboot → verify persistence
- [ ] Custom pages boundary: `page.delete { page: 1 }` returns error (min allowed: 7)
- [ ] Page audit: `page.list` + `element.list` for all custom pages, visualize layout in ASCII
- [ ] Web console: page selector dropdown shows custom pages after connect
- [ ] Browser CORS: `curl -X OPTIONS http://<IP>:8080/ -H "Origin: http://test"` returns 200 with `Access-Control-Allow-Origin: *`
