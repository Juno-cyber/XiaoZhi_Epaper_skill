# Local HTTP / MCP contracts

Reference: xiaozhi-esp32 `052d39e`, firmware 2.5.2.4 (2026-10-24).
Device base URL: `http://DEVICE_IP:8080`. Verify `GET /` before mutation.

## Portable CLI

```bash
python3 scripts/xiaozhi.py DEVICE_IP health
python3 scripts/xiaozhi.py DEVICE_IP pages
python3 scripts/xiaozhi.py DEVICE_IP elements 7
python3 scripts/xiaozhi.py DEVICE_IP layout 2
python3 scripts/xiaozhi.py DEVICE_IP show 7
python3 scripts/xiaozhi.py DEVICE_IP home
python3 scripts/xiaozhi.py DEVICE_IP home --page 7 --timeout-min 2
python3 scripts/xiaozhi.py DEVICE_IP name --set "书桌小智"
python3 scripts/xiaozhi.py DEVICE_IP voice
python3 scripts/xiaozhi.py DEVICE_IP voice --url wss://api.tenclass.net/xiaozhi/v1/
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
| `POST /api/home_page` | Both `{page,timeout_min}` required; page 1 or an existing custom page 2–15, minutes 0–60 |
| `GET /api/page_layout?page=N` | Read-only render description for chat or existing custom pages, including bitmap data |
| `GET /api/canvas_image` | Stored files `[{name,size},…]` |
| `POST /api/canvas_image?name=NAME` | Binary body, `application/octet-stream`; returns status |
| `GET /api/websocket_url` | `{url}` only; no token returned |
| `POST /api/websocket_url` | `{url}` only; persists selection; restart separately to apply |
| `GET/POST /api/websocket` | Advanced enabled/url/token/version configuration; see below |
| `GET /ui` | Firmware's local configuration UI |

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
`nextCursor`. Do not hardcode a tool count; fridge business tools are suspended.
`fridge.help` is absent. Legacy names such as `fridge.canvas.add_text` are mapped
only by `/api/call`; use aggregate names in new code. Older firmware is outside
the current builder contract; do not silently switch to an unsafe fallback.

## Page / element tools

| Tool | Actions / required fields |
|---|---|
| `fridge.pagemanager` | `target_page`: chat 1 or an existing custom page; requests a full refresh, including same-page calls |
| `fridge.canvas.control` | `action:add_text,add_rect,add_line,add_image,list,remove,clear,refresh,reorder` |
| `fridge.page.control` | `action:create,list,rename,delete,clear`; page 2–15 where applicable; create takes `name` and returns allocated `page` |
| `fridge.page.element.control` | `action:add,update,remove,list,reorder`, `page:2..15`; add also takes `type:text,rect,line,image` |
| `device.network.info` | `{}` → Wi-Fi/SSID, IP, MAC, mDNS and HTTP URLs |

Page list includes chat 1 (`builtin:true`) and existing custom pages (`builtin:false`).
Default page 2 is 时间显示; page 6, when present, is also custom. Never assume a
page exists or is free. Deleting the displayed page returns to chat 1; deleting
the configured home resets home to 1 while preserving the timeout.

| Element | Fields (flat in args) |
|---|---|
| text | `id,text,x,y,font_size:12|16,align:left|center|right`; all custom pages permit `max_width` (default 276) |
| rect | `id,x,y,w,h,filled` |
| line | `id,x1,y1,x2,y2,width`; custom pages also send `x=x1,y=y1` |
| image | `id,name,x,y,w,h`; file must exist with matching byte size |

For every custom page, including 6, use `action:add,type:text` etc.
`fridge.canvas.control` is a legacy compatibility surface, not the builder route. Reusing an ID replaces an element. `update` on custom pages changes **text
only**, not geometry; use add to replace geometry. `remove` requires `id`.
Always specify `refresh:false` during a batch, even where it is the default.
Custom page `clear` defaults true, so omission can show an empty page.

`reorder` takes comma-separated short IDs in `order`, bottom to top. On the legacy canvas API
**canvas reorder refreshes unconditionally**, ignoring `refresh:false`; custom
page reorder changes order without presenting it. For predictable batches, add
elements in desired z order.

Canvas `refresh` invokes `ShowCanvasPage` and full refresh, but does not reset the
home timer on the legacy canvas API. The builder uses one final `fridge.pagemanager` call
for consistent home-return behavior on every page.

## Suspended functions

`fridge.item.*`, `fridge.stats.*` and `fridge.recipe.recommend` are not registered
in this board's 2.5.2.4 firmware. Do not poll them for creative-layout footnotes
or fall back to inventory writes. Stored fridge data is retained. The fixed
stats/list/recipe/home-image pages and love/memorial counter are removed;
`fridge.page.*` and `fridge.pagemanager` remain active display tools.

## Voice server URL

`xiaozhi.py IP voice` reads `/api/websocket_url`; `voice --url URL` posts only
`{"url":"wss://…"}`. ws/wss URLs are limited to 512 UTF-8 bytes, without credentials,
fragments, spaces or control characters. The device returns only `{url}`. A saved
URL does not prove connection or activation. Saving selects manual WebSocket and
requires a separate device restart; the CLI does not reboot automatically.

The URL changes the voice/text dialogue connection, not the OTA address, Wi-Fi,
screen data or AEC parameters. Manual WebSocket mode skips boot OTA/activation
checks. Credentials are cached by the **complete URL**, retaining the current
and up to three historical targets (8 KB total bound). An unknown server does
not inherit another server's token. Activation/token renewal and TLS trust are
separate tasks; changing just the URL does not obtain credentials or trust a
self-signed certificate.

Advanced `/api/websocket`: GET reports `enabled,url,version,token_set` (no token).
POST requires boolean `enabled`; optional `url,token,version` (version 1–3, token
max 2048 bytes). Changing URL without a token clears the current token;
`token:""` explicitly clears that target's saved credentials. Saving
`{"enabled":false}` and restarting restores automatic OTA/activation mode.
Use this only when that advanced change is requested; avoid logging tokens.

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
