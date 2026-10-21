"""打印版：按段落切分原文、段首对齐译文，附表格译文、概念注释、整页讲解和文末解读
用法: python3 render.py <name> <name>orig.pdf <name>_print.tex
需要: <name>.json <name>_layout.json <name>_lines.json <name>_anchors.json <name>_zh.txt
可选: <name>_tables.json + <name>_tables_zh.txt（表格译文）、<name>_notes.txt（注释与整页讲解）、
      <name>_interp.tex（文末解读，原样接在参考文献之后）"""
import json, re, sys, html, os
name, origpdf, outtex = sys.argv[1], sys.argv[2], sys.argv[3]
D = json.load(open(f'{name}.json')); LAY = json.load(open(f'{name}_layout.json'))
AJ = json.load(open(f'{name}_anchors.json')); A = AJ['anchors']
ABSENT = set(AJ.get('absent', []))   # 只在 HTML 里、不在这份 PDF 里的附录块
pages = LAY['pages']; B = {b['id']: b for b in D['blocks']}
ZH = {}
for line in open(f'{name}_zh.txt', encoding='utf-8'):
    if '|||' in line: k, v = line.rstrip('\n').split('|||', 1); ZH[k] = v
ALT = {k: html.unescape(re.search(r'alttext="([^"]*)"', v).group(1)) for k, v in D['math'].items()}

# ---------- 注释文件：@Bxx 下每行“术语 | 解释”；@FULL Bxx 标题 ... @END 为整页讲解(原样 LaTeX) ----------
NOTES, FULL = {}, {}
nf = f'{name}_notes.txt'
if os.path.exists(nf):
    cur, full = None, None
    for raw in open(nf, encoding='utf-8'):
        line = raw.rstrip('\n')
        if full is not None:
            if line.strip() == '@END': FULL.setdefault(full[0], []).append((full[1], '\n'.join(full[2]))); full = None
            else: full[2].append(line)
            continue
        if line.startswith('@FULL '):
            _, bid, title = line.split(' ', 2); full = (bid, title, []); continue
        if line.startswith('@'): cur = line[1:].strip(); continue
        if cur and '|' in line:
            term, text = line.split('|', 1); NOTES.setdefault(cur, []).append((term.strip(), text.strip()))

# ---------- 译文 → LaTeX（沿用上一版的转换规则） ----------
def esc(s):
    rep = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
           '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
           # 宋体缺这几个字形，会印成方框
           '✓': r'$\checkmark$', '✔': r'$\checkmark$', '✗': r'$\times$', '✘': r'$\times$', '°': r'$^\circ$'}
    rep.update({chr(0x2460 + k): '（%d）' % (k + 1) for k in range(20)})      # ①–⑳
    return ''.join(rep.get(c, c) for c in s)
def fullwidth(s):
    if '://' in s: return s
    def par(m):
        prev = s[m.start()-1] if m.start() > 0 else ' '
        keep = re.fullmatch(r'[0-9A-Za-z]{1,3}', m.group(1)) and not ('一' <= prev <= '鿿')
        return m.group(0) if keep else '（' + m.group(1) + '）'
    s = re.sub(r'\(([^()]*)\)', par, s)
    out = []; depth = 0
    for i, ch in enumerate(s):
        if ch == '[': depth += 1
        elif ch == ']': depth = max(0, depth - 1)
        if ch in ',:;' and depth == 0:
            prv = s[i-1] if i > 0 else ''; nxt = s[i+1] if i + 1 < len(s) else ''
            if not (prv.isdigit() and nxt.isdigit()): ch = {',': '，', ':': '：', ';': '；'}[ch]
        out.append(ch)
    return ''.join(out)
def zh2tex(s):
    out, n = [], 0
    for ch in s:
        if ch == '"': out.append('“' if n % 2 == 0 else '”'); n += 1
        else: out.append(ch)
    s = fullwidth(''.join(out))
    res = []
    for p in re.split(r'(⟦M\d+⟧|\*\*.+?\*\*|\^\d+\^|【译注[^】]*】)', s):
        if not p: continue
        if p.startswith('⟦M'): res.append('$' + ALT[p[1:-1]] + '$')
        elif p.startswith('**'): res.append(r'\textbf{' + zh2tex(p[2:-2]) + '}')
        elif re.fullmatch(r'\^\d+\^', p): res.append(r'\textsuperscript{' + p[1:-1] + '}')
        elif p.startswith('【译注'): res.append(r'{\itshape\color{black!70}' + esc(p) + '}')
        else: res.append(esc(p))
    return ''.join(res)
def eq2tex(b):
    lines = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', b['html'], re.S):
        alts = [html.unescape(a) for a in re.findall(r'alttext="([^"]*)"', r)]
        if not alts: continue
        no = re.search(r'ltx_eqn_eqno[^>]*>.*?\((\d+[a-z]?)\)', r, re.S)
        body = ' '.join(a.replace(r'\displaystyle', '') for a in alts)
        lines.append(body + (r' \tag*{(' + no.group(1) + ')}' if no else r' \notag'))
    return (r'{\small\begin{gather*}' + r' \\ '.join(lines) + r'\end{gather*}}') if lines else ''
def block2tex(bid):
    b = B[bid]; t = b['type']
    if t == 'heading':
        if b['level'] == 1: return r'{\centering\fontsize{14}{18}\selectfont\bfseries ' + zh2tex(ZH[bid]) + r'\par}'
        size = {2: r'\large', 3: r'\normalsize'}.get(b['level'], r'\normalsize')
        return r'{' + size + r'\bfseries ' + zh2tex(ZH.get(bid, b['en'])) + r'\par}\vspace{2pt}'
    if t == 'para':
        return (r'\textbullet\ ' if b.get('list') else '') + zh2tex(ZH[bid]) + r'\par\vspace{2pt}'
    if t == 'footnote':
        return r'{\footnotesize\textsuperscript{' + str(b['num']) + '}' + zh2tex(ZH[bid]) + r'\par}'
    if t == 'equation': return eq2tex(b)
    if t in ('figure', 'table'):
        main = [zh2tex(ZH[bid])] if ZH.get(bid) else []
        subs = [zh2tex(ZH[f'{bid}.s{i}']) for i in range(len(b.get('panels', []))) if f'{bid}.s{i}' in ZH]
        grids = TABLES.get(bid, []) if t == 'table' else []
        cap = lambda cs: (r'{\small\color{black!85}' + r'\\'.join(cs) + r'\par}\vspace{3pt}') if cs else ''
        if grids and len(subs) == len(grids) > 1:      # 并排的几张子表：每张子表题后面紧跟它的中文表
            return cap(main) + ''.join(cap([s]) + table2tex(g) for s, g in zip(subs, grids))
        return cap(main + subs) + ''.join(table2tex(g) for g in grids)
    return ''
# ---------- 表格译文：按 tables.py 抽出的网格重建一张中文表 ----------
TABLES = json.load(open(f'{name}_tables.json', encoding='utf-8')) if os.path.exists(f'{name}_tables.json') else {}
TZH = {}
if os.path.exists(f'{name}_tables_zh.txt'):
    for line in open(f'{name}_tables_zh.txt', encoding='utf-8'):
        if '|||' in line:
            k, v = line.rstrip('\n').split('|||', 1)
            if v.strip(): TZH[k.strip()] = v.strip()
SYM = {'✓': r'$\checkmark$', '✔': r'$\checkmark$', '✗': r'$\times$', '✘': r'$\times$'}
def cell2tex(c):
    s = remap_cites(TZH.get(c['t'], c['t']))
    parts = re.split(r'(\$[^$]*\$)', s)
    s = ''.join(p if p.startswith('$') else ''.join(SYM.get(ch, esc(ch)) for ch in p) for p in parts)
    if c['b'] and s: s = r'\textbf{' + s + '}'
    if c['u'] and s: s = r'\underline{' + s + '}'
    return s
def table2tex(g):
    if not g: return ''
    nc = max(sum(c['cs'] for c in row) for row in g)
    occ, lines, spans = set(), [], []      # spans[r] = [(列起, 列止, 上边线, 下边线)]
    for r, row in enumerate(g):
        out, col, it, sp = [], 0, iter(row), []
        while col < nc:
            if (r, col) in occ: out.append(''); col += 1; continue
            c = next(it, None)
            if c is None: out.append(''); col += 1; continue
            s = cell2tex(c)
            if c['rs'] > 1:
                s = r'\multirow{%d}{*}{%s}' % (c['rs'], s)
                for k in range(1, c['rs']):
                    for j in range(c['cs']): occ.add((r + k, col + j))
            if c['cs'] > 1: s = r'\multicolumn{%d}{c}{%s}' % (c['cs'], s)
            out.append(s); sp.append((col, col + c['cs'] - 1, c['top'], c['bot'])); col += c['cs']
        lines.append(' & '.join(out) + r' \\'); spans.append(sp)
    body = []
    for r, ln in enumerate(lines):
        if r > 0:
            cols = set()
            for a, z, top, _ in spans[r]:
                if top: cols.update(range(a, z + 1))
            for a, z, _, bot in spans[r - 1]:
                if bot: cols.update(range(a, z + 1))
            if len(cols) >= nc - 1 and cols: body.append(r'\midrule')
            elif cols:                      # 只有部分列有横线：用 \cmidrule 画在对应的列上
                cs = sorted(cols); run = [cs[0]]
                for x in cs[1:] + [None]:
                    if x is not None and x == run[-1] + 1: run.append(x); continue
                    body.append(r'\cmidrule(lr){%d-%d}' % (run[0] + 1, run[-1] + 1))
                    if x is not None: run = [x]
        body.append(ln)
    spec = 'l' + 'c' * (nc - 1)
    return (r'\zhtable{\begin{tabular}{' + spec + r'}\toprule' + '\n' + '\n'.join(body) +
            '\n' + r'\bottomrule\end{tabular}}')

def notes_for(ids):
    items = [NOTES[i] for i in ids if i in NOTES]
    if not items: return ''
    body = ''.join(r'\concept{' + t + '}{' + x + '}' for it in items for (t, x) in it)
    return r'\notebox{' + body + '}'
def fullpages_for(ids):
    return ''.join(r'\begin{figure}[p]\begin{fullnote}{' + t + '}' + c + r'\end{fullnote}\end{figure}'
                   for i in ids if i in FULL for (t, c) in FULL[i])

# ---------- 检查译文是否齐全 ----------
need = []
for b in D['blocks']:
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): continue
    if b['id'] in ABSENT: continue
    if b['type'] in ('para', 'footnote') and b['id'] not in ZH: need.append(b['id'])
    if b['type'] == 'heading' and b['level'] == 1 and b['id'] not in ZH: need.append(b['id'])
    if b['type'] in ('figure', 'table') and b.get('src') and b['id'] not in ZH: need.append(b['id'])
if need:
    sys.exit(f'{name}_zh.txt 缺少这些块的译文：{" ".join(need)}')

# ---------- 分组：锚点 + 其后未锚定的块（行间公式等）归入同组 ----------
order = []
for b in D['blocks']:
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): continue
    if b['type'] in ('bib', 'authors') or b['id'] in ABSENT: continue
    order.append(b['id'])
groups, owner = {}, None       # (page,band,col,y) -> [ids]
for bid in order:
    b = B[bid]
    if b['type'] == 'heading' and b['level'] == 1:
        k = ('T',); groups.setdefault(k, []).append(bid); continue
    if bid in A:
        a = A[bid]; k = (a['page'], a['band'], a['col'], round(a['y']))
        # 同一行上的多个锚点并为一组（如 IEEE 摘要标题与正文同行）
        for g in list(groups):
            if g != ('T',) and g[:3] == k[:3] and abs(g[3] - k[3]) <= 2: k = g; break
        groups.setdefault(k, []).append(bid); owner = k
    elif owner is not None:
        groups[owner].append(bid)

def crop(pi, x0, y0, x1, y1, width):
    H = pages[pi]['h']
    return (r'\includegraphics[page=%d,viewport=%.1f %.1f %.1f %.1f,clip,width=%s]{%s}'
            % (pi + 1, x0 - 3, H - y1, x1 + 3, H - y0, width, origpdf))

# ---------- 参考文献：从 References 标题起，左右两栏原样并排，不再逐栏占半页 ----------
LINES = json.load(open(f'{name}_lines.json'))
REF = None
for pi, pl in enumerate(LINES):
    for ln in pl:
        if re.sub(r'[^a-z0-9]', '', ln['t'].lower()) == 'references':
            REF = (pi, ln['y0'], 'L' if ln['x0'] < pages[pi]['w'] / 2 else 'R'); break
    if REF: break
def gap_cuts(pi, xa, xb, ya, yb, n):
    # 在行与行之间的空隙处把一栏切成 n 段，避免切到字
    ls = sorted((l['y0'], l['y1']) for l in LINES[pi] if xa - 5 <= l['x0'] < xb and l['y0'] >= ya - 1 and l['y1'] <= yb + 1)
    gaps = [(ls[k][1] + ls[k+1][0]) / 2 for k in range(len(ls) - 1) if ls[k+1][0] > ls[k][1]]
    cuts = [ya]
    for k in range(1, n):
        t = ya + (yb - ya) * k / n
        c = min(gaps, key=lambda g: abs(g - t)) if gaps else t
        if c > cuts[-1] + 5: cuts.append(c)
    return cuts + [yb]
REFSTRIPS = []
def refstrips(pi, xa, xb, ya, yb):
    # 参考文献按原文阅读顺序（左栏→右栏→下一页）切成小条，最后用 multicol 重新排成两栏
    if xb - xa < 100 or not any(xa - 5 <= l['x0'] < xb and ya - 1 <= l['y0'] and l['y1'] <= yb + 1 for l in LINES[pi]):
        return                                   # 空栏（如最后一页只有左栏有文献）不输出
    n = max(1, round((yb - ya) / 110))
    c = gap_cuts(pi, xa, xb, ya, yb, n)
    REFSTRIPS.extend(crop(pi, xa, c[k], xb, c[k+1], r'\linewidth') for k in range(len(c) - 1))
# 参考文献之后若还有附录（arXiv 常把补充材料接在参考文献后面），参考文献到附录的第一个锚点为止
REF_END = None
if REF:
    post, seen = [], False
    for b in D['blocks']:
        if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): seen = True; continue
        if seen and b['type'] != 'bib' and b['id'] in A: post.append(A[b['id']])
    if post:
        a0 = min(post, key=lambda a: (a['page'], a['y']))
        refs_above = any(l['y0'] < a0['y'] - 2 and re.match(r'^\[\d+\]', l['t']) for l in LINES[a0['page']])
        # 附录另起一页（最常见）：参考文献在该页页首结束；与参考文献同页接排：在附录第一行处结束
        REF_END = (a0['page'], a0['y'] - 2) if (a0['page'] == REF[0] or refs_above) else (a0['page'], 0)
def in_refs(pi, y):
    return REF is not None and (pi, y) >= (REF[0], REF[1] - 1) and (REF_END is None or (pi, y) < REF_END)
# HTML 版与 PDF 版的参考文献编号可能不同（排序或条目略有差异）。按标题把两份参考文献表对上，
# 译文、表格里的引用编号一律改成 PDF 上印的编号，保证左右两栏一致
def build_citemap():
    if not REF: return {}
    rows = []
    for pi in range(REF[0], len(LINES)):
        for l in LINES[pi]:
            if (pi, l['y0']) < (REF[0], REF[1] - 1) or (REF_END and (pi, l['y0']) >= REF_END): continue
            rows.append((pi, l['x0'] >= pages[pi]['w'] / 2, l['y0'], l['t'], l['x0']))
    # 同一行里编号“[3]”与正文的 y 可能差零点几，先按行聚类（高差 < 2pt 视为同一行），行内再按 x 排
    rows.sort(key=lambda r: (r[0], r[1], r[2]))
    ordered, line = [], []
    for r in rows:
        if line and (r[0], r[1]) == (line[0][0], line[0][1]) and abs(r[2] - line[0][2]) < 2: line.append(r); continue
        ordered += sorted(line, key=lambda q: q[4]); line = [r]
    ordered += sorted(line, key=lambda q: q[4])
    parts = re.split(r'\[(\d+)\]', ' '.join(r[3] for r in ordered))
    pdf = {int(parts[i]): re.sub(r'[^a-z0-9]', '', parts[i + 1].lower()) for i in range(1, len(parts) - 1, 2)}
    cmap = {}
    for b in D['blocks']:
        if b['type'] != 'bib': continue
        t = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', b['en_html']))).strip()
        m = re.match(r'\[(\d+)\]\s*(.*)', t)
        if not m: continue
        title = re.split(r'\(\d{4}[a-z]?\)\s*', m.group(2), maxsplit=1)[-1]      # 作者-年份格式：年份后面是标题
        nt = re.sub(r'[^a-z0-9]', '', title.lower())
        for key in (nt[:28], nt[8:36]):        # 标题开头是公式时（如 π³），两边写法不同，改用标题中段匹配
            hits = [n for n, e in pdf.items() if len(key) >= 12 and key in e]
            if len(hits) == 1: cmap[int(m.group(1))] = hits[0]; break
    nbib = sum(1 for b in D['blocks'] if b['type'] == 'bib')
    if nbib and len(cmap) < 0.5 * nbib:      # 对上的条目太少，说明解析不可靠，宁可不改
        print(f'参考文献只对上 {len(cmap)}/{nbib} 条，不改写引用编号'); return {}
    return {h: p for h, p in cmap.items() if h != p}
CITEMAP = build_citemap()
def remap_cites(s):
    if not CITEMAP: return s
    def fix(m):
        return '[' + re.sub(r'\d+', lambda d: str(CITEMAP.get(int(d.group(0)), d.group(0))), m.group(1)) + ']'
    return re.sub(r'\[([\d,\s–-]+)\]', fix, s)
ZH = {k: remap_cites(v) for k, v in ZH.items()}
if CITEMAP: print('引用编号按 PDF 改写:', ', '.join(f'[{h}]→[{p}]' for h, p in sorted(CITEMAP.items())))
def flush_refs():
    if REFSTRIPS:
        flush_carry()
        body.append(r'\par\vspace{6pt}\begin{multicols}{2}\raggedcolumns' + '\n'
                    + '\n'.join('\\noindent' + x + r'\par' for x in REFSTRIPS) + '\n' + r'\end{multicols}')
        REFSTRIPS.clear()

body = []
title_ids = groups.get(('T',), [])
CARRY = {'notes': '', 'full': ''}   # 跨栏/跨页段落的注释与整页讲解，等这一段在下一栏排完再放
def flush_carry():
    if CARRY['notes']: body.append(r'\par\noindent\begin{minipage}{\textwidth}' + CARRY['notes'] + r'\end{minipage}\par\vspace{6pt}')
    if CARRY['full']: body.append(CARRY['full'])
    CARRY['notes'] = CARRY['full'] = ''
def take_carry():
    n, f = CARRY['notes'], CARRY['full']; CARRY['notes'] = CARRY['full'] = ''; return n, f
SINGLE = LAY.get('single', False)
XLMED = sorted(p['xL'][0] for p in pages)[len(pages) // 2]; XRMED = sorted(p['xR'][1] for p in pages)[len(pages) // 2]   # 单栏论文不按原版页面逐带裁切，改走下面的 flow()
for pi, p in ([] if SINGLE else enumerate(pages)):
    cx = p['w'] / 2; xl0, xr1 = p['xL'][0], p['xR'][1]
    # 某页的左右边界比全文中位数宽出 8pt 以上，多半是页边竖排的 arXiv 编号被算了进来，改用中位数
    if xl0 < XLMED - 8: xl0 = XLMED
    if xr1 > XRMED + 8: xr1 = XRMED
    for bi, bd in enumerate(p['bands']):
        y0b, y1b = bd['y0'], bd['y1']
        if REFSTRIPS and not in_refs(pi, y0b): flush_refs()     # 参考文献结束，接着排附录
        if REF and in_refs(pi, y0b) and not bd['full']:
            refstrips(pi, xl0, cx - 1, y0b - 2, y1b + 2); refstrips(pi, cx + 1, xr1, y0b - 2, y1b + 2); continue
        if REF and pi == REF[0] and y0b < REF[1] < y1b and not bd['full']:
            flush_carry(); ry = REF[1] - 2
            if REF[2] == 'L':      # 参考文献从左栏中部开始：上半段正常对照，下半段与整条右栏并排
                gsL = sorted([(g[3], v) for g, v in groups.items() if g != ('T',) and g[:3] == (pi, bi, 'L')])
                if gsL and gsL[0][0] - y0b > 8:
                    body.append(r'\bilrow{' + crop(pi, xl0, y0b - 2, cx - 1, gsL[0][0] - 1.5, r'\colw') + '}{}{}')
                for j, (y, ids) in enumerate(gsL):
                    yend = (gsL[j+1][0] - 1.5) if j + 1 < len(gsL) else ry
                    body.append(r'\bilrow{' + crop(pi, xl0, y - 1.5, cx - 1, yend, r'\colw') + '}{'
                                + '\n'.join(block2tex(i) for i in ids) + '}{' + notes_for(ids) + '}')
                    body.append(fullpages_for(ids))
                refstrips(pi, xl0, cx - 1, ry, y1b + 2); refstrips(pi, cx + 1, xr1, y0b - 2, y1b + 2)
                continue
        if bd['full'] and in_refs(pi, y0b):
            if y1b - y0b >= 20: flush_refs(); flush_carry(); body.append(r'\origonly{' + crop(pi, xl0, y0b - 2, xr1, y1b + 2, r'\textwidth') + '}')
            continue
        if bd['full']:
            ids = [i for g, v in groups.items() if g != ('T',) and g[:3] == (pi, bi, 'F') for i in v]
            if pi == 0 and bi == 0: ids = title_ids + ids
            if not ids and y1b - y0b < 20: continue
            flush_carry()
            zh = '\n'.join(block2tex(i) for i in ids)
            body.append(r'\fullband{' + crop(pi, xl0, y0b - 2, xr1, y1b + 2, r'\textwidth') + '}{' + zh + '}{' + notes_for(ids) + '}')
            body.append(fullpages_for(ids)); continue
        colgroups = {c: sorted([(g[3], v) for g, v in groups.items() if g != ('T',) and g[:3] == (pi, bi, c)]) for c in 'LR'}
        if not colgroups['L'] and not colgroups['R']:
            flush_carry(); body.append(r'\origonly{' + crop(pi, xl0, y0b - 2, xr1, y1b + 2, r'\textwidth') + '}'); continue
        for c in 'LR':
            xa, xb = (xl0, cx - 1) if c == 'L' else (cx + 1, xr1)
            gs = colgroups[c]
            cuts = [y for y, _ in gs]
            if not gs:
                n, f = take_carry()
                body.append(r'\bilrow{' + crop(pi, xa, y0b - 2, xb, y1b + 2, r'\colw') + '}{}{' + n + '}'); body.append(f); continue
            if cuts[0] - y0b > 8:                        # 栏顶：上一栏延续下来的文字或图，右侧留空，上一段的注释放在这里
                n, f = take_carry()
                body.append(r'\bilrow{' + crop(pi, xa, y0b - 2, xb, cuts[0] - 1.5, r'\colw') + '}{}{' + n + '}'); body.append(f)
            flush_carry()
            for j, (y, ids) in enumerate(gs):
                yend = (gs[j+1][0] - 1.5) if j + 1 < len(gs) else y1b + 2
                if REF and (pi, c) == (REF[0], REF[2]) and y < REF[1] < yend + 1: yend = REF[1] - 2
                zh = '\n'.join(block2tex(i) for i in ids)
                if j + 1 == len(gs) and yend > y1b:      # 一栏的最后一段，可能延续到下一栏：注释暂存
                    body.append(r'\bilrow{' + crop(pi, xa, y - 1.5, xb, yend, r'\colw') + '}{' + zh + '}{}')
                    CARRY['notes'], CARRY['full'] = notes_for(ids), fullpages_for(ids)
                else:
                    body.append(r'\bilrow{' + crop(pi, xa, y - 1.5, xb, yend, r'\colw') + '}{' + zh + '}{' + notes_for(ids) + '}')
                    body.append(fullpages_for(ids))
            if REF and (pi, c) == (REF[0], 'R') and REF[2] == 'R' and y0b < REF[1] < y1b:
                refstrips(pi, xa, xb, REF[1] - 2, y1b + 2)

# ---------- 单栏论文：按阅读顺序重排 ----------
# 原版的页面边界不再保留。每一段原文的所有行（包括翻页后的续行、段中的行间公式）先连续排完，
# 再接整段译文和注释，原文不会被译文从中间断开。图表的图形部分归到它的图表题，和图表题裁成一整块，
# 位置按阅读顺序不变；只有图表把一段原文从中间隔开时，才挪到这一段（含译文）之后。
def flow():
    import unicodedata
    from collections import Counter
    def nrm(s): return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKC', s).lower())
    # 正文栏左右边界：长行起止位置的中位数；裁切时两边各放宽 12pt，页边竖排的 arXiv 编号落在范围外
    longl = [l for pl in LINES for l in pl if len(l['t']) > 60]
    XL = sorted(l['x0'] for l in longl)[len(longl) // 2]; XR = sorted(l['x1'] for l in longl)[len(longl) // 2]
    xa, xb = XL - 12, XR + 12
    # 页眉页脚：页面上下 9% 以内、在三成以上页面重复出现的文字（数字不计），或纯页码
    def fkey(t): return re.sub(r'\d+', '#', t.strip().lower())
    def edge(pi, l): return l['y1'] < 0.09 * pages[pi]['h'] or l['y0'] > 0.91 * pages[pi]['h']
    cnt = Counter(k for pi, pl in enumerate(LINES) for k in {fkey(l['t']) for l in pl if edge(pi, l)})
    def furniture(pi, l):
        return edge(pi, l) and (cnt[fkey(l['t'])] >= max(2, 0.3 * len(LINES)) or re.fullmatch(r'[#\s–-]*', fkey(l['t'])))
    def inkmask(pi):
        w = pages[pi]['w']; return sum(1 << k for k in range(int(xa * 32 / w), min(31, int(xb * 32 / w)) + 1))
    MASK = [inkmask(pi) for pi in range(len(pages))]
    def inky(pi, y):
        ink = pages[pi].get('ink', []); y = int(y)
        return 0 <= y < len(ink) and ink[y] & MASK[pi]
    TOP, BOT, PL = [], [], []
    for pi, pl in enumerate(LINES):
        h = pages[pi]['h']; fu = [l for l in pl if furniture(pi, l)]
        t = int(max([l['y1'] for l in fu if l['y1'] < h / 2] + [0])); b = int(min([l['y0'] for l in fu if l['y0'] > h / 2] + [h]))
        if t: t = max([y for y in range(t, t + 7) if inky(pi, y)] + [t])   # 页眉下方 6pt 内的墨迹（字形下沿、页眉线）一并去掉
        if b < h: b = min([y for y in range(b - 6, b + 1) if inky(pi, y)] + [b])
        TOP.append(t + 1); BOT.append(b - 1)
        PL.append(sorted([l for l in pl if not furniture(pi, l) and xa <= (l['x0'] + l['x1']) / 2 <= xb
                          and l['y0'] >= TOP[pi] - 1 and l['y1'] <= BOT[pi] + 1], key=lambda l: l['y0']))

    # 分组：锚点按 (页, y) 排序；标题组从首页顶端开始；参考文献单独成组，组内不做文字匹配
    gl = sorted([[g[0], g[3], v] for g, v in groups.items() if g != ('T',)], key=lambda x: (x[0], x[1]))
    if title_ids: gl.insert(0, [0, -1, title_ids])
    if REF: gl.append([REF[0], REF[1] - 0.5, ['REF']]); gl.sort(key=lambda x: (x[0], x[1]))
    def kind(g):
        ids = gl[g][2]
        if ids == ['REF']: return 'ref'
        ts = {B[i]['type'] for i in ids}            # 段首的行内小标题与正文同组，按正文处理
        return 'fig' if 'figure' in ts else 'tab' if 'table' in ts else 'head' if ts <= {'heading'} else 'text'
    def gtext(ids):
        parts = []
        for i in ids:
            if i == 'REF': continue
            b = B[i]; parts += [b.get('src') or '', b.get('en') or '']
            parts += [sc.get('src', '') for sc in b.get('subcaps', [])]
        return nrm(re.sub(r'⟦M\d+⟧', ' ', ' '.join(parts)).replace('**', ''))
    GT = [gtext(g[2]) for g in gl]
    def match(n, T):
        # 一行里六成以上的 8 字符片段出现在这一组的原文里，才算这一组的文字；只靠几个词撞上的图中标签不算
        if len(n) < 16: return len(n) >= 3 and n in T
        ks = range(0, len(n) - 7, 4)
        return sum(n[k:k + 8] in T for k in ks) >= 0.6 * len(ks)

    # 1. 文字行归属：先归当前锚点所在的组；当前组是图表题时，正文续行归回图表之前的那一段
    def ingroup(pi, y):            # (页, y) 落在哪一组
        k = 0
        for j, g in enumerate(gl):
            if (g[0], g[1]) <= (pi, y + 1.5): k = j
        return k
    OWN = []                       # 每页 [(y0, y1, 组号)]
    last = {}                      # 组号 -> (页, 最后一行 y1, 最后一行 x0)
    for pi, pl in enumerate(PL):
        own = []
        for li, l in enumerate(pl):
            g = ingroup(pi, l['y0']); n = nrm(l['t'])
            if kind(g) == 'ref':
                own.append((l['y0'], l['y1'], g)); continue
            anchor = gl[g][0] == pi and abs(gl[g][1] - l['y0']) < 1.5
            wide = l['x1'] - l['x0'] >= 0.5 * (XR - XL)
            # 紧挨着上一行；窄行（段末短行）还要与上一行左端对齐，图中贴着正文的短标签不算
            def near(j): return (last.get(j, (-1, 0))[0] == pi and l['y0'] - last[j][1] < 4
                                 and (wide or abs(l['x0'] - last[j][2]) < 3))
            cands = [g]
            if kind(g) in ('fig', 'tab'):
                p = g
                while p > 0 and kind(p) in ('fig', 'tab'): p -= 1
                if kind(p) not in ('fig', 'tab', 'ref'):
                    cands = [g, p] if near(g) else [p, g]
            # 标题类只认紧挨着的行，免得图里的短标签（常与标题同词）被误认成标题
            pick = g if anchor else next((j for j in cands if match(n, GT[j])
                                          and (near(j) or li == 0 or (wide and kind(j) != 'head'))), None)
            if pick is not None:
                own.append((l['y0'], l['y1'], pick)); last[pick] = (pi, l['y1'], l['x0'])
        OWN.append(own)

    # 2. 没归属的墨迹（图形、表格主体、行间公式、图中文字）连成块。图表的图形与图表题之间、图形内部的空隙
    #    一般不超过 12pt：从图表题出发向图形一侧逐块延伸，空隙超过 12pt 就停；剩下的归前一组（行间公式归所在段）。
    #    图表题在图形上方还是下方，按全文多数情况判断（常见是图题在下、表题在上）
    covered = []
    for pi in range(len(pages)):
        c = set()
        for y0, y1, _ in OWN[pi]: c.update(range(int(y0), int(y1) + 2))   # 多算 1pt：字母下沿常伸出文字框
        covered.append(c)
    vote = {'fig': [0, 0], 'tab': [0, 0]}          # [图形在题下方, 图形在题上方]
    for pi, own in enumerate(OWN):
        byg = {}
        for y0, y1, g in own: byg.setdefault(g, []).append((y0, y1))
        for g, ys in byg.items():
            k = kind(g)
            if k not in vote or gl[g][0] != pi: continue
            top, bot = min(y for y, _ in ys), max(y for _, y in ys)
            free = lambda y: inky(pi, y) and y not in covered[pi]
            vote[k][0] += any(free(y) for y in range(int(bot) + 2, int(bot) + 13))
            vote[k][1] += any(free(y) for y in range(int(top) - 12, int(top) - 1))
    BELOW = {k: v[0] > v[1] for k, v in vote.items()}   # True：图形/表体在图表题下方
    GAP = 12
    HBODY = sorted(l['y1'] - l['y0'] for l in longl)[len(longl) // 2]
    EL = []                        # 每页 [(y0, y1, 组号)]
    prev_owner = 0
    for pi in range(len(pages)):
        own = OWN[pi]; top, bot = int(TOP[pi]), int(BOT[pi])
        free, cur = [], None
        for y in range(top, bot + 1):
            if y in covered[pi]: cur = None; continue
            if inky(pi, y):
                if cur and y - cur[1] <= 6: cur[1] = y
                else: cur = [y, y]; free.append(cur)
        items = sorted([(a, b, g) for a, b, g in own] + [(a, b + 1, None) for a, b in free], key=lambda t: t[0])
        out, i = [], 0
        while i < len(items):
            if items[i][2] is not None: out.append(items[i]); i += 1; continue
            j = i
            while j < len(items) and items[j][2] is None: j += 1
            run = [list(t) for t in items[i:j]]
            P = next((t[2] for t in reversed(out) if t[2] is not None), None)
            pend = next((t[1] for t in reversed(out) if t[2] is not None), None)
            N = items[j][2] if j < len(items) else None
            nstart = items[j][0] if j < len(items) else None
            if P is not None and kind(P) in BELOW and BELOW[kind(P)]:      # 图表题在上：表体向下延伸
                edge_ = pend
                for t in run:
                    if t[2] is None and t[0] - edge_ <= GAP: t[2] = P; edge_ = t[1]
                    else: break
            if N is not None and kind(N) in BELOW and not BELOW[kind(N)]:  # 图表题在下：图形向上延伸
                edge_ = nstart
                for t in reversed(run):
                    if t[2] is None and edge_ - t[1] <= GAP: t[2] = N; edge_ = t[0]
                    else: break
            rest = P if P is not None else (prev_owner if N is None or kind(N) not in BELOW else N)
            # 页脚注：页面最底下一串字号比正文小、从左边起排的行（脚注线一并带上），放到所在段的译文之后；
            # 居中的行间公式不算
            def footlike(k):
                ls = [l for l in PL[pi] if l['y0'] >= run[k][0] - 1 and l['y1'] <= run[-1][1] + 1]
                return bool(ls) and all(l['y1'] - l['y0'] < 0.93 * HBODY for l in ls) and min(l['x0'] for l in ls) < XL + 25
            k0 = len(run)
            if N is None and P is not None:
                k0 = next((k for k in range(len(run)) if footlike(k)), len(run))
            out += [(a, b, g if g is not None else (('foot', P) if k >= k0 else rest))
                    for k, (a, b, g) in enumerate(run)]
            i = j
        own_ = [t[2] for t in out if not isinstance(t[2], tuple)]
        if own_: prev_owner = own_[-1]
        EL.append(out)

    # 3. 每组的原文切片：同一页上连续属于同一组的元素合成一块；参考文献之外的块在行间空白处再切成小段，方便分页
    PIECES = {}                    # 组号 -> [[页, y0, y1]]
    for pi, out in enumerate(EL):
        prev = None
        for a, b, g in out:
            if g == prev: PIECES[g][-1][2] = max(PIECES[g][-1][2], b)
            else: PIECES.setdefault(g, []).append([pi, a, b]); prev = g
    W = '%.1fpt' % (xb - xa + 6)
    def slices(pi, a, b, cut):
        a, b = a - 1, b + 1
        if not cut or b - a < 150: return [(a, b)]
        res, s = [], a
        while b - s > 150:
            t = s + 110
            c = next((y for d in range(0, 40) for y in (t + d, t - d) if s + 30 < y < b - 30 and not inky(pi, y)), None)
            if c is None: break
            res.append((s, c + 0.5)); s = c + 0.5
        return res + [(s, b)]
    def slicetex(g):
        out = []
        for pi, a, b in PIECES.get(g, []):
            for s, e in slices(pi, a, b, not isinstance(g, tuple) and kind(g) not in ('fig', 'tab')):
                out.append(r'\flowslice{' + crop(pi, xa, s, xb, e, W) + '}')
        return out

    body.append(r'\begin{flowcol}{%.1fpt}' % ((xb - xa + 6) / 2))
    for g, (pi, y, ids) in enumerate(gl):
        sl = slicetex(g)
        if not sl: continue
        if ids == ['REF']:
            body.append(r'\Needspace{60pt}' + '\n'.join(sl) + r'\vspace{8pt}'); continue
        h = PIECES[g][0][2] - PIECES[g][0][1]
        need = (min(h, 120) + (90 if kind(g) == 'head' else 30))
        # 行间公式已经在原文切片里，译文里不再重排一遍
        zh = '\n'.join(block2tex(i) for i in ids if B[i]['type'] != 'equation')
        body.append(r'\Needspace{%dpt}' % need + '\n'.join(sl) + r'\flowzh{' + zh + '}' + notes_for(ids) + r'\vspace{8pt}')
        foot = slicetex(('foot', g))
        if foot: body.append('\n'.join(foot) + r'\vspace{8pt}')
        body.append(fullpages_for(ids))
    body.append(r'\end{flowcol}')
if SINGLE: flow()

flush_carry(); flush_refs()
interp = open(f'{name}_interp.tex', encoding='utf-8').read() if os.path.exists(f'{name}_interp.tex') else ''
PRE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'preamble.tex')
doc = open(PRE, encoding='utf-8').read() + '\n'.join(body) + '\n' + interp + '\n\\end{document}\n'
open(outtex, 'w', encoding='utf-8').write(doc)
print(f'写出 {outtex}: {len(body)} 个片段, 注释 {sum(len(v) for v in NOTES.values())} 条, 整页讲解 {sum(len(v) for v in FULL.values())} 页')
