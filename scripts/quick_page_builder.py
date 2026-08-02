#!/usr/bin/env python3
"""quick_page_builder.py — 快速构建小智墨水屏画布页面。

用法:
  python3 quick_page_builder.py 192.168.1.10 6 layout.txt
  echo '<layout>' | python3 quick_page_builder.py 192.168.1.10 6
  python3 quick_page_builder.py 192.168.1.10 6 - << 'EOF'
  ... layout ...
  EOF

布局文件格式（每行一个指令, # 注释, --- 分隔）:
  clear                           # 清空页面
  switch 6                        # 切换到页面
  text    id=.. text=".." x=.. y=.. font_size=.. align=..
  rect    id=.. x=.. y=.. w=.. h=.. filled=..
  line    id=.. x1=.. y1=.. x2=.. y2=.. width=..
  image   id=.. name=.. x=.. y=.. w=.. h=..
  pixart  id=.. art=heart x=.. y=.. w=24 h=24   # 自动生成+上传+显示
  refresh                         # 刷新显示

特性:
  - 所有元素默认 refresh=false (批量), 最后 refresh 统一刷新
  - pixart 指令自动生成位图+上传, 无需预先准备
  - 支持 page 6 (canvas) 和 page 7-15 (custom page)
"""
import sys, json, shlex, urllib.request, os, time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)

# ============================================================
# HTTP helpers
# ============================================================
def call_mcp(ip, tool, args):
    """Call MCP tool on device, return parsed result."""
    data = json.dumps({"tool": tool, "args": args}).encode()
    req = urllib.request.Request(
        f"http://{ip}:8080/api/call",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        raw = resp.read().decode()
        parsed = json.loads(raw)
        if "result" in parsed and "content" in parsed["result"]:
            for item in parsed["result"]["content"]:
                if item.get("type") == "text":
                    try:
                        return json.loads(item["text"])
                    except:
                        return {"raw": item["text"]}
        return parsed
    except Exception as e:
        return {"error": str(e)}

def upload_image(ip, name, bitmap):
    """Upload 1-bpp bitmap to device LittleFS."""
    req = urllib.request.Request(
        f"http://{ip}:8080/api/canvas_image?name={name}",
        data=bitmap,
        headers={"Content-Type": "application/octet-stream"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.read().decode()

# ============================================================
# Pixel art (import from generator)
# ============================================================
from pixel_art_generator import to_bitmap, ARTISTS

def ensure_pixart(ip, name):
    """Ensure pixel art is uploaded. Returns True if already available or uploaded."""
    # Check if already uploaded
    try:
        resp = urllib.request.urlopen(f"http://{ip}:8080/api/canvas_image", timeout=5)
        files = json.loads(resp.read().decode())
        if any(f.get("name") == name for f in files):
            return True
    except:
        pass
    # Upload
    if name in ARTISTS:
        bitmap = to_bitmap(ARTISTS[name]())
        upload_image(ip, name, bitmap)
        return True
    return False

# ============================================================
# Layout parser
# ============================================================
def parse_kv(line):
    """Parse key=value pairs from line, handling quoted strings."""
    d = {}
    for p in shlex.split(line):
        if "=" in p:
            k, v = p.split("=", 1)
            if v in ("true", "false"):
                d[k] = (v == "true")
            else:
                try:
                    d[k] = int(v)
                except ValueError:
                    d[k] = v
    return d

def build_page(ip, page, layout_text):
    """Build a complete page from layout text."""
    lines = layout_text.strip().split("\n")
    elem_count = 0
    is_canvas = (page == 6)
    tool_prefix = "fridge.canvas" if is_canvas else "fridge.page.element"

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or line == "---":
            continue

        parts = shlex.split(line)
        cmd = parts[0]
        rest = " ".join(parts[1:])

        if cmd == "clear":
            if is_canvas:
                r = call_mcp(ip, "fridge.canvas.clear", {"refresh": False})
            else:
                r = call_mcp(ip, "fridge.page.clear", {"page": page, "refresh": False})
            print(f"  [clear] -> {r.get('status', '?')}")
            time.sleep(0.2)

        elif cmd == "switch":
            target = int(rest)
            r = call_mcp(ip, "fridge.pagemanager", {"target_page": target})
            print(f"  [switch] page {target} -> {r.get('status', '?')}")
            time.sleep(0.3)

        elif cmd == "refresh":
            r = call_mcp(ip, "fridge.canvas.refresh", {})
            print(f"  [refresh] -> {r.get('status', '?')}")

        elif cmd == "pixart":
            args = parse_kv(rest)
            art = args.pop("art", "heart")
            x = args.get("x", 0)
            y = args.get("y", 0)
            w = args.get("w", 24)
            h = args.get("h", 24)
            elem_id = args.get("id", f"pa_{art}")
            print(f"  [pixart] {art} at ({x},{y})...", end=" ")
            ensure_pixart(ip, art)
            mcp_args = {"id": elem_id, "name": art, "x": x, "y": y, "w": w, "h": h, "refresh": False}
            if not is_canvas:
                mcp_args["page"] = page
            r = call_mcp(ip, f"{tool_prefix}.add_image", mcp_args)
            elem_count += 1
            print(f"-> {r.get('status', '?')}")
            time.sleep(0.15)

        elif cmd in ("text", "rect", "line", "image", "label"):
            args = parse_kv(rest)
            if "refresh" not in args:
                args["refresh"] = False
            if not is_canvas:
                args["page"] = page
            actual_cmd = "text" if cmd == "label" else cmd
            desc_val = args.get("text", args.get("id", "?"))
            desc = str(desc_val)[:40]
            print(f"  [{actual_cmd}] {desc}...", end=" ")
            r = call_mcp(ip, f"{tool_prefix}.add_{actual_cmd}", args)
            elem_count += 1
            print(f"-> {r.get('status', '?')}")
            time.sleep(0.15)

        else:
            print(f"  [skip] Unknown: {cmd}")

    print(f"\n✅ Done! {elem_count} elements on page {page}.")

# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    ip = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.10"
    page = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    layout_file = sys.argv[3] if len(sys.argv) > 3 else "/dev/stdin"

    if layout_file == "-":
        layout_text = sys.stdin.read()
    else:
        with open(layout_file) as f:
            layout_text = f.read()

    print(f"=== Building page {page} on {ip} ===")
    build_page(ip, page, layout_text)
