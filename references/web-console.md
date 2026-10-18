# Litsea console: source index and browser-specific behavior

Baseline: `Litsea_Top` commit `fae123e` (2026-10-18). Local checkout is commonly
`~/Gitproject/Litsea_Top`; use its actual location. Normal Agent control should
use this skill's Python scripts rather than driving the website.

## Maintained implementation

| Topic | File in Litsea_Top |
|---|---|
| Connection, discovery, home setting, canvas editor | `js/xiaozhi.js` |
| Console page | `xiaozhi.html` |
| Optional local proxy | `deploy/proxy_server.py` |
| HTTPS site / HTTP compatibility routes | `deploy/nginx-litsea.conf` |
| Discovery regression tests | `tests/test_device_scan.js`, `tests/test_subnet_detection.js` |
| Proxy tests | `tests/test_proxy_server.py` |

Do not copy old CORS patches or Nginx snippets into firmware/site configuration:
the current firmware already has CORS handlers and the website owns its routes.
LocalControl uses 32 handler slots and at most 5 open sockets in this baseline.

## What changed in recent discovery

The website prioritizes saved addresses and mDNS, obtains candidate networks
from local evidence, continues a full /24 scan for multiple devices, deduplicates
by MAC, supports cancellation, and reports likely browser blocking. A stale
candidate must not override a manually selected subnet. No default network
should be guessed when evidence is missing.

The Python discovery helper follows the same principles where relevant. Its
native socket access avoids browser permission/mixed-content restrictions;
website scanning timeouts and heuristics are not interchangeable with Python's.

## Browser cannot connect but Python can

Check browser local-network permission, HTTPS-to-HTTP restrictions and the
site's HTTP compatibility entry. CORS is separate from network reachability.
The web console includes device name, home page and timeout controls; 0 means
no automatic return. Connect directly to a known LAN device when appropriate.

The optional local proxy binds loopback by default and must be configured with
`XIAOZHI_TARGET`. It currently allows only health, `api/call`, `api/canvas_image`;
**it does not proxy `api/home_page`, `api/device_name` or `api/page_layout`**.
Therefore proxy success for a canvas call does not prove every console control
is supported. Public site/OTA hosting is separate from LAN control forwarding;
never publish a proxy to an unauthenticated device.

## Preview and image semantics

- Logical screen 296×128. CSS scaling is only a browser preview.
- Mutation list: line `(x1,y1)` → `(x2,y2)`. Render-layout endpoint: line `(x,y)`
  → `(x1,y1)`. Do not interchange the schemas.
- Raw bitmap: row-padded 1-bpp, MSB first, **dark pixels = 1, white = 0**.
  Transparent pixels become white. Resize before packing; `w/h` does not scale.
- `/api/page_layout` includes base64 built-in bitmap data but is not a screenshot.
  Browser fonts are approximations; physical panel appearance still needs checking.
- Whole layout: serial writes with `refresh:false`, then one page presentation.
  The web editor can use per-element auto-refresh; turn that off when batching.
  Canvas reorder triggers refresh even when a false flag is supplied; custom
  page reorder does not present.

For pointer handling and element editing read
[canvas-web-interaction.md](canvas-web-interaction.md) only when editing that UI.
