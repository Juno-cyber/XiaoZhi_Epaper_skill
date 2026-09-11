---
name: xiaozhi-control
description: Discover, health-check, and control xiaozhi ESP32 devices on a trusted LAN over HTTP, including fridge data, e-paper pages, canvas layouts, images, and recipes. Use for local xiaozhi device operations; not for cloud/MQTT control.
license: MIT
metadata:
  version: 2.3.2
  author: Juno-cyber
  platforms: [linux, macos]
  prerequisites:
    commands: [python3]
  tags: [xiaozhi, esp32, smart-home, iot, lan-control, mcp]
  hermes:
    tags: [xiaozhi, esp32, smart-home, iot, lan-control, mcp]
    related_skills: [openhue]
---

# Xiaozhi LAN Control

Control a xiaozhi ESP32 device through its LocalControl HTTP server, normally on port 8080.

## Safety and operating invariants

- LocalControl has no authentication and uses plain HTTP. Use it only on a trusted LAN; never expose port 8080 or the development proxy to the public internet.
- Confirm device identity with GET / before mutating data or a display.
- Send requests serially. The ESP32 handles one request at a time and may time out on concurrent calls.
- Treat HTTP 200 as transport success only. Check outer error, MCP result.isError, and the inner tool result.
- For layouts, validate the full input before clearing a page. Add with refresh=false, then refresh once.
- Do not retry a mutation automatically after an ambiguous timeout: it may already have succeeded. Inspect state first.

## Device discovery and health

From the installed Hermes copy:

~~~bash
SKILL=~/.hermes/skills/smart-home/xiaozhi-control
IP=$(python3 "$SKILL/scripts/xiaozhi_discovery.py" --save)
curl --fail --max-time 3 "http://$IP:8080/"
~~~

From the repository, use scripts/... directly. Discovery tries the compatibility mDNS name, browsed xiaozhi HTTP services when Avahi is available, cached addresses, UDP discovery, and bounded subnet scanning.

~~~bash
python3 scripts/xiaozhi_discovery.py --all --health
python3 scripts/xiaozhi_discovery.py --subnet 192.168.40.0/24 --all
~~~

If automatic interface detection fails, pass --subnet. Scans larger than 4096 hosts require explicit --allow-large-scan; a 65536-host hard cap still applies.

## Calling tools

For scripts and curl, use the simplified endpoint:

~~~bash
curl --fail-with-body --max-time 10 -X POST "http://$IP:8080/api/call" \
  -H "Content-Type: application/json" \
  -d '{"tool":"fridge.stats.summary","args":{}}'
~~~

POST /api/call accepts {"tool":"...","args":{}}. POST /mcp accepts MCP JSON-RPC. Do not mix formats. Read [references/api-reference.md](references/api-reference.md) before using an unfamiliar tool or parameter.

Visible firmware 2.0.7 tools:

- fridge.item.{get,add,remove,clear_all,list,update}
- fridge.stats.{summary,query}
- fridge.pagemanager and fridge.recipe.recommend
- fridge.canvas.control
- fridge.page.control and fridge.page.element.control
- device.network.info

Firmware 2.0.7 maps legacy fine-grained names at /api/call, but new automation should use aggregate tools.

## E-paper pages and contracts

| Page | Purpose |
|---|---|
| 1 | Chat/status |
| 2 | Fridge statistics |
| 3 | Food list |
| 4 | Recipe |
| 5 | Home image |
| 6 | Agent-controlled canvas |
| 7–15 | Persistent custom pages |

Canvas page 6 and custom pages have different contracts:

~~~json
{"tool":"fridge.canvas.control","args":{"action":"add_text","id":"t1","text":"Hello","x":8,"y":2,"font_size":16,"refresh":false}}
~~~

~~~json
{"tool":"fridge.page.element.control","args":{"action":"add","page":7,"id":"t1","type":"text","text":"Hello","x":8,"y":2,"font_size":16,"refresh":false}}
~~~

For custom-page elements, use action=add plus type=text|rect|line|image; parameters are flat in args. Line elements should include compatibility fields `x=x1,y=y1`; never hard-code them to `(0,0)`.

## Validated layout builder

Prefer the builder over hand-written request loops:

~~~bash
python3 scripts/quick_page_builder.py "$IP" 6 my.layout --check
python3 scripts/quick_page_builder.py "$IP" 6 my.layout
~~~

Example layout:

~~~text
clear
text id=title text="Hello world" x=8 y=2 font_size=16 align=left
hline id=sep x1=8 x2=287 y=22 width=1
pixart id=heart art=heart x=260 y=2 w=24 h=24
refresh
~~~

Commands are clear, switch N, text, rect, line, hline, image, pixart, and refresh. Use `hline` for horizontal rules so one `y` value deterministically becomes both `y1` and `y2`; reserve `line` for intentional diagonal or vertical segments. Quote values containing whitespace. The builder rejects malformed input, duplicate IDs, unknown parameters, zero-length/off-screen geometry, unsupported pages, and layouts over 30 elements before contacting the device. It also reads line elements back and verifies their stored endpoints before the final refresh. Before a clear it requires a validated, restorable snapshot; if the rebuild then fails, it restores that snapshot without refreshing the panel. Any device or transport error produces a nonzero exit.

Custom pages 7–15 use the same DSL; the builder converts element commands to action=add plus type.

## Display constraints

- Screen: 296×128; keep important content within x=5–291 and y=2–126.
- Fonts: ordinary text uses 12 or 16. Custom-page clock dynamics also support 56. Approximate Chinese glyph widths track the ordinary font size.
- On page 6, align=center/right uses x as the left edge of a max_width region. For full-screen alignment use x=10,max_width=276.
- On custom pages, firmware fixes that region at 276px and ignores max_width; use x=10 for full-screen center/right alignment.
- Canvas has a 30-element limit. Clear before replacing a complete layout.
- Bitmap images are row-padded 1-bpp, MSB first; required bytes are ceil(width/8) × height.
- Firmware GB2312 fonts do not reliably render ·, ・, or —; use ASCII - as a source separator.

For design rules and layouts, read [references/display-philosophy.md](references/display-philosophy.md) and [references/page-templates.md](references/page-templates.md).

## Supporting utilities

- pixel_art_generator.py: list, generate, or upload 25 built-in 24×24 icons.
- zentangle_generator.py: procedural full-screen line art; requires NumPy, and Pillow for PNG output/preview.
- quote_fetcher.py: fresh copy with a configurable rolling deduplication window and audit log.
- workflow_map.py: create a compact Litsea-style SVG of cron schedules, target pages, status, and risks.
- crash_log.py: bounded serial capture; requires pyserial.
- templates/todo-list-page.sh: ready-made custom-page layout.

## Cron visualization and conversational delivery

When creating or materially updating a cron job that writes a XiaoZhi page:

1. Put this bounded marker at the very start of the job prompt, replacing the
   page and mode with the real values:

   ~~~text
   [XIAOZHI_CRON_META v1 page=6 mode=canvas-refresh]
   ~~~

   Valid pages are 6–15. Use a short lowercase mode such as `canvas-refresh`,
   `element-update`, or `page-rebuild`. The marker is visualization metadata;
   it does not grant device permissions.
2. After the scheduler confirms creation/update, generate a fresh view. Device
   discovery is best-effort so an offline screen does not hide the cron result:

   ~~~bash
   python3 scripts/workflow_map.py --discover
   ~~~

   The default artifacts are
   `~/.hermes/xiaozhi_canvas/workflow-map.svg` and `workflow-map.json`.
3. Give the visual to the user in the same response. If the conversation can
   display local images, embed the absolute SVG path. If it can attach files,
   attach the SVG; use a PNG conversion only when the channel rejects SVG and a
   converter is already available. Otherwise provide the absolute path plus a
   concise status summary. Never claim the user received a visual when the
   channel only received text.

The SVG is intentionally compact and matches Litsea_Top: white surfaces,
black/gray type, and `#FF5A5A` only for attention states and trigger points.
It shows tasks, schedules, target pages, status, a compact 24-hour timeline,
and risks. Do not add device-screen previews, per-job colors, or a color legend.
Cron state belongs to Hermes, not the XiaoZhi device. Deliver this visualization
through the Hermes conversation; do not expose it as a XiaoZhi device API or add
it to a static device-control website that cannot access Hermes runtime data.

If the user asked only to design or preview a schedule, do not create a real
job just to draw it. Render a clearly labeled candidate instead:

~~~bash
python3 scripts/workflow_map.py --discover \
  --preview-name "工作日提醒" --preview-schedule "0 8 * * MON-FRI" --preview-page 7
~~~

After the user authorizes creation, create the job and regenerate without the
`--preview-*` arguments so the returned visual reflects scheduler state.

Regenerate after create, update, pause/resume, or delete requests, and when the
user asks to inspect automations. Do not regenerate on every scheduled run.
Read [references/workflow-map.md](references/workflow-map.md) for the snapshot
schema, legacy-task inference, delivery fallbacks, and privacy boundaries.

Install optional Python dependencies from requirements-optional.txt. Shell templates additionally require Bash and curl. Windows users should run the skill under WSL; native Windows is not claimed as supported.

## References

- Exact HTTP/MCP contracts: [references/api-reference.md](references/api-reference.md)
- Current failures and diagnostics: [references/pitfalls.md](references/pitfalls.md)
- Custom pages and persistence: [references/custom-pages.md](references/custom-pages.md)
- Layouts and design: [references/page-templates.md](references/page-templates.md), [references/display-philosophy.md](references/display-philosophy.md)
- Web console: [references/web-console.md](references/web-console.md), [references/canvas-web-interaction.md](references/canvas-web-interaction.md)
- Firmware: [references/firmware-development.md](references/firmware-development.md)
- Hermes automation: [references/hermes-workflow.md](references/hermes-workflow.md), [references/canvas-creativity.md](references/canvas-creativity.md)
- Workflow map: [references/workflow-map.md](references/workflow-map.md)

## Verification

With a real device, verify discovery and identity, one read-only call, a page-6 batch, a custom-page batch, and persistence after power-cycle. Without a device:

~~~bash
python3 -m unittest discover -s tests -v
python3 scripts/quick_page_builder.py 127.0.0.1 6 example.layout --check
~~~
