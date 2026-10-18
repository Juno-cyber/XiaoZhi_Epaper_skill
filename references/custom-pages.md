# Custom pages and dynamic elements

Firmware 2.5.2.1; aggregate tools are compatible with the 2.0.7+ contract.
Pages 7–15 persist user layouts. Page 6 is a separate canvas.

## Create, populate, display

1. `xiaozhi.py IP pages` lists built-in and custom pages. Do not assume 7 is free.
2. Call `fridge.page.control` with `{"action":"create","name":"Weather"}`.
   Read the allocated page from the response.
3. Build that page with a validated `.layout` file ending in `refresh`.
   The builder checks existence before clearing and reads back before display.

A custom text add has flat arguments:

```json
{"action":"add","page":7,"id":"title","type":"text","text":"天气","x":10,"y":4,"font_size":16,"align":"center","refresh":false}
```

Use `fridge.page.element.control` for elements, `fridge.page.control` for page
create/list/rename/delete/clear. Delete switches to page 5. Exact contracts,
line compatibility fields and reorder side effects: [API](api-reference.md).

## Layout and persistence

Fonts 12/16, plus 56 for device clocks. Text alignment uses a fixed 276px region;
`max_width` is ignored for custom pages. Use x=10 for full-screen center/right.
Builder caps layouts at 30 elements with unique IDs. The order of add commands
is the draw order. `update` changes text only; add with the same ID replaces geometry.

LittleFS: `/canvas/custom_pages.json`, `/canvas/page_N.json` for custom pages;
`/canvas/layout.json` for page 6. Operations save layouts; successful readback
verifies live state, not reboot persistence. Backup before replacing a page;
see [failure recovery](pitfalls.md). Do not clear just to update one value.

## Device-side clock/date

| `dynamic_type` | Value | Fonts |
|---|---|---|
| `clock` | `HH:MM` | 12, 16, 56 |
| `date` | `YYYY-MM-DD 周X` | 12, 16 |

```text
clear
text id=clock text="--:--" x=10 y=8 font_size=56 align=center dynamic=true dynamic_type=clock
text id=date text="日期" x=10 y=88 font_size=12 align=center dynamic=true dynamic_type=date
refresh
```

Dynamic type is returned as `dtype`; initial `text` is ignored and the device
computes the value. Time must be synchronized. Unchanged values do not cause
periodic refreshes. A clock tick during a staged batch can independently queue
a frame. Do not use a text-only update on a device clock: the handler replaces
its text callback; re-add its dynamic definition instead.

## Agent-provided values

Weather, counters, metrics and prices are external values, not firmware dynamic
types. Add an ordinary text element, fetch/validate data first, then update its
stable ID. The legacy `dynamic:true` flag alone does not create an updater.

```json
{"action":"update","page":7,"id":"weather","text":"晴 28C","refresh":true}
```

For multiple values use `refresh:false` on every update, read back and issue
one `fridge.pagemanager`. Do not rewrite or refresh unchanged external values.
A scheduled job is optional and belongs to the selected Agent runtime, not the
device; [Hermes-specific workflow](hermes-workflow.md) is only for Hermes tasks.
