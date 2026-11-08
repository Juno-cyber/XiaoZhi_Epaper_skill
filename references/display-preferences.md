# Display preferences for Juno’s XiaoZhi

User-selected defaults (2026-10-25), not a universal requirement for other users:

- Chinese: WenQuanYi bitmap 12/14/16 px. Body text regular, minimum 12 px;
  headings may be slightly heavier. Recipe body uses one size with about 17 px line spacing.
- Large digits: option F, Fredoka Regular 400 at 56 px. Keep its rounded shapes;
  do not substitute Mystery Quest. Sizes here are pixel sizes, not print points.
- Live wall-clock time and current date must be native dynamic text elements:
  `dynamic=true dynamic_type=clock` or `dynamic=true dynamic_type=date`.
  Leave their region blank in background artwork. Verify `dtype` on element readback
  and the changing value after a minute; an image of a clock is not dynamic.
- Historical publication/edition dates, shift anchors, durations and labeled historical
  countdown previews are fixed facts; do not replace them with the current date.
- A love-day counter, seasonal garden, news feed or rotation is NOT made automatic by
  adding a dynamic date. These need separate implemented update logic; never claim otherwise.

## Firmware compatibility

The maintained 2.5.2.8 firmware includes actual WenQuanYi 14 and uses Fredoka
Regular for the native 56 px clock. Older 2.5.2.4 builds may map size 14 to
WenQuanYi 16 and size 56 to Mystery Quest, so check the installed version before
relying on the newer appearance.
The layout builder accepts 14, but cannot infer the renderer from element metadata.

On the extended build, a clock/date layout can use:

```text
text id=time text="--:--" x=140 y=5 font_size=56 max_width=150 align=center dynamic=true dynamic_type=clock
text id=date text="日期" x=140 y=65 font_size=14 max_width=150 align=center dynamic=true dynamic_type=date
```

Native clock/date update without cron. A text-update call can remove a dynamic callback;
re-add the complete dynamic definition instead. Stage writes with `refresh=false`,
verify all pages, then present one selected page once.
