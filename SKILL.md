---
name: xiaozhi-control
description: Discover and control XiaoZhi e-paper devices on a trusted LAN, including pages, text, images, fridge data and home-page settings. Use for device operation over local HTTP, not cloud/MQTT control.
license: MIT
metadata:
  version: 3.0.0
  author: Juno-cyber
  platforms: [linux, macos, windows]
  prerequisites:
    commands: [python3]
  tags: [xiaozhi, esp32, smart-home, iot, lan-control]
  hermes:
    tags: [xiaozhi, esp32, smart-home, iot, lan-control]
    related_skills: [openhue]
---

# XiaoZhi LAN control

Operate from this skill directory. Core scripts use Python 3.10+ standard library;
on Windows replace `python3` with `py -3 -X utf8`. No curl, Bash, SDK or browser
is needed for normal control. Current reference: firmware **2.5.2.1**, 296×128.

## Connect, then choose one path

```bash
python3 scripts/xiaozhi_discovery.py --json --save
python3 scripts/xiaozhi.py DEVICE_IP health
```

Discovery validates cached addresses before mDNS/UDP/subnet scanning. On failure,
try `--host KNOWN_IP` or `--subnet LAN_CIDR --scan-timeout 4`; do not guess networks.
For multiple devices use `--all --json`, select by name/MAC, and pass the selected IP.
A cached IP can be reassigned: confirm `GET /` identity before every write session.

**Read or make a simple change:**

```bash
python3 scripts/xiaozhi.py DEVICE_IP pages
python3 scripts/xiaozhi.py DEVICE_IP elements 6
python3 scripts/xiaozhi.py DEVICE_IP show 6
python3 scripts/xiaozhi.py DEVICE_IP home
```

For home-page settings, rename, raw tool calls or fridge data, read
[api-reference.md](references/api-reference.md). CLI output is decoded JSON;
errors exit nonzero. HTTP success alone does not prove tool success.

**Build a layout:** write a UTF-8 `.layout` file and use the builder:

```bash
python3 scripts/quick_page_builder.py DEVICE_IP 6 templates/hello.layout --check
python3 scripts/quick_page_builder.py DEVICE_IP 6 templates/hello.layout --backup before.json
```

Use `clear`, then elements, then one `refresh`. The builder validates everything,
snapshots the old page, batches with `refresh=false`, reads back all written
elements, then submits one `fridge.pagemanager` call. Legacy `switch N` is deferred
and merged into that final call; it must target the page being built. With neither
`refresh` nor `switch`, it only writes and verifies. See
[page-templates.md](references/page-templates.md) for layouts.

## Constraints that matter

- Requests to one device are serial. Core calls wait 20s because firmware may
  queue an MCP call for 15s. Never automatically retry a timed-out write.
- A rejected rebuild can restore its snapshot before presentation. An ambiguous
  transport failure stops **without rollback**; read state and use the backup to
  decide recovery. The batch is not a firmware transaction.
- Do not switch before writing or refresh individual elements. `SetPage`, even
  for the same page, requests a full refresh. HTTP acknowledgment and layout
  readback do **not** prove physical panel completion. See
  [pitfalls.md](references/pitfalls.md) for double-flash diagnosis.
- Pages: 1 chat, 2 fridge stats, 3 food list, 4 recipe, 5 home image,
  6 canvas, 7–15 custom. List/create custom pages before writing them.
- Keep important content within x=5–291, y=2–126. Fonts: 12/16; custom `clock`
  also supports 56. At most 30 elements per layout. Built-in pixel art is 24×24;
  image `w/h` describes raw storage and does not resize it.
- For centered/right text use x=10. Canvas permits `max_width`; custom pages
  fix it at 276px. Prefer `hline` for separators. Avoid unsupported `·`, `・`, `—`.
- Device HTTP :8080 and development proxies belong on a trusted LAN/loopback.
  Do not expose them to the public internet.

## Read only what the task needs

| Task | Reference |
|---|---|
| Tool parameters, config, bitmap format | [API](references/api-reference.md) |
| Custom pages, clocks, persistence | [Custom pages](references/custom-pages.md) |
| Discovery, failed writes, extra refreshes | [Troubleshooting](references/pitfalls.md) |
| Layout examples / creative choices | [Templates](references/page-templates.md) / [Design](references/display-philosophy.md) |
| Litsea browser console / element editor | [Web console](references/web-console.md) / [Interaction](references/canvas-web-interaction.md) |
| Firmware changes or serial diagnostics | [Firmware](references/firmware-development.md) |
| Requested Hermes automation | [Hermes workflow](references/hermes-workflow.md) |

Scheduling is optional and runtime-specific. Do not create a schedule merely to
control a screen. Load the Hermes reference only when the user requests automation
in that runtime; other agents use their own scheduler.
