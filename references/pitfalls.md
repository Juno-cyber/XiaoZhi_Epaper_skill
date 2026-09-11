# Current operational pitfalls

This file describes the current supported behavior. Superseded incident notes belong in Git history, not in Agent instructions.

## Connection and API

1. **Verify identity before mutation.** GET / must return status=ok and the expected board/device information. A stale cached IP may now belong to another host.
2. **No authentication or encryption.** LocalControl is trusted-LAN only. Do not port-forward it, publish it through a public reverse proxy, or use it on an untrusted Wi-Fi network.
3. **HTTP 200 does not mean tool success.** Inspect outer error, result.isError, and the JSON/string inside result.content.
4. **Do not mix endpoint formats.** /api/call uses tool/args; /mcp uses MCP JSON-RPC.
5. **Requests are serial.** Avoid concurrent calls. A timeout after a mutation is ambiguous; inspect state before deciding whether to retry.
6. **Diagnose reachability first.** If GET / fails, investigate power/Wi-Fi/address changes. If GET works but browser POST fails, inspect CORS/OPTIONS or the local proxy.
7. **Firmware versions differ.** Firmware 2.0.7 exposes aggregate tools and maps legacy names at /api/call. Firmware 2.0.5 may require legacy names. Query health/version instead of guessing.

## Pages and rendering

8. **Page 6 differs from pages 7–15.** Canvas uses fridge.canvas.control with actions such as add_text. Custom pages use fridge.page.element.control with action=add and a separate type field.
9. **Custom element parameters are flat.** page, id, type, coordinates, and content are siblings in args.
10. **Line endpoints and compatibility.** Always send all four real endpoints `x1,y1,x2,y2`. For custom pages mirror the start into compatibility fields `x=x1,y=y1`; never hard-code `(0,0)`. Use builder `hline` for horizontal rules so `y1=y2` is guaranteed, and verify stored endpoints before refreshing.
11. **Preflight before clear.** Validate every command, required field, coordinate, ID, and element count before deleting the existing layout.
12. **Batch refresh.** Clear/add with refresh=false and refresh once at the end. This reduces latency, flicker, and e-paper wear.
13. **Canvas element limit.** Page 6 accepts at most 30 labels. Clear before replacing a whole composition; reuse stable IDs for updates.
14. **Text width is approximate.** Chinese glyphs are roughly 12px or 16px. English and punctuation vary; verify important layouts on the physical display.
15. **Alignment semantics differ from HTML Canvas.** For center and right alignment, x is the region's left edge. Page 6 uses x+max_width; custom pages fix the width at 276px and ignore max_width.
16. **Font repertoire is limited.** Use ASCII - instead of ·, ・, or —. Test unusual Unicode against the device font.
17. **Images are raw bitmaps.** Use row-padded 1-bpp MSB-first data of ceil(width/8) × height bytes. URL-encode and restrict image names; never treat them as filesystem paths.

## Persistence and browser console

18. **Persistence needs explicit verification.** After create/add/update, power-cycle and list the page. A successful in-memory render does not prove the layout was saved.
19. **Direct browser access needs OPTIONS and CORS headers on every endpoint.** A same-origin local proxy is usually more reliable.
20. **Keep the development proxy local.** Bind to loopback by default, cap request/response sizes, allow only known device paths, and use a threaded server so one stalled device call does not freeze static assets.

## Firmware debugging

21. **Tool registration is bounded.** The cloud/MQTT service may reject devices that expose too many MCP tools. Prefer aggregate tools and confirm tools/list pagination.
22. **CORS handlers count toward ESP HTTP handler limits.** Check every registration return value and size max_uri_handlers for all GET, POST, and OPTIONS handlers.
23. **Early application states may precede audio initialization.** Do not call audio-service methods before initialization; use a captured backtrace and addr2line for crash loops.
24. **Build/flash tools may need an interactive serial environment.** Use the documented ESP-IDF environment, correct baud rate, and a bounded serial capture. See firmware-development.md.
