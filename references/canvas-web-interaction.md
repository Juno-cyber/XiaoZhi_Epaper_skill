# Canvas interaction notes (website development only)

Normal screen control uses Python and does not need this reference. The live
implementation is `Litsea_Top/js/xiaozhi.js`; this document preserves design
constraints rather than duplicating JavaScript handlers that can drift.

## Input and element editing

- Register one event path for selection, text, rect, line and image
  modes. Duplicated pointer handlers cause competing state transitions.
- Scale pointer coordinates from the displayed bounding rectangle to logical
  296×128 coordinates before hit testing, placing elements or submitting.
- Selecting coordinates is a preview action. Submit on the user's Add/Apply
  action; do not make network mutations for every pointer movement.
- Lines retain both clicked endpoints until submit/cancel. Mouse leave clears
  the moving cursor but should not discard a completed preview.
- Drag changes must update both line endpoints; other elements update their
  origin. Persist only once after a completed drag.

## Device synchronization

- Use the custom-page contract for all existing pages 2–15 (including 6).
  Page 1 is read-only. Use the MCP element
  list for editing and backup; the render-layout endpoint uses a different line
  coordinate convention and internal IDs.
- Complete layout changes are validated first, then sent serially with all
  element refresh flags false and one final page presentation. An automatic
  per-element refresh mode is unsuitable for batching.
- Reorder is a firmware side effect: canvas reorder presents immediately;
  custom-page reorder only changes persisted order in 2.5.2.4.
- Handle inner MCP errors and unknown outcomes; a timeout is not permission to
  retry a mutation or rebuild a page automatically.
- Images must be resized/binarized on the host: row-padded 1-bpp, MSB first,
  1 black / 0 white, transparency white. Preview scaling does not resize storage.
- Keep unsaved browser edits distinct from device state; reconnect/list must
  not silently overwrite unsaved work. Test mouse/touch, cancellation, resizing,
  stale connections, a failed add and a failed final presentation.

Current routes, discovery and proxy limitations: [web-console.md](web-console.md).
