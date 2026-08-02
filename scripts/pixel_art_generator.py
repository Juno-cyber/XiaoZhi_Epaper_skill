#!/usr/bin/env python3
"""pixel_art_generator.py — 生成 24×24 像素画 1-bpp 位图并上传到设备。

用法:
  python3 pixel_art_generator.py --upload 192.168.1.10          # 上传全部
  python3 pixel_art_generator.py --upload 192.168.1.10 heart star  # 上传指定
  python3 pixel_art_generator.py --list                          # 列出可用
  python3 pixel_art_generator.py --dump heart /tmp/heart.bin      # 导出单文件
"""
import math, struct, sys, os, json, urllib.request, argparse

W, H = 24, 24
ROW_BYTES = (W + 7) // 8  # 3

def to_bitmap(pixels):
    """pixels: list of (x,y) tuples that are black. Returns 1-bpp bitmap bytes."""
    data = bytearray(ROW_BYTES * H)
    for x, y in pixels:
        if 0 <= x < W and 0 <= y < H:
            data[y * ROW_BYTES + x // 8] |= 1 << (7 - x % 8)
    return bytes(data)

def point_in_polygon(px, py, poly):
    n = len(poly); inside = False; j = n - 1
    for i in range(n):
        xi, yi = poly[i]; xj, yj = poly[j]
        if ((yi > py) != (yj > py)) and (px < (xj - xi) * (py - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside

def gen_heart():
    pts = []
    for y in range(H):
        for x in range(W):
            nx, ny = x - 12, y - 12
            # Heart shape: two circles + triangle
            left = (nx + 4) ** 2 + (ny - 3) ** 2 <= 36
            right = (nx - 4) ** 2 + (ny - 3) ** 2 <= 36
            bottom = ny > 3 and abs(nx) <= (10 - ny) * 0.7
            if left or right or (ny > 3 and abs(nx) <= (10 - ny) * 0.7 and ny <= 10):
                pts.append((x, y))
    return pts

def gen_star():
    cx, cy = 12, 12
    outer_r, inner_r = 10, 4
    verts = []
    for i in range(10):
        a = math.pi / 5 * i - math.pi / 2
        r = outer_r if i % 2 == 0 else inner_r
        verts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    pts = [(x, y) for y in range(H) for x in range(W) if point_in_polygon(x, y, verts)]
    return pts

def gen_note():
    pts = []
    for y in range(H):
        for x in range(W):
            draw = False
            # Note head (ellipse at (8,17))
            dx, dy = x - 8, y - 17
            if dx * dx * 9 + dy * dy * 16 <= 144: draw = True
            # Stem
            if 11 <= x <= 12 and 4 <= y <= 17: draw = True
            # Flag
            if 13 <= x <= 18 and 4 <= y <= 8:
                if y <= 4 + (x - 13) * 2: draw = True
            if draw: pts.append((x, y))
    return pts

def gen_diamond():
    pts = []
    for y in range(H):
        for x in range(W):
            if abs(x - 12) + abs(y - 12) <= 9: pts.append((x, y))
    return pts

def gen_smiley():
    pts = []
    for y in range(H):
        for x in range(W):
            dx, dy = x - 12, y - 12
            dist = math.hypot(dx, dy)
            draw = False
            if 8 <= dist <= 10: draw = True  # face outline
            ex, ey = x - 8, y - 8
            if ex * ex + ey * ey <= 4: draw = True  # left eye
            ex, ey = x - 16, y - 8
            if ex * ex + ey * ey <= 4: draw = True  # right eye
            if dist <= 7 and dy > 2 and 6 <= dist <= 8: draw = True  # smile
            if draw: pts.append((x, y))
    return pts

def gen_arrow():
    pts = []
    for y in range(H):
        for x in range(W):
            draw = False
            if 4 <= x <= 20 and 10 <= y <= 13: draw = True  # shaft
            if x >= 14 and abs(y - 12) <= (20 - x) + 1: draw = True  # arrowhead
            if draw: pts.append((x, y))
    return pts

def gen_check():
    pts = set()
    def line(x1, y1, x2, y2, thick=2):
        dx, dy = x2 - x1, y2 - y1
        length = max(1, int(math.hypot(dx, dy)))
        for i in range(length + 1):
            t = i / length
            px, py = int(x1 + t * dx), int(y1 + t * dy)
            for ox in range(-thick, thick + 1):
                for oy in range(-thick, thick + 1):
                    pts.add((px + ox, py + oy))
    line(3, 14, 9, 20)
    line(9, 20, 21, 3)
    return list(pts)

def gen_sun():
    pts = []
    cx, cy = 12, 12
    for y in range(H):
        for x in range(W):
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy)
            draw = False
            if dist <= 5: draw = True  # sun body
            if 6 <= dist <= 10:
                angle = math.atan2(dy, dx) if dist > 0 else 0
                a8 = round(angle / (math.pi / 4)) * (math.pi / 4)
                if abs(angle - a8) < 0.15: draw = True  # rays
            if draw: pts.append((x, y))
    return pts

def gen_moon():
    pts = []
    for y in range(H):
        for x in range(W):
            dx, dy = x - 12, y - 12
            dist = math.hypot(dx, dy)
            if dist <= 9:
                dx2, dy2 = x - 15, y - 12
                dist2 = math.hypot(dx2, dy2)
                if dist2 > 7: pts.append((x, y))
    return pts

def gen_house():
    pts = []
    for y in range(H):
        for x in range(W):
            draw = False
            if 2 <= y <= 12:
                half = 12 - y
                if 12 - half <= x <= 12 + half: draw = True  # roof
            if 4 <= x <= 20 and 12 <= y <= 21:
                if x == 4 or x == 20 or y == 12 or y == 21: draw = True  # walls
            if 10 <= x <= 14 and 16 <= y <= 21:
                if x == 10 or x == 14 or y == 21: draw = True  # door
            if 6 <= x <= 9 and 14 <= y <= 16:
                if x == 6 or x == 9 or y == 14 or y == 16: draw = True  # window
            if draw: pts.append((x, y))
    return pts

def gen_bolt():
    poly = [(14, 1), (6, 13), (10, 13), (8, 23), (18, 9), (14, 9), (16, 1)]
    return [(x, y) for y in range(H) for x in range(W) if point_in_polygon(x, y, poly)]

def gen_coffee():
    pts = []
    for y in range(H):
        for x in range(W):
            draw = False
            if 6 <= y <= 18:
                tl = 6 + (y - 6) * 0.2
                tr = 18 - (y - 6) * 0.2
                if 6 <= x <= 18 and (abs(x - tl) < 1.5 or abs(x - tr) < 1.5 or y == 18): draw = True
            if 18 <= x <= 22 and 8 <= y <= 14:
                if abs(x - 20) <= 2 and (abs(y - 8) < 1 or abs(y - 14) < 1): draw = True
            if 2 <= y <= 5 and x in [8, 12, 16]:
                if (y + (x % 2)) % 2 == 0: draw = True
            if draw: pts.append((x, y))
    return pts

def gen_bell():
    pts = []
    cx = 12
    for y in range(H):
        for x in range(W):
            draw = False
            dy = y - 12
            if -8 <= dy <= 4:
                r = 3 + (-dy) * 0.8
                if abs(x - cx) <= r + 0.5 and abs(x - cx) >= r - 1.5: draw = True
            if dy == 4 and abs(x - cx) <= 8: draw = True
            if abs(x - cx) <= 1 and 6 <= dy <= 7: draw = True
            if abs(x - cx) <= 1 and dy == -9: draw = True
            if draw: pts.append((x, y))
    return pts

# Registry
ARTISTS = {
    'heart': gen_heart,
    'star': gen_star,
    'note': gen_note,
    'diamond': gen_diamond,
    'smiley': gen_smiley,
    'arrow': gen_arrow,
    'check': gen_check,
    'sun': gen_sun,
    'moon': gen_moon,
    'house': gen_house,
    'bolt': gen_bolt,
    'coffee': gen_coffee,
    'bell': gen_bell,
}

def upload(ip, name, bitmap):
    req = urllib.request.Request(
        f"http://{ip}:8080/api/canvas_image?name={name}",
        data=bitmap,
        headers={"Content-Type": "application/octet-stream"},
        method="POST"
    )
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.read().decode()

def main():
    parser = argparse.ArgumentParser(description="Pixel art generator & uploader")
    parser.add_argument("--upload", metavar="IP", help="Upload to device at IP")
    parser.add_argument("--list", action="store_true", help="List available art")
    parser.add_argument("--dump", nargs=2, metavar=("NAME", "PATH"), help="Export to file")
    parser.add_argument("arts", nargs="*", help="Specific art names (default: all)")
    args = parser.parse_args()

    if args.list:
        print("Available pixel art (24×24, 1-bpp):")
        for name in sorted(ARTISTS):
            print(f"  {name}")
        return

    names = args.arts if args.arts else list(sorted(ARTISTS))

    if args.dump:
        name, path = args.dump
        if name not in ARTISTS:
            print(f"ERROR: {name} not found. Available: {sorted(ARTISTS)}", file=sys.stderr)
            sys.exit(1)
        bitmap = to_bitmap(ARTISTS[name]())
        with open(path, 'wb') as f:
            f.write(bitmap)
        print(f"Exported {name} ({len(bitmap)} bytes) to {path}")
        return

    if args.upload:
        ip = args.upload
        print(f"=== Uploading {len(names)} pixel arts to {ip} ===")
        for name in names:
            if name not in ARTISTS:
                print(f"  SKIP {name} (unknown)")
                continue
            bitmap = to_bitmap(ARTISTS[name]())
            result = upload(ip, name, bitmap)
            print(f"  {name:10s} ({len(bitmap)} bytes): {result}")
        print("Done!")
        return

    # Default: generate and print sizes
    for name in sorted(names):
        if name not in ARTISTS: continue
        bitmap = to_bitmap(ARTISTS[name]())
        print(f"{name:10s} {len(bitmap)} bytes")

if __name__ == "__main__":
    main()
