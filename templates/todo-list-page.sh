#!/bin/bash
# Todo List Page Template for xiaozhi e-paper display (296×128)
# Creates a "待办事项" layout on a custom page (7-15) with:
#   - Title bar + separator
#   - 3 checkbox (rect) + text pairs (dynamic, updateable via element.update)
#   - Bottom hint text
#
# Usage: ./todo-list-page.sh [IP] [PAGE] [ITEM1] [ITEM2] [ITEM3]
#   IP: device IP (default xiaozhi.local)
#   PAGE: target page number (default 7)
#   ITEM1/2/3: custom item text (defaults: 写专利/改论文/运动小智开发)
#
# Design (12px compact layout):
#   - font_size=12, row spacing 18px, checkbox 6×6
#   - separator at y=18, items at y=24/42/60, hint at y=112
#
# Adapt this template for other list-style pages:
#   shopping list, task list, schedule, etc.

IP="${1:-xiaozhi.local}"
PAGE="${2:-7}"
ITEM1="${3:-写专利}"
ITEM2="${4:-改论文}"
ITEM3="${5:-运动小智开发}"
BASE="http://$IP:8080/api/call"
HDR="Content-Type: application/json"

call() {
  curl -s -X POST "$BASE" -H "$HDR" -d "$1"
  echo
}

echo "=== Setting up todo list page $PAGE on $IP ==="
echo "=== Items: $ITEM1 / $ITEM2 / $ITEM3 ==="

# 1. Rename page (assumes page already exists; create first if needed)
call "{\"tool\":\"fridge.page.rename\",\"args\":{\"page\":$PAGE,\"name\":\"待办事项\"}}"

# 2. Clear any existing elements
call "{\"tool\":\"fridge.page.clear\",\"args\":{\"page\":$PAGE,\"refresh\":false}}"

# 3. Title + separator (batch mode: refresh=false)
call "{\"tool\":\"fridge.page.element.add\",\"args\":{\"page\":$PAGE,\"id\":\"title\",\"type\":\"text\",\"text\":\"待办事项\",\"x\":8,\"y\":2,\"font_size\":12,\"align\":\"left\",\"refresh\":false}}"
call "{\"tool\":\"fridge.page.element.add\",\"args\":{\"page\":$PAGE,\"id\":\"sep\",\"type\":\"line\",\"x\":0,\"y\":0,\"x1\":0,\"y1\":18,\"x2\":296,\"y2\":18,\"width\":1,\"refresh\":false}}"

# 4. Three todo items (checkbox + text pairs)
#    Compact 12px layout: row spacing 18px, checkbox 6×6
#    Row 1: y=24 (text+box aligned), Row 2: y=42, Row 3: y=60
for i in 1 2 3; do
  case $i in
    1) TEXT="$ITEM1"; Y=24 ;;
    2) TEXT="$ITEM2"; Y=42 ;;
    3) TEXT="$ITEM3"; Y=60 ;;
  esac
  call "{\"tool\":\"fridge.page.element.add\",\"args\":{\"page\":$PAGE,\"id\":\"box$i\",\"type\":\"rect\",\"x\":6,\"y\":$Y,\"w\":6,\"h\":6,\"filled\":false,\"refresh\":false}}"
  call "{\"tool\":\"fridge.page.element.add\",\"args\":{\"page\":$PAGE,\"id\":\"item$i\",\"type\":\"text\",\"text\":\"$TEXT\",\"x\":20,\"y\":$Y,\"font_size\":12,\"align\":\"left\",\"dynamic\":true,\"refresh\":false}}"
done

# 5. Bottom hint
call "{\"tool\":\"fridge.page.element.add\",\"args\":{\"page\":$PAGE,\"id\":\"hint\",\"type\":\"text\",\"text\":\"说\\\"提醒我...\\\"添加待办\",\"x\":8,\"y\":112,\"font_size\":12,\"align\":\"left\",\"refresh\":false}}"

# 6. Refresh display (all elements added with refresh=false, now flush)
call "{\"tool\":\"fridge.canvas.refresh\",\"args\":{}}"

# 7. Switch to the page to display
call "{\"tool\":\"fridge.pagemanager\",\"args\":{\"target_page\":$PAGE}}"

echo "=== Done. Page $PAGE is now showing the todo list. ==="
echo ""
echo "To update an item text:"
echo "  curl -X POST $BASE -H '$HDR' -d '{\"tool\":\"fridge.page.element.update\",\"args\":{\"page\":$PAGE,\"id\":\"item1\",\"text\":\"新内容\",\"refresh\":true}}'"
echo ""
echo "To mark item as done (fill the checkbox):"
echo "  curl -X POST $BASE -H '$HDR' -d '{\"tool\":\"fridge.page.element.remove\",\"args\":{\"page\":$PAGE,\"id\":\"box1\",\"refresh\":false}}'"
echo "  curl -X POST $BASE -H '$HDR' -d '{\"tool\":\"fridge.page.element.add\",\"args\":{\"page\":$PAGE,\"id\":\"box1\",\"type\":\"rect\",\"x\":6,\"y\":24,\"w\":6,\"h\":6,\"filled\":true,\"refresh\":true}}'"
