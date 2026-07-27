# API Reference — xiaozhi ESP32 HTTP & MCP Tools

Complete reference for the HTTP API and MCP tools exposed by the xiaozhi-esp32
device when LocalControl is enabled (HTTP server on port 8080 + mDNS `xiaozhi.local`).

## HTTP Endpoints

### Health Check

```bash
curl http://<IP>:8080/
# → {"status":"ok","board":"bread-compact-wifi-epaperx","version":"2.0.3",...}
```

### Call MCP Tool (simplified format — recommended)

```bash
curl -X POST http://<IP>:8080/api/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"fridge.stats.summary","args":{}}'
```

### Raw JSON-RPC (alternative endpoint)

```bash
curl -X POST http://<IP>:8080/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"fridge.stats.summary","arguments":{}}}'
```

**Two API formats — know which endpoint uses which**: The device has two HTTP
endpoints for MCP calls: `/api/call` uses `{"tool":"...","args":{}}` format
(simplified, by `local_control.cc`), while `/mcp` uses JSON-RPC
`{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"...","arguments":{}}}`
format. Mixing them up returns `{"error":"Missing 'tool' field"}`. For curl
testing, always use `/api/call` with the simplified format — it's shorter and
doesn't require an incrementing `id` field. The web console JS also uses `/api/call`.

### MCP Response Structure

The ESP32 returns JSON-RPC 2.0 wrapped responses. The actual tool result is a
JSON string inside `result.content[0].text`. For example:

```json
{
  "jsonrpc": "2.0", "id": 10000,
  "result": {
    "content": [{ "type": "text", "text": "{\"total_items\":1,...}" }],
    "isError": false
  }
}
```

Clients must `JSON.parse()` the inner `text` field to get the actual data.

### Canvas Image Upload

```bash
# Upload a 1-bpp raw bitmap (w*h/8 bytes)
curl -X POST "http://<IP>:8080/api/canvas_image?name=my_image" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @image.bin
```

### List Stored Images

```bash
curl http://<IP>:8080/api/canvas_image
# → [{"name":"my_image","size":512}]
```

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
| `fridge.canvas.add_rect` | Place rectangle on canvas (page 6) | `id`, `x`, `y`, `w`, `h`, `filled`, `refresh` |
| `fridge.canvas.add_line` | Place line on canvas (page 6) | `id`, `x1`, `y1`, `x2`, `y2`, `width`, `refresh` |
| `fridge.canvas.add_image` | Load image from LittleFS to canvas (page 6) | `id`, `name`, `x`, `y`, `w`, `h`, `refresh` |
| `fridge.canvas.clear` | Clear all canvas elements (page 6) | `refresh`, optional `id` for single-element removal |
| `fridge.page.create` | Create custom page (7-15) | `name` — returns `{page, name}` |
| `fridge.page.delete` | Delete custom page + elements | `page` (7-15) |
| `fridge.page.list` | List all pages (builtin + custom) | `{}` — returns `[{page, name, builtin}]` |
| `fridge.page.rename` | Rename custom page | `page` (7-15), `name` |
| `fridge.page.element.add` | Add element to custom page | `page`, `id`, `type`(text/rect/line), `x`, `y`, `text`, `font_size`, `align`, `w`, `h`, `filled`, `x1`, `y1`, `x2`, `y2`, `width`, `dynamic`, `dynamic_type`(clock/date/datetime/cpu_temp/heap/uptime), `refresh` |
| `fridge.page.element.update` | **Update dynamic element text** (cron → push to display) | `page`, `id`, `text`, `refresh`(default true) |
| `fridge.page.element.remove` | Remove element from custom page | `page`, `id`, `refresh` |
| `fridge.page.element.list` | List elements on custom page | `page` (7-15) |
| `fridge.page.clear` | Clear all elements from custom page | `page`, `refresh` |

## E-Paper Pages

| target_page | Name | Content |
|-------------|------|---------|
| 1 | CHAT | Status bar + chat (auto-switched on config/startup — has connection hints) |
| 2 | FRIDGE_STATS | Clock + fridge stats |
| 3 | FOOD_LIST | Item list (max 4 rows) |
| 4 | RECIPE | AI recipe |
| 5 | HOME_PIC | Memorial image |
| 6 | CANVAS | Free-form canvas (Agent-controlled) |
| 7-15 | CUSTOM | User-created pages with static + dynamic elements |

**Auto-switch on config/startup**: `SetDeviceState(kDeviceStateStarting)` and
`kDeviceStateWifiConfiguring` now call `display_epaper->SetPage(CHAT_PAGE)` so
the user always sees connection hints during startup and WiFi config mode. See
`docs/firmware-development.md` § Device State & E-Paper Page Auto-Switch for
the critical timing constraint (no `audio_service_` calls in early states).

## Canvas API (Page 6)

The canvas page lets the Agent freely place text, lines, and rectangles on the
296×128 e-paper display. Use `refresh=false` to batch multiple operations, then
call a final operation with `refresh=true` (or `fridge.canvas.refresh`) to update
the screen.

| Tool | Description | Key Args |
|------|-------------|----------|
| `fridge.canvas.add_text` | Place text | `id`, `text`, `x`, `y`, `font_size`(12/16), `align`(left/center/right), `refresh` |
| `fridge.canvas.add_rect` | Place rectangle | `id`, `x`, `y`, `w`, `h`, `filled`, `refresh` |
| `fridge.canvas.add_line` | Place line | `id`, `x1`, `y1`, `x2`, `y2`, `width`, `refresh` |
| `fridge.canvas.add_image` | Load image from LittleFS storage | `id`, `name`, `x`, `y`, `w`, `h`, `refresh` |
| `fridge.canvas.clear` | Clear all elements (or remove single by `id`) | `refresh`(default true), optional `id` for single-element removal |

### Canvas Workflow

1. `fridge.pagemanager target_page=6` — switch to canvas page
2. `fridge.canvas.clear refresh=false` — clear old content
3. Batch-add elements with `refresh=false`:
   - `fridge.canvas.add_text id=title text="..." x=10 y=5 font_size=16 align=center refresh=false`
   - `fridge.canvas.add_line id=div x1=10 y1=28 x2=286 y2=28 width=2 refresh=false`
   - `fridge.canvas.add_rect id=box x=8 y=33 w=280 h=60 filled=false refresh=false`
4. Final call with `refresh=true` — flush to screen

`fridge.canvas.clear` also supports an `id` param for single-element removal
(merged from the old `fridge.canvas.remove` tool to reduce total tool count).

## Canvas Image Storage (LittleFS)

Images are persisted in a 2MB LittleFS partition (`canvas_data`) on the device
flash. Upload via HTTP, then reference by name in `canvas.add_image`.

```bash
# Upload a 1-bpp raw bitmap (w*h/8 bytes)
curl -X POST "http://<IP>:8080/api/canvas_image?name=my_image" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @image.bin

# List stored images
curl http://<IP>:8080/api/canvas_image
# → [{"name":"my_image","size":512}]

# Display the image on canvas
curl -X POST http://<IP>:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.canvas.add_image","args":{"id":"img1","name":"my_image","x":100,"y":30,"w":64,"h":64}}'
```

### Image Format

1-bpp (black/white) raw bitmap:
- MSB first (bit 7 = leftmost pixel)
- Each row padded to byte boundary
- 1 = black, 0 = white (GxEPD2 `drawBitmap()` treats bit=1 as foreground=black)
- Size = `ceil(w/8) * h` bytes
- For a 64×64 image: 512 bytes
- For full screen (296×128): `ceil(296/8) * 128 = 37 * 128 = 4736` bytes

**Key detail**: the device reads `w * h / 8` bytes from the file and pads with
zeros if short. Width should ideally be a multiple of 8 (296 is NOT — 296/8=37
bytes per row, no remainder since 296 = 37*8, so it works perfectly). For
non-multiple-of-8 widths, pad the last byte's unused bits to white (1).

### Bitmap Color Inversion Pitfall

The GxEPD2 `drawBitmap()` function treats bit=1 as the **foreground color**
(black on a B&W display) and bit=0 as the **background color** (white). So if
your `pixelsTo1bpp()` function maps luminance≥128 (white pixels) to bit=1,
the screen will show them as **black** — the entire image is inverted.

**Fix**: invert the bit assignment: `var bitVal = (lum >= 128) ? 0 : 1;` —
dark pixels (lum<128) get bit=1 (foreground=black), light pixels get bit=0
(background=white).

### w*h/8 vs ceil(w/8)*h Pitfall

The device firmware (`HandleCanvasAddImage` in `fridge_mcp.cc`) calculates
`total_bytes = w * h / 8` using integer division. This is WRONG for widths
that are not multiples of 8 — e.g. a 100×50 image: device expects `100*50/8
= 625` bytes, but the correct 1-bpp packing is `ceil(100/8)*50 = 13*50 = 650`
bytes. The device will read 625 bytes, leaving 25 bytes of the last
column-pair unread, causing a garbled right edge.

**Workaround**: always use widths that are multiples of 8 for canvas images.
The full-screen freehand drawing (296×128) works because 296 = 37×8 (exact).
For the web console's image insertion feature, round the target width up to
the next multiple of 8 before generating the bitmap.

### Browser → Canvas Bitmap Workflow

For freehand drawing / image insertion from web:
1. Draw on an HTML `<canvas>` element (296×128)
2. Get pixel data: `ctx.getImageData(0, 0, 296, 128).data` (RGBA array)
3. Binarize: for each pixel, luminance = `0.299*R + 0.587*G + 0.114*B`;
   threshold at 128 → black (bit=0) / white (bit=1) — **inverted** per pitfall above
4. Pack into 1-bpp bitmap: 8 pixels per byte, MSB first, row-padded to byte
   boundary → `Uint8Array(ceil(296/8) * 128) = 37 * 128 = 4736 bytes`
5. Upload: `fetch('/xiaozhi-api/api/canvas_image?name=freehand_N', { method: 'POST', body: bitmapBuffer })`
6. Place on canvas: `api.callTool('fridge.canvas.add_image', { id: 'img1', name: 'freehand_N', x: 0, y: 0, w: 296, h: 128, refresh: true })`

See `docs/web-console.md` and `docs/canvas-web-interaction.md` for the full
browser-side implementation.

## Canvas Coordinate System

- Screen: 296 (W) × 128 (H) pixels
- Origin: top-left (0,0)
- Safe area: x ∈ [5, 291], y ∈ [5, 123]

## Recipe Recommendation Response

`fridge.recipe.recommend` returns these fields in the `text` JSON:

| Field | Meaning |
|-------|---------|
| `dish_name` | Recommended dish name |
| `cooking_time` | e.g. "20分钟" |
| `required_ingredients` | Comma-separated list the dish needs |
| `extra_ingredients` | Auto-filled missing ingredients (in `mixed_purchase` mode) |
| `missing_ingredients` | What's missing from fridge (empty if all present) |
| `recipe_text` | Formatted recipe text displayed on e-paper |
| `current_fridge_items` | Array of current fridge items |
| `recommendation_mode` | `fridge_only` or `mixed_purchase` |

**Behavior**: `fridge_only` rejects if any ingredient is missing (returns error
with list). `mixed_purchase` auto-fills `extra_ingredients` with what needs to
be bought. The response also includes a `missing_ingredients` field.

## One-Shot Recipe: Manage Fridge + Recommend Meal

```bash
IP=$(python3 scripts/xiaozhi_discovery.py)
# 1. Switch to food list page
curl -s -X POST http://$IP:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.pagemanager","args":{"target_page":3}}'
# 2. Check current stats
curl -s -X POST http://$IP:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.stats.summary","args":{}}'
# 3. Add an item (expire_time = now + N days)
curl -s -X POST http://$IP:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.item.add","args":{"name":"鸡蛋","category":"egg","quantity":1,"unit":"盒","expire_time":"2026-08-04 09:48:15"}}'
# 4. Switch to recipe page and recommend
curl -s -X POST http://$IP:8080/api/call -H "Content-Type: application/json" \
  -d '{"tool":"fridge.recipe.recommend","args":{"dish_name":"鸡蛋炒饭","required_ingredients":"鸡蛋","recommendation_mode":"fridge_only"}}'
# 5. IMPORTANT: cross-check required_ingredients vs current_fridge_items yourself
#    (Only needed for old firmware. New firmware auto-rejects in fridge_only mode.)
```
