#!/usr/bin/env bash
# Build a validated todo layout on an existing custom page (2-15).
set -euo pipefail

IP="${1:?usage: todo-list-page.sh <device-host> <page> [item1] [item2] [item3]}"
PAGE="${2:?usage: todo-list-page.sh <device-host> <page> [item1] [item2] [item3]}"
PORT="${XIAOZHI_PORT:-8080}"
ITEM1="${3:-写专利}"
ITEM2="${4:-改论文}"
ITEM3="${5:-运动小智开发}"

case "$PAGE" in
  2|3|4|5|6|7|8|9|10|11|12|13|14|15) ;;
  *) echo "ERROR: page must be 2-15" >&2; exit 2 ;;
esac
for value in "$ITEM1" "$ITEM2" "$ITEM3"; do
  case "$value" in
    *$'\n'*|*$'\r'*) echo "ERROR: todo text must be a single line" >&2; exit 2 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILDER="$SCRIPT_DIR/../scripts/quick_page_builder.py"
[ -f "$BUILDER" ] || { echo "ERROR: builder not found: $BUILDER" >&2; exit 1; }

shell_quote() {
  python3 -c 'import shlex, sys; print(shlex.quote(sys.argv[1]))' "$1"
}

ITEM1_Q="$(shell_quote "$ITEM1")"
ITEM2_Q="$(shell_quote "$ITEM2")"
ITEM3_Q="$(shell_quote "$ITEM3")"

python3 "$BUILDER" "$IP" "$PAGE" --port "$PORT" - <<EOF
clear
text id=title text="待办事项" x=8 y=2 font_size=12 align=left
hline id=sep x1=0 x2=295 y=18 width=1
rect id=box1 x=6 y=24 w=6 h=6 filled=false
text id=item1 text=$ITEM1_Q x=20 y=24 font_size=12 align=left dynamic=true
rect id=box2 x=6 y=42 w=6 h=6 filled=false
text id=item2 text=$ITEM2_Q x=20 y=42 font_size=12 align=left dynamic=true
rect id=box3 x=6 y=60 w=6 h=6 filled=false
text id=item3 text=$ITEM3_Q x=20 y=60 font_size=12 align=left dynamic=true
text id=hint text='说"提醒我..."添加待办' x=8 y=112 font_size=12 align=left
refresh
EOF
