---
name: yunmo-control
description: Discover and control Yunmo (云墨) e-paper devices on a trusted LAN, including pages, images, home-page settings, standard/Qwen realtime voice configuration, and local Agent management. Use for device operation over local HTTP, not cloud/MQTT control.
license: MIT
metadata:
  version: 3.3.0
  author: Juno-cyber
  platforms: [linux, macos, windows]
  prerequisites:
    commands: [python3]
  tags: [yunmo, esp32, e-paper, voice-device, lan-control]
  hermes:
    tags: [yunmo, esp32, e-paper, voice-device, lan-control]
---

# 云墨 LAN control

Operate from this skill directory. Core commands need Python 3.10+ only; on
Windows replace `python3` with `py -3 -X utf8`. Current target: `Yunmo_x1`,
firmware **2.5.2.9**, 296×128.

## Fast start

Do not inspect the repository, tests, script implementations, README, or every
reference before operating a device. Run the commands below and open one reference
only when the requested operation needs details.

```bash
python3 scripts/check_update.py --timeout 8
python3 scripts/xiaozhi_discovery.py --json --save
```

The update check reads the remote commit first and downloads Git data only when
an update exists. It may fast-forward a clean trusted `main` checkout and sync an
installed copy. A timeout, offline network, local edits, untrusted remote, or
diverged history reports a skip and must not block device control.

Discovery validates a cached address first and normally returns immediately. If
the user supplies an IP, skip discovery and run `python3 scripts/xiaozhi.py IP health`.
Use `--all --json` only when the user needs every device. If discovery fails, read
[troubleshooting](references/pitfalls.md); never guess a network range.

## Product naming

- Call the product and device **云墨** in user-facing text. For multiple devices,
  use `云墨（设备名/位置）` and confirm identity before writes.
- Use `name --set` only when the user explicitly asks to rename a device.

## Common operations

```bash
python3 scripts/xiaozhi.py DEVICE_IP health
python3 scripts/xiaozhi.py DEVICE_IP pages
python3 scripts/xiaozhi.py DEVICE_IP elements 2
python3 scripts/xiaozhi.py DEVICE_IP show 2
python3 scripts/xiaozhi.py DEVICE_IP home
python3 scripts/xiaozhi.py DEVICE_IP voice
python3 scripts/xiaozhi.py DEVICE_IP voice-config
```

Read [API](references/api-reference.md) for page creation, home settings, rename,
raw calls, images or standard voice URL changes. Read [Voice and Agent](references/voice-and-agent.md)
only for Qwen realtime or local Agent operations. CLI errors exit nonzero.

For a complete layout, write a UTF-8 `.layout` and use the builder:

```bash
python3 scripts/quick_page_builder.py DEVICE_IP PAGE_ID templates/hello.layout --check
python3 scripts/quick_page_builder.py DEVICE_IP PAGE_ID templates/hello.layout --backup before.json
```

`PAGE_ID` must be an existing `builtin:false` page selected by the user or the page
returned by page creation. Never assume page 6 exists. The builder validates,
backs up, writes without intermediate refreshes, reads back and presents once.
See [templates](references/page-templates.md) only when creating a layout.

## Required constraints

- Confirm device identity before writes. Requests to one device are serial. Never
  automatically retry a timed-out write; read state first because it may have run.
- Back up before replacing a page. Stop after an ambiguous transport failure.
- Batch with `refresh=false`, verify, then present once. A response does not prove
  the physical e-paper refresh has completed.
- Page 1 is read-only chat. Existing pages 2–15 are editable custom pages,
  and default page 2 is “时间显示”. Always list pages; preserve page 2 unless the
  user asks to replace it.
- Live time/date must use native `dynamic_type=clock/date` elements, never pixels
  baked into a bitmap. Keep content within x=5–291, y=2–126; use fonts 12/14/16
  (`clock` also supports 56), at most 30 elements, and avoid `·`, `・`, `—`.
- Device HTTP :8080 and development proxies belong on a trusted LAN/loopback.
  Do not expose them to the public internet.

## Open only when needed

| Task | Reference |
|---|---|
| Tool parameters, config, bitmap format | [API](references/api-reference.md) |
| Qwen realtime, voice modes, tasks or memory | [Voice and Agent](references/voice-and-agent.md) |
| Custom pages, clocks, persistence | [Custom pages](references/custom-pages.md) |
| Discovery, failed writes, extra refreshes | [Troubleshooting](references/pitfalls.md) |
| Layout design | [Templates](references/page-templates.md) / [Design](references/display-philosophy.md) |
| Website or firmware development | [Web](references/web-console.md) / [Firmware](references/firmware-development.md) |
| User-requested Hermes automation | [Hermes](references/hermes-workflow.md) |

Do not create schedules unless the user requests one.
