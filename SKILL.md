---
name: yunmo-control
description: Discover and control Yunmo (云墨) e-paper devices on a trusted LAN, including pages, images, home-page settings, XiaoZhi/Qwen voice backend configuration, and local Agent management. Use for device operation over local HTTP, not cloud/MQTT control.
license: MIT
metadata:
  version: 3.2.2
  author: Juno-cyber
  platforms: [linux, macos, windows]
  prerequisites:
    commands: [python3]
  tags: [yunmo, xiaozhi, esp32, smart-home, iot, lan-control]
  hermes:
    tags: [yunmo, xiaozhi, esp32, smart-home, iot, lan-control]
    related_skills: [openhue]
---

# 云墨 LAN control

Operate from this skill directory. Core scripts use Python 3.10+ standard library;
on Windows replace `python3` with `py -3 -X utf8`. No curl, Bash, SDK or browser
is needed for normal control. Current reference: firmware **2.5.2.8**, 296×128.

## Product naming in conversation

- Call the product and each controlled e-paper device **云墨** in all user-facing
  conversation, status reports, prompts and generated page copy. Do not call the
  device “小智”, “XiaoZhi” or “喵喵同学”.
- For multiple devices, use `云墨（设备名称）` when a saved name exists, otherwise
  use a clear location or short MAC suffix such as `云墨（书桌）` or `云墨（A1B2）`.
  Confirm device identity before writes; never guess which 云墨 the user means.
- `xiaozhi.py`, `xiaozhi-control`, mDNS names, board identifiers and the saved
  voice-mode value `xiaozhi` are compatibility identifiers. Keep them unchanged
  in commands and API payloads, but do not use them as the product name.
- Say **小智后端** only when distinguishing that voice backend from **千问实时语音**.
  Changing a backend does not rename the 云墨 device.
- Do not change the device's persisted name merely to match this vocabulary. Use
  `name --set` only when the user explicitly asks to rename that device.

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
python3 scripts/xiaozhi.py DEVICE_IP elements 2
python3 scripts/xiaozhi.py DEVICE_IP show 2
python3 scripts/xiaozhi.py DEVICE_IP home
python3 scripts/xiaozhi.py DEVICE_IP voice
python3 scripts/xiaozhi.py DEVICE_IP voice-config
```

For home-page settings, rename, raw tool calls or XiaoZhi URL configuration, read
[api-reference.md](references/api-reference.md). For Qwen realtime or local Agent
management, read [voice-and-agent.md](references/voice-and-agent.md). CLI output is decoded JSON;
errors exit nonzero. HTTP success alone does not prove tool success.

**Build a layout:** write a UTF-8 `.layout` file and use the builder:

```bash
python3 scripts/quick_page_builder.py DEVICE_IP PAGE_ID templates/hello.layout --check
python3 scripts/quick_page_builder.py DEVICE_IP PAGE_ID templates/hello.layout --backup before.json
```

Use the allocated `page` from `fridge.page.control action:create` for `PAGE_ID`,
or a listed `builtin:false` page the user wants to replace. Never assume page 6 exists.
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
- Page 1 is read-only chat. Existing pages 2–15 are editable custom pages,
  including migrated page 6. Default page 2 is “时间显示” (time/date/image).
  Always list pages and use `builtin:false`; create missing pages first.
  Fridge inventory/stats/recipes and love/memorial counters are suspended.
  The `fridge.page.*` prefix remains the display API, not active fridge business.
- Live time/date must use native `dynamic_type=clock/date` elements, never pixels
  baked into a bitmap. Historical publication dates, durations and explicitly
  labeled historical previews stay fixed. Read [display preferences](references/display-preferences.md)
  when updating this user’s canvases.
- Keep important content within x=5–291, y=2–126. Fonts: 12/14/16; custom `clock`
  also supports 56. At most 30 elements per layout. Built-in pixel art is 24×24;
  image `w/h` describes raw storage and does not resize it.
- For full-width centered/right text use x=10 and `max_width=276`. All custom
  pages accept `max_width`; retain it when backing up or restoring layouts. Prefer `hline` for separators. Avoid unsupported `·`, `・`, `—`.
- Device HTTP :8080 and development proxies belong on a trusted LAN/loopback.
  Do not expose them to the public internet.

## Read only what the task needs

| Task | Reference |
|---|---|
| Tool parameters, config, bitmap format | [API](references/api-reference.md) |
| Qwen realtime, voice modes, tasks or memory | [Voice and Agent](references/voice-and-agent.md) |
| Custom pages, clocks, persistence | [Custom pages](references/custom-pages.md) |
| Discovery, failed writes, extra refreshes | [Troubleshooting](references/pitfalls.md) |
| Layout examples / creative choices | [Templates](references/page-templates.md) / [Design](references/display-philosophy.md) |
| Litsea browser console / element editor | [Web console](references/web-console.md) / [Interaction](references/canvas-web-interaction.md) |
| Firmware changes or serial diagnostics | [Firmware](references/firmware-development.md) |
| Requested Hermes automation | [Hermes workflow](references/hermes-workflow.md) |

Scheduling is optional and runtime-specific. Do not create a schedule merely to
control a screen. Load the Hermes reference only when the user requests automation
in that runtime; other agents use their own scheduler.
