# Canvas Web Interaction Patterns

Patterns for building an interactive canvas-based web UI that syncs with the xiaozhi ESP32 e-paper display (296×128, page 6). All code is vanilla JS (no frameworks).

## Unified Canvas Event System (CRITICAL)

When a canvas element serves multiple interaction modes (brush drawing, element dragging, click-to-place preview), DO NOT register separate `mousedown`/`mousemove`/`mouseup` listeners for each mode. Multiple listeners on the same canvas cause:
- Event ordering issues (one handler's `preventDefault()` doesn't stop the next)
- Silent failures (hit-test in one handler never fires because another handler already returned)
- Impossible-to-debug "dragging doesn't work" symptoms

**Correct pattern**: ONE `attachCanvasEvents()` function that registers a single set of `mousedown`/`mousemove`/`mouseup`/`mouseleave`/`click` listeners, with an internal state machine that switches between modes:

```javascript
var state = {
  brush: { drawing: false, size: 2, mode: 'draw', lastX: 0, lastY: 0, offscreen: null },
  drag: { active: false, elementIndex: -1, startX: 0, startY: 0, moved: false, justDragged: false, initial: null },
  preview: { active: false, x: 0, y: 0, x1: 0, y1: 0, x2: 0, y2: 0, firstClick: true, lineReady: false }
};
```

## Brush Offscreen Canvas (CRITICAL — prevents笔迹消失)

**Problem**: `renderCanvasPreview()` is called on every mousemove (preview mode), mouseleave, and tab switch. It starts with `ctx.fillStyle='#fff'; ctx.fillRect(0,0,296,128)` — wiping ALL pixel data from the visible canvas. If brush strokes are drawn directly on the visible canvas, they vanish instantly when any mousemove/leave/tab-switch triggers a redraw.

**Fix**: Use an offscreen canvas (`state.brush.offscreen`) as a persistent backing store for freehand brush strokes:

1. **`getBrushCanvas()`**: lazily creates a 296×128 offscreen canvas, fills it white
2. **`drawBrushDot(x,y)`** and **`drawBrushSegment(x1,y1,x2,y2)`**: draw to BOTH the visible canvas AND the offscreen canvas
3. **`renderCanvasPreview()`**: after drawing grid + elements, composite the offscreen canvas on top: `ctx.drawImage(state.brush.offscreen, 0, 0)`
4. **`clearFreehandCanvas()`**: clear the offscreen canvas only, then call `renderCanvasPreview()` to redraw visible canvas (preserves grid + elements)
5. **`submitFreehandToScreen()`**: read pixels from the OFFSCREEN canvas (not the visible one) — this avoids grid/element pixels contaminating the 1-bpp bitmap

```javascript
function getBrushCanvas() {
  if (!state.brush.offscreen) {
    state.brush.offscreen = document.createElement('canvas');
    state.brush.offscreen.width = 296;
    state.brush.offscreen.height = 128;
    var ctx = state.brush.offscreen.getContext('2d');
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, 296, 128);
  }
  return state.brush.offscreen;
}

function drawBrushSegment(x1, y1, x2, y2) {
  var ctx = el.epaperPreview.getContext('2d');
  var bctx = getBrushCanvas().getContext('2d');
  var color = state.brush.mode === 'erase' ? '#fff' : '#000';
  ctx.strokeStyle = color; bctx.strokeStyle = color;
  ctx.lineWidth = bctx.lineWidth = Math.max(1, state.brush.size);
  ctx.lineCap = bctx.lineCap = 'round';
  ctx.lineJoin = bctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  bctx.beginPath(); bctx.moveTo(x1, y1); bctx.lineTo(x2, y2); bctx.stroke();
}

// In renderCanvasPreview(), AFTER drawing all elements:
if (state.brush.offscreen) {
  ctx.drawImage(state.brush.offscreen, 0, 0);
}
```

## Click-to-Place Preview (Decoupled Submit Model)

When a non-brush tool is active, mousemove shows a semi-transparent preview of the element at the cursor position. This is drawn AFTER `renderCanvasPreview()` as an overlay.

**IMPORTANT — decoupled submit model**: Clicking on the canvas fills coordinate input fields and shows a preview, but does **NOT** automatically call the API to submit the element. The user must click the corresponding "添加" (Add) button to sync to the device. This reduces e-paper refresh frequency (extending screen lifespan) and lets users adjust parameters before committing. The `line` tool uses a `lineReady` state: after two clicks (start + end), a full preview shows until the button is pressed.

```javascript
function renderPreview() {
  if (isBrushActive() || !state.preview.active) return;
  var tool = getActiveTool();
  if (tool !== 'text' && tool !== 'rect' && tool !== 'line') return;

  var ctx = el.epaperPreview.getContext('2d');
  ctx.save();
  ctx.globalAlpha = 0.4;

  if (tool === 'text') { /* ... fillText at preview.x/y ... */ }
  else if (tool === 'rect') { /* ... strokeRect at preview.x/y ... */ }
  else if (tool === 'line') {
    var lw = parseInt(document.getElementById('lineWidth').value) || 2;
    ctx.lineWidth = Math.max(1, lw);
    ctx.lineCap = 'round';
    if (!state.preview.firstClick) {
      // After first click: show line from start to cursor
      ctx.beginPath();
      ctx.moveTo(state.preview.x1, state.preview.y1);
      ctx.lineTo(state.preview.x, state.preview.y);
      ctx.stroke();
    } else if (state.preview.lineReady) {
      // After second click: show full line preview until button submit
      ctx.beginPath();
      ctx.moveTo(state.preview.x1, state.preview.y1);
      ctx.lineTo(state.preview.x2, state.preview.y2);
      ctx.stroke();
    }
  }
  ctx.restore();
}
```

Click handler fills coordinates AND activates preview (no API call):

```javascript
function onCanvasClick(e) {
  if (state.drag.justDragged) { state.drag.justDragged = false; return; }
  if (isBrushActive()) return;
  var p = canvasPointFromEvent(e);
  var cp = clampCanvasPoint(p.x, p.y);
  var tool = getActiveTool();

  if (tool === 'line') {
    if (state.preview.firstClick) {
      setVal('lineX1', cp.x); setVal('lineY1', cp.y);
      state.preview.x1 = cp.x; state.preview.y1 = cp.y;
      state.preview.firstClick = false;
      state.preview.active = true;
      toast('起点已设置，点击设置终点', 'info');
    } else {
      setVal('lineX2', cp.x); setVal('lineY2', cp.y);
      state.preview.x2 = cp.x; state.preview.y2 = cp.y;
      state.preview.firstClick = true;
      state.preview.lineReady = true;  // Show full preview until button
      state.preview.active = true;
      toast('终点已设置，点击「添加直线」按钮同步到屏幕', 'info');
    }
    renderCanvasPreview();
    renderPreview();
    return;
  }
  // Text/rect: fill coords, activate preview, draw it (no auto-submit)
  fillCoordsToInputs(p.x, p.y);
  state.preview.x = cp.x;   // MUST use clamped coords, not raw p.x/p.y
  state.preview.y = cp.y;
  state.preview.active = true;
  renderCanvasPreview();
  renderPreview();
}
```

After successful button-submit, reset `lineReady` and `active`:
```javascript
// In addLine() success callback:
state.preview.lineReady = false;
state.preview.active = false;
```

### Preview Persistence After Mouse Leave (CRITICAL)

**Problem**: `onCanvasMouseLeave` used to set `state.preview.active = false`, causing placed previews to vanish as soon as the cursor left the canvas. The user clicks to place a rect/text/line, moves the mouse to the input fields to adjust parameters — and the preview disappears.

**Fix**: `mouseleave` must NOT deactivate the preview. Only tool switch (`switchToolTab`), Esc key, or successful button-submit should reset `preview.active`. The `mouseleave` handler should still clear the coordinate display and call `renderCanvasPreview()` + `renderPreview()` to redraw without the mouse-following cursor:

```javascript
function onCanvasMouseLeave(e) {
  // ... end brush drawing / commit drag (unchanged) ...
  // Clear coordinate display
  el.canvasCoords.textContent = '— , —';
  // DO NOT set state.preview.active = false here!
  // Preview stays visible until: tool switch, Esc, or button submit
  renderCanvasPreview();
  renderPreview();  // Redraw the placed preview (without mouse-following)
}
```

### Live Preview on Input Field Changes

When the user adjusts parameters (text content, font size, rect dimensions, line width, etc.) after placing a preview, the preview should update in real-time. Add input/change listeners:

```javascript
// In init():
['textText', 'textFont', 'textAlign', 'rectW', 'rectH', 'rectFilled', 'lineWidth'].forEach(function (id) {
  var node = document.getElementById(id);
  if (node) {
    var evt = node.type === 'checkbox' ? 'change' : 'input';
    node.addEventListener(evt, function () {
      if (state.preview.active && !isBrushActive()) {
        renderCanvasPreview();
        renderPreview();
      }
    });
  }
});
```

### Clamped Coords in Mousemove

In `onCanvasMouseMove`, the preview position must use clamped coordinates (`cp`) not raw values (`p.x/p.y`), otherwise the preview can extend beyond the canvas bounds:

```javascript
// In onCanvasMouseMove, preview mode branch:
state.preview.x = cp.x;  // clamped, not p.x
state.preview.y = cp.y;  // clamped, not p.y
if (!state.preview.active) {
  state.preview.active = true;  // only activate if not already (don't override placed state)
}
```

## Element Dragging

After hit-test succeeds in mousedown, mousemove updates element coordinates locally (no API call), mouseup commits:

```javascript
// mousemove during drag
var dx = p.x - state.drag.startX;
var dy = p.y - state.drag.startY;
var elem = state.canvasElements[state.drag.elementIndex];
var init = state.drag.initial;
if (elem.type === 'text' || elem.type === 'rect' || elem.type === 'image') {
  elem.x = init.x + dx; elem.y = init.y + dy;
} else if (elem.type === 'line') {
  elem.x1 = init.x1 + dx; elem.y1 = init.y1 + dy;
  elem.x2 = init.x2 + dx; elem.y2 = init.y2 + dy;
}
renderCanvasPreview();  // Redraw with new position

// mouseup: commit to device
function submitDraggedElement(elem) {
  if (elem.type === 'text')
    api.callTool('fridge.canvas.add_text', { id: elem.id, text: elem.text, x: Math.round(elem.x), y: Math.round(elem.y), font_size: elem.font_size, align: elem.align, refresh: state.autoRefresh });
  else if (elem.type === 'rect')
    api.callTool('fridge.canvas.add_rect', { id: elem.id, x: Math.round(elem.x), y: Math.round(elem.y), w: elem.w, h: elem.h, filled: elem.filled, refresh: state.autoRefresh });
  else if (elem.type === 'line')
    api.callTool('fridge.canvas.add_line', { id: elem.id, x1: Math.round(elem.x1), y1: Math.round(elem.y1), x2: Math.round(elem.x2), y2: Math.round(elem.y2), width: elem.width, refresh: state.autoRefresh });
  else if (elem.type === 'image')
    api.callTool('fridge.canvas.add_image', { id: elem.id, name: elem.name, x: Math.round(elem.x), y: Math.round(elem.y), w: elem.w, h: elem.h, refresh: state.autoRefresh });
}
```

**Key detail**: The API `add_text/add_rect/add_line` with the same `id` replaces the existing element (doesn't create a duplicate). This is by design in the firmware — `CheckCanvasLabelLimit` skips the count check for same-ID adds.

## Loading Existing Elements

On connect and on tab switch to canvas, call `fridge.canvas.list` to sync the web preview with the device state:

```javascript
function loadCanvasElements() {
  if (!state.connected) return;
  api.callTool('fridge.canvas.list', {})
    .then(function(elements) {
      state.canvasElements = Array.isArray(elements) ? elements : [];
      renderCanvasPreview();
      renderElementList();
    })
    .catch(function(err) { console.warn('加载画布元素失败:', err.message); });
}
```

**Image elements**: The web preview cannot redraw the actual bitmap (no pixel data available). Draw a dashed placeholder box with the image name as text label. The element list still shows full details.

## Bbox Calculation for Hit-Testing

Each element needs a `bbox` property for drag hit-testing. Set it during `renderCanvasPreview()`:

| Type | bbox calculation |
|------|-----------------|
| text | `{ x: align-adjusted x, y: elem.y, w: ctx.measureText(text).width, h: font_size + 2 }` |
| rect | `{ x: elem.x, y: elem.y, w: elem.w, h: elem.h }` |
| line | `{ x: min(x1,x2), y: min(y1,y2), w: abs(x2-x1), h: abs(y2-y1) }` |
| image | `{ x: elem.x, y: elem.y, w: elem.w, h: elem.h }` |

Add 4px padding to hit-test for easier selection of thin elements (lines, small text).

## Esc Key Handling

Register a keydown listener to cancel ongoing interactions:
- During line first-click or lineReady (waiting for button): Esc resets `firstClick=true`, `lineReady=false`, `active=false`
- During drag: Esc restores element to initial position, cancels drag

## Touch Event Support

Map touch events to the same handlers. Key: `touchend` has empty `e.touches` — use `e.changedTouches[0]` in `canvasPointFromEvent()`:

```javascript
function canvasPointFromEvent(e) {
  var clientX, clientY;
  if (e.touches && e.touches.length) {
    clientX = e.touches[0].clientX; clientY = e.touches[0].clientY;
  } else if (e.changedTouches && e.changedTouches.length) {
    clientX = e.changedTouches[0].clientX; clientY = e.changedTouches[0].clientY;
  } else {
    clientX = e.clientX; clientY = e.clientY;
  }
  // ... convert to canvas coords
}
```

Add `touch-action: none` CSS on the canvas to prevent page scroll during touch drawing.

## Promise.allSettled for Parallel API Fetches

When loading multiple independent datasets in parallel (e.g. `fridge.stats.summary` + `fridge.item.list`), use `Promise.allSettled` instead of `Promise.all`. With `Promise.all`, if either call fails, both datasets are lost — the user sees "加载冰箱数据失败" even if only one API is down. `Promise.allSettled` lets each succeed/fail independently:

```javascript
function loadFridgeData() {
  if (!state.connected) return;
  renderStatsSkeleton();
  renderItemsSkeleton();

  withButton(el.refreshFridgeBtn, Promise.allSettled([
    api.callTool('fridge.stats.summary', {}),
    api.callTool('fridge.item.list', { sort_by: 'expiry' })
  ]))
    .then(function (results) {
      var statsR = results[0];
      var itemsR = results[1];
      if (statsR.status === 'fulfilled') renderStats(statsR.value);
      else renderStats(null);
      if (itemsR.status === 'fulfilled') state.fridge.items = itemsR.value || [];
      else state.fridge.items = [];
      updateFilterCounts();
      renderItems();
      // Only show error toast if BOTH failed, or partial warning if one failed
      if (statsR.status === 'rejected' && itemsR.status === 'rejected') {
        renderItemsError(statsR.reason.message);
        toast('加载冰箱数据失败: ' + statsR.reason.message, 'error');
      } else if (statsR.status === 'rejected' || itemsR.status === 'rejected') {
        var msg = statsR.status === 'rejected' ? statsR.reason.message : itemsR.reason.message;
        toast('部分冰箱数据加载失败: ' + msg, 'error');
      }
    });
}
```

**When to use**: any `Promise.all` over independent API calls where partial results are still useful to the user. If the calls are truly all-or-nothing (e.g. a transaction), `Promise.all` is fine.
