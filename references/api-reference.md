# Local HTTP / MCP contracts

Reference: xiaozhi-esp32 `178aca9`, firmware 2.5.2.1 (2026-10-18).
Device base URL: `http://DEVICE_IP:8080`. Verify `GET /` before mutation.

## Portable CLI

```bash
python3 scripts/xiaozhi.py DEVICE_IP health
python3 scripts/xiaozhi.py DEVICE_IP pages
python3 scripts/xiaozhi.py DEVICE_IP elements 7
python3 scripts/xiaozhi.py DEVICE_IP layout 5
python3 scripts/xiaozhi.py DEVICE_IP show 7
python3 scripts/xiaozhi.py DEVICE_IP home
python3 scripts/xiaozhi.py DEVICE_IP home --page 7 --timeout-min 2
python3 scripts/xiaozhi.py DEVICE_IP name --set "书桌小智"
python3 scripts/xiaozhi.py DEVICE_IP call fridge.stats.summary
python3 scripts/xiaozhi.py DEVICE_IP call fridge.page.element.control --args-file args.json
```

`--port`, `--timeout` (default 20s), `--expect-mac` go before the subcommand.
For raw tool calls `args.json` contains only the args object, e.g.:

```json
{"action":"update","page":7,"id":"weather","text":"晴 28C","refresh":true}
```

Use stable IDs for small updates; use the validated builder for complete layouts.
An update with `refresh=true` already presents the page: do not call `show` again.
CLI errors are nonzero; output is decoded JSON. No automatic write retries.

## HTTP endpoints

| Method / path | Input / response |
|---|---|
| `GET /` | `status,board,name,version,idf_version,wifi_connected,mac,hostname,mdns,ip,http_port,http_url,mdns_url` |
| `POST /api/call` | `{"tool":"fridge.…","args":{…}}`; simplified MCP call |
| `POST /mcp` | JSON-RPC `tools/list` or `tools/call`; not the simplified format |
| `GET /api/device_name` | `{status,name}` |
| `POST /api/device_name` | `{name}`; 1–64 UTF-8 bytes, no controls; empty string restores default |
| `GET /api/home_page` | `{status,page,timeout_min}`; configured home, **not current page** |
| `POST /api/home_page` | Both `{page,timeout_min}` required; integer page 1–15, minutes 0–60 |
| `GET /api/page_layout?page=N` | Read-only render description for pages 1–15, including bitmap data |
| `GET /api/canvas_image` | Stored files `[{name,size},…]` |
| `POST /api/canvas_image?name=NAME` | Binary body, `application/octet-stream`; returns status |
| `GET /ui` | Firmware's small device scanner UI |

Home-page setting persists in NVS, resets the return countdown immediately, and
**does not switch/refresh**. `timeout_min:0` disables return while keeping the
boot home page. Return runs only in idle state; after conversation ends, a fresh
full wait begins. Confirm a custom page exists before selecting it as home.

`/api/page_layout` is a preview description, not a screenshot or restorable
mutation list. IDs are internal/prefixed; line start is `(x,y)` and end is
`(x1,y1)`. Its `x2,y2` are internal fields, not the API's second endpoint.
For backup/edit/readback use the MCP element list, whose line endpoints really
are `(x1,y1)` → `(x2,y2)`. Preview does not report currently displayed page,
frame completion, or guaranteed z order.

## MCP results and transport

Current `/api/call` usually returns `{result:{content:[{type:"text",text:"…"}],isError:false}}`;
older firmware may also include `jsonrpc,id`. Decode `content[].text` JSON to
obtain the result object/array. Reject outer `error`, `result.isError`, inner
`error`/failed `status`, malformed output, or plain-text error messages.

Firmware waits up to **15 seconds** for tool execution. Client timeout should be
20s or longer. A tool request body must fit **4095 UTF-8 bytes**. Calls are serial;
batch means several serial calls with `refresh:false`, not a transaction endpoint.
No API reports physical panel completion. A timeout can occur after execution;
inspect state before another write, including rollback.

For capability discovery use JSON-RPC `tools/list` on `/mcp` and follow every
`nextCursor`. There are 14 fridge/UI/network tools, plus other firmware tools.
`fridge.help` is absent. Legacy names such as `fridge.canvas.add_text` are mapped
only by `/api/call`; use aggregate names in new code. Firmware 2.0.5 is outside
the current builder contract; do not silently switch to an unsafe fallback.

## Page / element tools

| Tool | Actions / required fields |
|---|---|
| `fridge.pagemanager` | `target_page:1..15`; requests a full refresh, including same-page calls |
| `fridge.canvas.control` | `action:add_text,add_rect,add_line,add_image,list,remove,clear,refresh,reorder` |
| `fridge.page.control` | `action:create,list,rename,delete,clear`; page 7–15 where applicable; create takes `name` and returns allocated `page` |
| `fridge.page.element.control` | `action:add,update,remove,list,reorder`, `page:7..15`; add also takes `type:text,rect,line,image` |
| `device.network.info` | `{}` → Wi-Fi/SSID, IP, MAC, mDNS and HTTP URLs |

Page list includes built-ins (`builtin:true`) and custom pages; never assume
page 7 is free. Delete a custom page also switches to page 5 in current firmware.

| Element | Fields (flat in args) |
|---|---|
| text | `id,text,x,y,font_size:12|16,align:left|center|right`; canvas permits `max_width` |
| rect | `id,x,y,w,h,filled` |
| line | `id,x1,y1,x2,y2,width`; custom pages also send `x=x1,y=y1` |
| image | `id,name,x,y,w,h`; file must exist with matching byte size |

For canvas use `action:add_text` etc.; for custom pages use `action:add,type:text`
etc. Reusing an ID replaces an element. `update` on custom pages changes **text
only**, not geometry; use add to replace geometry. `remove` requires `id`.
Always specify `refresh:false` during a batch, even where it is the default.
Custom page `clear` defaults true, so omission can show an empty page.

`reorder` takes comma-separated short IDs in `order`, bottom to top. In 2.5.2.1
**canvas reorder refreshes unconditionally**, ignoring `refresh:false`; custom
page reorder changes order without presenting it. For predictable batches, add
elements in desired z order.

Canvas `refresh` invokes `ShowCanvasPage` and full refresh, but does not reset the
home timer in this version. The builder uses one final `fridge.pagemanager` call
for consistent home-return behavior on every page.

## Fridge tools

| Tool | Main arguments |
|---|---|
| `fridge.item.get` | `item_id` |
| `fridge.item.add` | `name,category,quantity,unit,expire_time`; optional `storage_state` |
| `fridge.item.update` | `item_id,name` and changed fields |
| `fridge.item.remove` | `item_id` |
| `fridge.item.clear_all` | `{}`; deletes inventory, unrelated to clearing a display |
| `fridge.item.list` | optional `category,limit,sort_by,order` |
| `fridge.stats.summary` | `{}` |
| `fridge.stats.query` | optional `category,filter:all|expired|expiring_soon,expiring_days` |
| `fridge.recipe.recommend` | `recommendation_mode,dish_name,required_ingredients`; optional `summary,extra_ingredients,cooking_time,switch_page` |

`expire_time`: `YYYY-MM-DD HH:MM:SS`. Categories:
`vegetable,fruit,meat,egg,dairy,cooked,seasoning,beverage,quick,other`.
Storage: `Fresh` / `Frozen`. `fridge_only` rejects missing ingredients;
`mixed_purchase` includes missing ingredients. Inspect `missing_ingredients` and
`current_fridge_items` in the result. Query current `tools/list` for uncommon
fields instead of guessing.

## Bitmap contract

Raw row-padded 1-bpp, MSB first, **1=black, 0=white**.
Bytes = `ceil(w/8) × h`; 24×24 = 72 bytes, 296×128 = 4736 bytes. Pad unused row
bits with zero. Transparency is white. `w/h` are bitmap dimensions, not scaling.
Pre-render/resize on the host. Built-in `pixart` is exactly 24×24.

Images live in LittleFS. Use safe basenames (letters, digits, `_`, `.`);
Paths, `..`, hyphens (firmware rewrites them) and `.json` names (reserved for
layouts/registry) are rejected by the client. The file-list endpoint also includes
these metadata files; they are not bitmap assets. Do not overwrite a name referenced by another page
unless changing that shared asset is intended.
