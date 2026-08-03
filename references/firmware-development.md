# xiaozhi-esp32 Firmware Development Reference

Details for building, flashing, and modifying the xiaozhi-esp32 firmware.
The skill focuses on LAN control; this file covers firmware-level work.

## Build & Flash

```bash
source ~/esp/esp-idf/export.sh
cd <path-to>/xiaozhi-esp32
idf.py build
idf.py -p /dev/ttyUSB0 flash
```

- ESP-IDF v5.4.2 at `~/esp/esp-idf`
- Serial: `/dev/ttyUSB0` (needs `sudo chmod 666` after reboot)
- Active board: `bread-compact-wifi-epaperx`
- Flash: 16MB, partition table `partitions/v2/16m.csv`

## Partition Table (16MB Flash)

```
nvs:          0x9000    16KB
otadata:      0xD000    8KB
phy_init:     0xF000    4KB
ota_0:        0x20000   ~4MB (app)
ota_1:        auto      ~4MB (OTA backup)
assets:       0x800000  6MB  (SPIFFS: fonts, emoji, sounds)
canvas_data:  0xE00000  2MB  (LittleFS: uploaded canvas images)
```

**Changing the partition table** requires `idf.py fullclean` and flashing all partitions, not just the app.

## Key Source Files

| File | Role |
|------|------|
| `main/display/epaperdisplay/epaper_display.{h,cc}` | E-paper display engine: `EpaperLabel` system, `SetPage()`, `AddLabel()`, `UpdateUI()` |
| `main/display/epaperdisplay/epaperui.h` | `EpaperLabel` class: 8 object types (TEXT/RECT/LINE/BITMAP/CIRCLE/TRIANGLE/ROUND_RECT/PIXEL), factory functions |
| `main/boards/bread-compact-wifi-epaperx/Fridge/fridge_mcp.{h,cc}` | All MCP tool registration + handlers (fridge + canvas) |
| `main/boards/bread-compact-wifi-epaperx/local_control.{h,cc}` | HTTP server (port 8080), mDNS, LittleFS mount, image upload endpoint |
| `main/boards/bread-compact-wifi-epaperx/compact_wifi_board_epaperx.cc` | Board init, `InitializeTools()`, `DECLARE_BOARD` |

## Adding a New MCP Tool

1. **Register** in `fridge_mcp.cc::Initialize()`: `AddTool("fridge.xxx", desc, props, lambda)`
2. **Declare** handler in `fridge_mcp.h`: `ReturnValue HandleXxx(const PropertyList& properties);`
3. **Implement** handler in `fridge_mcp.cc`
4. **Update page range** if tool uses `fridge.pagemanager`: both the Property max (`kPropertyTypeInteger, 1, N`) and the `HandlePageManager` range check
5. **Build & flash**: `idf.py build && idf.py -p /dev/ttyUSB0 flash`

## Adding a New E-Paper Page

1. Add to `EpaperPage` enum in `epaper_display.h`
2. Update `fridge.pagemanager` Property max and `HandlePageManager` range check
3. Add labels in `SetupUI()` with `page = N`
4. If the page needs dynamic content, add a method like `SetRecipeContent()` / `ShowCanvasPage()`

## Canvas Image Format

1-bpp (black/white) raw bitmap:
- MSB first (bit 7 = leftmost pixel)
- Each row padded to byte boundary
- 1 = black, 0 = white
- Size = `ceil(w/8) * h` bytes
- For a 64x64 image: 512 bytes

### Generating test bitmaps from the host

```python
# Generate a 64x64 1-bpp heart bitmap using the heart inequality
# (x² + y² - 1)³ - x²y³ ≤ 0
W, H = 64, 64
row_bytes = (W + 7) // 8
bitmap = bytearray(row_bytes * H)
cx, cy = 32, 32
for py in range(H):
    for px in range(W):
        x = (px - cx) / 16.0
        y = -(py - cy) / 16.0
        if (x*x + y*y - 1)**3 - x*x * y*y*y <= 0:
            byte_idx = py * row_bytes + (px // 8)
            bitmap[byte_idx] |= (1 << (7 - (px % 8)))
with open("/tmp/heart_64x64.bin", "wb") as f:
    f.write(bitmap)
```

Then upload: `curl -X POST "http://<IP>:8080/api/canvas_image?name=heart" --data-binary @/tmp/heart_64x64.bin`

## LittleFS Integration

- Component: `joltwallet__littlefs` (managed_component)
- Mount: `esp_vfs_littlefs_register()` with `base_path="/canvas"`, `partition_label="canvas_data"`
- Config struct uses `base_path` (not `mount_point`) -- this version's API differs from SPIFFS
- `format_if_mount_failed=true` on first mount auto-formats the partition

## Recipe Recommend: Missing Ingredient Detection

The `HandleRecipeRecommend` function in `fridge_mcp.cc`:
1. Splits `required_ingredients` by comma (supports UTF-8 Chinese comma)
2. Checks each against fridge items via bidirectional substring match (case-insensitive)
3. `fridge_only` mode: rejects if any missing, returns error with list
4. `mixed_purchase` mode: auto-fills `extra_ingredients` with missing items
5. Returns `missing_ingredients` field in JSON response

## Canvas Layout Persistence (LittleFS)

Canvas text/lines/rects/**images** are auto-saved to `/canvas/layout.json` on every `add`/`remove`/`clear` operation via `SaveCanvasLayout()`, and restored on boot via `LoadCanvasLayout()`.

**CRITICAL**: `LoadCanvasLayout()` must NOT be called from `FridgeMcpTools::Initialize()` — at that point LittleFS is not yet mounted (mount happens later in `LocalControl::Start()` → `MountCanvasStorage()`, after WiFi connects). Instead, call it from `MountCanvasStorage()` after `esp_vfs_littlefs_register()` succeeds, via `FridgeMcpTools::RestoreCanvasLayout()` (a public static method). Symptoms of calling too early: `fopen("/canvas/layout.json")` silently returns NULL, no layout restored, no error logged.

**Layout format** (`/canvas/layout.json`):
```json
[
  {"type":"text","id":"title","text":"...","x":10,"y":5,"font_size":16,"align":"center","max_width":276},
  {"type":"line","id":"div","x1":10,"y1":28,"x2":286,"y2":28,"width":2},
  {"type":"rect","id":"box","x":8,"y":33,"w":280,"h":60,"filled":false}
]
```

**Image persistence**: As of the latest firmware, images ARE persisted in layout.json. The `EpaperLabel` struct has an `image_name[32]` field (added in `epaperui.h`), set via the `Bitmap()` factory's optional `image_name` parameter. `SaveCanvasLayout()` writes `{"type":"image","id":"...","name":"...","x":...,"y":...,"w":...,"h":...}` entries. `LoadCanvasLayout()` re-reads the image file from LittleFS (`/canvas/<name>`) and recreates the bitmap. Both the layout entry and the image file itself must survive — if the image file is deleted from LittleFS, the restore will silently skip it (logs a warning).

**Parser limitations**:
- The parser is hand-rolled (not cJSON), so field names must match exactly.
- `"font_size":` is 12 characters including quotes and colon — the atoi offset must be `pos + 12`, not `pos + 13`. Same for `"max_width":`. An off-by-one here causes font_size to silently default to 0, which selects the wrong u8g2 font and renders text at the wrong size after reboot.

**Canvas label management**:
- **Max 30 canvas labels** (`CANVAS_MAX_LABELS`): `CheckCanvasLabelLimit()` checks count before each `add` operation. If the same `id` already exists (replacement, not new), it's allowed regardless of count. When the limit is reached, the call returns `"Canvas label limit reached (30). Call fridge.canvas.clear first."`.
- **`SaveCanvasLayout()` with 0 labels**: deletes `layout.json` via `unlink()` instead of writing `[]`. This prevents file accumulation on a blank canvas.
- **`HandleCanvasClear`**: calls `unlink(CANVAS_LAYOUT_FILE)` directly (not `SaveCanvasLayout`) to delete the file, keeping storage clean.
- **Without these guards**: labels accumulate across reboots (LoadCanvasLayout restores old labels, user adds new ones without clearing, SaveCanvasLayout saves all). A device used 20+ times without explicit `canvas.clear` can accumulate 100+ labels, inflating layout.json to 8KB+ of overlapping/hidden controls. The 30-label limit + delete-on-empty prevents this.

**Key functions** in `fridge_mcp.cc`:
- `SaveCanvasLayout()` — iterates `epaper->GetAllLabels()`, writes canvas-prefixed labels to file; deletes file if 0 labels
- `LoadCanvasLayout()` — reads file, parses JSON objects, recreates `EpaperLabel` instances
- `CountCanvasLabels()` — counts `canvas_`-prefixed labels currently in memory
- `CheckCanvasLabelLimit(full_id)` — returns false if at limit and ID is new (not replacement)
- `FridgeMcpTools::RestoreCanvasLayout()` — public static, called from `LocalControl::MountCanvasStorage()` after LittleFS mount
- `EpaperDisplay::GetAllLabels()` — returns `&ui_labels_` map pointer for external iteration
- `EpaperDisplay::ClearCanvasLabels()` — removes all `canvas_`-prefixed labels, returns count

## Critical Runtime Pitfalls

### Stack Overflow in RestoreCanvasLayout (crash loop)

**Symptom**: Device enters boot loop — `***ERROR*** A stack overflow in task pthread has been detected.` immediately after `CustomPageMgr: Loaded N custom pages from registry`.

**Root cause**: `FridgeMcpTools::RestoreCanvasLayout()` was called directly from `LocalControl::MountCanvasStorage()`, which runs in the WiFi callback's pthread context. `LoadPageLayout()` allocates multiple `std::string` locals and does hand-rolled JSON parsing — the pthread stack (~4KB) is not enough.

**Fix**: Wrap the call in a dedicated FreeRTOS task with a larger stack:
```cpp
// In LocalControl::MountCanvasStorage(), AFTER esp_vfs_littlefs_register():
xTaskCreate([](void* arg) {
    FridgeMcpTools::RestoreCanvasLayout();
    vTaskDelete(nullptr);
}, "restore_layout", 16384, nullptr, 5, nullptr);
```

**Diagnostic**: The crash log shows `CustomPageMgr: Loaded N custom pages from registry` followed immediately by the stack overflow error and a backtrace. The crash happens during `LoadPageLayout()`, not during `LoadRegistry()`.

### LoadPageLayout JSON Parser Bug (elements not restored)

**Symptom**: After reboot, custom page elements are not restored — `element.list` returns `[]` or only 1 element, even though `page_N.json` on LittleFS contains all elements.

**Root cause**: The hand-rolled JSON parser scans for `{` from position 0. But the file format is `{"page":7,"elements":[{...},{...}]}`. The first `{` is the **outer wrapper object**, not an element. The depth-based `{}` matching consumes the entire file as one "object" (the outer `}` matches the opening `{`), so the parser only processes 0 or 1 elements.

**Fix**: Skip past the outer wrapper to the `[` character before scanning for element objects:
```cpp
const char* p = strstr(buf, "[");  // skip {"page":N,"elements":
if (!p) { free(buf); return; }
```

**Lesson**: When using hand-rolled JSON parsers (not cJSON), always handle the wrapper object. If the format is `{"wrapper_key":...,"elements":[...]}`, scan for `[` first to enter the array, then scan for individual `{` objects inside.

## Device State & E-Paper Page Auto-Switch

The ESP32 has a `DeviceState` enum (`main/device_state.h`) and the e-paper has a `current_page_` (default `HOME_PIC_DISPLAY` = page 5, NOT page 1). When the device enters certain states, the e-paper must be on CHAT_PAGE (page 1) so the user can see connection hints.

**Key states** (`device_state.h`):
| State | Meaning |
|-------|---------|
| `kDeviceStateStarting` | Boot/initial state |
| `kDeviceStateWifiConfiguring` | AP config mode (no WiFi credentials) |
| `kDeviceStateActivating` | Checking OTA/server version |
| `kDeviceStateIdle` | Ready, standby |
| `kDeviceStateConnecting` | Opening audio channel |

**Where states are set** (`application.cc`):
- `Start()`: `kDeviceStateStarting` (line 367)
- `CheckNewVersion()`: `kDeviceStateActivating` (line 136)
- `EnterWifiConfigMode()` (`wifi_board.cc:37`): `kDeviceStateWifiConfiguring` — called when `force_ap=1` or no SSID configured or WiFi connect timeout 60s
- `protocol_->OnConnected()`: → `DismissAlert()` → sets idle (line 456)

**`SetDeviceState()`** (`application.cc:720`) switch handles `kDeviceStateIdle/Connecting/Listening/Speaking` but `kDeviceStateStarting` and `kDeviceStateWifiConfiguring` fall through to `default` → **no e-paper page switch**.

**The bug**: If the user is on page 5 (default) or any non-CHAT page when the device boots into config mode or initial connection, they won't see the WiFi/server connection hints because `EnterWifiConfigMode()` calls `Alert()` which updates `chat_message_label` (on page 1 only). The e-paper `current_page_` stays at its default (page 5).

**Fix**: In `SetDeviceState()`, add a case for `kDeviceStateStarting` and `kDeviceStateWifiConfiguring` that calls `display_epaper->SetPage(CHAT_PAGE)` (value 1, from `EpaperPage` enum in `epaper_display.h`). This ensures the user always sees connection prompts when the device is in a pre-connected state.

**CRITICAL PITFALL — `audio_service_` not yet initialized during `kDeviceStateStarting`**: The first version of this fix also called `audio_service_.EnableVoiceProcessing(false)` and `audio_service_.EnableWakeWordDetection(true)` inside the `kDeviceStateStarting` case. This caused an immediate crash — `Guru Meditation Error: Core 0 panic'ed (LoadProhibited)` — because `SetDeviceState(kDeviceStateStarting)` is called at `application.cc` line 367 (the very first line of `Start()`), but `audio_service_.Initialize()` is not called until line 380. Calling methods on an uninitialized `std::unique_ptr<AudioProcessor>` dereferences a null pointer. **The fix is to ONLY call `display_epaper->SetPage(CHAT_PAGE)` in the Starting/WifiConfiguring cases — do NOT touch `audio_service_`, `display->SetStatus()`, or `display->SetEmotion()` in those branches.** Those are handled later in the normal state flow (e.g. when transitioning to `kDeviceStateIdle`).

**`SetPage()`** (`epaper_display.cc:721`): sets `current_page_` and calls `UpdateUI(true)` (full refresh) if the page actually changed.

## E-Paper Chat Page (Page 1) Layout Customization

The chat page layout is defined entirely in `EpaperDisplay::SetupUI()` (`epaper_display.cc` line ~475). All labels are created via `AddLabel(id, new EpaperLabel(EpaperLabel::Text/Bitmap/Line(...)))` with the last parameter being the page number (1 for CHAT_PAGE).

### EpaperLabel Factory Parameters

From `epaperui.h`:

- **Text**: `EpaperLabel::Text(TextValue text, x, y, max_width, h, font_height, u8g2_font, color, align, rotation, visible, invert, page)`
  - `x, y`: top-left corner (y is auto-adjusted: `obj.y = y + font_height` to align baseline)
  - `max_width`: text wrapping width, 0 = no limit
  - `font_height`: pixel height of font (also used for y-offset, so it must match the actual font)
  - `visible`: whether label shows on initial render
  - Available fonts: `u8g2_font_wqy12_t_gb2312` (12px Chinese), `u8g2_font_wqy16_t_gb2312` (16px Chinese), `u8g2_font_freedoomr25_mn` (25px digital), `u8g2_font_emoticons21_tr` (21px emoji)

- **Bitmap**: `EpaperLabel::Bitmap(x, y, bitmap_data, w, h, depth, rotation, mirror_h, mirror_v, invert, visible, page)`
  - `visible`: whether bitmap shows on initial render
  - Emoji bitmaps: `EpaperImage::EMO_NEUTRAL_32x32`, `EMO_HAPPY_32x32`, etc. (32×32 pixels)

- **Line**: `EpaperLabel::Line(x0, y0, x1, y1, width, color, rotation, visible, page)`

### Hiding/Showing Labels at Runtime

- `LabelHide("id")` / `LabelShow("id")`: sets `visible = false/true` and refreshes
- `UpdateLabel("id")`: refreshes a single label's area
- `UpdateUI(bool fullRefresh)`: refreshes entire screen; `fullRefresh=true` = full screen clear+redraw, `false` = partial refresh

### Hiding Default UI Elements (No Code Removal Needed)

To hide a label without removing it (preserving runtime toggle capability), set its `visible` parameter to `false` in the `AddLabel()` factory call. For example, to hide the WiFi icon, battery icon, and status bar divider on the chat page, change the last `true` to `false` in the `Bitmap()`/`Line()` factory call. This is cleaner than commenting out `AddLabel()` lines — the label still exists for potential runtime show/hide via `LabelShow()`/`LabelHide()`.

### Hiding time_label — Must Also Update Runtime Show Paths

**Pitfall**: Setting `time_label` visible=false in `SetupUI()` is NOT enough. Two runtime code paths will re-show it on the chat page:

1. **`UpdateStatusBar()`** (`epaper_display.cc` ~line 404): When `kDeviceStateIdle` and time is valid, it calls `LabelShow("time_label")` and hides `status_label`. This overrides your visible=false.
2. **Notification timer callback** (`epaper_display.cc` ~line 38): After a notification expires, if `kDeviceStateIdle`, it calls `LabelShow("time_label")`.

**Fix**: When removing time from the chat page, also:
- In `UpdateStatusBar()` idle branch: remove the `LabelShow("time_label")` call and the hide-status/show-time logic. Just keep `time_label->text` updated for other pages that reference it (e.g. `home_time`, `homepic_time`).
- In the notification timer callback: change the idle branch to `LabelShow("status_label")` instead of `LabelShow("time_label")`.

This keeps `time_label` text current (other pages sync from it) but prevents it from appearing on the chat page.

### Reorganizing Chat Page Layout — Left/Right Split Pattern

The chat page supports a left/right split layout using a vertical divider line. This is a reusable design pattern for the 296×128 screen:

```
┌───────────┬────────────────────────┐
│  状态提示  │  通知文本(临时显示)      │  y=5
│  (居中)   │                        │
│           │                        │
│    😊     │  对话文本内容            │  y=50
│  (32×32)  │  (居中显示)             │
│           │                        │
└───────────┴────────────────────────┘
  左 96px        右 192px
```

**Key layout parameters**:
- Divider: `Line(96, 2, 96, 126, 1, ...)` — vertical line at x=96
- Left zone (0~95): `status_label` at (x=0, y=10, w=96, CENTER align), `emoji_image` at (x=32, y=50, 32×32)
- Right zone (100~295): `notification_label` at (x=100, y=5, w=192, CENTER), `chat_message_label` at (x=100, y=50, w=192, CENTER, 16px font)

**EpaperLabel Text alignment**: For CENTER alignment, `x` is the left edge and `max_width` is the full width of the centering region. Text is centered within `[x, x+max_width]`. For example, to center in the right zone (100~295, width=192): `x=100, max_width=192`.

### Hidden TEXT Label White-Fill Can Erase Visible BITMAP Labels (Overlap Bug)

**Pitfall**: When a TEXT label with `visible=false` overlaps a visible BITMAP label, the hidden TEXT label's `RenderLabel()` execution will `fillRect(white)` its calculated text bounds area, erasing part of the BITMAP underneath. The symptom is a visible bitmap (e.g. emoji) with a white block covering its lower-left corner on initial render.

**Root cause**: `RenderLabel()` (`epaper_display.cc:801`) handles `!label->visible` by computing the label's bounds (via `CalculateTextBounds` for TEXT type) and calling `display_epaper.fillRect(clear_x, clear_y, clear_w, clear_h, GxEPD_WHITE)` to clear the area. If another visible label (BITMAP, RECT, etc.) occupies the same screen region, its pixels get overwritten with white.

**Example**: `emoji_label` (TEXT, 21px font, visible=false, x=32 y=81) and `emoji_image` (BITMAP 32×32, visible=true, x=32 y=50) overlapped in the y=81~82 region. On every `UpdateUI()` call, `emoji_label`'s hidden-render path filled a white rectangle over the bottom of `emoji_image`.

**Fix**: Remove the unused hidden TEXT label entirely (if it's a pure placeholder that's never shown at runtime). In this case `emoji_label` was a leftover text-based emoji that was never toggled visible — `SetEmotion()` only operates on `emoji_image`. Removing it eliminated the overlap.

**General rule**: Never position a hidden TEXT label on top of a visible BITMAP/RECT label. The hidden-render white-fill is not optional — it always runs during `UpdateUI()` for all labels on the current page, regardless of visibility. If you must keep both, ensure their screen regions do not overlap.

## MCP Tool Count Limit (Server-Side, 32 Max)

The xiaozhi MQTT server enforces a **hard limit of 32 MCP tools** per device. When exceeded, the server returns an error message `"The number of tools has reached the limit: 32"` which triggers `protocol_->OnNetworkError()` → `Alert(Error, ...)` on the e-paper display (shows "Error" text with 😞 emoji). The error also plays a warning sound via `audio_service_.PlaySound()`, which blocks the main event loop, causing secondary `AFE: Ringbuffer of AFE(FEED) is full` warnings on first wake word invocation (audio feed task can't consume data while the main loop is blocked).

**Current tool count breakdown (after fix)**:
- 3 common tools (`self.get_device_status`, `self.audio_speaker.set_volume`, `self.screen.set_brightness`)
- 2 user-only tools (`self.get_system_info`, `self.reboot`)
- 3 lamp tools (`self.lamp.*`)
- 24 fridge tools (10 fridge + 5 canvas + 9 custom page)
- **Total: 32 = exactly the limit**

**Diagnosis**: capture serial log with `crash_log.py`, look for `Alert [sad] Error: The number of tools has reached the limit: 32` after `MQTT: Connected to endpoint`. The error appears ~3-4 seconds after MQTT connection is established, when the server processes the `tools/list` response and rejects the registration.

**Fix**: reduce tool count to ≤32 by removing redundant canvas tools. Candidates for removal:
- `fridge.canvas.list` → `page.element.list` can serve the same purpose for web preview sync
- `fridge.canvas.refresh` → pass `refresh=true` on the last operation instead
- `fridge.canvas.remove` → merged into `canvas.clear` with optional `id` parameter: when `id` is passed and non-empty, only that element is removed; when omitted, all elements are cleared

**Implementation detail for merging `canvas.remove` into `canvas.clear`**: The `canvas.clear` tool's PropertyList now includes an optional `id` property (default empty string). The lambda checks if `id` is non-empty via try/catch on `properties["id"]` (PropertyList has no `find()` method, and `operator[]` throws `std::runtime_error` if not found). If `id` is set, delegate to `HandleCanvasRemove(properties)`; otherwise call `HandleCanvasClear(properties)`. This pattern can be reused for merging other tools.

**Secondary AFE ringbuffer warning**: The `AFE: Ringbuffer of AFE(FEED) is full, Please use fetch() to read data to avoid data loss or overwriting` warning appears when the main event loop is blocked (e.g. by `audio_service_.PlaySound()` during the Error alert). This is a **symptom**, not a root cause — it resolves once the tool count error is fixed and the alert no longer triggers. The AFE feed task runs in `AudioService::AudioInputTask()` and reads data in a loop; if the main loop is blocked, the event group bits don't get processed, and the AFE ringbuffer overflows. See `audio_service.cc:190` for the input task loop.

### Available Emoji Bitmaps

Defined in `epaper_image.h`: `EMO_NEUTRAL, EMO_HAPPY, EMO_LAUGHING, EMO_FUNNY, EMO_SAD, EMO_ANGRY, EMO_CRYING, EMO_LOVING, EMO_EMBARRASSED, EMO_SURPRISED, EMO_SHOCKED, EMO_THINKING, EMO_WINKING, EMO_COOL, EMO_RELAXED, EMO_DELICIOUS, EMO_KISSY, EMO_CONFIDENT, EMO_SLEEPY, EMO_SILLY, EMO_CONFUSED` — all 32×32 pixels.

### `SetEmotion()` and `SetChatMessage()` Behavior

- `SetEmotion(emotion)`: updates `emoji_image` label's bitmap to the matching emotion. Does NOT change visibility — if `emoji_image` is hidden, it stays hidden.
- `SetChatMessage(role, content)`: updates `chat_message_label`. If content is empty, hides the label; otherwise shows it.
- `SetStatus(status)`: updates `status_label`, hides `notification_label` and `time_label` if they're visible.
- `ShowNotification(text, duration_ms)`: shows `notification_label`, hides `status_label` and `time_label`. Auto-restores after timeout via `notification_timer_`.

**Key source files for device state / page switching**:
| File | Role |
|------|------|
| `main/device_state.h` | `DeviceState` enum definition |
| `main/application.cc` | `SetDeviceState()` (line 720), `Start()` (line 365), state machine |
| `main/display/epaperdisplay/epaper_display.h` | `EpaperPage` enum (CHAT_PAGE=1...), `current_page_` default |
| `main/display/epaperdisplay/epaper_display.cc` | `SetPage()` (line 721), `SetupUI()` (line 475) — all labels created here with page assignments |
| `main/boards/common/wifi_board.cc` | `EnterWifiConfigMode()` (line 35), `StartNetwork()` (line 74), `ResetWifiConfiguration()` (line 170) |

## Debugging Crashes with addr2line

When the ESP32 crashes with `Guru Meditation Error`, the serial log prints a backtrace with hex addresses. Use `xtensa-esp32s3-elf-addr2line` to map these to source lines:

```bash
cd <path-to>/xiaozhi-esp32
source ~/esp/esp-idf/export.sh
xtensa-esp32s3-elf-addr2line -pfiaC -e build/xiaozhi.elf 0x4200dc70 0x4201ff32 0x420216f6
```

- `-p` = pretty print, `-f` = show function names, `-i` = inline frames, `-a` = show addresses, `-C` = demangle C++ names
- The ELF file is at `build/xiaozhi.elf`
- Feed the backtrace addresses from the crash log (space-separated, drop the `0x` prefix is not needed — keep them)
- The output shows function name → file:line for each frame, including inlined functions

**Workflow**: After a crash, capture serial log via `crash_log.py`, copy the backtrace addresses, run `addr2line`. This immediately reveals the crash location — e.g. `AudioService::EnableVoiceProcessing(bool)` at `audio_service.cc:491` called from `Application::SetDeviceState()` at `application.cc:367` showed that `audio_service_` was used before initialization.

## Wake Word Blocking (Root-Cause Analysis)

**Symptom**: After saying the wake word ("喵喵同学"), the device takes 5+ seconds to respond. The serial log shows hundreds of `AFE: Ringbuffer of AFE(FEED) is full` warnings between the wake detection and the actual response. The MQTT handshake and UDP audio channel setup are delayed because the CPU is saturated logging ringbuffer warnings.

**Timeline** (captured via `serial_115200.py` background monitor at 115200 baud):
```
36.04s  STATE: connecting (wake word triggered)
36.68s  Encode wake word opus 66 packets in 392ms
37.66s  First "Ringbuffer of AFE(FEED) is full" warning  ← blocking starts
   ↓    ~5 seconds of continuous ringbuffer warnings
42.04s  MQTT Session ID received, UDP channel established
42.04s  Wake word detected: 喵喵同学
42.04s  STATE: listening
42.70s  << 我在呢 (reply received)
44.05s  Audio Processor re-initialized (ringbuffer finally consumed)
```

**Root cause**: Two independent event groups control the wake word pipeline, and they get out of sync:

1. **`AfeWakeWord::event_group_`** (private, with `DETECTION_RUNNING_EVENT` bit): controlled by `Start()`/`Stop()`. The `AudioDetectionTask` calls `Stop()` immediately after detecting a wake word (see `afe_wake_word.cc:140`), which clears `DETECTION_RUNNING_EVENT`. This stops the `fetch()` side of the AFE pipeline.

2. **`AudioService::event_group_`** (with `AS_EVENT_WAKE_WORD_RUNNING` bit): controlled by `EnableWakeWordDetection(true/false)`. This bit stays set after wake detection because `OnWakeWordDetected()` (in `application.cc:669`) does NOT call `EnableWakeWordDetection(false)` — it leaves that to the state machine, which only fires later when transitioning to `kDeviceStateListening` → `EnableVoiceProcessing(true)` → `EnableWakeWordDetection(false)`.

The gap: between `AudioDetectionTask::Stop()` and `SetDeviceState(kDeviceStateListening)`, the `AudioInputTask` (in `audio_service.cc:190`) sees `AS_EVENT_WAKE_WORD_RUNNING` still set, so it keeps calling `wake_word_->Feed(data)`. But the AFE's `fetch()` consumer has stopped (DETECTION_RUNNING_EVENT cleared), so the feed ringbuffer overflows.

**Fix** (verified, in `afe_wake_word.cc`):

```cpp
void AfeWakeWord::Feed(const std::vector<int16_t>& data) {
    if (afe_data_ == nullptr) {
        return;
    }
    // If detection has stopped (DETECTION_RUNNING_EVENT cleared by Stop()),
    // the AFE fetch side is no longer running. Feeding data now only floods
    // the ringbuffer. Drop the data — the state machine will call
    // EnableWakeWordDetection(false) shortly, which clears AS_EVENT_WAKE_WORD_RUNNING.
    if (!(xEventGroupGetBits(event_group_) & DETECTION_RUNNING_EVENT)) {
        return;
    }
    afe_iface_->feed(afe_data_, data.data());
}
```

**Result**: wake response time dropped from 5+ seconds to ~1.3 seconds. Ringbuffer warnings eliminated entirely. Wake word detection continues to work normally across repeated invocations.

**Failed approach (do NOT repeat)**: The first fix attempt was in `Application::OnWakeWordDetected()` — adding `audio_service_.EnableWakeWordDetection(false)` at the top of the `kDeviceStateIdle` branch. This **broke wake word detection entirely**: after the first wake, the device never responded to wake words again. The serial log showed zero wake events. Root cause: `EnableWakeWordDetection(false)` clears `AS_EVENT_WAKE_WORD_RUNNING` and calls `wake_word_->Stop()`, but the subsequent state transitions (`kDeviceStateConnecting` → `kDeviceStateListening`) call `EnableVoiceProcessing(true)` which calls `EnableWakeWordDetection(false)` again, and the re-enable path (`kDeviceStateIdle` → `EnableWakeWordDetection(true)`) requires `wake_word_initialized_` to be false or calls `Initialize()` again — the state machine's assumptions about when wake word is enabled/disabled get confused. The correct fix is at the `Feed()` source — let the state machine manage `AS_EVENT_WAKE_WORD_RUNNING` as designed, just prevent the AFE ringbuffer from flooding when the consumer has stopped.

See the section above for the full root-cause analysis, including the `AudioDetectionTask` → `Stop()` → `DETECTION_RUNNING_EVENT` clear path, and the `AudioInputTask` → `Feed()` → ringbuffer overflow loop.

## Serial Port Busy After Flash/monitor

If `esptool` reports `Could not exclusively lock port /dev/ttyUSB0`, a previous process is holding it:

```bash
fuser -k /dev/ttyUSB0 2>/dev/null  # kill the process
sleep 2                              # wait for port release
# now retry the flash command
```

Common culprits: `idf.py monitor`, `cat /dev/ttyUSB0`, `crash_log.py` — all hold the port open. Always `fuser -k` before flash after any serial capture.

## Common Build Issues

- **`undefined reference to` a new class's methods**: Two distinct causes:
  1. **CMake glob didn't pick up the new `.cc` file** — the glob pattern `boards/${BOARD_TYPE}/**/*.cc` works in ESP-IDF's CMake, but sometimes a stale cache prevents new files from being detected. Fix: `touch main/CMakeLists.txt` to force reconfigure, or `idf.py fullclean && idf.py build`.
  2. **Missing `GetInstance()` implementation** — if you declare `static MySingleton& GetInstance();` in the header but forget to define it in the `.cc` file, the linker reports `undefined reference to _ZN11MySingleton11GetInstanceEv`. The `.obj` file compiles fine (it has all other methods), but the symbol for `GetInstance` is missing. Fix: add `MySingleton& MySingleton::GetInstance() { static MySingleton inst; return inst; }` in the `.cc` file. This is easy to miss because the compiler doesn't warn — it's a link-time error.
- **`undefined reference to create_board`**: Stale build cache. Run `idf.py fullclean` then rebuild.
- **`Value exceeds maximum allowed: N`**: MCP Property has a max validator. Update the max in `AddProperty()` call.
- **`esp_vfs_littlefs_conf_t has no member named mount_point`**: This LittleFS version uses `base_path`, not `mount_point`.
- **Adding `REQUIRES` to `idf_component_register` can break implicit dependency resolution**: Only add `REQUIRES` if a fullclean doesn't fix it. Adding `REQUIRES` forces explicit listing of all transitive deps, which can cascade into missing includes from other components (e.g. adding `joltwallet__littlefs` triggers needing `GxEPD2`, `U8g2_for_Adafruit_GFX`, `78__esp-opus`, etc.). If you hit this cascade, **remove the REQUIRES line entirely** — fullclean + rebuild without it resolves correctly because ESP-IDF's implicit dep resolution handles it.
- **`undefined reference to create_board` after fullclean**: The `fullclean` removes `managed_components/` and rebuilds them. The `BOARD_SOURCES` glob in CMakeLists.txt (`boards/${BOARD_TYPE}/**/*.cc`) correctly picks up all `.cc` files including `compact_wifi_board_epaperx.cc` which contains `DECLARE_BOARD(CompactWifiBoardEpaperX)` → `create_board()`. If the error persists, check that the `.cc` file containing `DECLARE_BOARD` is in the glob path and not excluded.
- **Serial port permission lost after reboot**: `/dev/ttyUSB0` resets to `crw-rw---- root:dialout` on every device reconnect or host reboot. Must `sudo chmod 666 /dev/ttyUSB0` before each flash session. This is not fixable permanently without udev rules.

## Post-Flash WiFi Reconnection Delay

After flashing, the ESP32 reboots and goes through: boot → WiFi connect → mDNS register → HTTP server start. This takes 15-25 seconds. The device IP may change (DHCP) — the cached IP in `~/.cache/xiaozhi_ip.txt` may be stale. After flashing, always re-run `xiaozhi_discovery.py --health --save` to find the new IP and verify connectivity before attempting any API calls. If the device doesn't respond after 30s, check the serial log for crash loops.

## Device IP Change (DHCP)

The device IP can change between sessions due to DHCP lease expiry or router reassignment. Always run discovery first. The cached IP in `~/.cache/xiaozhi_ip.txt` is a convenience, not a guarantee. Update the cache when the IP changes.
