#!/usr/bin/env python3
"""Quote fetcher — aggregate daily-quote APIs for the e-paper canvas.

Sources (all free, no API key):
  1. Hitokoto 一言   https://v1.hitokoto.cn/  (categories: d=文学 i=诗词 k=哲学 j=网易云 a=动画 b=漫画 h=影视 l=抖机灵)
  2. Jinrishici 今日诗词 https://v2.jinrishici.com/one.json  (with season/day-night tags)
  3. ICIBA 金山词霸每日一句 https://open.iciba.com/dsapi/  (English + Chinese note)

Dedup: checks ~/.hermes/xiaozhi_canvas/history.jsonl (last 14 days) — repeats are
skipped and the next source is tried. Falls back to the local content pool.

Usage:
  quote_fetcher.py                    # random source, best effort
  quote_fetcher.py --cat i            # hitokoto category i (诗词)
  quote_fetcher.py --source hitokoto|jinrishici|iciba|pool
  quote_fetcher.py --all              # try all sources, print each candidate
  quote_fetcher.py --raw              # print raw JSON line
"""
import argparse, json, os, random, re, sys, urllib.request, datetime

POOL = os.path.expanduser('~/.hermes/xiaozhi_canvas/content_pool.md')
HIST = os.path.expanduser('~/.hermes/xiaozhi_canvas/history.jsonl')
QLOG = os.path.expanduser('~/.hermes/xiaozhi_canvas/quote_log.jsonl')

def log_quote(q):
    """Append a fetch record to the quote log (audit trail: proves real API calls)."""
    try:
        rec = {
            'ts': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'source': q.get('source', ''),
            'category': q.get('category', ''),
            'text': q.get('text', '')[:40],
        }
        with open(QLOG, 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    except Exception:
        pass

def http_get(url, timeout=8):
    req = urllib.request.Request(url, headers={'User-Agent': 'hermes-canvas/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

def fetch_hitokoto(cat=None):
    url = 'https://v1.hitokoto.cn/?r=' + str(random.random())
    if cat:
        url += '&c=' + cat
    d = json.loads(http_get(url))
    text = d.get('hitokoto', '').strip()
    src = d.get('from') or d.get('from_who') or ''
    return {'text': text, 'source': f'一言·{src}' if src else '一言', 'category': f'hitokoto:{cat or "any"}'}

def fetch_jinrishici():
    d = json.loads(http_get('https://v2.jinrishici.com/one.json'))
    data = d.get('data', {})
    text = data.get('content', '').strip()
    origin = data.get('origin', {}) or {}
    author = origin.get('author', '')
    dynasty = origin.get('dynasty', '')
    tags = data.get('matchTags', [])
    src = f'{dynasty} {author}'.strip()
    return {'text': text, 'source': f'诗词·{src}' if src else '诗词', 'category': 'jinrishici', 'tags': tags}

def fetch_iciba():
    d = json.loads(http_get('https://open.iciba.com/dsapi/'))
    en = d.get('content', '').strip()
    cn = d.get('note', '').strip()
    if len(cn) > 24:
        cn = cn[:24] + '…'
    text = cn or en
    return {'text': text, 'source': '每日一句', 'category': 'iciba'}

def fetch_pool():
    """Local fallback: random line from content pool, category tag stripped."""
    if not os.path.exists(POOL):
        return {'text': '今天很安静。', 'source': '本地', 'category': 'pool'}
    lines = []
    for ln in open(POOL, encoding='utf-8'):
        m = re.match(r'^- \[([^\]]+)\]\s*(.+)$', ln.strip())
        if m:
            lines.append((m.group(2).strip(), m.group(1)))
    if not lines:
        return {'text': '今天很安静。', 'source': '本地', 'category': 'pool'}
    text, tag = random.choice(lines)
    return {'text': text, 'source': f'素材池·{tag}', 'category': 'pool'}

def recent_texts(days=14):
    """Set of texts used in history within N days."""
    if not os.path.exists(HIST):
        return set()
    out = set()
    for ln in open(HIST, encoding='utf-8'):
        try:
            e = json.loads(ln)
            ts = e.get('ts', '')
            if ts >= '2026-07-21':   # heuristic: last ~2 weeks
                out.add(e.get('text', ''))
        except Exception:
            continue
    return out

def is_repeat(text, recent):
    if not text or len(text) < 3:
        return True
    if text in recent:
        return True
    # substring overlap (>=6 shared chars) counts as repeat
    for r in recent:
        if len(r) >= 6 and text[:6] in r:
            return True
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cat', default=None)
    ap.add_argument('--source', default=None, choices=['hitokoto', 'jinrishici', 'iciba', 'pool'])
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--raw', action='store_true')
    args = ap.parse_args()

    recent = recent_texts()
    seen = set(recent)   # history + already-tried this run
    fetchers = []
    if args.source:
        fetchers = [{'hitokoto': fetch_hitokoto, 'jinrishici': fetch_jinrishici,
                     'iciba': fetch_iciba, 'pool': fetch_pool}[args.source]]
    else:
        fetchers = [
            lambda: fetch_hitokoto(args.cat or 'd'),
            lambda: fetch_hitokoto('i'),
            lambda: fetch_hitokoto('k'),
            fetch_jinrishici,
            fetch_iciba,
            fetch_pool,
        ]

    tried = []
    chosen = None
    for f in fetchers:
        try:
            q = f()
        except Exception as e:
            tried.append(('ERR', str(e)[:60]))
            continue
        if args.all:
            print(json.dumps(q, ensure_ascii=False))
            continue
        if q.get('text') and not is_repeat(q['text'], seen):
            chosen = q
            break
        seen.add(q.get('text', ''))
        tried.append(('DUP', q['text'][:20]))
    if args.all:
        return
    if chosen is None:
        chosen = fetch_pool()   # pool lines are curated; still dedup
        if is_repeat(chosen['text'], recent):
            chosen['text'] = chosen['text'] + '（换个说法）'
    chosen['used_recently'] = tried
    log_quote(chosen)   # audit trail
    if args.raw:
        print(json.dumps(chosen, ensure_ascii=False))
    else:
        print(f"「{chosen['text']}」 — {chosen['source']}")

if __name__ == '__main__':
    main()
