# Troubleshooting: discovery, writes and panel refresh

## Cannot find a powered-on device

1. `python3 scripts/xiaozhi_discovery.py --json --save --verbose` validates cached
   IPs first, then tries bounded mDNS, UDP and actual local subnets.
2. Known IP: `--host IP --timeout 5`. This does not scan other addresses.
   DHCP can reassign an old IP to another device; compare name/MAC/board.
3. Unknown IP: use the confirmed Wi-Fi CIDR with `--subnet CIDR --scan-timeout 4`.
   Default scan timeout is 2s (formerly 0.5s, which missed a real device).
   An explicit subnet also bounds cache/mDNS candidates; inactive Linux interfaces
   are skipped. `--workers 8` reduces network pressure. All requests to one host remain serial.
4. Check same LAN, Wi-Fi connection, power, guest/AP isolation and VPN routing.
   A powered e-paper panel can retain its picture while its controller is offline.
   If interface detection fails, `--host` and `--subnet` still work.
5. mDNS is optional. Linux can use Avahi; macOS can use `dns-sd`; native Windows
   interface detection uses PowerShell JSON. Neither a missing mDNS tool nor a
   blocked broadcast should prevent an explicit IP probe.

Cache only supplies candidates. `--all --json` enumerates devices; select by
identity. Do not write to the first device just because several share a board.
The default discovery call stops after finding one; it is not an inventory.

## An update seems to refresh twice

First distinguish **two display requests** from the **multi-phase waveform of
one full refresh**. The firmware's async queue coalesces some nearby frames,
but this is not a guarantee that redundant requests will collapse.

- `fridge.pagemanager` always requests full refresh, even on the same page.
  `canvas.refresh` and add/update/clear with `refresh:true` also present.
- Use clear/add with explicit `refresh:false`, read back, then **one** final
  `fridge.pagemanager`. Do not switch before writing. The builder defers old
  `switch N` commands and merges them with final `refresh`.
- Legacy canvas `reorder` refreshes regardless of its refresh flag (custom-page reorder
  does not). Prefer adding
  in desired z order. A create/list/readback operation is not a reason to refresh.
- A clock/date tick, voice state transition, a different web/Agent writer, or
  the home-return timer can independently produce a later frame. Check
  `python3 scripts/xiaozhi.py IP home`; do not silently disable user settings.
- `GET /api/home_page` reports the configured home, not current page. A return
  to that page after the configured idle timeout is expected, not a lost write.

For evidence, observe the physical panel or capture a bounded serial log and
count `Refresh full frame=…` / `Refresh partial frame=…` entries with page and
sequence. `Queued frame` is not necessarily displayed. `writeImageAgain` updates
panel controller RAM after a refresh; it is not a second `panel.refresh` call.
A single successful HTTP response cannot establish physical completion.

The skill can eliminate duplicate requests it sends. Strict atomic batches,
refresh-completion telemetry and a same-page partial-refresh API would require
firmware changes; do not claim they exist in 2.5.2.4.

## Failed / partial writes

- Inspect outer errors, MCP `isError`, and inner result. HTTP 200 is insufficient.
- Client default is 20s; firmware's MCP wait is 15s. Keep tool JSON under 4096
  bytes. If a response times out, read elements before deciding to retry.
- Builder validates the entire input and restorable snapshot before clear;
  images must exist and match raw size. `--backup before.json` saves the old
  element state on the host. Known pre-presentation failures restore it without
  refreshing. Transport/timeout failures stop without automatic rollback.
- Recovery: list current elements, compare with the intended layout and backup,
  then deliberately finish or rebuild from the backup. The backup JSON contains
  `page` and `elements`; use add commands with the saved type/fields and one final
  show. For dynamic text translate `dynamic_type`/`dtype` as appropriate.
- The multi-request batch is not atomic. Other writers or dynamic labels on the
  active page may expose intermediate changes. Avoid concurrent editors.
- Readback verifies content/geometry, not exact font appearance or disk durability.
  Reboot verification is a separate test; do not power-cycle for an ordinary edit.

## Wrong-looking output

- Use the MCP element list for mutation coordinates. `/api/page_layout` uses
  internal render coordinates and is not a directly replayable backup.
- Lines require all four endpoints; custom pages mirror the start into `x,y`.
  `hline` avoids accidental diagonals. Builder verifies every written element.
- Text widths are estimates; use 12/16px, leave margins, and avoid unsupported
  punctuation. Custom pages ignore `max_width` and align within 276px.
- Image bits: 1 black, 0 white, row-padded. Width/height never scales an asset.
- For browser-only failures consult [web-console.md](web-console.md); do not
  reflash firmware just because the browser blocks a local network request.
