# Web Console for Xiaozhi ESP32 — Setup Guide

How to build a browser-based control panel for the xiaozhi ESP32 device, served from a separate web server (e.g. a personal website) and communicating with the device over HTTP.

## Architecture

```
Browser (HTTPS) ──→ Web Server (Nginx/Python) ──→ ESP32 (HTTP :8080)
                     /xiaozhi-api/ proxy           MCP tools
```

Two connection modes:
1. **Proxy mode** (recommended for HTTPS production): Nginx `location /xiaozhi-api/ { proxy_pass http://<IP>:8080/; }` — no CORS needed
2. **Direct mode** (HTTP only): browser fetches `http://<IP>:8080/` directly — requires firmware CORS support

## Firmware CORS Support

ESP32 `esp_http_server` does not send CORS headers by default. Patches needed in `local_control.cc`:

### 1. Add CORS helper functions (after TAG definition)

```cpp
static void SetCorsHeaders(httpd_req_t* req) {
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Methods", "GET, POST, OPTIONS");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Headers", "Content-Type");
}

static esp_err_t HandleOptions(httpd_req_t* req) {
    SetCorsHeaders(req);
    httpd_resp_send(req, nullptr, 0);
    return ESP_OK;
}
```

### 2. Call SetCorsHeaders(req) in every handler

Before each `httpd_resp_sendstr()` call, add `SetCorsHeaders(req);`.

Handlers to patch:
- `HandleHealth` (GET /)
- `HandleMcpPost` (POST /mcp)
- `HandleApiCall` (POST /api/call)
- `HandleCanvasImageUpload` (POST /api/canvas_image) — **including the success path** (after `fclose(f)`, before `httpd_resp_sendstr`), not just the error/mount-failure paths
- `HandleCanvasImageList` (GET /api/canvas_image) — **including the success path** (before `httpd_resp_sendstr(json.c_str())`)

### 3. Register OPTIONS handlers for all URIs

In `LocalControl::Start()`, for each registered URI, add an OPTIONS handler:

```cpp
httpd_uri_t options_uri = {
    .uri = "/",
    .method = HTTP_OPTIONS,
    .handler = HandleOptions,
    .user_ctx = this
};
httpd_register_uri_handler(server_, &options_uri);
// Repeat for "/mcp", "/api/call", "/api/canvas_image"
```

Also increase `config.max_uri_handlers` to `16` (original 5 handlers + 4 OPTIONS = 9, but the default `8` silently fails to register the last OPTIONS handler — `httpd_register_uri_handler` returns `ESP_ERR_HTTPD_HANDLERS_FULL` without any visible error).

### 4. Rebuild and flash

```bash
source ~/esp/esp-idf/export.sh
idf.py build && idf.py -p /dev/ttyUSB0 flash
```

## Nginx Reverse Proxy Config

Add to the HTTPS server block:

```nginx
location /xiaozhi-api/ {
    proxy_pass http://<IP>:8080/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_connect_timeout 5s;
    proxy_read_timeout 10s;
}
```

`proxy_pass` with trailing slash strips the `/xiaozhi-api/` prefix, so `/xiaozhi-api/api/call` → `http://<IP>:8080/api/call`.

## Local Dev Proxy (Python)

For local development without Nginx, use a Python proxy server that serves static files and forwards `/xiaozhi-api/` requests to the device. Key points:

- Subclass `http.server.SimpleHTTPRequestHandler`
- Override `do_GET`, `do_POST`, `do_OPTIONS`
- In `do_OPTIONS`: return 204 with CORS headers (for preflight)
- For proxied paths: read request body, forward with `urllib.request`, relay response + CORS headers
- Static files: fall through to `super().do_GET()`

## Frontend JavaScript API Client

```javascript
var api = {
  health: function() {
    return fetch(baseUrl).then(function(res) { return res.json(); });
  },
  callTool: function(tool, args) {
    return fetch(baseUrl + 'api/call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tool: tool, args: args })
    }).then(function(res) { return res.json(); })
      .then(function(data) {
        // MCP response: { jsonrpc, id, result: { content: [{ type: "text", text: "..." }], isError: false } }
        var text = data.result.content[0].text;
        try { return JSON.parse(text); } catch(e) { return text; }
      });
  }
};
```

### MCP Response Structure

The ESP32 returns JSON-RPC 2.0 wrapped responses. The actual tool result is a JSON string inside `result.content[0].text`. For example, `fridge.stats.summary` returns:

```json
{
  "jsonrpc": "2.0", "id": 10000,
  "result": {
    "content": [{ "type": "text", "text": "{\"total_items\":1,...}" }],
    "isError": false
  }
}
```

The frontend must `JSON.parse()` the inner `text` field to get the actual data.

### Testing API Calls from Browser Console

When testing the web console, use the browser console to run inline fetch calls. This verifies the proxy path and API without needing to interact with UI elements:

```javascript
(async () => {
  const r = await fetch('/xiaozhi-api/api/call', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({tool: 'fridge.stats.summary', args: {}})
  });
  const d = await r.json();
  return JSON.stringify(d);
})()
```

Useful DOM checks:
- `document.getElementById('fridgeStats')?.innerHTML` — verify stats were rendered
- `document.querySelector('.conn-status-text')?.textContent` — check connection state
- `document.querySelectorAll('.food-card').length` — count rendered food cards
- `document.getElementById('tab-fridge')?.classList.contains('tab-content--active')` — verify tab switched

## Canvas Preview & Freehand Drawing

The e-paper display is 296×128 pixels. For a browser preview:
- Use a `<canvas>` element with `width="296" height="128"`
- Scale via CSS (`width: 592px` for 2x display)
- Draw elements: `fillText` for text, `strokeRect/fillRect` for rectangles, `moveTo/lineTo` for lines
- Draw a light grid background to show pixel boundaries

### Freehand Drawing (Canvas → Device Bitmap Pipeline)

The web console supports direct freehand drawing on the canvas preview, then submitting the result to the e-paper display. The pipeline:

1. **Draw**: User draws on the HTML `<canvas>` with mouse/touch events (`mousedown`→`mousemove`→`mouseup`, plus touch equivalents). Use `ctx.strokeStyle`, `ctx.lineWidth`, `ctx.lineCap='round'` for smooth strokes.
2. **Binarize**: Read all pixels via `ctx.getImageData(0, 0, 296, 128).data` (RGBA array). For each pixel, compute luminance `0.299*R + 0.587*G + 0.114*B`. Threshold at 128: `>=128` → white (bit=1), `<128` → black (bit=0). Alpha < 128 → treat as white (transparent = background).
3. **Pack to 1-bpp bitmap**: 8 pixels per byte, MSB first, each row padded to byte boundary. For 296px width: `rowBytes = Math.ceil(296/8) = 37`, total = `37 * 128 = 4736` bytes. (296 = 37×8, so no padding needed.)
4. **Upload**: `POST /api/canvas_image?name=freehand_N` with `Content-Type: application/octet-stream`, body = `Uint8Array` of bitmap bytes.
5. **Place on canvas**: `fridge.canvas.add_image` with `id`, `name=freehand_N`, `x=0, y=0, w=296, h=128, refresh=true`.

```javascript
// Core conversion function
function pixelsTo1bpp(data, width, height) {
  var rowBytes = Math.ceil(width / 8);
  var out = new Array(rowBytes * height);
  var idx = 0;
  for (var row = 0; row < height; row++) {
    for (var bcol = 0; bcol < rowBytes; bcol++) {
      var byte = 0;
      for (var bit = 0; bit < 8; bit++) {
        var px = bcol * 8 + bit;
        if (px < width) {
          var pi = (row * width + px) * 4;
          var a = data[pi + 3];
          var lum = (a < 128) ? 255 : (0.299 * data[pi] + 0.587 * data[pi+1] + 0.114 * data[pi+2]);
          var bitVal = (lum >= 128) ? 1 : 0;  // 1=white, 0=black
          byte |= (bitVal << (7 - bit));       // MSB first
        }
      }
      out[idx++] = byte;
    }
  }
  return out;
}
```

### Image Insertion (File/URL → Device Bitmap)

Same pipeline as freehand, but the source image is loaded from a local file (`FileReader.readAsDataURL`) or a URL (`<img crossOrigin="anonymous">`). The image is drawn to a temporary canvas at the target dimensions (with white background fill first to avoid transparent pixels becoming black), then the same `pixelsTo1bpp` → upload → `add_image` pipeline runs.

**Key detail**: Always fill the temp canvas with white before `drawImage()`, otherwise transparent PNG regions become black (bit=0) instead of white.

## Pitfalls

1. **Mixed content blocking**: HTTPS pages cannot fetch `http://` URLs. Use the proxy mode or firmware CORS with HTTP-only pages.
2. **ESP32 httpd OPTIONS**: The default config does not handle OPTIONS method. Must explicitly register `HTTP_OPTIONS` handlers for each URI.
3. **max_uri_handlers**: Adding OPTIONS handlers doubles the URI count. Increase `config.max_uri_handlers` to `16`. The default `8` silently fails to register the 9th handler (OPTIONS /api/canvas_image) — `httpd_register_uri_handler` returns `ESP_ERR_HTTPD_HANDLERS_FULL` with no visible error. This manifests as `405 Method Not Allowed` on OPTIONS preflight for `/api/canvas_image` even though the handler code exists and other endpoints' OPTIONS work fine.
4. **SetCorsHeaders on ALL response paths, not just errors**: `HandleCanvasImageUpload` and `HandleCanvasImageList` had `SetCorsHeaders` only on their error paths (storage not mounted, missing name param). The **success paths** — where the file is actually saved and JSON response sent — were missing `SetCorsHeaders`. This means the upload itself succeeds (HTTP 200, file written to LittleFS) but the browser rejects the response due to missing CORS headers, showing "获取失败" to the user. Fix: add `SetCorsHeaders(req)` right before every `httpd_resp_sendstr()` call, including success paths.
5. **One request at a time**: The ESP32 processes MCP calls sequentially. The frontend should not fire concurrent API calls.
6. **5s timeout**: The device waits 5s for MCP tool completion. Complex canvas operations with `refresh=true` may take longer — use `refresh=false` for batch operations then a single `canvas.refresh`.
7. **Canvas 30-label limit**: Always call `fridge.canvas.clear` before drawing a new layout. See SKILL.md pitfalls for details.
8. **HTTPS dev proxy breaks browser navigation**: If the Python dev proxy uses SSL certs, browser navigation fails with `ERR_CERT_COMMON_NAME_INVALID` because the cert CN doesn't match `localhost`. **Fix**: for testing, run a plain HTTP proxy without SSL. Write a minimal script that forwards `/xiaozhi-api/` to the device without wrapping the socket in SSL. Browser tools can then navigate to `http://localhost:<port>/xiaozhi.html`.
9. **`fridge.item.add` requires valid `expire_time`**: Although the tool schema marks `expire_time` as optional, the firmware rejects calls without a valid `YYYY-MM-DD HH:MM:SS` format date, returning `"Invalid expire_time format"`. Always provide a valid future date when adding items via the API or web console.
10. **Canvas tools require `id` parameter**: `fridge.canvas.add_text`, `add_rect`, `add_line`, and `add_image` all require a string `id` parameter. Omitting it returns `"Missing valid argument: id"`. The web console must auto-generate or require the user to provide an ID for each canvas element.
