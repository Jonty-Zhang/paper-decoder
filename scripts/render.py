"""打印版：按段落切分原文、段首对齐译文，附表格译文、概念注释、整页讲解和文末解读
用法: python3 render.py <name> <name>orig.pdf <name>_print.tex
需要: <name>.json <name>_layout.json <name>_lines.json <name>_anchors.json <name>_zh.txt
可选: <name>_tables.json + <name>_tables_zh.txt（表格译文）、<name>_notes.txt（注释与整页讲解）、
      <name>_interp.tex（文末解读，原样接在参考文献之后）"""
import json, re, sys, html, os
name, origpdf, outtex = sys.argv[1], sys.argv[2], sys.argv[3]
D = json.load(open(f'{name}.json')); LAY = json.load(open(f'{name}_layout.json'))
A = json.load(open(f'{name}_anchors.json'))['anchors']
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
           '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
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
    s = TZH.get(c['t'], c['t'])
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
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): break
    if b['type'] in ('para', 'footnote') and b['id'] not in ZH: need.append(b['id'])
    if b['type'] == 'heading' and b['level'] == 1 and b['id'] not in ZH: need.append(b['id'])
    if b['type'] in ('figure', 'table') and b.get('src') and b['id'] not in ZH: need.append(b['id'])
if need:
    sys.exit(f'{name}_zh.txt 缺少这些块的译文：{" ".join(need)}')

# ---------- 分组：锚点 + 其后未锚定的块（行间公式等）归入同组 ----------
order = []
for b in D['blocks']:
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): break
    if b['type'] in ('bib', 'authors'): continue
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
def in_refs(pi, y):
    return REF is not None and (pi, y) >= (REF[0], REF[1] - 1)

body = []
title_ids = groups.get(('T',), [])
for pi, p in enumerate(pages):
    cx = p['w'] / 2; xl0, xr1 = p['xL'][0], p['xR'][1]
    for bi, bd in enumerate(p['bands']):
        y0b, y1b = bd['y0'], bd['y1']
        if REF and in_refs(pi, y0b) and not bd['full']:
            refstrips(pi, xl0, cx - 1, y0b - 2, y1b + 2); refstrips(pi, cx + 1, xr1, y0b - 2, y1b + 2); continue
        if REF and pi == REF[0] and y0b < REF[1] < y1b and not bd['full']:
            ry = REF[1] - 2
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
            if y1b - y0b >= 20: body.append(r'\origonly{' + crop(pi, xl0, y0b - 2, xr1, y1b + 2, r'\textwidth') + '}')
            continue
        if bd['full']:
            ids = [i for g, v in groups.items() if g != ('T',) and g[:3] == (pi, bi, 'F') for i in v]
            if pi == 0 and bi == 0: ids = title_ids + ids
            if not ids and y1b - y0b < 20: continue
            zh = '\n'.join(block2tex(i) for i in ids)
            body.append(r'\fullband{' + crop(pi, xl0, y0b - 2, xr1, y1b + 2, r'\textwidth') + '}{' + zh + '}{' + notes_for(ids) + '}')
            body.append(fullpages_for(ids)); continue
        colgroups = {c: sorted([(g[3], v) for g, v in groups.items() if g != ('T',) and g[:3] == (pi, bi, c)]) for c in 'LR'}
        if not colgroups['L'] and not colgroups['R']:
            body.append(r'\origonly{' + crop(pi, xl0, y0b - 2, xr1, y1b + 2, r'\textwidth') + '}'); continue
        for c in 'LR':
            xa, xb = (xl0, cx - 1) if c == 'L' else (cx + 1, xr1)
            gs = colgroups[c]
            cuts = [y for y, _ in gs]
            if not gs:
                body.append(r'\bilrow{' + crop(pi, xa, y0b - 2, xb, y1b + 2, r'\colw') + '}{}{}'); continue
            if cuts[0] - y0b > 8:                        # 栏顶：上一栏延续下来的文字或图，右侧留空
                body.append(r'\bilrow{' + crop(pi, xa, y0b - 2, xb, cuts[0] - 1.5, r'\colw') + '}{}{}')
            for j, (y, ids) in enumerate(gs):
                yend = (gs[j+1][0] - 1.5) if j + 1 < len(gs) else y1b + 2
                if REF and (pi, c) == (REF[0], REF[2]) and y < REF[1] < yend + 1: yend = REF[1] - 2
                zh = '\n'.join(block2tex(i) for i in ids)
                body.append(r'\bilrow{' + crop(pi, xa, y - 1.5, xb, yend, r'\colw') + '}{' + zh + '}{' + notes_for(ids) + '}')
                body.append(fullpages_for(ids))
            if REF and (pi, c) == (REF[0], 'R') and REF[2] == 'R' and y0b < REF[1] < y1b:
                refstrips(pi, xa, xb, REF[1] - 2, y1b + 2)

if REFSTRIPS:
    body.append(r'\par\vspace{6pt}\begin{multicols}{2}\raggedcolumns' + '\n'
                + '\n'.join('\\noindent' + x + r'\par' for x in REFSTRIPS) + '\n' + r'\end{multicols}')
interp = open(f'{name}_interp.tex', encoding='utf-8').read() if os.path.exists(f'{name}_interp.tex') else ''
PRE = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'preamble.tex')
doc = open(PRE, encoding='utf-8').read() + '\n'.join(body) + '\n' + interp + '\n\\end{document}\n'
open(outtex, 'w', encoding='utf-8').write(doc)
print(f'写出 {outtex}: {len(body)} 个片段, 注释 {sum(len(v) for v in NOTES.values())} 条, 整页讲解 {sum(len(v) for v in FULL.values())} 页')
