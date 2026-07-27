# Custom Pages & Dynamic Elements Architecture

Multi-page custom e-paper system with Agent-driven dynamic elements.

## Core Concept: ESP32 = Dumb Display, Agent = Smart Controller

Dynamic elements are NOT computed on the ESP32. The Agent runs cron jobs to fetch
external data (weather, stock prices, fan counts, countdowns), then pushes the
final text string to the device via `fridge.page.element.update`. The ESP32 only
stores layouts and renders text — it doesn't know or care where data comes from.

This means any data the Agent can access → can appear on the e-paper display.
No firmware changes needed to support new data sources.

## Page Numbering

| Range | Type | Notes |
|-------|------|-------|
| 1-5 | System pages | Chat/Stats/List/Recipe/HomePic (built-in, not deletable) |
| 6 | Default canvas | Backward-compatible single canvas page (`canvas_` prefix) |
| 7-15 | Custom pages | User-created, persisted to LittleFS, max 9 pages |

## File Layout (LittleFS /canvas/)

```
/canvas/
├── layout.json              ← Page 6 layout (legacy, backward compatible)
├── custom_pages.json        ← Page registry: [{page, name}]
├── page_7.json              ← Page 7 layout
├── page_8.json              ← Page 8 layout
├── img_freehand_1           ← Uploaded 1-bpp bitmaps (shared with page 6)
└── ...
```

## Label Prefix Scheme

Each page has its own prefix to avoid ID collisions in `EpaperDisplay::ui_labels_`:

| Page | Prefix | Example label ID |
|------|--------|-----------------|
| 6 | `canvas_` | `canvas_title` |
| 7 | `cp_p7_` | `cp_p7_title` |
| 8 | `cp_p8_` | `cp_p8_fan_count` |
| ... | `cp_pN_` | ... |

This allows all pages' labels to coexist in the same `std::map<String, EpaperLabel*>`.
`SetPage(N)` switches `current_page_` and `UpdateUI()` only renders labels where
`label->page == current_page_`.

## MCP Tools (9 new)

### Page Management

| Tool | Args | Returns |
|------|------|---------|
| `fridge.page.create` | `name` (string) | `{page, name}` — page auto-assigned 7-15 |
| `fridge.page.delete` | `page` (int 7-15) | `{removed}` — deletes layout file + registry entry |
| `fridge.page.list` | `{}` | `[{page, name, builtin}]` — includes built-in 1-6 |
| `fridge.page.rename` | `page`, `name` | `{page, name}` |

### Element Management

| Tool | Args | Returns |
|------|------|---------|
| `fridge.page.element.add` | `page`, `id`, `type`(text/rect/line), `x`, `y`, `text`, `font_size`, `align`, `w`, `h`, `filled`, `x1`, `y1`, `x2`, `y2`, `width`, `dynamic`, `refresh` | `{page, id, type}` |
| `fridge.page.element.update` | `page`, `id`, `text`, `refresh`(default true) | `{page, id, text}` — **core dynamic push** |
| `fridge.page.element.remove` | `page`, `id`, `refresh` | `{removed, page}` |
| `fridge.page.element.list` | `page` | `[elements...]` |
| `fridge.page.clear` | `page`, `refresh` | `{page}` |

## Dynamic Element Push Pattern (Agent Cron)

```
User: "创建一个B站粉丝数页面，每5分钟更新"

Agent:
1. fridge.page.create { name: "B站粉丝" }  → { page: 7 }
2. fridge.page.element.add {
     page: 7, id: "title", type: "text",
     text: "B站粉丝数", x: 148, y: 5, font_size: 16, align: "center"
   }
3. fridge.page.element.add {
     page: 7, id: "fan_count", type: "text",
     text: "加载中...", x: 148, y: 40, font_size: 24, align: "center",
     dynamic: true
   }
4. fridge.pagemanager { target_page: 7 }
5. Create cron job (every 5 min):
   - Fetch bilibili API → fan count
   - fridge.page.element.update {
       page: 7, id: "fan_count", text: "12,345", refresh: true
     }
```

## SetPage Behavior for Custom Pages

`EpaperDisplay::SetPage()` has special handling for pages >= 7:

```cpp
void EpaperDisplay::SetPage(uint16_t page) {
    if (page >= 7) {
        // Custom pages: always trigger refresh (element.update needs this)
        current_page_ = page;
        UpdateUI(true);
    } else if (current_page_ != page) {
        current_page_ = page;
        UpdateUI(true);
    }
}
```

For pages 1-6, `SetPage` only refreshes if the page actually changed (avoids
unnecessary redraws). For pages 7-15, it ALWAYS refreshes — this is critical
for `element.update` which calls `SetPage(page)` to push the new text to the
screen even when already on that page.

## Boot Recovery Sequence

```
WiFi connects
  → LocalControl::MountCanvasStorage()
    → esp_vfs_littlefs_register("/canvas")
    → xTaskCreate(restore_layout, 16384)   ← MUST run in dedicated task
      → FridgeMcpTools::RestoreCanvasLayout()
        → LoadCanvasLayout()           // page 6 (legacy)
        → CustomPageManager::LoadAllPages()
          → LoadRegistry()             // read custom_pages.json
          → for each page: LoadPageLayout(page)  // restore labels
          → StartDynamicTimer()        // 1s esp_timer for device-side dynamics
```

**CRITICAL — Stack overflow crash if RestoreCanvasLayout runs in WiFi pthread**:
`LocalControl::MountCanvasStorage()` is called from the WiFi event handler, which
runs in a pthread with a small default stack (~4KB). `LoadPageLayout()` uses large
`std::string` local variables and hand-rolled JSON parsing that can exceed 4KB of
stack. Symptom: `***ERROR*** A stack overflow in task pthread has been detected.`
followed by an immediate reboot loop. Fix: wrap the call in `xTaskCreate()` with
a 16KB stack:

```cpp
// local_control.cc — MountCanvasStorage()
// BAD: FridgeMcpTools::RestoreCanvasLayout();  // stack overflow in pthread!
// GOOD:
xTaskCreate([](void* arg) {
    FridgeMcpTools::RestoreCanvasLayout();
    vTaskDelete(nullptr);
}, "restore_layout", 16384, nullptr, 5, nullptr);
```

## CustomPageManager Singleton

Located in `Fridge/fridge_mcp.cc` (static functions) — not a separate class.
In the v2 implementation, a proper `CustomPageManager` class was added in
`Fridge/custom_page_manager.{h,cc}` with:
- Page registry CRUD (custom_pages.json)
- Layout save/load per page (page_N.json)
- Element add/update/remove/clear
- Label prefix management

**CRITICAL**: The `GetInstance()` static method must be defined in the `.cc`
file, not just declared in the `.h`. Forgetting the definition causes
`undefined reference to _ZN17CustomPageManager11GetInstanceEv` at link time.
The compiler won't catch this — it's a link-time error only. The `nm` command
on the `.obj` file is the fastest diagnostic: if `GetInstance` shows as `W`(weak)
in the object file but has no `T`(text) symbol, the definition is missing.

## Testing Workflow (Verified on Hardware)

After flashing new MCP tools, test each tool via curl using the `/api/call`
endpoint (NOT `/mcp` — the local_control HTTP handler uses `{"tool":"...","args":{}}`
format, not JSON-RPC `{"jsonrpc":"2.0","method":"tools/call","params":{}}`).
Using the wrong format returns `{"error":"Missing 'tool' field"}` — this is
the #1 gotcha when testing MCP tools via curl.

Full test sequence (all 9 tools):
1. `page.list` — initial state, should return 6 built-in pages only
2. `page.create` × 2 — should return page 7, then page 8
3. `page.list` — verify both custom pages appear with `builtin: false`
4. `page.rename` — rename page 7
5. `element.add` (text) — with `refresh: true` to trigger screen update
6. `element.add` (rect) — with `refresh: false` (batch mode)
7. `element.add` (dynamic text) — with `dynamic: true` flag
8. `element.add` (line) — **must include `x` and `y` params** (they're required
   for all element types even though line uses x1/y1/x2/y2 for coordinates)
9. `element.list` — verify all 4 elements returned with correct properties
10. `pagemanager` — switch to page 7, screen should show the custom layout
11. `element.update` × 3 — push new text values (e.g. "14:30" → "14:31"),
    each with `refresh: true` — screen refreshes each time
12. `element.remove` — delete one element, verify via `element.list`
13. `page.clear` — clear a different page
14. `page.delete` — delete a page, verify via `page.list`
15. **Persistence test**: reboot device, then `page.list` + `element.list`
    should show the page and elements fully restored
16. **Boundary test**: `page.delete { page: 1 }` should be rejected
    (returns error: `"Value is below minimum allowed: 7"`)

## element.add x/y Required for Line Type

The `fridge.page.element.add` MCP tool has `x` and `y` as required parameters
(range 0-295 and 0-127). When adding a `line` element, the actual coordinates
come from `x1/y1/x2/y2`, but `x` and `y` must still be provided (can be 0)
to pass parameter validation. Omitting them returns:
`{"error":"Missing valid argument: x"}`

## Layout File Format (page_N.json)

```json
{
  "page": 7,
  "elements": [
    {"type":"text","id":"title","text":"B站粉丝数","x":148,"y":5,"font_size":16,"align":"center"},
    {"type":"text","id":"fan_count","text":"12,345","x":148,"y":40,"font_size":24,"align":"center"},
    {"type":"rect","id":"box","x":20,"y":30,"w":256,"h":40,"filled":false}
  ]
}
```

## Dynamic Element Examples

| Scenario | Cron Frequency | Data Source | Pushed Text |
|----------|---------------|-------------|-------------|
| B站粉丝数 | 5 min | bilibili API | `"12,345 粉丝"` |
| 天气 | 30 min | weather API | `"晴 23°C"` |
| 生日倒计时 | daily | local calc | `"还有 170 天"` |
| 正向计时 | 1 min | local calc | `"已运行 42天3小时"` |
| 股价 | 5 min (trading) | stock API | `"¥3,456.78 ↑2.3%"` |
| 冰箱统计 | 10 min | `fridge.stats.summary` | `"3件 · 1即将过期"` |
| 黄金价格 | 60 min | `api.gold-api.com/price/XAU` | `"¥892.6/g"` |

### Concrete Example: Gold Price Cron Job (Verified)

A cron job that fetches gold prices hourly and pushes to a split-screen todo page.

**Cron config**: `schedule: "every 60m"`, `no_agent: true`, `script: "gold_price_update.sh"`

**Script** (`scripts/gold_price_update.sh`):
```bash
#!/bin/bash
# Fetch gold price (CNY/oz → CNY/g) and push to xiaozhi e-paper page 7
IP="<IP>"
RESP=$(curl -s --max-time 10 "https://api.gold-api.com/price/XAU/CNY")
PRICE_CNY_OZ=$(echo "$RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['price'])")
PRICE_CNY_G=$(python3 -c "print(f'{$PRICE_CNY_OZ/31.1035:.1f}')")
HHMM=$(date '+%H:%M')
curl -s -X POST "http://$IP:8080/api/call" -H "Content-Type: application/json" \
  -d "{\"tool\":\"fridge.page.element.update\",\"args\":{\"page\":7,\"id\":\"gold_price\",\"text\":\"¥${PRICE_CNY_G}/g\",\"refresh\":false}}"
curl -s -X POST "http://$IP:8080/api/call" -H "Content-Type: application/json" \
  -d "{\"tool\":\"fridge.page.element.update\",\"args\":{\"page\":7,\"id\":\"gold_time\",\"text\":\"${HHMM}更新\",\"refresh\":true}}"
echo "金价已更新: ¥${PRICE_CNY_G}/g (${HHMM})"
```

**Key details**:
- `api.gold-api.com/price/XAU/CNY` returns `{price, currency, exchangeRate}` — price is already in CNY per troy oz
- Conversion: `price_cny / 31.1035` (1 troy ounce = 31.1035 grams)
- Cron uses `no_agent=true` + script — the script IS the job, stdout is delivered verbatim
- `gold_price` uses `refresh:false`, `gold_time` uses `refresh:true` — only one refresh for both updates

## Device-Side Dynamic Elements (dynamic_type)

For high-frequency updates (clock, CPU temp, heap), having the Agent push updates
every second via cron is impractical. Instead, the device self-updates these
elements using the existing `EpaperLabel::TextValue` lambda mechanism.

### How It Works

1. `element.add` with `dynamic_type: "clock"` → `CustomPageManager::AddElement()`
   creates a `TextValue` with a lambda: `[dtype]() { return FormatDynamicValue(dtype); }`
2. The lambda captures `dtype` by value (string copy, safe for C++ lambdas)
3. On every render cycle, `TextValue::operator()()` calls the lambda → real-time value
4. `application.cc` has a 1-second `esp_timer` (clock_timer) that sets `MAIN_EVENT_CLOCK_TICK`
5. The main loop's CLOCK_TICK handler calls `CustomPageManager::GetInstance().TickDynamicUpdate()`
6. `TickDynamicUpdate()` checks: (a) is current_page a custom page (7-15)?
   (b) does it have any labels with `dynamic_type[0] != '\0'`?
   If yes → `DisplayLockGuard lock(epaper); epaper->UpdateUI(false);` (partial refresh)
7. The partial refresh re-renders all labels on the current page, each lambda re-evaluates

### Supported dynamic_type Values

| dynamic_type | Output Format | Data Source | Update Frequency |
|---|---|---|---|
| `clock` | `HH:MM` | `strftime` + `localtime_r` | effective every 1s (visible change every 1 min) |
| `date` | `YYYY-MM-DD 周X` | `strftime` + Chinese weekday names | effective every 1s (visible change every 1 day) |
| `datetime` | `MM-DD HH:MM` | `strftime` | effective every 1s (visible change every 1 min) |
| `cpu_temp` | `XX.X°C` | `temperature_sensor_get_celsius()` (new `driver/temperature_sensor.h` API) | every 1s |
| `heap` | `Heap: XXKB` | `esp_get_free_heap_size()` | every 1s |
| `uptime` | `Up: Xd Xh Xm` | `esp_timer_get_time() / 1000000ULL` | every 1s (visible change every 1 min) |

### Persistence

The `dynamic_type` is stored as `dtype` field in `page_N.json`:
```json
{"type":"text","id":"clock","text":"14:31","x":10,"y":5,"font_size":16,"align":"left","dtype":"clock"}
```

On boot, `LoadPageLayout()` parses the `dtype` field. If present, it creates a
lambda-based `TextValue` instead of a static string. The `dynamic_type[16]` field
on `EpaperLabel` is also set via `strncpy` so `TickDynamicUpdate()` can detect it.

### Firmware Changes Required

6 files modified:
1. `epaperui.h` — `EpaperLabel` gains `char dynamic_type[16] = {0};`
2. `custom_page_manager.h` — adds `FormatDynamicValue()` (returns `std::string`, not Arduino `String`), `TickDynamicUpdate()` (public)
3. `custom_page_manager.cc` — `AddElement()` creates lambda when `dynamic_type` non-empty;
   `SavePageLayout()` writes `dtype` field; `LoadPageLayout()` parses `dtype` and creates lambda;
   `ListElements()` outputs `dtype` if present
4. `fridge_mcp.cc` — `elem_add_props` gains `dynamic_type` property;
   `HandleElementAdd` parses and passes it
5. `epaper_display.h` — exposes `uint16_t GetCurrentPage() const { return current_page_; }`
6. `application.cc` — CLOCK_TICK handler calls `CustomPageManager::GetInstance().TickDynamicUpdate()`

### ESP-IDF API Pitfalls

Three compilation errors encountered when implementing device-side dynamics:

1. **`esp_timer_get_seconds()` does NOT exist** — Despite the name, this is not a real ESP-IDF API. The correct function is `esp_timer_get_time()` (returns microseconds as `int64_t`). Convert: `(uint64_t)(esp_timer_get_time() / 1000000ULL)`.

2. **Temperature sensor: new vs deprecated API** — ESP-IDF v5.4.2 has two APIs:
   - New: `#include "driver/temperature_sensor.h"` → `temperature_sensor_install()`, `temperature_sensor_enable()`, `temperature_sensor_get_celsius()` (handle-based)
   - Deprecated: `#include "driver/temp_sensor.h"` → `temp_sensor_start()`, `temp_sensor_read_celsius()` (global)
   
   The new API header is at `esp_driver_tsens/include/driver/temperature_sensor.h`. The deprecated one is at `components/driver/deprecated/driver/temp_sensor.h`. Mixing function names from different APIs causes `was not declared in this scope` errors. Use the new API with lazy init (install+enable on first call, read on subsequent calls).

3. **`String` (Arduino) vs `std::string` in headers** — If `FormatDynamicValue()` is declared as `static String FormatDynamicValue(...)` in the `.h` but the `.h` doesn't `#include <Arduino.h>`, you get `'String' does not name a type`. Fix: declare the function as `static std::string FormatDynamicValue(...)` in the header, and in the `.cc` wrap the return for lambda use: `[dtype]() -> String { return String(CustomPageManager::FormatDynamicValue(dtype).c_str()); }`. The explicit `-> String` return type + `.c_str()` wrapping is needed because the compiler can't auto-convert `std::string` to `String` inside a lambda return.

### Key Design Decisions

- **Partial refresh only** (`UpdateUI(false)`) — full refresh wears the e-paper faster.
  The existing `UpdateUI(false)` uses `setPartialWindow()` which is less harsh.
- **Only refreshes when on a custom page** — `TickDynamicUpdate()` returns early
  if `current_page_ < 7 || current_page_ > 15`, so built-in pages are unaffected.
- **Only refreshes if dynamic elements exist** — scans labels for `dynamic_type[0] != '\0'`
  before refreshing. A static-only custom page won't trigger unnecessary refreshes.
- **Lambda captures dtype by value** — `std::string` copy in lambda capture, safe
  for the label's lifetime (lambda stored inside `TextValue::func_`).
- **1-second tick is sufficient** — clock changes every 60s, temp/heap change
  every 1s but partial refresh is fast enough. No need for a separate timer.

### Mixing Device-Side and Agent-Pushed Dynamics

A single page can have both:
- `dynamic_type: "clock"` → device updates the time automatically
- `dynamic: true` (no dynamic_type) → Agent pushes text via `element.update`

Example: A weather page with `clock` (device-side) + `weather_text` (cron
every 30 min). The clock updates every second without the Agent; the weather text
updates when the Agent pushes new data. Both coexist on the same page.

### Creating a Device-Side Dynamic Element

```bash
curl -X POST http://<IP>:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.page.element.add","args":{"page":8,"id":"clock","type":"text","text":"--:--","x":10,"y":5,"font_size":16,"align":"left","dynamic_type":"clock","refresh":true}}'
```

The `text` field is the initial value (shown briefly before first lambda render).
After the first `TickDynamicUpdate()` tick (≤1 second), the lambda overwrites it
with the real-time value.

### 6 Verification Pages

When implementing device-side dynamics, create 6 pages to validate the system
covers most use cases:

| # | Page Name | Dynamic Elements | Static Elements |
|---|---|---|---|
| 1 | 时间+天气 | `clock` + `date` | Weather text (Agent push) |
| 2 | 每日一句 | — | Quote text + separator |
| 3 | Pixel Art | — | Image bitmap |
| 4 | CPU Dashboard | `cpu_temp` + `heap` + `uptime` | Frame/labels |
| 5 | 节假日倒计时 | — | Agent cron pushes countdown days |
| 6 | 今日 Focus | — | Static text |

Pages 1 and 4 test device-side dynamics. Pages 2, 3, 5, 6 test static layouts,
Agent-pushed dynamics, image rendering, and minimal layouts respectively.

## Custom Page Element Persistence (Critical Bug Fix)

**Bug 1**: `CustomPageManager::UpdateElementText()` updated `label->text` in RAM but
did NOT call `SavePageLayout(page)`. Text updates via `fridge.page.element.update`
were lost on reboot — elements themselves persisted (AddElement/RemoveElement
both call SavePageLayout), but their current text values reverted to the values
saved at add-time.

**Symptom**: User marks todo items as "已完成" via `element.update`, reboots
device, all text reverts to original values. Gold price pushed by cron also
reverts. Element positions/types are intact — only text content is lost.

**Root cause**: `UpdateElementText()` at line ~354 of `custom_page_manager.cc`:
```cpp
// BUG (before fix):
label->text = text.c_str();
// Missing: SavePageLayout(page);
return true;

// FIX (applied):
label->text = text.c_str();
SavePageLayout(page);  // ← persist to /canvas/page_N.json
return true;
```

**Bug 2**: `LoadPageLayout()` JSON parser failed to restore elements after reboot.
`page_N.json` contained all elements but only 0-1 were restored.

**Root cause**: The parser scanned for `{` from position 0 in the file buffer.
But the file format is `{"page":7,"elements":[{...},{...}]}`. The first `{` is
the **outer wrapper object**, not an element. The depth-based `{}`
matching consumed the entire file as one object, so only 0-1 elements were
parsed.

**Fix**: Skip past the wrapper to the `[` character before scanning:
```cpp
// BAD:  const char* p = buf;  // matches outer { first
// GOOD: const char* p = strstr(buf, "[");  // skip to elements array
//       if (!p) { free(buf); return; }
```

**Lesson**: When using hand-rolled JSON parsers (not cJSON), always handle
wrapper objects. If the format is `{"wrapper_key":...,"elements":[...]}`,
scan for `[` first to enter the array, then scan for individual `{` objects.

## Font Size Selection (Device Limitation)

The device supports only TWO font sizes for custom page text elements:
- `font_size <= 12` → `u8g2_font_wqy12_t_gb2312` (12px Chinese font)
- `font_size > 12` → `u8g2_font_wqy16_t_gb2312` (16px Chinese font)

This is hardcoded in `custom_page_manager.cc` AddElement() and LoadPageLayout().
Passing `font_size=10` still renders at 12px (the smallest available). Passing
`font_size=14` renders at 16px. Use 12 for compact layouts, 16 for readable headers.

## Split-Screen Layout Pattern

For pages showing two independent data zones (e.g. todo list + live price),
use a vertical divider line at x=185 to split the 296px screen:

```
┌────────────────────────────────┬───────────────┐
│ Left zone (x: 0-184)           │ Right (186-295)│
│ ~185px wide                    │ ~110px wide    │
└────────────────────────────────┴───────────────┘
```

- Left: 185px = ~9 Chinese chars at 16px, ~12 at 12px
- Right: 110px = ~5 Chinese chars at 16px, ~7 at 12px
- Vertical line: `element.add { type:"line", x1:185, y1:2, x2:185, y2:108, width:1 }`
- Horizontal separator for title area: `y1=18` (for 12px font) or `y1=20` (for 16px)

## Compact Todo List Layout (12px Font)

When 16px font is too large, use 12px font with tighter spacing:

```
 y=0  待办事项                                (title, font=12, x=8, y=2)
 y=18 ════════════ separator line ════════════
 y=22  ☐ 买菜                                 (item1, font=12, x=18, y=22)
 y=36  ☐ 做饭                                 (item2, font=12, x=18, y=36)
 y=50  ☐ 写日记                               (item3, font=12, x=18, y=50)
 ...
 y=112 说"提醒我..."添加待办                  (hint, font=10→12, x=8, y=112)
```

- Row spacing: 14px (vs 20px for 16px font)
- Checkbox: 6×6 rect (vs 8×8 for 16px font)
- Separator at y=18 (vs y=20 for 16px font)
- Left text x=18 (vs x=20 for 16px font, tighter gap with smaller box)

## Web Console Integration

The web console (`xiaozhi.html` + `js/xiaozhi.js`) was extended to support
multi-page management. Key patterns:

### Page Selector (Canvas Tab)

A dropdown + action buttons at the top of the canvas tab:

```html
<div class="page-selector" id="pageSelector">
  <div class="page-selector__main">
    <label>编辑页面</label>
    <select id="customPageSelect">
      <option value="6">默认画布 (Page 6)</option>
      <!-- 动态填充 7-15 -->
    </select>
  </div>
  <div class="page-selector__actions">
    <button id="newPageBtn">+ 新建页面</button>
    <button id="renamePageBtn">重命名</button>
    <button id="deletePageBtn">删除</button>
  </div>
</div>
```

State tracking: `state.canvas.currentPage` (default 6) and `state.canvas.pages`
(loaded from `fridge.page.list` on connect).

### Page-Aware Tool Routing (CRITICAL)

Every canvas operation checks `state.canvas.currentPage` and routes to the
correct MCP tool:

| Operation | Page 6 (canvas) | Page 7+ (custom) |
|-----------|-----------------|-------------------|
| Load elements | `fridge.canvas.list` | `fridge.page.element.list { page }` |
| Add text | `fridge.canvas.add_text` | `fridge.page.element.add { page, type:"text", ... }` |
| Add rect | `fridge.canvas.add_rect` | `fridge.page.element.add { page, type:"rect", ... }` |
| Add line | `fridge.canvas.add_line` | `fridge.page.element.add { page, type:"line", x:0, y:0, ... }` |
| Remove | `fridge.canvas.remove { id }` | `fridge.page.element.remove { page, id }` |
| Clear | `fridge.canvas.clear` | `fridge.page.clear { page }` |
| Refresh | `fridge.canvas.refresh` | `fridge.pagemanager { target_page: page }` |

**Line type pitfall**: `page.element.add` requires `x`/`y` params even for
lines (which use `x1/y1/x2/y2`). Always pass `x:0, y:0` when adding a line.

### Dynamic Element UI

On custom pages (7+), all text elements get:
- 📡 icon next to the type label in the element list
- An "更新" (Update) button that calls `page.element.update`

**Why ALL text elements get 📡 (not just those added with `dynamic: true`)**:
The `dynamic` flag passed to `element.add` is accepted by the MCP tool but is
NOT persisted to the layout file (`page_N.json`). Consequently, `element.list`
does NOT return a `dynamic` field. Rather than tracking dynamic state locally
in the web UI (which would be lost on page reload), the simpler design treats
ALL text elements on custom pages as potentially dynamic — any text element
can be updated via `element.update` at any time, so the `dynamic` flag is
redundant on the device side. The flag remains useful as a UI hint during
element creation, but after that, every text element on page 7+ shows the
📡 icon and update button.

```javascript
function updateDynamicElement(page, id) {
  var newText = prompt('输入新的文本值：');
  if (newText === null) return;
  api.callTool('fridge.page.element.update',
    { page: page, id: id, text: newText, refresh: true })
    .then(function () { loadCanvasElements(); });
}
```

### Page Switching Tab Integration

`renderPageCards()` merges the static `PAGES` array (built-in 1-6) with
`state.canvas.pages` (custom 7-15) so the page switching tab shows all pages.
`loadCustomPages()` is called on connect success and refreshes both the
page selector dropdown and the page cards grid.

### Connected Flow

```
connect() success
  → loadFridgeData()
  → loadCustomPages()     ← NEW: loads page.list, renders selector + cards
  → loadCanvasElements()  ← routes to canvas.list or page.element.list
```

## Page Inspection & Layout Audit

When the user asks "检查自定义页面" or "what's on the custom pages" or "is the
layout reasonable", use this remote audit sequence — no screenshot needed.

### API Call Sequence

```bash
IP=<IP>  # or use discovery script

# 1. List all pages (builtin + custom)
curl -s -X POST http://$IP:8080/api/call -H 'Content-Type: application/json' \
  -d '{"tool":"fridge.page.list","args":{}}'

# 2. For each custom page (7-15), list its elements
curl -s -X POST http://$IP:8080/api/call -H 'Content-Type: application/json' \
  -d '{"tool":"fridge.page.element.list","args":{"page":7}}'
# repeat for page 8, 9, ...

# 3. List canvas elements (page 6)
curl -s -X POST http://$IP:8080/api/call -H 'Content-Type: application/json' \
  -d '{"tool":"fridge.canvas.list","args":{}}'

# 4. List stored images in LittleFS (includes test remnants)
curl -s http://$IP:8080/api/canvas_image

# 5. (Optional) Switch to a page for visual verification on the physical screen
curl -s -X POST http://$IP:8080/api/call -H 'Content-Type: application/json' \
  -d '{"tool":"fridge.pagemanager","args":{"target_page":7}}'
```

### ASCII Layout Visualization

Convert element JSON into an ASCII diagram to check spatial layout remotely.
Screen is 296×128 pixels. Example for page 7 with 3 elements:

```
Elements: rect(box: x=20,y=30,w=256,h=60), text(clock: "14:31" x=148,y=40,font=16,center), line(sep: x1=20,y1=25,x2=276,y2=25)

 y=0
 ┌──────────────────────────────────────────────────────────┐
 │  (empty 0-25)                                            │
 y=25  ═══════ line "sep" (x:20→276) ═════════════════════════
 y=30  ┌──── rect "box" (x=20,y=30,w=256,h=60) ───────────┐  │
 │     │          text "clock" = "14:31" (y=40)          │  │
 y=90  └────────────────────────────────────────────────────┘  │
 │  (empty 90-128)                                          │
 y=128└──────────────────────────────────────────────────────────┘
      x=0       x=20                                    x=276  x=296
```

### Layout Review Checklist

When auditing custom pages, check for:

1. **Static text that should be dynamic** — e.g. a clock page showing a fixed
   time ("14:31") instead of updating via cron + `element.update`
2. **Vertical centering** — for text inside a rect (y=Y0, h=H) with font_size F,
   centered y = `Y0 + (H - F) / 2`. E.g. rect y=30 h=60, font 16 → y=52 (not 40)
3. **Test remnant pages** — names like `__test_tmp__`, single generic elements
   ("updated", "test", "dyn1") — these should be deleted via `page.delete`
4. **Wasted screen space** — large empty regions (e.g. 38px bottom margin on
   a 128px screen = 30% wasted). Consider adding useful info there
5. **Orphaned separator lines** — a line at y=25 with nothing above it serves
   no visual purpose; either add a title above or remove the line
6. **Out-of-bounds coordinates** — any x > 295, y > 127, or x+w > 296, y+h > 128
7. **Element ID collisions** — same ID on different elements on the same page
   (the device treats same-ID add as replacement, so the first element is lost)
8. **Stored image cleanup** — `GET /api/canvas_image` may show test images
   (test_face, test_manual, proxy_test) that can be cleaned up
9. **Page name vs actual content mismatch** — a page named "时钟桌面" but
   showing static time text, or "时钟桌面" repurposed to "待办事项" without
   renaming. Always `page.rename` when repurposing a page.

## Element Limits

- Max 30 elements per custom page
- Max 9 custom pages (7-15)
- Each `EpaperLabel` ~100 bytes → 30 × 9 = 270 labels max ≈ 27KB (well within 512KB SRAM)
- Layout files: ~4KB each × 9 = 36KB total (within 2MB LittleFS)
