#!/usr/bin/env python3
"""Zentangle (禅绕画) generator for the 296x128 e-paper.

Procedurally generates 1-bit line-art patterns — repetitive, meditative,
perfect for e-ink (which is a native 1-bit medium). Each pattern is driven
by a random seed + density/spacing params, so output is effectively infinite.

Usage:
  zentangle_generator.py --list                  # list pattern names
  zentangle_generator.py --preview               # render 8 samples to PNG grid
  zentangle_generator.py --gen <name> [--seed N] [--out /tmp/x.png] [--raw /tmp/x.raw]
  zentangle_generator.py --upload <IP> [--name <n>] [--seed N]   # render + upload to device
"""
import argparse, math, os, random, sys
import numpy as np

W, H = 296, 128
BYTES = (W // 8) * H          # 37 * 128 = 4736

# ---------------------------------------------------------------- helpers

def _line_shading(xs, ys, spacing):
    """Given a set of (x,y) points on a curve, return the full pixel set for a
    shaded band around it (thick line), computed by distance."""
    # fast path: for sparse curves use numpy distance is too heavy; instead
    # we rasterize each curve point with a small cross/diamond footprint.
    pts = set()
    for (x, y) in zip(xs, ys):
        xi, yi = int(round(x)), int(round(y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if abs(dx) + abs(dy) <= 2:
                    pts.add((xi + dx, yi + dy))
    return pts

def _curve(func, t0, t1, n=600):
    xs, ys = [], []
    for i in range(n + 1):
        t = t0 + (t1 - t0) * i / n
        x, y = func(t)
        if 0 <= x < W and 0 <= y < H:
            xs.append(x); ys.append(y)
    return xs, ys

# ---------------------------------------------------------------- patterns

def gen_waves(seed, spacing=9):
    """Layered sine waves — calm ocean lines."""
    rng = random.Random(seed)
    img = set()
    base = rng.uniform(0.6, 1.2)
    n_layers = rng.randint(2, 4)
    for layer in range(n_layers):
        amp = rng.uniform(4, 9)
        freq = rng.uniform(0.02, 0.05) * (layer + 1)
        phase = rng.uniform(0, math.tau)
        yoff = rng.randint(10, 110)
        for x in range(0, W, 2):
            y = yoff + amp * math.sin(freq * x + phase) + amp * 0.4 * math.sin(freq * 2.7 * x + phase * 1.7)
            yi = int(round(y))
            img.add((x, yi)); img.add((x + 1, yi))
    return img

def gen_concentric(seed, spacing=11):
    """Concentric circles / ripples from a focal point."""
    rng = random.Random(seed)
    img = set()
    cx = rng.randint(60, 236); cy = rng.randint(30, 98)
    r0 = rng.uniform(2, 4)
    rmax = math.hypot(max(cx, W - cx), max(cy, H - cy)) + 6
    n = int(rmax // spacing)
    for k in range(1, n + 1):
        r = r0 + k * spacing
        # sample points on circle
        steps = max(24, int(4 * math.pi * r))
        for i in range(steps):
            a = 2 * math.pi * i / steps
            x = cx + r * math.cos(a); y = cy + r * math.sin(a)
            xi, yi = int(round(x)), int(round(y))
            if 0 <= xi < W and 0 <= yi < H:
                img.add((xi, yi))
    return img

def gen_spiral(seed, spacing=5):
    """Archimedean spiral — meditative vortex."""
    rng = random.Random(seed)
    img = set()
    cx = rng.randint(60, 236); cy = rng.randint(30, 98)
    a = rng.uniform(0.9, 1.3)
    rmax = math.hypot(max(cx, W - cx), max(cy, H - cy))
    theta_max = rmax / a
    n = int(theta_max / 0.14)
    for i in range(n):
        th = i * 0.14
        r = a * th
        x = cx + r * math.cos(th); y = cy + r * math.sin(th)
        xi, yi = int(round(x)), int(round(y))
        if 0 <= xi < W and 0 <= yi < H:
            img.add((xi, yi))
    return img

def gen_grid_tangle(seed, cell=20):
    """Grid of cells, each filled with a random mini-tangle."""
    rng = random.Random(seed)
    img = set()
    styles = ['dots', 'slash', 'backslash', 'cross', 'ring', 'wavy', 'checker', 'hash']
    for gy in range(0, H, cell):
        for gx in range(0, W, cell):
            style = rng.choice(styles)
            x0, y0 = gx + 2, gy + 2
            x1 = min(gx + cell - 2, W - 1); y1 = min(gy + cell - 2, H - 1)
            if x1 <= x0 or y1 <= y0: continue
            if style == 'dots':
                for yy in range(y0, y1 + 1, 3):
                    for xx in range(x0, x1 + 1, 3):
                        img.add((xx, yy))
            elif style in ('slash', 'backslash'):
                d = 1 if style == 'slash' else -1
                for i in range(-(y1 - y0), (x1 - x0) + (y1 - y0) + 1, 4):
                    for yy in range(y0, y1 + 1):
                        xx = x0 + i + d * (yy - y0)
                        if x0 <= xx <= x1:
                            img.add((xx, yy))
            elif style == 'cross':
                cx = (x0 + x1) // 2; cy = (y0 + y1) // 2
                for xx in range(x0, x1 + 1): img.add((xx, cy))
                for yy in range(y0, y1 + 1): img.add((cx, yy))
            elif style == 'ring':
                cx = (x0 + x1) / 2; cy = (y0 + y1) / 2
                r = min(x1 - x0, y1 - y0) / 2 - 1
                for i in range(36):
                    a = 2 * math.pi * i / 36
                    xi, yi = int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))
                    img.add((xi, yi))
            elif style == 'wavy':
                for xx in range(x0, x1 + 1, 2):
                    yy = y0 + (y1 - y0) * 0.5 + (y1 - y0) * 0.35 * math.sin((xx - x0) / 4 + gy)
                    img.add((xx, int(round(yy))))
            elif style == 'checker':
                for yy in range(y0, y1 + 1):
                    for xx in range(x0, x1 + 1):
                        if (xx + yy) % 6 < 3: img.add((xx, yy))
            elif style == 'hash':
                for i in range(y0, y1 + 1, 3):
                    for xx in range(x0, x1 + 1):
                        img.add((xx, i))
    return img

def gen_vine(seed, spacing=7):
    """Sinuous vine with leaf accents."""
    rng = random.Random(seed)
    img = set()
    y = rng.uniform(15, 110)
    amp = rng.uniform(8, 20)
    freq = rng.uniform(0.02, 0.035)
    phase = rng.uniform(0, math.tau)
    prev = (0, y)
    for x in range(0, W, 3):
        yy = y + amp * math.sin(freq * x + phase) + amp * 0.3 * math.sin(freq * 3 * x + phase)
        xi, yi = int(x), int(round(yy))
        # stem: line from prev to here
        for t in range(0, 11):
            lx = prev[0] + (xi - prev[0]) * t / 10
            ly = prev[1] + (yi - prev[1]) * t / 10
            img.add((int(round(lx)), int(round(ly))))
        # leaf every ~40px
        if x % 40 < 3 and rng.random() < 0.8:
            lx = xi + rng.randint(6, 14) * rng.choice([-1, 1])
            ly = yi + rng.randint(-8, 8)
            img.add((lx, ly))
            img.add((lx + 1, ly)); img.add((lx - 1, ly))
            img.add((lx, ly + 1)); img.add((lx, ly - 1))
        prev = (xi, yi)
    return img

def gen_honeycomb(seed, size=22):
    """Hexagon tessellation — geometric calm."""
    rng = random.Random(seed)
    img = set()
    a = size / 2; h = size * math.sqrt(3) / 2
    for row in range(-1, H // int(h) + 2):
        for col in range(-1, W // int(3 * a) + 2):
            cx = col * 3 * a + (row % 2) * 1.5 * a
            cy = row * h
            for i in range(6):
                ang0 = math.pi / 6 + i * math.pi / 3
                ang1 = math.pi / 6 + (i + 1) * math.pi / 3
                x0 = cx + size * math.cos(ang0); y0 = cy + size * math.sin(ang0)
                x1 = cx + size * math.cos(ang1); y1 = cy + size * math.sin(ang1)
                steps = max(2, int(8 * size / 14))
                for t in range(steps):
                    lx = x0 + (x1 - x0) * t / steps
                    ly = y0 + (y1 - y0) * t / steps
                    xi, yi = int(round(lx)), int(round(ly))
                    if 0 <= xi < W and 0 <= yi < H:
                        img.add((xi, yi))
    return img

def gen_zen_circle(seed, spacing=7):
    """Large mandala ring with inner tangle — classic Zentangle look."""
    rng = random.Random(seed)
    img = set()
    cx, cy = W / 2, H / 2
    R = 50 + rng.uniform(-4, 4)
    # outer double ring
    for r in (R, R + 2):
        steps = int(2 * math.pi * r)
        for i in range(steps):
            a = 2 * math.pi * i / steps
            xi, yi = int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))
            img.add((xi, yi))
    # spokes (like a mandala)
    n_spokes = rng.choice([8, 12, 16])
    for k in range(n_spokes):
        a0 = 2 * math.pi * k / n_spokes
        for t in range(0, 60):
            r = R * t / 60
            xi = int(round(cx + r * math.cos(a0))); yi = int(round(cy + r * math.sin(a0)))
            img.add((xi, yi))
    # inner tangle: wavy ring or zigzag
    inner = rng.choice(['wavy', 'zigzag'])
    for i in range(72):
        a = 2 * math.pi * i / 72
        r = R * 0.55 + (4 if inner == 'wavy' else 0) * math.sin(6 * a)
        xi, yi = int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))
        img.add((xi, yi))
        if inner == 'zigzag':
            # add alternating dots
            if i % 3 == 0:
                rr = R * 0.38
                xi2, yi2 = int(round(cx + rr * math.cos(a))), int(round(cy + rr * math.sin(a)))
                img.add((xi2, yi2))
    # corner dots
    for (px, py) in [(14, 14), (W - 14, 14), (14, H - 14), (W - 14, H - 14)]:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                img.add((px + dx, py + dy))
    return img

def gen_meander(seed, spacing=6):
    """Greek-key meander border + inner waves — architectural calm."""
    rng = random.Random(seed)
    img = set()
    # border meander
    bw = 10
    for y in range(0, H, spacing * 2):
        for x in range(0, W):
            if y < bw and (x // spacing) % 2 == 0:
                img.add((x, y))
        # bottom border
    for y in range(H - bw, H, 1):
        for x in range(0, W, 2):
            if ((x + y) // spacing) % 2 == 0:
                img.add((x, y))
    # vertical meanders at edges
    for x in range(0, bw, 2):
        for y in range(0, H, 2):
            if ((x + y) // spacing) % 2 == 0:
                img.add((x, y))
    for x in range(W - bw, W, 2):
        for y in range(0, H, 2):
            if ((x + y) // spacing) % 2 == 0:
                img.add((x, y))
    # interior waves
    for yy in range(bw + 8, H - bw - 8, 10):
        for x in range(bw + 4, W - bw - 4, 2):
            y = yy + 3 * math.sin((x - bw) / 14 + yy / 5)
            img.add((x, int(round(y))))
    return img

def gen_ripple_leaf(seed, spacing=6):
    """Concentric arcs + leaf veins — organic tangle."""
    rng = random.Random(seed)
    img = set()
    cx = rng.randint(50, 246); cy = rng.randint(20, 108)
    r0 = 4
    n = rng.randint(4, 7)
    for k in range(1, n + 1):
        r = r0 + k * rng.uniform(6, 9)
        steps = int(2 * math.pi * r)
        for i in range(steps):
            a = 2 * math.pi * i / steps
            xi, yi = int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))
            if 0 <= xi < W and 0 <= yi < H:
                img.add((xi, yi))
    # leaf: ellipse outline + veins, placed away from center
    lx = rng.randint(30, 266); ly = rng.randint(20, 108)
    if math.hypot(lx - cx, ly - cy) < 40:
        lx = (lx + 60) % W
    a = rng.uniform(0, math.pi)
    rx, ry = rng.uniform(14, 22), rng.uniform(6, 10)
    for i in range(50):
        t = i / 50
        ang = a + (t - 0.5) * 1.2
        xx = lx + rx * math.cos(ang) * math.cos(t * math.pi)  # simplified leaf
        yy = ly + ry * math.sin(ang)
        img.add((int(round(xx)), int(round(yy))))
    return img


# ---------------------------------------------------------------- patterns v2 (classic tangle patterns)

def gen_knightsbridge(seed, brick_h=10):
    """Knightsbridge 砖墙编织 — offset brick rows with diagonal shading."""
    rng = random.Random(seed)
    img = set()
    bw = 24
    for row, y0 in enumerate(range(0, H, brick_h)):
        y1 = min(y0 + brick_h - 1, H - 1)
        off = (row % 2) * (bw // 2)
        for x0 in range(-bw, W, bw):
            x1 = min(x0 + bw - 1, W - 1)
            # brick outline (skip bottom edge to merge rows)
            for xx in range(max(0, x0), x1 + 1):
                img.add((xx, y0))
                if y1 == H - 1: img.add((xx, y1))
            for yy in range(y0 + 1, y1):
                img.add((max(0, x0), yy)); img.add((x1, yy))
            # diagonal shading inside brick
            for yy in range(y0 + 2, y1 - 1, 3):
                xx = x0 + off + (yy - y0)
                if 0 <= xx <= x1: img.add((xx, yy))
    return img

def gen_paradox(seed, n=10):
    """Paradox 帕拉多克斯 — rotating shrinking squares inside a frame."""
    rng = random.Random(seed)
    img = set()
    cx, cy = W / 2, H / 2
    size = min(W, H) * 0.9
    ang = rng.uniform(0, math.pi / 4)
    shrink = 0.88
    for k in range(n):
        s = size * (shrink ** k)
        if s < 3: break
        a = ang + k * 0.12
        corners = []
        for i in range(4):
            ca = a + i * math.pi / 2
            corners.append((cx + s * math.cos(ca), cy + s * math.sin(ca)))
        for i in range(4):
            x0, y0 = corners[i]; x1, y1 = corners[(i + 1) % 4]
            steps = max(4, int(s * 0.7))
            for t in range(steps):
                xi = int(round(x0 + (x1 - x0) * t / steps))
                yi = int(round(y0 + (y1 - y0) * t / steps))
                if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    return img

def gen_printemps(seed, spacing=22, turns=1.4):
    """Printemps 春 — field of small spirals."""
    rng = random.Random(seed)
    img = set()
    for gy in range(8, H, spacing):
        for gx in range(8, W, spacing):
            if rng.random() < 0.25: continue  # sparse
            cx = gx + rng.uniform(-2, 2); cy = gy + rng.uniform(-2, 2)
            a = rng.uniform(0.6, 1.1)
            thmax = turns * 2 * math.pi
            for i in range(int(thmax / 0.12)):
                th = i * 0.12
                r = a * th
                xi = int(round(cx + r * math.cos(th)))
                yi = int(round(cy + r * math.sin(th)))
                if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    return img

def gen_crescent(seed, spacing=20):
    """Crescent Moon 新月 — arcs with radial hash lines."""
    rng = random.Random(seed)
    img = set()
    for gy in range(14, H, spacing):
        for gx in range(14, W, spacing):
            if rng.random() < 0.3: continue
            cx = gx + rng.uniform(-3, 3); cy = gy + rng.uniform(-3, 3)
            r = rng.uniform(5, 8)
            a0 = rng.uniform(0, math.tau)
            span = math.pi * rng.uniform(0.7, 1.1)
            # arc
            n = max(12, int(r * 6))
            for i in range(n + 1):
                a = a0 + span * i / n
                xi = int(round(cx + r * math.cos(a)))
                yi = int(round(cy + r * math.sin(a)))
                if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
            # radial hash from center to arc
            for i in range(0, n + 1, 3):
                a = a0 + span * i / n
                for t in range(3, int(r) - 1):
                    xi = int(round(cx + t * math.cos(a)))
                    yi = int(round(cy + t * math.sin(a)))
                    if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    return img

def gen_flux(seed):
    """Flux 流动 — bundles of parallel flowing curves."""
    rng = random.Random(seed)
    img = set()
    n_bundles = rng.randint(3, 5)
    for b in range(n_bundles):
        y_off = rng.randint(15, 110)
        amp = rng.uniform(6, 14)
        freq = rng.uniform(0.01, 0.025)
        phase = rng.uniform(0, math.tau)
        n_lines = rng.randint(3, 5)
        for li in range(n_lines):
            dy = (li - n_lines / 2) * rng.uniform(2.5, 4)
            for x in range(0, W, 2):
                y = y_off + dy + amp * math.sin(freq * x + phase + li * 0.3)
                yi = int(round(y))
                if 0 <= yi < H:
                    img.add((x, yi))
    return img

def gen_mooka(seed):
    """Mooka 莫卡 — S-curve tendrils with round tips."""
    rng = random.Random(seed)
    img = set()
    n = rng.randint(4, 7)
    for i in range(n):
        x0 = rng.randint(10, W - 10)
        y0 = rng.randint(10, H - 10)
        length = rng.randint(40, 90)
        dirn = rng.choice([-1, 1])
        amp = rng.uniform(4, 8)
        # S-curve: x = x0 + t*dirn, y = y0 + amp*sin(t*pi/length*2)
        for t in range(0, length, 2):
            xx = int(x0 + t * dirn)
            yy = int(round(y0 + amp * math.sin(t / length * 2 * math.pi)))
            if 0 <= xx < W and 0 <= yy < H: img.add((xx, yy))
        # round tip
        tipx = int(x0 + length * dirn); tipy = int(round(y0))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                img.add((tipx + dx, tipy + dy))
    return img

def gen_fescu(seed):
    """Fescu 费斯库 — feather/leaf clusters (spine + diagonal barbs)."""
    rng = random.Random(seed)
    img = set()
    n = rng.randint(3, 5)
    for i in range(n):
        x0 = rng.randint(20, W - 20); y0 = rng.randint(15, H - 15)
        length = rng.randint(30, 70)
        ang = rng.uniform(-0.8, 0.8)
        dx, dy = math.cos(ang), math.sin(ang)
        # spine
        for t in range(length):
            xi = int(round(x0 + dx * t)); yi = int(round(y0 + dy * t))
            if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
        # barbs both sides
        for t in range(4, length - 2, 4):
            bx = x0 + dx * t; by = y0 + dy * t
            nx, ny = -dy, dx  # normal
            for side in (1, -1):
                for s in range(3, 9, 3):
                    xi = int(round(bx + nx * side * s)); yi = int(round(by + ny * side * s))
                    if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    return img

def gen_betweed(seed):
    """Betweed 编织带 — interleaving sine bands."""
    rng = random.Random(seed)
    img = set()
    n = rng.randint(3, 5)
    for i in range(n):
        yc = rng.randint(15, 113)
        amp = rng.uniform(8, 16)
        freq = rng.uniform(0.015, 0.03)
        phase = rng.uniform(0, math.tau)
        w = rng.uniform(2.5, 4)
        for x in range(0, W, 2):
            y = yc + amp * math.sin(freq * x + phase)
            for wy in range(-int(w), int(w) + 1):
                yi = int(round(y + wy))
                if 0 <= yi < H: img.add((x, yi))
    return img

def gen_hollibaugh(seed, arch=16):
    """Hollibaugh 霍利博 — arcade of nested arches."""
    rng = random.Random(seed)
    img = set()
    n_layers = rng.randint(2, 3)
    for col, x0 in enumerate(range(6, W, arch)):
        x1 = min(x0 + arch, W - 4)
        cx = (x0 + x1) / 2
        for layer in range(n_layers):
            r = (x1 - x0) * 0.45 + layer * 4
            for i in range(0, 19):
                a = math.pi * i / 18  # top half only
                xi = int(round(cx + r * math.cos(math.pi - a)))
                yi = int(round(H - 6 - r * math.sin(a)))
                if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    return img

def gen_weave(seed, spacing=10):
    """Weave 编织篮 — diagonal basket weave (45° cross-hatch with gaps)."""
    rng = random.Random(seed)
    img = set()
    for i in range(-H, W + H, spacing):
        for j in range(0, H, 2):
            x = i + j; y = j
            if 0 <= x < W and 0 <= y < H: img.add((x, y))
    for i in range(-H, W + H, spacing):
        for j in range(0, H, 2):
            x = i - j + H; y = j
            if 0 <= x < W and 0 <= y < H: img.add((x, y))
    return img

def gen_scale(seed, scale=16):
    """Scale 鱼鳞 — overlapping semicircle scales."""
    rng = random.Random(seed)
    img = set()
    r = int(scale / 2)
    for row in range(0, H + r, r):
        off = (row // r) % 2 * r
        for cx in range(0, W + r, r * 2):
            xx = cx + off
            for i in range(19):
                a = math.pi * i / 18
                xi = int(round(xx + r * math.cos(a)))
                yi = int(round(row + r - r * math.sin(a)))  # arch up
                if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    return img

def gen_rose(seed, k=None):
    """Rose 玫瑰线 — r = a*cos(kθ) flower curves."""
    rng = random.Random(seed)
    img = set()
    cx, cy = W / 2, H / 2
    k = k or rng.choice([3, 4, 5, 6])
    a = min(W, H) * 0.42
    for i in range(2000):
        th = i / 2000 * 2 * math.pi * 4
        r = a * math.cos(k * th)
        if r < 0: continue
        x = cx + r * math.cos(th); y = cy + r * math.sin(th)
        xi, yi = int(round(x)), int(round(y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if 0 <= xi + dx < W and 0 <= yi + dy < H: img.add((xi + dx, yi + dy))
    return img

def gen_lissajous(seed):
    """Lissajous 利萨茹 — parametric closed curves."""
    rng = random.Random(seed)
    img = set()
    cx, cy = W / 2, H / 2
    ax, ay = min(W, H) * 0.4, min(W, H) * 0.35
    na = rng.choice([3, 4, 5]); nb = rng.choice([4, 5, 6])
    delta = rng.uniform(0, math.pi / 2)
    n = 4000
    for i in range(n):
        t = i / n * 2 * math.pi * (na if nb % 2 == 0 else 1) * 4
        x = cx + ax * math.sin(na * t + delta)
        y = cy + ay * math.sin(nb * t)
        xi, yi = int(round(x)), int(round(y))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                if 0 <= xi + dx < W and 0 <= yi + dy < H: img.add((xi + dx, yi + dy))
    return img

def gen_aster(seed):
    """Aster 星芒 — radial burst with dotted rings."""
    rng = random.Random(seed)
    img = set()
    cx, cy = W / 2, H / 2
    n_rays = rng.choice([12, 16, 20])
    rmax = max(W, H) * 0.7
    for k in range(n_rays):
        a = 2 * math.pi * k / n_rays + rng.uniform(-0.02, 0.02)
        for r in range(0, int(rmax), 2):
            xi = int(round(cx + r * math.cos(a)))
            yi = int(round(cy + r * math.sin(a)))
            if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    # dotted rings
    for ring, rr in enumerate(range(14, int(rmax * 0.9), 16)):
        for i in range(48):
            a = 2 * math.pi * i / 48
            xi = int(round(cx + rr * math.cos(a)))
            yi = int(round(cy + rr * math.sin(a)))
            if 0 <= xi < W and 0 <= yi < H: img.add((xi, yi))
    return img

def gen_stipple(seed):
    """Stipple 点彩 — dot density gradient (dense center → sparse edges)."""
    rng = random.Random(seed)
    img = set()
    cx, cy = W / 2, H / 2
    rmax = math.hypot(cx, cy)
    for y in range(0, H, 2):
        for x in range(0, W, 2):
            d = math.hypot(x - cx, y - cy) / rmax
            p = max(0.05, 0.65 - d * 0.7)
            if rng.random() < p:
                img.add((x, y))
    return img


PATTERNS = {
    'waves': gen_waves, 'concentric': gen_concentric, 'spiral': gen_spiral,
    'grid': gen_grid_tangle, 'vine': gen_vine, 'honeycomb': gen_honeycomb,
    'mandala': gen_zen_circle, 'meander': gen_meander, 'ripple': gen_ripple_leaf,
    'knightsbridge': gen_knightsbridge, 'paradox': gen_paradox, 'printemps': gen_printemps,
    'crescent': gen_crescent, 'flux': gen_flux, 'mooka': gen_mooka,
    'fescu': gen_fescu, 'betweed': gen_betweed, 'hollibaugh': gen_hollibaugh,
    'weave': gen_weave, 'scale': gen_scale, 'rose': gen_rose,
    'lissajous': gen_lissajous, 'aster': gen_aster, 'stipple': gen_stipple,
}

# Patterns suitable for local-region (patch) rendering:
#  - center-based: recentered to region center (complete motif inside region)
#  - tiling: uniform, clip works
#  - NOT suitable: meander/hollibaugh (edge-anchored), vine/fescu/mooka/ripple (random scatter, may clip empty)
PATCH_OK = {
    'spiral', 'concentric', 'mandala', 'rose', 'aster', 'lissajous', 'paradox',
    'waves', 'flux', 'printemps', 'crescent', 'stipple', 'scale', 'weave',
    'betweed', 'grid', 'knightsbridge',
}

def gen_patch(pattern, seed, x0, y0, w, h):
    """Generate a pattern confined to region (x0, y0, w, h), absolute coords.
    Center-based patterns recenter to the region center; tiling patterns clip."""
    rng = random.Random(seed)
    cx, cy = x0 + w / 2.0, y0 + h / 2.0
    X1, Y1 = x0 + w, y0 + h
    pts = set()

    def _in(x, y):
        return x0 <= x < X1 and y0 <= y < Y1

    if pattern == 'spiral':
        a = rng.uniform(0.9, 1.3)
        rmax = math.hypot(w, h) / 2
        for i in range(int((rmax / a) / 0.14)):
            th = i * 0.14
            r = a * th
            xi, yi = int(round(cx + r * math.cos(th))), int(round(cy + r * math.sin(th)))
            if _in(xi, yi): pts.add((xi, yi))
    elif pattern == 'concentric':
        spacing = max(4, min(w, h) // 12)
        rmax = math.hypot(w, h) / 2
        for k in range(1, int(rmax // spacing) + 1):
            r = 2 + k * spacing
            steps = max(24, int(4 * math.pi * r))
            for i in range(steps):
                a = 2 * math.pi * i / steps
                xi, yi = int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))
                if _in(xi, yi): pts.add((xi, yi))
    elif pattern == 'mandala':
        R = min(w, h) * 0.42
        steps = int(2 * math.pi * R)
        for i in range(steps):
            a = 2 * math.pi * i / steps
            xi, yi = int(round(cx + R * math.cos(a))), int(round(cy + R * math.sin(a)))
            if _in(xi, yi): pts.add((xi, yi))
        n_spokes = rng.choice([8, 12])
        for k in range(n_spokes):
            a0 = 2 * math.pi * k / n_spokes
            for t in range(0, int(R), 2):
                xi, yi = int(round(cx + t * math.cos(a0))), int(round(cy + t * math.sin(a0)))
                if _in(xi, yi): pts.add((xi, yi))
        for i in range(48):
            a = 2 * math.pi * i / 48
            r = R * 0.55
            xi, yi = int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))
            if _in(xi, yi): pts.add((xi, yi))
    elif pattern == 'rose':
        k = rng.choice([3, 4, 5])
        a = min(w, h) * 0.4
        for i in range(2000):
            th = i / 2000 * 2 * math.pi * 4
            r = a * math.cos(k * th)
            if r < 0: continue
            xi, yi = int(round(cx + r * math.cos(th))), int(round(cy + r * math.sin(th)))
            if _in(xi, yi):
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if _in(xi + dx, yi + dy): pts.add((xi + dx, yi + dy))
    elif pattern == 'aster':
        n_rays = rng.choice([8, 12])
        rmax = max(w, h) * 0.6
        for k in range(n_rays):
            a = 2 * math.pi * k / n_rays
            for r in range(0, int(rmax), 2):
                xi, yi = int(round(cx + r * math.cos(a))), int(round(cy + r * math.sin(a)))
                if _in(xi, yi): pts.add((xi, yi))
    elif pattern == 'lissajous':
        ax, ay = w * 0.36, h * 0.34
        na, nb = rng.choice([3, 4]), rng.choice([4, 5])
        delta = rng.uniform(0, math.pi / 2)
        for i in range(4000):
            t = i / 4000 * 2 * math.pi * (na if nb % 2 == 0 else 1) * 4
            xi, yi = int(round(cx + ax * math.sin(na * t + delta))), int(round(cy + ay * math.sin(nb * t)))
            if _in(xi, yi):
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        if _in(xi + dx, yi + dy): pts.add((xi + dx, yi + dy))
    elif pattern == 'paradox':
        size = min(w, h) * 0.9
        ang = rng.uniform(0, math.pi / 4)
        for k in range(10):
            s = size * (0.88 ** k)
            if s < 3: break
            a = ang + k * 0.12
            corners = [(cx + s * math.cos(a + i * math.pi / 2), cy + s * math.sin(a + i * math.pi / 2)) for i in range(4)]
            for i in range(4):
                xc0, yc0 = corners[i]; xc1, yc1 = corners[(i + 1) % 4]
                steps = max(4, int(s * 0.7))
                for t in range(steps):
                    xi = int(round(xc0 + (xc1 - xc0) * t / steps))
                    yi = int(round(yc0 + (yc1 - yc0) * t / steps))
                    if _in(xi, yi): pts.add((xi, yi))
    else:
        # tiling pattern: full-screen then clip (only for PATCH_OK tiling patterns)
        full = PATTERNS[pattern](seed)
        pts = {(x, y) for (x, y) in full if _in(x, y)}
    return pts

# ---------------------------------------------------------------- render/convert

def to_bitmap(img_set, w=W, h=H):
    """1-bpp raw bitmap, MSB first, row padded to 8."""
    row_bytes = (w + 7) // 8
    buf = bytearray(row_bytes * h)
    for (x, y) in img_set:
        if 0 <= x < w and 0 <= y < h:
            byte = y * row_bytes + x // 8
            buf[byte] |= 0x80 >> (x % 8)
    return bytes(buf)

def render_png(img_set, path, scale=2):
    from PIL import Image
    img = Image.new('RGB', (W, H), 'white')
    px = img.load()
    for (x, y) in img_set:
        if 0 <= x < W and 0 <= y < H:
            px[x, y] = (0, 0, 0)
    img = img.resize((W * scale, H * scale), Image.NEAREST)
    img.save(path)
    return path

def upload(ip, name, data):
    import urllib.request
    req = urllib.request.Request(
        f"http://{ip}:8080/api/canvas_image?name={name}", data=data,
        headers={"Content-Type": "application/octet-stream"}, method="POST")
    return urllib.request.urlopen(req, timeout=10).read().decode()

# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="Zentangle generator for e-paper")
    ap.add_argument('--list', action='store_true')
    ap.add_argument('--preview', action='store_true', help='render 8 samples to one PNG')
    ap.add_argument('--gen', metavar='NAME')
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--out', default=None)
    ap.add_argument('--raw', default=None)
    ap.add_argument('--upload', metavar='IP')
    ap.add_argument('--pattern', default=None, help='pattern name for --upload')
    ap.add_argument('--name', default='zentangle')
    ap.add_argument('--region', default=None, help='local region "x0,y0,w,h" (patch mode: small area, not full screen)')
    args = ap.parse_args()

    if args.list:
        print('Zentangle patterns:')
        for n in sorted(PATTERNS): print(f'  {n}')
        return

    if args.preview:
        names = ['waves', 'concentric', 'spiral', 'grid', 'vine', 'honeycomb', 'mandala', 'meander', 'ripple',
                 'knightsbridge', 'paradox', 'printemps', 'crescent', 'flux', 'mooka', 'fescu', 'betweed',
                 'hollibaugh', 'weave', 'scale', 'rose', 'lissajous', 'aster', 'stipple']
        from PIL import Image, ImageDraw, ImageFont
        try:
            font = ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 14)
        except Exception:
            font = ImageFont.load_default()
        cols = 4; cell_w = W * 2; cell_h = H * 2 + 26
        rows = (len(names) + cols - 1) // cols
        grid = Image.new('RGB', (cols * cell_w, rows * cell_h), '#dddddd')
        gd = ImageDraw.Draw(grid)
        for i, n in enumerate(names):
            r, c = divmod(i, cols)
            x0, y0 = c * cell_w, r * cell_h
            gd.rectangle([x0 + 3, y0 + 3, x0 + cell_w - 3, y0 + cell_h - 3], fill='white', outline='#bbbbbb')
            img_set = PATTERNS[n](random.randrange(10**6))
            render_png(img_set, '/tmp/_z.png', scale=1)
            from PIL import Image as I2
            small = I2.open('/tmp/_z.png').resize((W * 2, H * 2), Image.NEAREST)
            grid.paste(small, (x0 + 3, y0 + 3))
            gd.text((x0 + 8, y0 + H * 2 + 6), n, fill='black', font=font)
        out = os.path.expanduser('~/.hermes/xiaozhi_canvas/zentangle_overview.png')
        grid.save(out)
        print(out, grid.size)
        return

    if args.gen:
        if args.gen not in PATTERNS:
            print(f'ERROR: unknown pattern {args.gen}. Use --list', file=sys.stderr); sys.exit(1)
        seed = args.seed if args.seed is not None else random.randrange(10**6)
        img_set = PATTERNS[args.gen](seed)
        out = args.out or f'/tmp/zentangle_{args.gen}_{seed}.png'
        render_png(img_set, out)
        print(f'{out} seed={seed} pixels={len(img_set)}')
        if args.raw:
            with open(args.raw, 'wb') as f: f.write(to_bitmap(img_set))
            print(f'raw: {args.raw} ({BYTES} bytes)')
        return

    if args.upload:
        pname = args.pattern or 'mandala'
        if pname not in PATTERNS:
            print(f'ERROR: unknown pattern {pname}. Use --list', file=sys.stderr); sys.exit(1)
        seed = args.seed if args.seed is not None else random.randrange(10**6)
        if args.region:
            try:
                rx, ry, rw, rh = (int(v) for v in args.region.split(','))
            except Exception:
                print('ERROR: --region must be "x0,y0,w,h"', file=sys.stderr); sys.exit(1)
            if pname not in PATCH_OK:
                print(f'WARNING: {pname} not in PATCH_OK (may render empty in a small region)', file=sys.stderr)
            img_set = gen_patch(pname, seed, rx, ry, rw, rh)
        else:
            img_set = PATTERNS[pname](seed)
        data = to_bitmap(img_set)
        resp = upload(args.upload, args.name, data)
        mode = f'region=({rx},{ry},{rw}x{rh})' if args.region else 'full'
        print(f'pattern={pname} seed={seed} name={args.name} {mode} {len(data)}B -> {resp}')
        return

    ap.print_help()

if __name__ == '__main__':
    main()
