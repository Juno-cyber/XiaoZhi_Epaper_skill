# Layout templates

Save UTF-8 `.layout` files; validate with `quick_page_builder.py IP PAGE FILE --check`,
then run the same command without `--check`. `refresh` presents once after readback.
All element writes have `refresh:false`. `switch PAGE` is a compatibility alias
for the final presentation, not an instruction to show an intermediate screen.

## Greeting / one thought (an existing custom page)

Use `templates/hello.layout`. Replace its message; keep generous white space.
A full-screen centered line is `x=10 align=center` (region width 276), not x=148.

## Three tasks (existing custom page 2–15)

```text
clear
text id=title text="今日待办" x=16 y=6 font_size=16
hline id=sep x1=16 x2=280 y=30
rect id=box1 x=16 y=46 w=8 h=8 filled=false
text id=item1 text="完成最重要的一件事" x=36 y=42 font_size=12
rect id=box2 x=16 y=68 w=8 h=8 filled=false
text id=item2 text="散步一会儿" x=36 y=64 font_size=12
rect id=box3 x=16 y=90 w=8 h=8 filled=false
text id=item3 text="给今天留一点空白" x=36 y=86 font_size=12
refresh
```

For changing text on a custom page use `page.element.control action=update` with
stable IDs; no need to clear/rebuild. A filled checkbox is replaced with add.
The older `templates/todo-list-page.sh` remains a Bash convenience wrapper.

## Device clock (custom pages only)

Use the [custom-page clock example](custom-pages.md#device-side-clockdate).
It updates on the device without Agent polling or cron.

## Image and caption

```text
clear
image id=art name=my_art x=16 y=12 w=96 h=80
text id=caption text="留一点想象" x=132 y=32 font_size=16
text id=note text="今天的小小发现" x=132 y=64 font_size=12
refresh
```

Upload `my_art` first with exactly `ceil(96/8)*80=960` bytes. For procedural art,
see `zentangle_generator.py --help`. Built-in icons use `pixart … art=heart`
with a fixed 24×24 footprint; run `pixel_art_generator.py --list` for names.
The builder prepares images before clearing and checks stored byte counts.

## DSL reference

Commands: `clear`, `text` (`label` alias), `rect`, `line`, `hline`, `image`,
`pixart`, `refresh`, `switch N`. Keys follow the [API fields](api-reference.md).
Quote text with spaces; booleans are `true/false`. For horizontal rules use
`hline id=sep x1=16 x2=280 y=30 width=1`; use `line` for intentional diagonals.
At most 30 elements, unique IDs, no individual `refresh:true`, and no unsupported
fields. Add in bottom-to-top drawing order. Omit `clear` for a small replacement
of known IDs; omit `refresh`/`switch` when only staging data is intended.

Builder calls are not atomic against independent writers, dynamic clocks or
voice transitions. See [refresh diagnosis](pitfalls.md#an-update-seems-to-refresh-twice).
