#!/usr/bin/env bash
# legacy_canvas_push.sh — push a canvas layout to xiaozhi e-paper (firmware v2.0.5)
#
# Why this script: firmware v2.0.5 does NOT register the aggregator tools
# (fridge.canvas.control / fridge.page.control), so quick_page_builder.py fails
# silently. This script drives the legacy single-point names exactly as the
# skill specifies: clear -> batch add (refresh=false on every element) ->
# final fridge.canvas.refresh. Serial, no concurrent requests (pitfall #9).
#
# Usage:
#   bash legacy_canvas_push.sh <IP> <layout-file>
#   bash legacy_canvas_push.sh <IP> -            # read layout lines from stdin
#
# Layout file format: one full /api/call body per line, e.g.
#   {"tool":"fridge.canvas.add_text","args":{"id":"t1","text":"你好","x":10,"y":10,"font_size":16,"refresh":false}}
#   {"tool":"fridge.canvas.add_image","args":{"id":"ic","name":"sun","x":20,"y":20,"w":24,"h":24,"refresh":false}}
#
# The script ALWAYS: (1) clears the canvas first, (2) checks every response for
# "status":"success", (3) appends a final fridge.canvas.refresh if the layout
# doesn't already end with one.
#
# Example (from page-templates.md §8 小海报+角落禅绕画):
#   cat > /tmp/layout.jsonl << 'EOF'
#   {"tool":"fridge.canvas.add_text","args":{"id":"title","text":"有顶天家族","x":16,"y":10,"font_size":12,"refresh":false}}
#   {"tool":"fridge.canvas.add_line","args":{"id":"div","x":0,"y":0,"x1":16,"y1":26,"x2":180,"y2":26,"width":1,"refresh":false}}
#   {"tool":"fridge.canvas.add_image","args":{"id":"cat","name":"cat","x":24,"y":44,"w":24,"h":24,"refresh":false}}
#   {"tool":"fridge.canvas.add_text","args":{"id":"t1","text":"这是傻瓜的","x":58,"y":46,"font_size":16,"refresh":false}}
#   {"tool":"fridge.canvas.add_text","args":{"id":"t2","text":"血脉使然啊。","x":58,"y":68,"font_size":16,"refresh":false}}
#   {"tool":"fridge.canvas.add_text","args":{"id":"note","text":"一言・有顶天家族","x":24,"y":100,"font_size":12,"refresh":false}}
#   {"tool":"fridge.canvas.add_image","args":{"id":"zp","name":"zp","x":196,"y":6,"w":92,"h":62,"refresh":false}}
#   EOF
#   bash legacy_canvas_push.sh 192.168.40.98 /tmp/layout.jsonl
set -euo pipefail

IP="${1:?usage: legacy_canvas_push.sh <IP> <layout-file|->}"
LAYOUT="${2:?usage: legacy_canvas_push.sh <IP> <layout-file|->}"
API="http://${IP}:8080/api/call"
declare -a LINES=()
if [ "$LAYOUT" = "-" ]; then
    while IFS= read -r l; do [ -n "$l" ] && LINES+=("$l"); done
else
    [ -f "$LAYOUT" ] || { echo "ERROR: layout file not found: $LAYOUT" >&2; exit 1; }
    while IFS= read -r l; do [ -n "$l" ] && LINES+=("$l"); done < "$LAYOUT"
fi
[ "${#LINES[@]}" -gt 0 ] || { echo "ERROR: empty layout" >&2; exit 1; }

echo "→ clear canvas"
curl -s --max-time 8 -X POST "$API" -H "Content-Type: application/json" \
    -d '{"tool":"fridge.canvas.clear","args":{}}' >/dev/null || { echo "ERROR: clear failed (device offline?)" >&2; exit 1; }

last="${LINES[${#LINES[@]}-1]}"
if ! echo "$last" | grep -q '"fridge.canvas.refresh"'; then
    LINES+=('{"tool":"fridge.canvas.refresh","args":{"refresh":true}}')
fi

ok=0; fail=0
for cmd in "${LINES[@]}"; do
    r=$(curl -s --max-time 8 -X POST "$API" -H "Content-Type: application/json" -d "$cmd")
    # Device returns JSON-RPC: result.content[].text contains an ESCAPED inner JSON
    # (\"status\":\"success\") — match the top-level unescaped "isError":false instead.
    if echo "$r" | grep -q '"isError":false'; then
        ok=$((ok+1))
        id=$(echo "$cmd" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p')
        echo "  ✓ ${id:-refresh}"
    else
        fail=$((fail+1))
        echo "  ✗ FAILED: $cmd" >&2
        echo "    response: $(echo "$r" | head -c 200)" >&2
    fi
done
echo "→ done: $ok ok, $fail failed"
[ "$fail" -eq 0 ]
