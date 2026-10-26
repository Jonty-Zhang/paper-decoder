"""没有 arXiv 网页版的论文（期刊正式版 PDF 等）：直接从 PDF 的文字行拆出标题、段落、图表题、行间公式和图形区域
用法: python3 pdfblocks.py <name>
需要: <name>_lines.json（lines.swift）、<name>_layout.json（layout.swift）
输出: <name>.json（块，每块带 "pdf": [[页, x0, y0, x1, y1], …] 裁切框，按阅读顺序排列）、<name>_anchors.json、
      <name>_src.txt（待译清单，格式与 extract.py 相同）
可选: <name>_blocks_override.json，手工修正分段：{"split": ["页:y", …], "join": ["页:y", …],
      "heading": ["页:y", …], "para": ["页:y", …], "meta": ["页:y", …], "eq": ["页:y", …],
      "meta_rect": [[页, x0, y0, x1, y1], …], "setcol": {"页:y": ["L", x0, x1]}}
      “页:y”的 y 取该行在 <name>_lines.json 里的 y0（取整），页码从 0 数；meta_rect 里的行只裁切不翻译；
      setcol 用来修正 PDF 文字框坐标出错的行（例如被根号撑歪的行）
适用于常见的期刊双栏/单栏版式，包括正文绕着图排的页面；版式特殊的论文要检查输出，必要时用 override 修正。"""
import json, re, sys, os, statistics as st

name = sys.argv[1]
LINES = json.load(open(f'{name}_lines.json')); LAY = json.load(open(f'{name}_layout.json'))
pages = LAY['pages']
OVR = json.load(open(f'{name}_blocks_override.json')) if os.path.exists(f'{name}_blocks_override.json') else {}
def okey(pi, l): return f'{pi}:{round(l["y0"])}'
def inovr(kind, pi, l):
    # 键写作“页:y”或“页:y:x”（y、x 为该行 y0、x0 取整；同一高度有好几行时加上 x 区分）
    if any(k == okey(pi, l) or k == f'{okey(pi, l)}:{round(l["x0"])}' for k in OVR.get(kind, [])): return True
    return kind == 'meta' and any(r[0] == pi and r[1] <= l['x0'] and l['x1'] <= r[3] and r[2] <= l['y0'] and l['y1'] <= r[4]
                                  for r in OVR.get('meta_rect', []))

# ---------- 基本尺度：正文行高、版心上下沿 ----------
from collections import Counter
def fkey(t): return re.sub(r'\d+', '#', re.sub(r'\s+', '', t.lower()))
rep = Counter(k for pl in LINES for k in {fkey(l['t']) for l in pl})
def bodyline(l): return len(l['t']) > 40 and rep[fkey(l['t'])] < max(2, 0.3 * len(LINES))   # 每页重复的长行是页眉页脚
longl = [l for pl in LINES for l in pl if bodyline(l)]
H = st.median(l['y1'] - l['y0'] for l in longl)
tops = sorted(min(l['y0'] for l in pl if bodyline(l)) for pl in LINES if any(bodyline(l) for l in pl))
bots = sorted(max(l['y1'] for l in pl if bodyline(l)) for pl in LINES if any(bodyline(l) for l in pl))
BT, BB = tops[len(tops) // 2], bots[len(bots) // 2]

# ---------- 页面杂项：页眉页脚、页码、竖排的下载水印 ----------
cnt = Counter(k for pi, pl in enumerate(LINES) for k in {fkey(l['t']) for l in pl if l['y1'] < BT - 2 or l['y0'] > BB + 2})
def furniture(pi, l):
    h = l['y1'] - l['y0']
    if h > 3 * H and l['x1'] - l['x0'] < 3 * H: return True          # 竖排文字
    if (l['y1'] < BT - 2 or l['y0'] > BB + 2) and (cnt[fkey(l['t'])] >= max(2, 0.3 * len(LINES)) or re.fullmatch(r'[#\sof]*', fkey(l['t']))):
        return True
    return False

CAP = re.compile(r'^(Fig\.?|Figure|Movie|Table|TABLE|FIG\.?)\s*([0-9]+|[IVX]+)\s*[.:]')
def soft(t): return re.sub(r'\xad\s*', '', t).replace('\n', ' ')        # 软连字符（含其后的空格）去掉，“high-\xad performance”还原成“high-performance”

P = []                                       # 每页保留的行（加上编号、栏别）
for pi, pl in enumerate(LINES):
    w = pages[pi]['w']; cx = w / 2
    keep = []
    for l in pl:
        if furniture(pi, l) or not l['t'].strip(): continue
        l = dict(l); l['t'] = soft(l['t']).strip(); l['h'] = l['y1'] - l['y0']
        fix = OVR.get('setcol', {}).get(f'{pi}:{round(l["y0"])}') or OVR.get('setcol', {}).get(f'{pi}:{round(l["y0"])}:{round(l["x0"])}')
        if fix: l['x0'], l['x1'] = fix[1], fix[2]
        l['col'] = 'L' if l['x1'] <= cx + 6 else ('R' if l['x0'] >= cx - 6 else 'S')
        keep.append(l)
    keep.sort(key=lambda l: (l['y0'], l['x0']))
    P.append(keep)

def overlap(a0, a1, b0, b1): return max(0, min(a1, b1) - max(a0, b0))

# ---------- 图表：图表题 + 上方（或下方）的图形区域 ----------
FIGS = []                                    # {page, cap:[lines], box:[x0,y0,x1,y1], gbox:[...], label}
used = set()
COLW = st.median(l['x1'] - l['x0'] for l in longl)          # 一栏的典型宽度
def is_body(l):                              # 正文行：字号与正文相同、足够长；图里的标注一般短而窄
    return l['h'] >= 0.85 * H and len(l['t']) >= 25 and l['x1'] - l['x0'] >= 0.45 * COLW
for pi, pl in enumerate(P):
    for i, l in enumerate(pl):
        m = CAP.match(l['t'])
        if not m or l['h'] >= 0.9 * H or id(l) in used: continue
        cap = [l]; used.add(id(l))
        for k in pl[i + 1:]:                 # 图表题续行：字号同样小、与上一行紧挨、横向范围重叠
            if id(k) in used: continue
            last = cap[-1]
            if k['y0'] - last['y1'] > 0.5 * H: break
            if k['h'] <= l['h'] + 2.5 and overlap(k['x0'], k['x1'], min(c['x0'] for c in cap), max(c['x1'] for c in cap)) > 0.5 * (k['x1'] - k['x0']):
                cap.append(k); used.add(id(k))
        x0, x1 = min(c['x0'] for c in cap), max(c['x1'] for c in cap)
        ctop, cbot = cap[0]['y0'], cap[-1]['y1']
        # 图形在图表题上方：往上找到同一横向范围内最近的正文行或前一个图表题为止
        above = [k['y1'] for k in pl if k['y1'] <= ctop + 1 and id(k) not in used and is_body(k)
                 and overlap(k['x0'], k['x1'], x0, x1) > 0.6 * (k['x1'] - k['x0'])]
        above += [f['box'][3] for f in FIGS if f['page'] == pi and overlap(f['box'][0], f['box'][2], x0, x1) > 20 and f['box'][3] <= ctop]
        gtop = max(above) + 2 if above else BT - 3
        FIGS.append({'page': pi, 'cap': cap, 'label': m.group(0), 'box': [x0, gtop, x1, cbot], 'gbox': [x0, gtop, x1, ctop - 1]})
# 图形区域内的文字（坐标轴、标注）不算正文
def in_fig(pi, l):
    return any(f['page'] == pi and l['y0'] >= f['box'][1] - 1 and l['y1'] <= f['box'][3] + 1
               and overlap(l['x0'], l['x1'], f['box'][0], f['box'][2]) > 0.5 * (l['x1'] - l['x0']) for f in FIGS)

# ---------- 栏与行的局部左右边界：整栏的左右沿，旁边有图时让出图的位置（正文绕图排） ----------
COLX = {}
for c in 'LR':
    xs = [l for pl in P for l in pl if l['col'] == c and is_body(l)]
    COLX[c] = (st.median(l['x0'] for l in xs), sorted(l['x1'] for l in xs)[len(xs) * 3 // 4]) if xs else None
SX = [l for pl in P for l in pl if l['col'] == 'S' and is_body(l)]
COLX['S'] = (min(COLX['L'][0], COLX['R'][0]) if COLX['L'] and COLX['R'] else 0, max(COLX['L'][1], COLX['R'][1]) if COLX['L'] and COLX['R'] else 9999)
def col_bounds(pi, l, pl):
    a, b = COLX[l['col']] if COLX.get(l['col']) else (l['x0'], l['x1'])
    for f in FIGS:
        # 图下方紧接着的一两行往往仍是窄栏，判断时把图的下沿放宽一点
        if f['page'] != pi or overlap(f['box'][1], f['box'][3] + 2 * H, l['y0'], l['y1']) <= 0: continue
        if f['box'][0] >= l['x1'] - 2 and f['box'][0] < b: b = f['box'][0] - 4      # 图在右边
        if f['box'][2] <= l['x0'] + 2 and f['box'][2] > a: a = f['box'][2] + 4      # 图在左边
    return min(a, l['x0']), max(b, l['x1'])

# ---------- 行间公式：缩进、右端带式号，或夹在正文之间、开头不在栏左沿的碎行 ----------
EQNO = re.compile(r'\((\d+[a-z]?)\)\s*$')
for pi, pl in enumerate(P):
    for l in pl:
        l['fig'] = in_fig(pi, l)
        if l['fig']: continue
        a, b = col_bounds(pi, l, pl); l['cl'], l['cr'] = a, b
    body_y = {}
    for l in pl:
        if l['fig']: continue
        l['eq'] = False
        if l['col'] == 'S': continue
        indented = l['x0'] > l['cl'] + 18
        sharing = any(k is not l and not k.get('fig') and k['col'] == l['col'] and k['x0'] <= k.get('cl', k['x0']) + 15
                      and overlap(k['y0'], k['y1'], l['y0'], l['y1']) > 0.5 * min(l['h'], k['h']) for k in pl)
        if indented and not sharing and len(l['t']) < 70 and not inovr('para', pi, l) and not inovr('heading', pi, l): l['eq'] = True
        if inovr('eq', pi, l): l['eq'] = True

# ---------- 阅读顺序：跨栏文字把页面分段，段内先左栏后右栏 ----------
order = []
for pi, pl in enumerate(P):
    txt = [l for l in pl if not l['fig']]
    groups = []                              # 相邻的跨栏行并成一组，每组把页面切开一次
    for l in sorted([l for l in txt if l['col'] == 'S'], key=lambda l: l['y0']):
        if groups and l['y0'] - groups[-1][1] < H: groups[-1][1] = max(groups[-1][1], l['y1'])
        else: groups.append([l['y0'], l['y1']])
    def seg(l): return sum(1 for g in groups if g[1] <= l['y0'] + 1)
    for l in txt:
        l['page'] = pi
        l['key'] = (pi, seg(l), {'S': -1, 'L': 0, 'R': 1}[l['col']], l['y0'], l['x0'])     # 跨栏行排在它那一段的最前面
    # 首页标题区：两栏正文开始之前的内容（标题、作者、摘要）不分栏，按 y 排；旁边的小字（版权框等）放在最后
    bl = [l for l in txt if is_body(l) and l['col'] == 'L']; br = [l for l in txt if is_body(l) and l['col'] == 'R']
    front = min((a['y0'] for a in bl if any(abs(a['y0'] - b['y0']) < 3 * H for b in br)), default=0) - 1.5 * H if pi == 0 else 0
    for l in txt:
        if l['y1'] <= front:
            side = l['h'] < 0.85 * H and l['col'] == 'R'
            l['key'] = (pi, -1, 2 if side else -1, l['y0'], l['x0'])
            if not side: l['front'] = True       # 标题区的行一律按整个版心宽度裁切
    order += sorted(txt, key=lambda l: l['key'])

# 同一行被拆成几段（行内公式把一行切开）：上下重叠一半以上的视为同一行，按 x 拼起来
merged = []
for l in order:
    m = merged[-1] if merged else None
    if m and m['page'] == l['page'] and m['col'] == l['col'] and not l['eq'] and not m['eq'] \
            and overlap(m['y0'], m['y1'], l['y0'], l['y1']) > 0.5 * min(l['h'], m['h']):
        a, b = (m, l) if m['x0'] <= l['x0'] else (l, m)
        a = dict(a); a['t'] = a['t'] + ' ' + b['t']; a['x0'] = min(m['x0'], l['x0']); a['x1'] = max(m['x1'], l['x1'])
        a['y0'] = min(m['y0'], l['y0']); a['y1'] = max(m['y1'], l['y1']); a['h'] = max(m['h'], l['h'])
        merged[-1] = a; continue
    merged.append(l)
order = merged

# ---------- 分段 ----------
REFHEAD = re.compile(r'^(references( and notes)?|bibliography)\s*$', re.I)
POSTREF = re.compile(r'^(Acknowledgments?|Funding|Author contributions|Competing interests|Data and materials availability|Supplementary Materials)\b')
blocks, cur = [], None
def flush():
    global cur
    if cur: blocks.append(cur)
    cur = None
def new(kind, l, **kw):
    global cur
    flush(); cur = {'type': kind, 'lines': [l], **kw}
in_refs = False
for i, l in enumerate(order):
    prev = order[i - 1] if i else None
    nxt = order[i + 1] if i + 1 < len(order) else None
    t = l['t']
    if inovr('meta', l['page'], l):
        if cur and cur['type'] == 'meta' and l['page'] == cur['lines'][-1]['page'] and l['y0'] - cur['lines'][-1]['y1'] < H: cur['lines'].append(l)
        else: new('meta', l)
        continue
    # 论文标题：首页上部、字号明显大于正文，连续几行并成一个一级标题
    title = l['page'] == 0 and l['y0'] < 0.25 * pages[0]['h'] and l['h'] > 1.4 * H and not l['eq'] and len(t) > 8
    if title:
        if cur and cur['type'] == 'heading' and cur.get('level') == 1 and l['y0'] - cur['lines'][-1]['y1'] < 0.6 * H: cur['lines'].append(l)
        else: new('heading', l, level=1)
        continue
    if (l['h'] < 0.85 * H and l['page'] == 0 and not in_refs) or inovr('meta', l['page'], l):
        # 小字号的非图表题文字：作者单位、版权说明等，只裁切不翻译
        if cur and cur['type'] == 'meta' and l['page'] == cur['lines'][-1]['page'] and l['y0'] - cur['lines'][-1]['y1'] < H:
            cur['lines'].append(l)
        else: new('meta', l)
        continue
    if REFHEAD.match(t):
        new('heading', l, level=2); flush(); in_refs = True; continue
    if in_refs:
        if POSTREF.match(t): in_refs = False
        else:
            if cur and cur['type'] == 'refs': cur['lines'].append(l)
            else: new('refs', l)
            continue
    if l['eq']:
        if cur and cur['type'] == 'equation' and l['page'] == cur['lines'][-1]['page'] and l['y0'] - cur['lines'][-1]['y1'] < 0.9 * H:
            cur['lines'].append(l)
        else: new('equation', l)
        continue
    gap = (l['y0'] - prev['y1']) if prev and prev['page'] == l['page'] and prev['col'] == l['col'] else None
    short = l['x1'] < l.get('cr', l['x1']) - 25
    caps = re.sub(r'[^A-Za-z]', '', t).isupper()
    nostop = not t.rstrip().endswith(('.', ',', ';', ':'))
    nxt_flush = nxt is not None and nxt['x0'] <= nxt.get('cl', nxt['x0']) + 6 and not nxt['eq']
    lasth = blocks[-1] if (cur is None and blocks and blocks[-1]['type'] == 'heading' and blocks[-1]['lines'][-1] is prev) else None
    # 小标题：前面空出一段（或紧跟在章标题后面）、不以句号结尾、下一行顶格；空出一段时不要求是短行
    headish = len(t) < 80 and nostop and nxt_flush and not t.endswith('-') and '. ' not in t \
        and not (prev is not None and prev['eq']) and (
        (gap is None and short) or (gap is not None and gap > 0.55 * H) or
        (lasth is not None and lasth['level'] == 2 and not caps and short))
    if lasth is not None and lasth['level'] == 3 and not caps and len(t) < 60 and nostop and gap is not None and gap < 0.3 * H and nxt_flush \
            and len(lasth['lines']) < 2 and abs(l['h'] - lasth['lines'][0]['h']) < 0.15 and l['h'] < H - 0.15:
        lasth['lines'].append(l); continue                    # 两行的小标题
    if inovr('heading', l['page'], l) or (headish and not inovr('para', l['page'], l)):
        new('heading', l, level=2 if caps else 3); flush(); continue
    start = False
    if cur is None or cur['type'] != 'para': start = True
    elif l['x0'] > l.get('cl', l['x0']) + 7 and l['col'] != 'S': start = True                   # 首行缩进
    elif gap is not None and gap > 0.8 * H: start = True
    elif cur['lines'][-1]['col'] != l['col'] or cur['lines'][-1]['page'] != l['page']:
        last = cur['lines'][-1]                     # 换栏、换页：上一栏最后一行写满才算同一段
        if last['x1'] < last.get('cr', last['x1']) - 20 and last['t'].rstrip().endswith(('.', ':', '?')): start = True
    elif cur['lines'][-1]['col'] == 'S' and l['col'] == 'S' and gap is not None and gap > 0.5 * H: start = True
    if inovr('split', l['page'], l): start = True
    if inovr('join', l['page'], l): start = False
    if start: new('para', l)
    else: cur['lines'].append(l)
flush()

# 没有式号、却主要由英文单词组成的“公式”，其实是缩进排版的普通文字（版权说明、期刊信息页等）
for b in blocks:
    if b['type'] == 'equation':
        t = ' '.join(l['t'] for l in b['lines'])
        if not any(EQNO.search(l['t']) for l in b['lines']) and len(re.findall(r'[A-Za-z]{4,}', t)) >= 3:
            b['type'] = 'meta' if b['lines'][0]['page'] == 0 else 'para'

# ---------- 文字与裁切框 ----------
def join_text(ls):
    out = ''
    for l in ls:
        t = l['t'].strip()
        if out.endswith('-') and t[:1].islower() and not out.endswith(' -'): out = out[:-1] + t
        else: out = (out + ' ' + t) if out else t
    return re.sub(r'\s+', ' ', out)
def boxes(ls, pad=1.5, tight=False):
    """同一页、同一栏、上下相连的行合成一个裁切框；宽度取该栏左右边界（tight 时取文字本身的左右范围）"""
    out = []
    full = (COLX['L'][0], COLX['R'][1]) if COLX.get('L') and COLX.get('R') else None
    for l in ls:
        x0, x1 = (l['x0'], l['x1']) if tight else (l.get('cl', l['x0']), l.get('cr', l['x1']))
        if l.get('front') and full: x0, x1 = full
        col = 'F' if l.get('front') else l['col']
        if out and out[-1][0] == l['page'] and out[-1][5] == col and l['y0'] - out[-1][4] < 1.2 * H \
                and (tight or (abs(out[-1][1] - x0) < 8 and abs(out[-1][3] - x1) < 8)):   # 栏宽变了（绕图）就另起一个框
            b = out[-1]; b[1] = min(b[1], x0); b[3] = max(b[3], x1); b[4] = l['y1']
        else: out.append([l['page'], x0, l['y0'], x1, l['y1'], col])
    return [[b[0], round(b[1] - pad, 1), round(b[2] - pad, 1), round(b[3] + pad, 1), round(b[4] + pad, 1)] for b in out]

items = []                                   # (阅读顺序位置, 块)
pos = {id(l): k for k, l in enumerate(order)}
for b in blocks:
    ls = b['lines']; blk = {'type': b['type']}
    if b['type'] == 'heading': blk.update(level=b['level'], en=join_text(ls))
    elif b['type'] in ('para', 'meta'): blk.update(src=join_text(ls), list=False)
    elif b['type'] == 'equation':
        nos = [m.group(1) for l in ls for m in [EQNO.search(l['t'])] if m]
        blk.update(nos=nos, src=join_text(ls))
    elif b['type'] == 'refs': blk.update(src=join_text(ls))
    blk['pdf'] = boxes(ls, tight=b['type'] == 'meta') if b['type'] != 'equation' else \
        [[ls[0]['page'], round(min(l.get('cl', l['x0']) for l in ls) - 1.5, 1), round(min(l['y0'] for l in ls) - 2, 1),
          round(max(l.get('cr', l['x1']) for l in ls) + 1.5, 1), round(max(l['y1'] for l in ls) + 2, 1)]]
    items.append((pos[id(ls[0])], blk, ls))

# 图表插入阅读顺序：插在它所在栏、它上沿之上最后一行所属的那一段之后
for f in FIGS:
    pi = f['page']; cx = pages[pi]['w'] / 2
    col = 'L' if f['box'][0] < cx - 20 else 'R'
    if f['box'][0] < cx - 20 and f['box'][2] > cx + 20: col = 'L'
    stream = [l for l in order if l['page'] == pi and (l['col'] == col or l['col'] == 'S')]
    above = [l for l in stream if l['y1'] <= f['box'][1] + 2]
    if above: p = pos[id(above[-1])]
    else:
        below = [l for l in stream if l['y0'] >= f['box'][3] - 2]
        p = (pos[id(below[0])] - 0.5) if below else max(pos[id(l)] for l in order if l['page'] <= pi)
    # 找到包含 p 这一行的块，插到这个块之后
    host = None
    for k, blk, ls in items:
        if blk['type'] not in ('figure', 'table') and any(pos.get(id(l)) == p for l in ls): host = (k, ls)
    k = max(pos[id(l)] for l in host[1]) + 0.25 if host else p + 0.25
    x0, y0, x1, y1 = f['box']
    items.append((k, {'type': 'figure' if not f['label'].lower().startswith('tab') else 'table',
                      'src': join_text(f['cap']), 'subcaps': [], 'panels': [],
                      'pdf': [[pi, round(x0 - 2, 1), round(y0, 1), round(x1 + 2, 1), round(y1 + 2, 1)]],
                      'gfx': [pi, round(x0 - 2, 1), round(y0, 1), round(x1 + 2, 1), round(f['gbox'][3], 1)]}, f['cap']))
items.sort(key=lambda it: it[0])

out, anchors = [], {}
for n, (_, blk, ls) in enumerate(items, 1):
    blk['id'] = f'B{n}'; out.append(blk)
    p0 = blk['pdf'][0]
    anchors[blk['id']] = {'page': p0[0], 'band': 0, 'col': 'F', 'y': p0[2] + 1.5}
json.dump({'blocks': out, 'math': {}, 'pdfmode': True}, open(f'{name}.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump({'anchors': anchors, 'fails': [], 'absent': []}, open(f'{name}_anchors.json', 'w'), indent=1)
TAG = {'para': 'P', 'figure': '图题', 'table': '表题'}
with open(f'{name}_src.txt', 'w', encoding='utf-8') as f:
    for b in out:
        if b['type'] == 'heading': f.write(f"{b['id']} [H{b['level']}] {b['en']}\n")
        elif b['type'] == 'equation':
            lab = (f"式 ({b['nos'][0]})" if len(b['nos']) == 1 else f"式 ({b['nos'][0]})–({b['nos'][-1]})") if b['nos'] else '公式'
            f.write(f"{b['id']} [{lab}] {b['src']}\n")
        elif b['type'] in TAG: f.write(f"{b['id']} [{TAG[b['type']]}] {b['src']}\n")
c = Counter(b['type'] for b in out)
print(f'{name}.json: {dict(c)}；行间公式的文字是 PDF 抽出来的，可能残缺，写解释时对照原版 PDF')
