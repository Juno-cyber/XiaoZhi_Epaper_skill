#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workflow_map.py — 生成「小智定时任务 × 屏幕显示」工作流总览图 (自包含 SVG)。

把三处来源合成一张图，回答：「用户用 skill 建了哪些定时任务、它们又如何改变了屏幕」：
  1) Hermes cron 注册表   ~/.hermes/cron/jobs.json      （每个 job 的调度/状态/目标）
  2) 画布历史台账          ~/.hermes/xiaozhi_canvas/history.jsonl （每 30 分钟一屏的实际输出）
  3) 设备当前页面/元素      http://<IP>:8080             （fridge.page.list / element.list / canvas.list）

无第三方依赖（纯标准库），跨平台。输出 SVG 浏览器直接打开；juno 上可再转 PNG。

用法：
  python3 workflow_map.py --ip 192.168.1.10 \
      --jobs ~/.hermes/cron/jobs.json \
      --history ~/.hermes/xiaozhi_canvas/history.jsonl \
      --out workflow_map.svg
"""
import argparse, json, os, re, sys, urllib.request, urllib.error, datetime, html

# ---------- 小工具 ----------

def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def call_device(ip, tool, args):
    """调用设备 /api/call，返回内层解析后的 JSON（列表或字典），失败返回 None。"""
    body = json.dumps({"tool": tool, "args": args}).encode()
    req = urllib.request.Request(f"http://{ip}:8080/api/call", data=body,
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            outer = json.loads(r.read().decode('utf-8'))
    except (urllib.error.URLError, ValueError, OSError) as e:
        return None
    if "error" in outer:
        return None
    t = outer.get("result", {}).get("content", [{}])[0].get("text", "")
    try:
        return json.loads(t)
    except ValueError:
        return None


# ---------- cron 表达式（`分 时 日 月 周`）最小解析 ----------

DOW = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']

def _expand(field, lo, hi, names=None):
    out = set()
    for chunk in field.split(','):
        if chunk in ('*', '?'):
            return None  # 全范围
        step = 1
        if '/' in chunk:
            chunk, step = chunk.split('/', 1)
            step = int(step)
        if '-' in chunk:
            a, b = chunk.split('-', 1)
            a, b = int(a), int(b)
            out.update(range(a, b + 1, step))
        elif names and chunk.lower() in names:
            out.add(names.index(chunk.lower()))
        else:
            out.add(int(chunk))
    return out

def parse_cron(expr):
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute, hour, _dom, _mon, dow = parts
    return {
        'minutes': _expand(minute, 0, 59),
        'hours': _expand(hour, 0, 23),
        'dow': _expand(dow, 0, 6, DOW),
    }

def humanize(expr):
    """把常见 cron 表达式翻译成中文，看不懂就原样返回。"""
    c = parse_cron(expr)
    if not c:
        return expr
    hs = c['hours']; ms = c['minutes']; ds = c['dow']
    if ds:  # 星期几触发
        dnames = ' '.join(DOW[i] for i in sorted(ds))
        h = (sorted(hs)[0] if hs else 0)
        m = (sorted(ms)[0] if ms else 0)
        return f'每周 {dnames} {h:02d}:{m:02d}'
    # 分钟粒度
    if hs and len(hs) <= 2 and ms is not None and len(ms) <= 4:
        htxt = (f'{min(hs)}:00-{max(hs)}:00' if len(hs) > 1 else f'{min(hs)}:00')
        mtxt = ','.join(str(x) for x in sorted(ms))
        return f'每天 {htxt} 的第 {mtxt} 分'
    if hs and len(hs) == 1 and ms:
        return f'每天 {min(hs):02d} 点 {",".join(str(x) for x in sorted(ms))} 分'
    return expr


# ---------- 设备页面 / 元素 ----------

def fetch_pages(ip):
    pages = call_device(ip, 'fridge.page.control', {'action': 'list'})
    return pages or []

def fetch_elements(ip, page):
    if page == 6:
        return call_device(ip, 'fridge.canvas.control', {'action': 'list'}) or []
    return call_device(ip, 'fridge.page.element.control', {'action': 'list', 'page': page}) or []


# ---------- 判断 job 是否写屏 + 目标页 ----------

def job_target_page(job):
    """粗略判断 job 写给哪个页面；写屏返回页码，否则 None。"""
    blob = ' '.join([str(job.get('name', '')), str(job.get('prompt', '')),
                     str(job.get('script', ''))])
    low = blob.lower()
    is_screen = ('xiaozhi' in low or '墨水' in blob or 'e-paper' in low or '画布' in blob
                 or '屏幕' in blob or '页' in blob and '排班' in blob)
    if job.get('skill') == 'xiaozhi-control':
        is_screen = True
    if not is_screen:
        return None
    m = re.search(r'页\s*(\d+)', blob) or re.search(r'page\s*([0-9]+)', low)
    if m:
        return int(m.group(1))
    if ('画布' in blob or 'canvas' in low):
        return 6
    return None


# ---------- SVG 生成 ----------

PALETTE = ['#e07b39', '#3f7fbf', '#2fa06b', '#9b59b6', '#c0392b', '#d68910']

def svg_text(c, x, y, size, anchor='start', fill='#222', weight='normal', extra=''):
    return (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{fill}" font-weight="{weight}" font-family="Noto Sans CJK SC, WenQuanYi Zen Hei, Arial, sans-serif" {extra}>{c}</text>')

def svg_rect(x, y, w, h, fill='none', stroke='#bbb', sw=1, rx=0, extra=''):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" rx="{rx}" {extra}/>'

def svg_line(x1, y1, x2, y2, stroke='#666', sw=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}/>'

def page_mockup(page, name, elems, x, y, s=0.52, title_color='#333'):
    """在 (x,y) 画一个 296x128 屏幕缩略图（比例 s），含元素。"""
    W, H = 296 * s, 128 * s
    out = [svg_rect(x, y, W, H, fill='#fff', stroke=title_color, sw=1.4, rx=2)]
    cid = f'clip_{page}_{x}_{y}'
    out.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{W}" height="{H}"/></clipPath>')
    out.append(f'<g clip-path="url(#{cid})">')
    for e in elems:
        t = e.get('type')
        if t == 'text':
            fs = int(e.get('font_size', 12)) * s
            align = e.get('align', 'left')
            mw = int(e.get('max_width', 276)) * s
            tx = x + e.get('x', 0) * s
            ty = y + e.get('y', 0) * s + fs  # SVG 基线
            anchor = 'start'; xx = tx
            if align == 'center':
                anchor = 'middle'; xx = tx + mw / 2
            elif align == 'right':
                anchor = 'end'; xx = tx + mw
            color = '#b23' if e.get('dtype') else '#111'
            out.append(svg_text(html.escape(e.get('text', ''))[:40], xx, ty, fs, anchor, color))
        elif t == 'rect':
            f = '#222' if e.get('filled') else 'none'
            ex, ey = x + e.get('x', 0) * s, y + e.get('y', 0) * s
            out.append(svg_rect(ex, ey, e.get('w', 0) * s, e.get('h', 0) * s, fill=f, stroke='#222', sw=0.8))
        elif t == 'line':
            out.append(svg_line(x + e.get('x1', 0) * s, y + e.get('y1', 0) * s,
                                x + e.get('x2', 0) * s, y + e.get('y2', 0) * s,
                                stroke='#222', sw=max(0.6, e.get('width', 1) * s)))
        elif t == 'image':
            ex, ey = x + e.get('x', 0) * s, y + e.get('y', 0) * s
            w, h = e.get('w', 24) * s, e.get('h', 24) * s
            out.append(svg_rect(ex, ey, w, h, fill='#f2f2f2', stroke='#999', sw=0.6, dash='4,3'))
            out.append(svg_text(html.escape(e.get('name', 'img'))[:8], ex + 2, ey + h / 2, 7, 'start', '#888'))
    out.append('</g>')
    return out


def build(jobs, history, device):
    """组装整张 SVG，返回字符串。"""
    ip = device['ip'] or '（未连设备）'
    ver = device.get('version', '')
    devname = device.get('name', '')
    pages = device['pages']

    dev_jobs = [j for j in jobs if job_target_page(j) is not None]
    dev_jobs = sorted(dev_jobs, key=lambda j: j.get('created_at') or '')
    color = {}
    for i, j in enumerate(dev_jobs):
        color[j['id']] = PALETTE[i % len(PALETTE)]

    buf = []
    W = 1180
    pad = 24

    # ---------- 头部 ----------
    chips = (f'定时任务 {len(jobs)} · 写屏任务 {len(dev_jobs)} · 页面 {len(pages)}'
             f' · 最近刷新 {history[-1]["ts"][:16] if history else "-"}')
    ym = 20
    buf.append(svg_rect(0, 0, W, 3000, fill='#ffffff', stroke='none'))
    buf.append(svg_text('小智 定时任务 × 屏幕显示 · 工作流总览', pad, pad + 8, 22, 'start', '#111', 'bold'))
    buf.append(svg_text(f'设备 {devname} · {ip} · 固件 {ver} · 生成于 {datetime.datetime.now().strftime("%Y-%m-%d %H:%M")}',
                        pad, pad + 32, 12, 'start', '#666'))
    buf.append(svg_rect(pad, pad + 42, W - 2 * pad, 26, fill='#f6f6f6', stroke='#e0e0e0', rx=4))
    buf.append(svg_text(chips, pad + 12, pad + 59, 12, 'start', '#333'))
    y = pad + 92

    # ---------- 1) 定时任务面板 ----------
    buf.append(svg_text('① 定时任务（cron jobs）—— 谁在驱动屏幕', pad, y, 14, 'start', '#111', 'bold'))
    y += 10
    col = {'调度': 16, '状态': 158, '上次': 208, '下次': 320, '目标/内容': 432, '类型': 700}
    # 表头
    buf.append(svg_text('任务 / 调度', pad + 6, y + 14, 11, 'start', '#999'))
    buf.append(svg_text('状态', pad + 158, y + 14, 11, 'start', '#999'))
    buf.append(svg_text('上次运行', pad + 208, y + 14, 11, 'start', '#999'))
    buf.append(svg_text('下次运行', pad + 320, y + 14, 11, 'start', '#999'))
    buf.append(svg_text('写屏目标', pad + 432, y + 14, 11, 'start', '#999'))
    buf.append(svg_text('方式', pad + 700, y + 14, 11, 'start', '#999'))
    y += 18
    for j in jobs:
        jid = j['id']
        is_dev = jid in color
        c = color.get(jid, '#999')
        expr = j.get('schedule_display') or j.get('schedule', {}).get('expr', '')
        name = (j.get('name') or jid)[:34]
        if is_dev:
            name = jid[:8] + ' ' + name
        status = j.get('last_status') or '—'
        if not j.get('enabled', True):
            status = 'disabled'
        stcolor = {'ok': '#2fa06b', 'error': '#c0392b', 'skipped': '#b8860b', 'disabled': '#999'}.get(status, '#666')
        last = (j.get('last_run_at') or '—')
        if len(last) > 16:
            last = last[5:16]
        nxt = (j.get('next_run_at') or '—')
        if len(nxt) > 16:
            nxt = nxt[5:16]
        buf.append(svg_rect(pad, y - 4, W - 2 * pad, 26, fill='#fff', stroke=c if is_dev else '#eee', sw=1))
        buf.append(svg_rect(pad, y - 4, 3, 26, fill=c, stroke='none'))
        buf.append(svg_text(html.escape(name), pad + 12, y + 12, 11, 'start', '#111'))
        buf.append(svg_text(html.escape(expr), pad + 12, y + 24, 9, 'start', '#888'))
        buf.append(svg_text(status, pad + 158, y + 12, 11, 'start', stcolor, 'bold'))
        buf.append(svg_text(last, pad + 208, y + 12, 10, 'start', '#555'))
        buf.append(svg_text(nxt, pad + 320, y + 12, 10, 'start', '#555'))
        tgt = job_target_page(j)
        tgtxt = f'page {tgt}' if tgt else ('feishu 报告' if j.get('deliver') == 'origin' else '—')
        buf.append(svg_text(tgtxt, pad + 432, y + 12, 11, 'start', c if is_dev else '#666',
                            'bold' if is_dev else 'normal'))
        kind = 'shell 脚本' if j.get('no_agent') else ('Agent(' + (j.get('model') or '?').split('/')[-1] + ')')
        buf.append(svg_text(kind, pad + 700, y + 12, 10, 'start', '#555'))
        y += 32

    # ---------- 2) 24h 调度条 ----------
    y += 8
    buf.append(svg_text('② 24 小时触发视图 —— 写屏任务在一天里的触发时点', pad, y, 14, 'start', '#111', 'bold'))
    y += 8
    barx, bary, barw, barh = pad + 120, y + 2, W - 2 * pad - 220, 46
    buf.append(svg_rect(barx, bary, barw, barh, fill='#fafafa', stroke='#ddd', rx=3))
    # 时间轴刻度
    for h in range(0, 25, 2):
        xx = barx + barw * h / 24
        buf.append(svg_line(xx, bary, xx, bary + barh, stroke='#eee'))
        buf.append(svg_text(f'{h}', xx, bary + barh + 12, 8, 'middle', '#999'))
    # 画布任务活动窗口 7:00-22:30 淡蓝底
    buf.append(svg_rect(barx + barw * 7 / 24, bary, barw * 15.5 / 24, barh, fill='#eef4fb', stroke='none'))
    for j in dev_jobs:
        c = color[j['id']]
        cron = parse_cron(j.get('schedule_display') or j.get('schedule', {}).get('expr', ''))
        ly = bary + 8 + (dev_jobs.index(j) * 16)
        buf.append(svg_text(html.escape((j.get('name') or j['id'])[:14]), barx - 118, ly + 6, 9, 'end', c))
        if not cron:
            continue
        hours = cron['hours'] if cron['hours'] is not None else set(range(24))
        mins = cron['minutes'] if cron['minutes'] is not None else {0}
        for h in sorted(hours):
            for m in sorted(mins):
                xx = barx + barw * (h + m / 60) / 24
                buf.append(f'<circle cx="{xx}" cy="{ly}" r="3" fill="{c}"/>')
    y = bary + barh + 22

    # ---------- 3) 屏幕页面面板 ----------
    y += 8
    buf.append(svg_text('③ 当前屏幕 —— 每页内容与驱动它的任务（同色）', pad, y, 14, 'start', '#111', 'bold'))
    y += 8
    gw = 300  # 每格宽
    gx, gy = pad, y
    for p in pages:
        pn = p.get('page')
        name = p.get('name') or f'page {pn}'
        owner = None
        for j in dev_jobs:
            if job_target_page(j) == pn:
                owner = color[j['id']]
                break
        c = owner or ('#999' if p.get('builtin') else '#666')
        elems = device['elements'].get(pn, []) if pn in device['elements'] else []
        buf.extend(page_mockup(pn, name, elems, gx, gy, s=0.52, title_color=c))
        # 页名横幅
        buf.append(svg_rect(gx, gy + 128 * 0.52 + 2, 296 * 0.52, 16, fill=c, stroke='none', rx=2))
        extra = ''
        dyn = [e for e in elems if e.get('dtype')]
        if dyn:
            extra = ' ⚡' + '+'.join(sorted(set(e['dtype'] for e in dyn)))
        buf.append(svg_text(f'p{pn} {html.escape(name)}{extra}', gx + 4, gy + 128 * 0.52 + 13, 9, 'start', '#fff', 'bold'))
        gx += gw
        if gx + gw > W - pad:
            gx = pad
            gy += 128 * 0.52 + 42
    y = gy + 128 * 0.52 + 44

    # ---------- 4) 最近活动 ----------
    y += 6
    buf.append(svg_text('④ 最近画布刷新（history.jsonl）—— 每 30 分钟一屏（截图前 16 字）', pad, y, 14, 'start', '#111', 'bold'))
    y += 8
    kw = (W - 2 * pad) / 4
    recent = history[-16:]
    for i, h in enumerate(recent):
        cx = pad + (i % 4) * (kw + 4)
        cy = y + (i // 4) * 40
        buf.append(svg_rect(cx, cy, kw, 32, fill='#fbfbfb', stroke='#e5e5e5', rx=3))
        buf.append(svg_text(h['ts'][11:16], cx + 6, cy + 11, 8, 'start', '#999'))
        buf.append(svg_text(f"{h.get('intent','')} · {h.get('layout','')}", cx + 6, cy + 22, 8, 'start', '#666'))
        txt = h.get('text', '')
        if '（' in txt:
            txt = txt.split('（')[0]
        buf.append(svg_text(html.escape(txt[:15]), cx + 6, cy + 32, 8, 'start', '#333'))
    y += ((len(recent) - 1) // 4 + 1) * 40 + 8

    # ---------- 图例 ----------
    if dev_jobs:
        buf.append(svg_text('图例（颜色 = 写屏任务）', pad, y, 11, 'start', '#666', 'bold'))
        y += 12
        lx = pad
        for j in dev_jobs:
            c = color[j['id']]
            tgt = job_target_page(j)
            buf.append(svg_rect(lx, y - 8, 10, 10, fill=c, stroke='none', rx=2))
            buf.append(svg_text(f'{j["id"][:8]} → page {tgt}', lx + 14, y, 10, 'start', '#444'))
            lx += 150

    height = max(y + 30, 700)
    svg = ['<?xml version="1.0" encoding="UTF-8"?>']
    svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}">')
    svg.extend(buf)
    svg.append('</svg>')
    return '\n'.join(svg)


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser(description='生成小智定时任务 × 屏幕总览图 (SVG)')
    ap.add_argument('--jobs', default=os.path.expanduser('~/.hermes/cron/jobs.json'))
    ap.add_argument('--history', default=os.path.expanduser('~/.hermes/xiaozhi_canvas/history.jsonl'))
    ap.add_argument('--ip', default=None, help='设备 IP；缺省则不连设备、不画页面')
    ap.add_argument('--out', default='workflow_map.svg')
    args = ap.parse_args()

    jobs = load_json(args.jobs).get('jobs', []) if os.path.exists(args.jobs) else []

    history = []
    if os.path.exists(args.history):
        with open(args.history, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    history.append(json.loads(line))
                except ValueError:
                    pass

    device = {'ip': args.ip, 'name': '', 'version': '', 'pages': [], 'elements': {}}
    if args.ip:
        h = call_device(args.ip, 'device.network.info', {})
        if h:
            device['ip'] = h.get('ip') or args.ip
        # 健康检查拿 name/version
        try:
            with urllib.request.urlopen(f"http://{args.ip}:8080/", timeout=8) as r:
                hh = json.loads(r.read().decode('utf-8'))
                device['name'] = hh.get('name', '')
                device['version'] = hh.get('version', '')
        except Exception:
            pass
        pages = fetch_pages(args.ip)
        device['pages'] = pages
        for p in pages:
            pn = p.get('page')
            device['elements'][pn] = fetch_elements(args.ip, pn)

    svg = build(jobs, history, device)
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(svg)
    print(f'[OK] 已生成 {args.out}  (cron {len(jobs)} 个 / 写屏 {sum(1 for j in jobs if job_target_page(j))} 个 / 页面 {len(device["pages"])} 个 / 历史 {len(history)} 屏)')


if __name__ == '__main__':
    main()