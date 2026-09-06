# Custom Pages and Dynamic Elements

Pages 7–15 are persistent user pages. Page 6 is a separate compatibility canvas;
do not reuse its action names for custom pages.

## Current Contracts

Firmware 2.0.7 exposes aggregate MCP tools:

| Operation | Tool | Important args |
|---|---|---|
| Create/list/rename/delete/clear | `fridge.page.control` | `action`, `page`, `name`, `refresh` |
| Add/update/remove/list elements | `fridge.page.element.control` | `action`, `page`, `id`, element fields |
| Show a page | `fridge.pagemanager` | `target_page` |

Fine-grained names such as `fridge.page.create` are compatibility aliases in
`/api/call`; they are not individually exposed by `/mcp`. New integrations
should use the aggregate names.

Create and populate a page serially:

```json
{"tool":"fridge.page.control","args":{"action":"create","name":"Weather"}}
{"tool":"fridge.page.element.control","args":{"action":"add","page":7,"id":"title","type":"text","text":"Weather","x":10,"y":4,"font_size":16,"align":"center","refresh":false}}
{"tool":"fridge.page.element.control","args":{"action":"add","page":7,"id":"sep","type":"line","x":0,"y":0,"x1":10,"y1":24,"x2":285,"y2":24,"width":1,"refresh":false}}
{"tool":"fridge.pagemanager","args":{"target_page":7}}
```

Line elements must include compatibility fields `x=0,y=0` as well as their
real coordinates. Add all elements with `refresh=false`, then switch/refresh
once to reduce timeouts and e-paper wear.

## Geometry and Fonts

- Screen bounds are x=0–295 and y=0–127. Rectangles and images must fit fully.
- Text supports font 12 or 16. A device-side `clock` also supports font 56.
- Custom-page text uses a fixed 276px alignment/wrapping region. Firmware ignores
  `max_width`; omit it. Use x=10 for full-screen center or right alignment.
- Keep at most 30 elements, use unique stable IDs, and bound text to 1024 UTF-8
  bytes. The validated builder enforces these constraints before mutation.

## Persistence

LittleFS stores the page registry and layouts under `/canvas/`:

```text
/canvas/custom_pages.json
/canvas/page_7.json
/canvas/page_8.json
/canvas/layout.json       # page 6, separate format/lifecycle
```

The firmware prefixes in-memory label IDs by page so equal user IDs on different
pages do not collide. Add/remove/update operations persist the affected layout.
After firmware changes, verify both the live element list and a reboot reload.

Before rebuilding a page, validate the whole desired layout. Do not clear first
and discover a bad element later. `scripts/quick_page_builder.py --check` performs
an offline preflight, and its live mode checks that the custom page exists before
clearing it.

## Dynamic Values

There are two distinct patterns.

### Device-side dynamics

Firmware 2.0.7 accepts exactly:

| `dynamic_type` | Display value | Valid fonts |
|---|---|---|
| `clock` | `HH:MM` | 12, 16, 56 |
| `date` | `YYYY-MM-DD 周X` | 12, 16 |

```json
{"tool":"fridge.page.element.control","args":{"action":"add","page":7,"id":"clock","type":"text","text":"--:--","x":10,"y":4,"font_size":56,"align":"center","dynamic":true,"dynamic_type":"clock","refresh":true}}
```

The type is persisted as `dtype`. The periodic update compares the new rendered
value with the previous snapshot, so an unchanged minute/date does not refresh
the panel. Unsupported types must be rejected rather than silently displayed as
static placeholders.

### Agent-pushed dynamics

For weather, counters, system metrics, prices, or countdowns, add a stable text
element with `dynamic=true` but no `dynamic_type`. An Agent or cron task computes
the final string and updates it:

```json
{"tool":"fridge.page.element.control","args":{"action":"update","page":7,"id":"weather","text":"晴 28C","refresh":true}}
```

Fetch external data before contacting the device. If fetching fails, leave the
old display intact. Record history only after the device confirms success.

## Page 6 vs Custom Pages

| Operation | Page 6 | Pages 7–15 |
|---|---|---|
| Add text | `canvas.control action=add_text` | `page.element.control action=add,type=text` |
| Add rect | `canvas.control action=add_rect` | `page.element.control action=add,type=rect` |
| Add line | `canvas.control action=add_line` | `page.element.control action=add,type=line` |
| Add image | `canvas.control action=add_image` | `page.element.control action=add,type=image` |
| Clear | `canvas.control action=clear` | `page.control action=clear,page=N` |
| List | `canvas.control action=list` | `page.element.control action=list,page=N` |

## Failure and Adversarial Checks

- Reject page numbers outside 7–15 and refuse changes to built-in pages.
- Reject unknown fields, duplicate IDs, unsupported dynamic types, non-integer or
  off-screen geometry, unsafe image names, control characters, and oversized input.
- Confirm GET `/` identifies a xiaozhi board before mutation.
- Treat outer errors, `result.isError`, inner errors, malformed JSON, and timeouts
  as failures even when HTTP status is 200.
- Do not follow HTTP redirects from the validated device address; a redirect can
  otherwise escape the trusted-LAN boundary.
- Do not automatically retry a timed-out mutation. List current state first; the
  request may have succeeded before the response was lost.
- The builder snapshots and validates the existing element list before `clear`.
  On a later failure it clears partial state and restores the snapshot without a
  display refresh. If either snapshot or rollback is unsafe, it stops explicitly.
- Use serial requests. Concurrent display operations can exhaust ESP32 resources
  or race persistence.
- The LocalControl service has no authentication. Keep it and the web proxy on a
  trusted LAN or loopback; never publish them directly.

## Verification

Without a device, run the builder tests and the local `Litsea_Top` mock/proxy
integration suite. With a device, test create, add, update, list, remove, clear,
delete, an invalid built-in-page mutation, the 30-element limit, and persistence
after reboot.
