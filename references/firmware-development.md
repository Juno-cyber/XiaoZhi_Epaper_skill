# Firmware source index

Read this only for firmware development or serial diagnosis. Normal LAN control
needs no SDK, serial port or flashing. Source baseline: `xiaozhi-esp32` commit
`178aca9` (2026-10-18), version **2.5.2.1**.

## Find the maintained source

The user's checkout is `~/Gitproject/xiaozhi-esp32`; other machines may use a
different directory. Read that checkout's `AGENTS.md` and
`docs/agent/build-and-boards.md` before building. Those files own SDK setup,
board configuration and flash instructions; this skill does not duplicate them.

- Current branch uses ESP-IDF **6.0.1+**, validated with **6.1**.
- Historical `jzx/xiaozhi_2.0.8` uses IDF 5.4.2. Use a separate checkout and
  build environment; do not reuse build/config/dependency artifacts across them.
- Active board: `bread-compact-wifi-epaperx`, 16MB flash; retain NVS and
  `canvas_data` when updating firmware. A routine control task never needs erase.
- Serial names vary: Linux `/dev/ttyUSB*`, macOS `/dev/cu.*`, Windows `COM*`.
  Identify the actual device instead of assuming `/dev/ttyUSB0`.

## Relevant paths within the firmware repository

| Question | Source |
|---|---|
| HTTP endpoints, mDNS, 15s MCP wait, response wrapper | `main/boards/bread-compact-wifi-epaperx/local_control.cc` |
| MCP registration, defaults, actions, refresh side effects | `main/boards/bread-compact-wifi-epaperx/Fridge/fridge_mcp.cc` |
| Custom page storage and dynamics | `main/boards/bread-compact-wifi-epaperx/Fridge/custom_page_manager.cc` |
| Home return, page switching, render-layout JSON | `main/display/epaperdisplay/epaper_display.cc` |
| Frame comparison/full refresh decisions | `main/display/epaperdisplay/epaper_refresh.h` |
| Panel waveform | `components/GxEPD2/src/epd/GxEPD2_290_T5D.cpp` |
| Voice/idle transitions | `main/application.cc` |
| Refresh/home-return regression tests | `scripts/tests/test_epaper_refresh.py`, `test_epaper_home_return.py` |

## Current behavior relevant to Agents

A background task owns the panel. It waits 80ms to coalesce queued frames, then
uses full refresh for startup/page changes/explicit full-refresh generation;
other frames use changed regions. There is no periodic automatic full refresh.
`SetPage` explicitly increments the full-refresh generation, even for the same
page; current HTTP tools do not expose a dedicated same-page partial present.

HTTP response confirms tool execution, not panel completion. Serial
`Refresh full/partial frame=… page=…` records actual driver work. A queued frame
can be superseded. Controller RAM synchronization after refresh does not imply
an additional physical refresh.

Home return pauses outside idle, restarts after conversation, and discards stale
callbacks. Config changes reset the deadline; `timeout_min=0` disables return.
Details: [API](api-reference.md), [diagnosis](pitfalls.md).

Canvas/custom layouts are stored in LittleFS and restored after it mounts.
In-memory readback alone cannot prove successful persistence; test reboot reload
only when that behavior is in scope. `scripts/crash_log.py` offers bounded serial
capture (pyserial required); opening serial may affect some boards, so identify
port ownership/reset wiring before use.
