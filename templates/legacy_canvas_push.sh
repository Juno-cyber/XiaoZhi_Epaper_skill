#!/usr/bin/env bash
# legacy_canvas_push.sh — push a canvas layout to xiaozhi e-paper (firmware v2.0.5)
#
# Why this script: firmware v2.0.5 does NOT register the aggregator tools
# (fridge.canvas.control / fridge.page.control), so quick_page_builder.py fails
# silently. This script drives the legacy single-point names exactly as the
# skill specifies: clear -> batch add (refresh=false on every element) ->
# final fridge.canvas.refresh. Requests are serial, never concurrent.
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
#   {"tool":"fridge.canvas.add_line","args":{"id":"div","x1":16,"y1":26,"x2":180,"y2":26,"width":1,"refresh":false}}
#   {"tool":"fridge.canvas.add_image","args":{"id":"cat","name":"cat","x":24,"y":44,"w":24,"h":24,"refresh":false}}
#   {"tool":"fridge.canvas.add_text","args":{"id":"t1","text":"这是傻瓜的","x":58,"y":46,"font_size":16,"refresh":false}}
#   {"tool":"fridge.canvas.add_text","args":{"id":"t2","text":"血脉使然啊。","x":58,"y":68,"font_size":16,"refresh":false}}
#   {"tool":"fridge.canvas.add_text","args":{"id":"note","text":"一言-有顶天家族","x":24,"y":100,"font_size":12,"refresh":false}}
#   {"tool":"fridge.canvas.add_image","args":{"id":"zp","name":"zp","x":196,"y":6,"w":92,"h":62,"refresh":false}}
#   EOF
#   bash legacy_canvas_push.sh <IP> /tmp/layout.jsonl
set -euo pipefail

INPUT_HOST="${1:?usage: legacy_canvas_push.sh <IP> <layout-file|->}"
LAYOUT="${2:?usage: legacy_canvas_push.sh <IP> <layout-file|->}"
PORT="${XIAOZHI_PORT:-8080}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IP="$(PYTHONPATH="$SCRIPT_DIR/../scripts" python3 -c 'import sys; from quick_page_builder import DeviceClient; print(DeviceClient(sys.argv[1], port=int(sys.argv[2])).host)' "$INPUT_HOST" "$PORT")" || {
    echo "ERROR: invalid or non-LAN device host" >&2; exit 2;
}
API="http://${IP}:${PORT}/api/call"
declare -a LINES=()
if [ "$LAYOUT" = "-" ]; then
    while IFS= read -r l; do [ -n "$l" ] && LINES+=("$l"); done
else
    [ -f "$LAYOUT" ] || { echo "ERROR: layout file not found: $LAYOUT" >&2; exit 1; }
    while IFS= read -r l; do [ -n "$l" ] && LINES+=("$l"); done < "$LAYOUT"
fi
[ "${#LINES[@]}" -gt 0 ] || { echo "ERROR: empty layout" >&2; exit 1; }

# Validate every command before clearing the current page. Only canvas layout
# operations are allowed; this prevents malformed/hostile JSONL from invoking
# unrelated device tools after a destructive clear.
python3 -c 'import json,sys
sys.path.insert(0,sys.argv[1]); from quick_page_builder import BuildError,validate_element
raws=sys.argv[2:]
if len(raws)>31: raise BuildError("layout exceeds 30 elements plus optional refresh")
ids=set()
for index,raw in enumerate(raws):
 d=json.loads(raw); tool=d.get("tool"); args=d.get("args")
 allowed={"fridge.canvas.add_text","fridge.canvas.add_rect","fridge.canvas.add_line","fridge.canvas.add_image","fridge.canvas.refresh"}
 if tool not in allowed or not isinstance(args,dict): raise BuildError("unsupported legacy canvas command")
 if tool == "fridge.canvas.refresh":
  if index!=len(raws)-1 or set(args)-{"refresh"}: raise BuildError("refresh must be last and contain no unknown fields")
 else:
  if args.get("refresh",False) is not False: raise BuildError("element refresh must be false")
  command=tool.rsplit("_",1)[-1]
  validate_element(command,args,index+1)
  item_id=args["id"]
  if item_id in ids: raise BuildError("duplicate id")
  ids.add(item_id)
if len(ids)>30: raise BuildError("layout exceeds 30 elements")' "$SCRIPT_DIR" "${LINES[@]}" || {
        echo "ERROR: invalid legacy layout" >&2; exit 2;
    }

response_ok() {
    python3 -c 'import json,sys
d=json.load(sys.stdin)
if d.get("error"): raise SystemExit(1)
r=d.get("result",{})
if r.get("isError"): raise SystemExit(1)
content=r.get("content") or []
if not content: raise SystemExit(1)
inner=json.loads(content[0].get("text",""))
if not isinstance(inner,dict) or inner.get("status") not in ("success","ok"): raise SystemExit(1)'
}

echo "→ clear canvas"
clear_response="$(curl -sS --fail-with-body --max-time 8 -X POST "$API" -H "Content-Type: application/json" \
    -d '{"tool":"fridge.canvas.clear","args":{}}')" || { echo "ERROR: clear failed (device offline?)" >&2; exit 1; }
printf '%s' "$clear_response" | response_ok || { echo "ERROR: device rejected clear: $clear_response" >&2; exit 1; }

last="${LINES[${#LINES[@]}-1]}"
if ! echo "$last" | grep -q '"fridge.canvas.refresh"'; then
    LINES+=('{"tool":"fridge.canvas.refresh","args":{"refresh":true}}')
fi

ok=0; fail=0
for cmd in "${LINES[@]}"; do
    r=$(curl -sS --fail-with-body --max-time 8 -X POST "$API" -H "Content-Type: application/json" -d "$cmd") || r='{"error":"transport failure"}'
    if printf '%s' "$r" | response_ok; then
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
