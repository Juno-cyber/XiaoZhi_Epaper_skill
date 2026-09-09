#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""workflow_map.py — 生成「小智定时任务 × 屏幕显示」工作流总览图 (自包含 SVG)。

把运行时事实合成一张图，回答：「用户用 skill 建了哪些定时任务、它们又如何改变了屏幕」。
也可用 --preview-* 在不创建 cron 的情况下预览一个候选任务。
  1) Hermes cron 注册表   ~/.hermes/cron/jobs.json      （每个 job 的调度/状态/目标）
  2) 画布历史台账          ~/.hermes/xiaozhi_canvas/history.jsonl （每 30 分钟一屏的实际输出）
  3) 设备当前页面/元素      http://<IP>:8080             （fridge.page.list / element.list / canvas.list）

无第三方依赖（纯标准库），跨平台。输出 SVG 可直接在浏览器中打开。

用法：
  python3 workflow_map.py --ip 192.168.1.10 \
      --jobs ~/.hermes/cron/jobs.json \
      --history ~/.hermes/xiaozhi_canvas/history.jsonl \
      --out workflow_map.svg
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
import tempfile

from quick_page_builder import BuildError, DeviceClient
from workflow_snapshot import MAX_JOBS, build_snapshot, infer_target_page

MAX_INPUT_BYTES = 8 * 1024 * 1024

# ---------- 小工具 ----------

def load_json(path):
    if os.path.getsize(path) > MAX_INPUT_BYTES:
        raise ValueError(f'input file exceeds {MAX_INPUT_BYTES} bytes: {path}')
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def atomic_write_text(path, content):
    """Replace an output atomically and refuse symlink destinations."""
    target = os.path.abspath(os.path.expanduser(path))
    parent = os.path.dirname(target)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    if os.path.lexists(target) and os.path.islink(target):
        raise ValueError(f'refusing symlink output: {target}')
    descriptor, temporary = tempfile.mkstemp(prefix='.workflow-map-', dir=parent, text=True)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return target

def call_device(client, tool, args):
    """调用设备 /api/call，返回内层解析后的 JSON（列表或字典），失败返回 None。"""
    try:
        return client.call(tool, args)
    except BuildError:
        return None


# ---------- cron 表达式（`分 时 日 月 周`）最小解析 ----------

DOW = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']

def _expand(field, lo, hi, names=None):
    def parse_value(value):
        if names and value.lower() in names:
            return names.index(value.lower())
        return int(value)

    out = set()
    for chunk in field.split(','):
        if chunk in ('*', '?'):
            return None  # 全范围
        step = 1
        if '/' in chunk:
            chunk, step = chunk.split('/', 1)
            step = int(step)
            if step <= 0:
                raise ValueError('cron step must be positive')
        if chunk in ('*', '?'):
            out.update(range(lo, hi + 1, step))
            continue
        if '-' in chunk:
            a, b = chunk.split('-', 1)
            a, b = parse_value(a), parse_value(b)
            if not lo <= a <= b <= hi:
                raise ValueError('cron range is out of bounds')
            out.update(range(a, b + 1, step))
        else:
            value = parse_value(chunk)
            if not lo <= value <= hi:
                raise ValueError('cron value is out of bounds')
            if step == 1:
                out.add(value)
            else:
                out.update(range(value, hi + 1, step))
    return out

def parse_cron(expr):
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    return {
        'minutes': _expand(minute, 0, 59),
        'hours': _expand(hour, 0, 23),
        'days': _expand(dom, 1, 31),
        'months': _expand(month, 1, 12),
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


# ---------- 判断 job 是否写屏 + 目标页 ----------

def job_target_page(job):
    """Return the explicit/inferred page from raw or sanitized job data."""
    target = job.get('target')
    if isinstance(target, dict):
        page = target.get('page')
        return page if isinstance(page, int) and 6 <= page <= 15 else None
    return infer_target_page(job)[0]


# ---------- SVG 生成 ----------

COLOR = {
    'bg': '#FFFFFF',
    'surface': '#FAFAFA',
    'surface_2': '#F5F5F5',
    'text': '#0A0A0A',
    'text_2': '#3A3A3A',
    'muted': '#6E6E6E',
    'border': '#E5E5E5',
    'strong': '#1A1A1A',
    'red': '#FF5A5A',
}
MAX_TIMELINE_POINTS_PER_JOB = 48

def svg_text(c, x, y, size, anchor='start', fill='#0A0A0A', weight='normal', extra='', family='sans'):
    c = html.escape(str(c), quote=False)
    fonts = ('Noto Serif CJK SC, Noto Serif SC, Songti SC, STSong, SimSun, serif' if family == 'serif'
             else 'Noto Sans CJK SC, PingFang SC, Microsoft YaHei, Noto Sans SC, Arial, sans-serif')
    return (f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
            f'fill="{fill}" font-weight="{weight}" font-family="{fonts}" {extra}>{c}</text>')

def svg_rect(x, y, w, h, fill='none', stroke='#E5E5E5', sw=1, rx=0, dash=None, extra=''):
    dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" stroke="{stroke}" stroke-width="{sw}" rx="{rx}"{dash_attr} {extra}/>'

def svg_line(x1, y1, x2, y2, stroke='#6E6E6E', sw=1, dash=None):
    d = f' stroke-dasharray="{dash}"' if dash else ''
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{sw}"{d}/>'

def warning_label(warning):
    code = warning.get('code')
    labels = {
        'device_offline': '设备当前离线，任务信息仍可查看',
        'device_partial': '设备在线，但部分页面信息读取失败',
        'target_inferred': f'任务 {warning.get("job_id", "-")[:8]} 的目标页来自旧配置推断',
        'failure_streak': f'任务 {warning.get("job_id", "-")[:8]} 已连续失败 {warning.get("count", 0)} 次',
        'page_conflict': f'页面 {warning.get("page", "-")} 被多个启用任务共同写入',
        'invalid_schedule': f'任务 {warning.get("job_id", "-")[:8]} 的 cron 表达式无效',
        'executions_unavailable': '近期执行记录暂时不可读取',
        'jobs_truncated': f'任务过多，仅显示前 {MAX_JOBS} 个',
    }
    return labels.get(code, '检测到需要关注的任务配置')


def job_display_name(job, limit=28):
    """Prefer a concise label when legacy jobs stored prompt text as their name."""
    name = str(job.get('name') or job.get('id') or '未命名任务').strip()
    if len(name) > 48 or name.startswith(('你是 ', '请执行', '严格读取')):
        page = job_target_page(job)
        name = f'小智页面 {page} 定时任务' if page else '小智定时任务'
    return name[:limit]


def build(jobs, history, device, generated_at=None, warnings=None):
    """Render a compact Litsea-style black, white, and red cron overview."""
    warnings = warnings if isinstance(warnings, list) else []
    device = device if isinstance(device, dict) else {}
    history = history if isinstance(history, list) else []
    jobs = jobs if isinstance(jobs, list) else []
    screen_jobs = [
        job for job in jobs
        if job.get('enabled', True) and job_target_page(job) is not None
    ]

    width = 1040
    pad = 36
    content_width = width - pad * 2
    out = ['<rect x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>']

    # Brand header: restrained serif title and one Litsea-red rule.
    out.append(svg_rect(pad, 32, 4, 52, fill=COLOR['red'], stroke='none', rx=2))
    out.append(svg_text('小智定时任务', pad + 18, 56, 26, fill=COLOR['text'], weight='bold', family='serif'))
    out.append(svg_text('Cron overview · 简洁查看任务、时间与风险', pad + 18, 78, 12, fill=COLOR['muted']))
    generated_label = (generated_at or datetime.datetime.now().isoformat())[:16].replace('T', ' ')
    out.append(svg_text(f'更新于 {generated_label}', width - pad, 55, 11, anchor='end', fill=COLOR['muted']))

    online = bool(device.get('online'))
    partial = bool(device.get('partial'))
    device_label = '在线' if online and not partial else '部分可用' if online else '离线'
    active_count = sum(1 for job in jobs if job.get('enabled', True))
    last_refresh = history[-1].get('ts', '')[5:16].replace('T', ' ') if history else '暂无'
    metrics = [
        ('任务', str(len(jobs)), COLOR['text']),
        ('启用', str(active_count), COLOR['text']),
        ('风险', str(len(warnings)), COLOR['red'] if warnings else COLOR['text']),
        ('设备', device_label, COLOR['red'] if not online or partial else COLOR['text']),
    ]
    gap = 12
    card_width = (content_width - gap * 3) / 4
    for index, (label, value, value_color) in enumerate(metrics):
        x = pad + index * (card_width + gap)
        out.append(svg_rect(x, 108, card_width, 70, fill=COLOR['surface'], stroke=COLOR['border'], rx=4))
        out.append(svg_text(label, x + 16, 132, 11, fill=COLOR['muted']))
        out.append(svg_text(value, x + 16, 160, 22, fill=value_color, weight='bold'))
    out.append(svg_text(f'最近画布刷新 {last_refresh}', width - pad, 199, 10, anchor='end', fill=COLOR['muted']))

    # Task list: one quiet row per task, red reserved for attention states.
    y = 220
    out.append(svg_text('任务', pad, y, 17, fill=COLOR['text'], weight='bold', family='serif'))
    out.append(svg_text('名称', pad + 18, y + 28, 10, fill=COLOR['muted']))
    out.append(svg_text('调度', pad + 420, y + 28, 10, fill=COLOR['muted']))
    out.append(svg_text('目标', pad + 650, y + 28, 10, fill=COLOR['muted']))
    out.append(svg_text('状态', pad + 816, y + 28, 10, fill=COLOR['muted']))
    y += 40
    if not jobs:
        out.append(svg_rect(pad, y, content_width, 58, fill=COLOR['surface'], stroke=COLOR['border'], rx=4))
        out.append(svg_text('暂无小智定时任务', pad + 18, y + 34, 13, fill=COLOR['muted']))
        y += 74
    for job in jobs:
        status = 'disabled' if not job.get('enabled', True) else (job.get('last_status') or 'scheduled')
        streak = int(job.get('failure_streak') or 0)
        attention = status in {'error', 'failed', 'preview'} or streak > 0
        status_names = {
            'ok': '正常', 'success': '正常', 'error': '失败', 'failed': '失败',
            'disabled': '已暂停', 'preview': '预览', 'scheduled': '待运行', 'skipped': '已跳过',
        }
        status_label = status_names.get(status, status[:16])
        if streak:
            status_label += f' ×{streak}'
        expression = job.get('schedule_display') or job.get('schedule', {}).get('expr', '') or '未设置'
        target = job_target_page(job)
        confidence = (job.get('target') or {}).get('confidence') if isinstance(job.get('target'), dict) else None
        target_label = f'页面 {target}' if target else '待确认'
        if target and confidence != 'explicit':
            target_label += ' ?'
        out.append(svg_rect(pad, y, content_width, 60, fill=COLOR['bg'], stroke=COLOR['border'], rx=4))
        out.append(svg_rect(pad, y, 3, 60, fill=COLOR['red'] if attention else COLOR['strong'], stroke='none', rx=1))
        out.append(svg_text(job_display_name(job), pad + 18, y + 27, 13, fill=COLOR['text'], weight='bold'))
        out.append(svg_text(str(job.get('id') or '')[:8], pad + 18, y + 45, 9, fill=COLOR['muted']))
        out.append(svg_text(expression[:32], pad + 420, y + 35, 12, fill=COLOR['text_2']))
        out.append(svg_text(target_label, pad + 650, y + 35, 12, fill=COLOR['text_2']))
        out.append(svg_text(status_label, pad + 816, y + 35, 12,
                            fill=COLOR['red'] if attention else COLOR['text'], weight='bold'))
        y += 70

    # Compact 24-hour view. Every task shares one red visual language.
    y += 12
    out.append(svg_text('24 小时触发', pad, y, 17, fill=COLOR['text'], weight='bold', family='serif'))
    y += 22
    timeline_x = pad + 170
    timeline_width = content_width - 190
    if not screen_jobs:
        out.append(svg_text('暂无可定位到页面的任务', pad, y + 24, 12, fill=COLOR['muted']))
        y += 50
    else:
        for hour in (0, 6, 12, 18, 24):
            x = timeline_x + timeline_width * hour / 24
            out.append(svg_text(str(hour), x, y + 11, 9, anchor='middle', fill=COLOR['muted']))
        y += 20
        for job in screen_jobs:
            row_y = y + 16
            out.append(svg_text(job_display_name(job, limit=18), pad, row_y + 4, 10, fill=COLOR['text_2']))
            out.append(svg_line(timeline_x, row_y, timeline_x + timeline_width, row_y, stroke=COLOR['border'], sw=1))
            try:
                cron = parse_cron(job.get('schedule_display') or job.get('schedule', {}).get('expr', ''))
            except (TypeError, ValueError):
                cron = None
            if cron:
                hours = cron['hours'] if cron['hours'] is not None else set(range(24))
                minutes = cron['minutes'] if cron['minutes'] is not None else set(range(60))
                points = [(hour, minute) for hour in sorted(hours) for minute in sorted(minutes)]
                dense = len(points) > MAX_TIMELINE_POINTS_PER_JOB
                if dense:
                    stride = max(1, (len(points) + MAX_TIMELINE_POINTS_PER_JOB - 1) // MAX_TIMELINE_POINTS_PER_JOB)
                    points = points[::stride][:MAX_TIMELINE_POINTS_PER_JOB]
                for hour, minute in points:
                    x = timeline_x + timeline_width * (hour + minute / 60) / 24
                    out.append(f'<circle cx="{x}" cy="{row_y}" r="3" fill="{COLOR["red"]}"/>')
                if dense:
                    out.append(svg_text('高频', width - pad, row_y + 4, 9, anchor='end', fill=COLOR['muted']))
            y += 30

    # Risk summary replaces technical legends and device mockups.
    y += 18
    out.append(svg_text('需要关注', pad, y, 17, fill=COLOR['text'], weight='bold', family='serif'))
    y += 18
    visible_warnings = warnings[:6]
    if not visible_warnings:
        out.append(svg_rect(pad, y, content_width, 48, fill=COLOR['surface'], stroke=COLOR['border'], rx=4))
        out.append(svg_text('未发现需要关注的问题', pad + 18, y + 30, 12, fill=COLOR['text_2']))
        y += 58
    else:
        out.append(svg_rect(pad, y, content_width, 16 + len(visible_warnings) * 28,
                            fill=COLOR['surface'], stroke=COLOR['border'], rx=4))
        for index, warning in enumerate(visible_warnings):
            line_y = y + 27 + index * 28
            out.append(f'<circle cx="{pad + 18}" cy="{line_y - 4}" r="3" fill="{COLOR["red"]}"/>')
            out.append(svg_text(warning_label(warning), pad + 32, line_y, 11, fill=COLOR['text_2']))
        if len(warnings) > len(visible_warnings):
            out.append(svg_text(f'另有 {len(warnings) - len(visible_warnings)} 项', width - pad - 16, y + 27,
                                10, anchor='end', fill=COLOR['muted']))
        y += 30 + len(visible_warnings) * 28

    out.append(svg_line(pad, y + 8, width - pad, y + 8, stroke=COLOR['border']))
    out.append(svg_text('Litsea · XiaoZhi', pad, y + 30, 10, fill=COLOR['muted']))
    out.append(svg_text('黑白为信息，红色为行动提示', width - pad, y + 30, 10, anchor='end', fill=COLOR['muted']))
    height = max(520, y + 52)
    svg = ['<?xml version="1.0" encoding="UTF-8"?>']
    svg.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
    )
    svg.append('<title id="title">小智定时任务总览</title>')
    svg.append('<desc id="desc">显示任务、触发时间、目标页面、运行状态和风险。</desc>')
    svg.extend(out)
    svg.append('</svg>')
    return '\n'.join(svg)


def load_history(path):
    history = []
    if not os.path.exists(path):
        return history
    if os.path.islink(path) or not os.path.isfile(path):
        raise ValueError('history input must be a regular non-symlink file')
    if os.path.getsize(path) > MAX_INPUT_BYTES:
        raise ValueError(f'history file exceeds {MAX_INPUT_BYTES} bytes')
    with open(path, encoding='utf-8') as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError:
                continue
            if isinstance(item, dict) and isinstance(item.get('ts'), str):
                history.append(item)
    return history


def discover_one_device():
    import xiaozhi_discovery as discovery

    networks = discovery.local_networks()
    if not networks:
        return None
    found = discovery.discover(networks, all_devices=False)
    return next(iter(found), None)


def collect_device(ip, strict=False):
    device = {'online': False, 'partial': False, 'ip': ip, 'name': '', 'version': '', 'pages': [], 'elements': {}}
    if not ip:
        return device
    try:
        client = DeviceClient(ip)
        health = client.health()
        device.update({'online': True, 'name': health.get('name', ''), 'version': health.get('version', '')})
        network = call_device(client, 'device.network.info', {})
        if isinstance(network, dict):
            device['ip'] = network.get('ip') or ip
    except BuildError:
        if strict:
            raise
    return device


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    default_svg = os.path.expanduser(
        os.environ.get('XIAOZHI_WORKFLOW_SVG', '~/.hermes/xiaozhi_canvas/workflow-map.svg')
    )
    ap = argparse.ArgumentParser(description='生成 Litsea 风格的小智定时任务总览图 (SVG + JSON)')
    ap.add_argument('--jobs', default=os.path.expanduser('~/.hermes/cron/jobs.json'))
    ap.add_argument('--history', default=os.path.expanduser('~/.hermes/xiaozhi_canvas/history.jsonl'))
    ap.add_argument('--executions', default=os.path.expanduser('~/.hermes/cron/executions.db'))
    ap.add_argument('--ip', default=None, help='设备 IP；用于显示连接状态，SVG 不绘制屏幕内容')
    ap.add_argument('--discover', action='store_true', help='自动发现一台局域网小智设备')
    ap.add_argument('--strict-device', action='store_true', help='设备不可达时失败，而不是生成离线快照')
    ap.add_argument('--include-all-jobs', action='store_true', help='包含非 xiaozhi 定时任务')
    ap.add_argument('--preview-name', help='只预览、不创建：候选任务名称')
    ap.add_argument('--preview-schedule', help='只预览、不创建：5 段 cron 表达式')
    ap.add_argument('--preview-page', type=int, help='只预览、不创建：目标页 6-15')
    ap.add_argument('--preview-mode', default='canvas-refresh', help='预览任务模式（小写字母/数字/连字符）')
    ap.add_argument('--out', default=default_svg)
    ap.add_argument('--json-out', default=None, help='快照 JSON 路径；默认与 SVG 同名')
    args = ap.parse_args(argv)

    jobs_data = load_json(args.jobs) if os.path.exists(args.jobs) else {}
    raw_jobs = list(jobs_data.get('jobs', [])) if isinstance(jobs_data, dict) else []
    preview_requested = any((args.preview_name, args.preview_schedule, args.preview_page is not None))
    if preview_requested:
        if not args.preview_name or not args.preview_schedule or args.preview_page is None:
            raise ValueError('--preview-name、--preview-schedule、--preview-page 必须一起提供')
        if not 6 <= args.preview_page <= 15:
            raise ValueError('--preview-page 必须在 6-15 之间')
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,31}', args.preview_mode):
            raise ValueError('--preview-mode 格式无效')
        if parse_cron(args.preview_schedule) is None:
            raise ValueError('--preview-schedule 必须是有效的 5 段 cron 表达式')
        raw_jobs.append({
            'id': 'preview',
            'name': f'{args.preview_name[:200]}（预览，尚未创建）',
            'prompt': (
                f'[XIAOZHI_CRON_META v1 page={args.preview_page} mode={args.preview_mode}]\n'
                'preview only'
            ),
            'schedule': {'kind': 'cron', 'expr': args.preview_schedule},
            'enabled': True,
            'state': 'preview',
            'last_status': 'preview',
            'skills': ['xiaozhi-control'],
        })
    history = load_history(args.history)
    ip = args.ip
    if args.discover and not ip:
        ip = discover_one_device()
        if not ip and args.strict_device:
            raise BuildError('no xiaozhi device discovered')
    device = collect_device(ip, strict=args.strict_device)
    snapshot = build_snapshot(
        raw_jobs,
        history,
        device,
        executions_path=args.executions,
        include_all=args.include_all_jobs,
    )
    for job in snapshot['jobs']:
        expression = job.get('schedule_display') or job.get('schedule', {}).get('expr', '')
        try:
            valid_schedule = parse_cron(expression) is not None
        except (TypeError, ValueError):
            valid_schedule = False
        if not valid_schedule:
            snapshot['warnings'].append({'code': 'invalid_schedule', 'job_id': job['id']})
    svg = build(
        snapshot['jobs'],
        snapshot['history'],
        snapshot['device'],
        generated_at=snapshot['generated_at'],
        warnings=snapshot['warnings'],
    )
    svg_path = atomic_write_text(args.out, svg)
    json_path = args.json_out or os.path.splitext(svg_path)[0] + '.json'
    json_path = atomic_write_text(json_path, json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
    print(
        f'[OK] 已生成 {svg_path}  (xiaozhi cron {len(snapshot["jobs"])} 个 / '
        f'写屏 {sum(1 for job in snapshot["jobs"] if job_target_page(job))} 个 / '
        f'页面 {len(snapshot["device"]["pages"])} 个 / 历史 {len(snapshot["history"])} 屏)'
    )
    print(f'ARTIFACT_SVG={svg_path}')
    print(f'ARTIFACT_JSON={json_path}')
    return 0


if __name__ == '__main__':
    try:
        main()
    except (BuildError, OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
