"""纯中文版：按原版版式重排（双栏仍双栏、单栏仍单栏），正文、标题、图表题全部换成中文，
图、表格图形、行间公式从原版 PDF 矢量裁切，按阅读顺序放回原来的位置
用法: python3 render_zh.py <name> <name>orig.pdf <out.tex>
需要: <name>.json <name>_layout.json <name>_lines.json <name>_anchors.json <name>_zh.txt
可选: <name>_tables.json + <name>_tables_zh.txt（表题后接中文表）
行间公式块在 <name>_zh.txt 里写的是解释，这一版不印解释，只印原版公式的裁切图
PDF 模式（<name>.json 里 "pdfmode": true，由 pdfblocks.py 产出）：块自带裁切框，图用 gfx 框、公式/meta/参考文献用 pdf 框，
译文里的行内公式直接写 $…$"""
import json, re, sys, html, os, unicodedata
from collections import Counter
name, origpdf, outtex = sys.argv[1], sys.argv[2], sys.argv[3]
D = json.load(open(f'{name}.json')); LAY = json.load(open(f'{name}_layout.json'))
AJ = json.load(open(f'{name}_anchors.json')); A = dict(AJ['anchors'])
ABSENT = set(AJ.get('absent', []))
LINES = json.load(open(f'{name}_lines.json'))
pages = LAY['pages']; B = {b['id']: b for b in D['blocks']}
SINGLE = LAY.get('single', False)
PDFMODE = D.get('pdfmode', False)   # pdfblocks.py 产出的块：自带裁切框，按阅读顺序排列
ZH = {}
for line in open(f'{name}_zh.txt', encoding='utf-8'):
    if '|||' in line: k, v = line.rstrip('\n').split('|||', 1); ZH[k] = v
ALT = {k: html.unescape(re.search(r'alttext="([^"]*)"', v).group(1)) for k, v in D['math'].items()}

# ---------- 译文 → LaTeX（与 render.py 相同的转换规则） ----------
def esc(s):
    rep = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
           '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
           '✓': r'$\checkmark$', '✔': r'$\checkmark$', '✗': r'$\times$', '✘': r'$\times$', '°': r'$^\circ$'}
    rep.update({chr(0x2460 + k): '（%d）' % (k + 1) for k in range(20)})
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

# ---------- 表格译文（与 render.py 的 table2tex 相同） ----------
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
    occ, lines, spans = set(), [], []
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
            elif cols:
                cs = sorted(cols); run = [cs[0]]
                for x in cs[1:] + [None]:
                    if x is not None and x == run[-1] + 1: run.append(x); continue
                    body.append(r'\cmidrule(lr){%d-%d}' % (run[0] + 1, run[-1] + 1))
                    if x is not None: run = [x]
        body.append(ln)
    spec = 'l' + 'c' * (nc - 1)
    return (r'\zhtable{\begin{tabular}{' + spec + r'}\toprule' + '\n' + '\n'.join(body) +
            '\n' + r'\bottomrule\end{tabular}}')

# ---------- 参考文献的位置与引用编号对照（与 render.py 相同） ----------
REF = None
for pi, pl in enumerate(LINES):
    for ln in pl:
        if re.sub(r'[^a-z0-9]', '', ln['t'].lower()) == 'references':
            REF = (pi, ln['y0'], ln['y1']); break
    if REF: break
REF_END = None
if REF:
    post, seen = [], False
    for b in D['blocks']:
        if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): seen = True; continue
        if seen and b['type'] != 'bib' and b['id'] in A: post.append(A[b['id']])
    if post:
        a0 = min(post, key=lambda a: (a['page'], a['y']))
        refs_above = any(l['y0'] < a0['y'] - 2 and re.match(r'^\[\d+\]', l['t']) for l in LINES[a0['page']])
        REF_END = (a0['page'], a0['y'] - 2) if (a0['page'] == REF[0] or refs_above) else (a0['page'], 0)
def in_refs(pi, y):
    return REF is not None and (pi, y) >= (REF[0], REF[1] - 1) and (REF_END is None or (pi, y) < REF_END)
def build_citemap():
    if not REF: return {}
    rows = []
    for pi in range(REF[0], len(LINES)):
        for l in LINES[pi]:
            if (pi, l['y0']) < (REF[0], REF[1] - 1) or (REF_END and (pi, l['y0']) >= REF_END): continue
            rows.append((pi, l['x0'] >= pages[pi]['w'] / 2 and not SINGLE, l['y0'], l['t'], l['x0']))
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
        title = re.split(r'\(\d{4}[a-z]?\)\s*', m.group(2), maxsplit=1)[-1]
        nt = re.sub(r'[^a-z0-9]', '', title.lower())
        for key in (nt[:28], nt[8:36]):
            hits = [n for n, e in pdf.items() if len(key) >= 12 and key in e]
            if len(hits) == 1: cmap[int(m.group(1))] = hits[0]; break
    nbib = sum(1 for b in D['blocks'] if b['type'] == 'bib')
    if nbib and len(cmap) < 0.5 * nbib:
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

# ---------- 检查译文是否齐全（公式块不要求） ----------
need = []
for b in D['blocks']:
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): continue
    if b['id'] in ABSENT: continue
    if b['type'] in ('para', 'footnote') and b['id'] not in ZH: need.append(b['id'])
    if b['type'] == 'heading' and b['level'] == 1 and b['id'] not in ZH: need.append(b['id'])
    if b['type'] in ('figure', 'table') and b.get('src') and b['id'] not in ZH: need.append(b['id'])
if need and not PDFMODE:
    sys.exit(f'{name}_zh.txt 缺少这些块的译文：{" ".join(need)}')

# ---------- 文字匹配（与 render.py 相同） ----------
def nrm(s): return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKC', s).lower())
def gtext(ids):
    parts = []
    for i in ids:
        b = B[i]; parts += [b.get('src') or '', b.get('en') or '']
        parts += [sc.get('src', '') for sc in b.get('subcaps', [])]
    return nrm(re.sub(r'⟦M\d+⟧', ' ', ' '.join(parts)).replace('**', ''))
def match(n, T):
    if len(n) < 16: return len(n) >= 3 and n in T
    ks = range(0, len(n) - 7, 4)
    return sum(n[k:k + 8] in T for k in ks) >= 0.6 * len(ks)
def score(n, T):
    ks = range(0, max(1, len(n) - 7), 4)
    return sum(n[k:k + 8] in T for k in ks) / len(ks) if len(n) >= 8 else 0

# ---------- 版心：正文长行的左右边界中位数；页边竖排的 arXiv 编号落在范围外 ----------
def med(v, d=0): v = sorted(v); return v[len(v) // 2] if v else d
longl = [(pi, l) for pi, pl in enumerate(LINES) for l in pl if len(l['t']) > 50]
W0 = med([pages[pi]['w'] for pi, _ in longl])
if SINGLE:
    XL = med([l['x0'] for _, l in longl]); XR = med([l['x1'] for _, l in longl])
    CL = CR = None
else:
    lft = [l for pi, l in longl if l['x1'] < pages[pi]['w'] / 2 + 5]
    rgt = [l for pi, l in longl if l['x0'] > pages[pi]['w'] / 2 - 5]
    XL = med([l['x0'] for l in lft]); XR = med([l['x1'] for l in rgt])
    CL = med([l['x1'] for l in lft]); CR = med([l['x0'] for l in rgt])   # 左栏右沿、右栏左沿
HBODY = med([l['y1'] - l['y0'] for _, l in longl], 9)
pitch = []                                       # 正文行距：同一栏相邻长行的 y 差
for pi, pl in enumerate(LINES):
    ls = sorted([l for l in pl if len(l['t']) > 50], key=lambda l: (l['x0'] > pages[pi]['w'] / 2 and not SINGLE, l['y0']))
    pitch += [b['y0'] - a['y0'] for a, b in zip(ls, ls[1:]) if 0 < b['y0'] - a['y0'] < 20]
PITCH = med(pitch, 12)

# ---------- 页眉页脚：页面上下 12% 以内、三成以上页面重复出现的文字（数字不计），或孤立的纯页码 ----------
def fkey(t): return re.sub(r'\d+', '#', t.strip().lower())
def edge(pi, l): return l['y1'] < 0.12 * pages[pi]['h'] or l['y0'] > 0.88 * pages[pi]['h']
cnt = Counter(k for pi, pl in enumerate(LINES) for k in {fkey(l['t']) for l in pl if edge(pi, l)})
def furniture(pi, l):
    if not edge(pi, l): return False
    if cnt[fkey(l['t'])] >= max(2, 0.3 * len(LINES)): return True
    if re.fullmatch(r'[#\s–-]*', fkey(l['t'])):                     # 纯页码：上下 10pt 内没有别的行
        return not any(o is not l and o['y0'] < l['y1'] + 10 and o['y1'] > l['y0'] - 10 for o in LINES[pi])
    return False
def inbody(pi, l):
    c = (l['x0'] + l['x1']) / 2
    return XL - 10 <= c <= XR + 10 and not furniture(pi, l)
PL = [[l for l in pl if inbody(pi, l)] for pi, pl in enumerate(LINES)]
TOP = [min([l['y0'] for l in pl] + [pages[pi]['h']]) for pi, pl in enumerate(PL)]
BOT = [max([l['y1'] for l in pl] + [0]) for pi, pl in enumerate(PL)]
for pi, pl in enumerate(LINES):                  # 去掉页眉页脚后，版心上下沿收到页眉下方、页脚上方
    fu = [l for l in pl if furniture(pi, l)]; h = pages[pi]['h']
    t = max([l['y1'] for l in fu if l['y1'] < h / 2] + [0]); b = min([l['y0'] for l in fu if l['y0'] > h / 2] + [h])
    TOP[pi] = max(t + 3, min(TOP[pi], *[bd['y0'] for bd in pages[pi]['bands']]) - 2)
    BOT[pi] = min(b - 3, max(BOT[pi], *[bd['y1'] for bd in pages[pi]['bands']]) + 2)

# ---------- 版式：纸张、版心、栏距、字号都取自原版 ----------
pw, ph = pages[0]['w'], pages[0]['h']
top = med([TOP[pi] for pi in range(len(pages))]); bot = ph - med([BOT[pi] for pi in range(len(pages))])
FS = round(PITCH * 0.8, 1); BS = round(FS * 1.55, 1)
colsep = (CR - CL) if not SINGLE else 0
PRE = r'''\documentclass[10pt]{article}
\usepackage[paperwidth=%(pw).1fpt,paperheight=%(ph).1fpt,left=%(l).1fpt,right=%(r).1fpt,top=%(t).1fpt,bottom=%(b).1fpt,footskip=%(fk).1fpt,headheight=0pt,headsep=0pt]{geometry}
\usepackage{fontspec}
\usepackage{xeCJK}
\usepackage{graphicx,amsmath,amssymb,bm,xcolor}
\usepackage{booktabs,array,multicol,needspace,multirow}
\setmainfont{Times New Roman}
\setCJKmainfont{Songti SC}[BoldFont={Songti SC Bold}]
\setCJKsansfont{Heiti SC}
\xeCJKsetup{CJKecglue={\hskip 0.15em plus 0.05em}}
\providecommand{\degree}{^\circ}
\setlength{\columnsep}{%(cs).1fpt}
\setlength{\parskip}{0pt}
\renewcommand{\normalsize}{\fontsize{%(fs).1f}{%(bs).1f}\selectfont}
\AtBeginDocument{\normalsize\setlength{\parindent}{2em}}
\raggedbottom
\clubpenalty=10000 \widowpenalty=10000
%% 标题后紧跟 \nobreak，段落首尾不留单行（club/widow 罚分），标题就不会孤零零落在页底/栏底
\setlength{\multicolsep}{4pt}
\setcounter{topnumber}{4}\setcounter{totalnumber}{6}\setcounter{dbltopnumber}{3}
\renewcommand{\topfraction}{0.9}\renewcommand{\dbltopfraction}{0.9}\renewcommand{\textfraction}{0.05}
\renewcommand{\floatpagefraction}{0.8}\renewcommand{\dblfloatpagefraction}{0.8}
\setlength{\textfloatsep}{10pt plus 4pt}\setlength{\dbltextfloatsep}{10pt plus 4pt}\setlength{\floatsep}{8pt}
\newcommand{\zhsec}[1]{\par\addvspace{8pt}{\noindent\sffamily\bfseries\fontsize{%(fs2).1f}{%(bs2).1f}\selectfont #1\par}\nobreak\addvspace{4pt}\nobreak}
\newcommand{\zhsub}[1]{\par\addvspace{6pt}{\noindent\sffamily\bfseries #1\par}\nobreak\addvspace{2pt}\nobreak}
\newcommand{\zhsubsub}[1]{\par\addvspace{4pt}{\noindent\sffamily #1\par}\nobreak}
\newcommand{\zhcap}[1]{\par\vspace{3pt}{\fontsize{%(cf).1f}{%(cb).1f}\selectfont\noindent #1\par}}
\newcommand{\zhgraph}[1]{\par\noindent #1\par}
\newcommand{\zheq}[1]{\par\addvspace{3pt}\noindent #1\par\addvspace{3pt}}
\newcommand{\zhref}[1]{\par\noindent #1\par}
\newcommand{\zhfig}[1]{\par\addvspace{8pt}\noindent\begin{minipage}{\linewidth}\setlength{\parindent}{0pt}#1\end{minipage}\par\addvspace{8pt}}
\newsavebox\bztab
\newcommand{\zhtable}[1]{\par\vspace{4pt}\sbox\bztab{\fontsize{8}{10}\selectfont\setlength{\tabcolsep}{3.5pt}#1}%%
  {\centering\ifdim\wd\bztab>\linewidth\resizebox{\linewidth}{!}{\usebox\bztab}\else\usebox\bztab\fi\par}\vspace{2pt}}
\begin{document}
''' % {'pw': pw, 'ph': ph, 'l': XL - 3, 'r': pw - XR - 3, 't': top, 'b': bot, 'fk': max(12, bot * 0.55),
       'cs': max(colsep - 6, 8), 'fs': FS, 'bs': BS, 'fs2': FS * 1.15, 'bs2': BS * 1.1, 'cf': FS * 0.88, 'cb': FS * 0.88 * 1.5}

body = []
incol = False
def setcols(on):
    global incol
    if SINGLE or on == incol: return
    body.append(r'\begin{multicols}{2}\raggedcolumns' if on else r'\end{multicols}'); incol = on

# ---------- PDF 模式（pdfblocks.py 产出，没有 arXiv 网页版的论文）：块已按阅读顺序排好，每块自带裁切框，
#            不用再找图、公式；图只裁图形（gfx），下面接中文图题；公式、meta、参考文献原样裁切 ----------
def ztex(s):
    # PDF 模式的译文直接写 $…$ 行内公式，公式原样保留，其余按译文规则转换
    return ''.join(p if re.fullmatch(r'\$[^$]+\$', p) else zh2tex(p) for p in re.split(r'(\$[^$]+\$)', s) if p)
def render_pdfmode():
    TW = XR - XL + 6                                   # 版心宽（与 geometry 一致）
    LW = (TW - max(colsep - 6, 8)) / 2 if not SINGLE else TW      # 栏宽
    COLO = (CL - XL) if not SINGLE else (XR - XL)      # 原版栏宽
    def wide(bx): return (bx[3] - bx[1]) > 1.1 * COLO
    def pcrop(bx, maxw):
        pi, x0, y0, x1, y1 = bx; H = pages[pi]['h']
        w = min(x1 - x0, maxw - 0.5)
        return (r'\includegraphics[page=%d,viewport=%.1f %.1f %.1f %.1f,clip,width=%.1fpt]{%s}'
                % (pi + 1, x0, H - y1, x1, H - y0, w, origpdf))
    def text(b):
        return ztex(ZH[b['id']]) if b['id'] in ZH else None
    def head(b):
        t = ztex(ZH.get(b['id'], b['en']))
        return (r'\zhsec{' if b['level'] <= 2 else r'\zhsub{') + t + '}'
    def strips(bx, maxw):
        # 参考文献一栏切成约 110pt 高的小条（在行间空隙下刀），多栏环境里可以跨栏、跨页
        pi, x0, y0, x1, y1 = bx
        ls = sorted((l['y0'], l['y1']) for l in LINES[pi] if x0 - 2 <= (l['x0'] + l['x1']) / 2 <= x1 + 2 and y0 - 1 <= l['y0'] and l['y1'] <= y1 + 1)
        gaps = [(ls[k][1] + ls[k + 1][0]) / 2 for k in range(len(ls) - 1) if ls[k + 1][0] > ls[k][1]]
        cuts = [y0]
        for k in range(1, max(1, round((y1 - y0) / 110))):
            t = y0 + (y1 - y0) * k / max(1, round((y1 - y0) / 110))
            c = min(gaps, key=lambda q: abs(q - t)) if gaps else t
            if c > cuts[-1] + 5: cuts.append(c)
        cuts.append(y1)
        return [r'\zhref{' + pcrop([pi, x0, cuts[k], x1, cuts[k + 1]], maxw) + '}' for k in range(len(cuts) - 1)]
    def st_median(v): v = sorted(v); return v[len(v) // 2] if v else 9
    def metacrops(b, maxw):
        # meta 的框是按栏算的，可能压到旁边的标题、版权框：只取文字能对上这一块的行，收紧到这些行；
        # 收紧后的框里还夹着别的行，就逐行裁
        T, seen, out = nrm(b.get('src', '')), set(), []
        for bx in b['pdf']:
            pi, x0, y0, x1, y1 = bx
            ms = [l for l in LINES[pi] if x0 - 2 <= (l['x0'] + l['x1']) / 2 <= x1 + 2 and y0 - 2 <= (l['y0'] + l['y1']) / 2 <= y1 + 2
                  and id(l) not in seen and match(nrm(l['t']), T)]
            if not ms: continue
            seen.update(id(l) for l in ms)
            hm = st_median([l['y1'] - l['y0'] for l in ms])
            r = [pi, min(l['x0'] for l in ms) - 1.5, min(l['y0'] for l in ms) - 1, max(l['x1'] for l in ms) + 1.5, max(l['y1'] for l in ms) + 1]
            # 上下标（“1†”“2,3”）常被抽成单独的小行，不算别的内容
            other = [l for l in LINES[pi] if all(l is not m for m in ms) and l['x0'] < r[3] and l['x1'] > r[1]
                     and l['y0'] < r[4] - 1 and l['y1'] > r[2] + 1 and len(nrm(l['t'])) > 6 and l['y1'] - l['y0'] > 0.8 * hm]
            if not other: out.append(r); continue
            ms.sort(key=lambda l: (l['y0'], l['x0']))
            for k, l in enumerate(ms):          # 逐行裁：上下沿取到与相邻行的中线，不带进邻行的笔画
                a = max(l['y0'] - 1, (ms[k - 1]['y1'] + l['y0']) / 2) if k else l['y0'] - 1
                z = min(l['y1'] + 1, (l['y1'] + ms[k + 1]['y0']) / 2) if k + 1 < len(ms) else l['y1'] + 1
                out.append([pi, l['x0'] - 1.5, a, l['x1'] + 1.5, z])
        return [r'\zhref{' + pcrop(r, maxw) + '}' for r in out] or [r'\zhref{' + pcrop(x, maxw) + '}' for x in b['pdf']]
    BL = [b for b in D['blocks'] if b['id'] not in ABSENT and not b.get('drop')]   # drop：期刊版权声明、末页期刊信息等
    # 首页标题区：论文标题及其之前的块，以及标题之后、第一个栏宽的标题/段落之前的块；首页上沿高于它的 meta（版权框等）也归标题区
    ti = next((k for k, b in enumerate(BL) if b['type'] == 'heading' and b['level'] == 1), -1)
    fe = next((k for k, b in enumerate(BL) if k > ti and b['type'] in ('heading', 'para') and not wide(b['pdf'][0])), len(BL))
    ylim = BL[fe]['pdf'][0][2] if fe < len(BL) and BL[fe]['pdf'][0][0] == 0 else 0
    front = set(range(fe)) | {k for k, b in enumerate(BL) if b['type'] == 'meta' and b['pdf'][0][0] == 0 and b['pdf'][0][2] < ylim}
    late = []
    for k in sorted(front):
        b = BL[k]
        if b['type'] == 'heading' and b['level'] == 1:
            body.append(r'{\centering\sffamily\bfseries\fontsize{%.1f}{%.1f}\selectfont %s\par}\vspace{6pt}' % (FS * 1.8, FS * 2.5, text(b) or esc(b['en'])))
        elif b['type'] == 'heading':                   # 标题之前的栏目名（如 HOPPING LOCOMOTION）
            body.append(r'{\sffamily\bfseries\color{black!70} %s\par}\vspace{4pt}' % ztex(ZH.get(b['id'], b['en'])))
        elif b['type'] == 'meta':
            x = (r'{\small ' + text(b) + r'\par}') if text(b) else ''.join(metacrops(b, TW))
            (late if k > ti + 1 and any(BL[j]['type'] == 'para' for j in front if j < k) else body).append(x + r'\vspace{4pt}')
        elif b['type'] == 'para':
            body.append(r'\par{\setlength{\parindent}{0pt}' + (text(b) or '') + r'\par}\vspace{6pt}')
    body.extend(late); body.append(r'\vspace{8pt}')
    seq = [k for k in range(len(BL)) if k not in front]
    for j in range(len(seq) - 1):                  # 栏底的单位脚注等 meta 夹在一段和它的续段之间时，挪到续段之后，不把句子隔开
        a, c = BL[seq[j]], BL[seq[j + 1]]
        if a['type'] == 'meta' and c['type'] == 'para' and re.match(r'[a-z]', c.get('src', '')):
            seq[j], seq[j + 1] = seq[j + 1], seq[j]
    for k in seq:
        b = BL[k]
        t, bx = b['type'], b['pdf'][0]
        if t == 'heading':
            if b['level'] == 1: continue
            setcols(not (wide(bx) and not SINGLE)); body.append(head(b))
        elif t == 'para':
            full = wide(bx) and not SINGLE
            setcols(not full)
            if re.match(r'[a-z]', b.get('src', '')) and body and body[-1].endswith(r'\par') and body[-1].startswith(r'\par'):
                body[-1] = body[-1][:-4] + (text(b) or '') + r'\par'      # 以小写字母开头的是上一段被栏、页或脚注切开的后半段：接着排
            else: body.append((r'\par ' if not full else r'\par\noindent ') + (text(b) or '') + r'\par')
        elif t in ('figure', 'table'):
            g = b.get('gfx') or bx
            cap = r'\zhcap{' + text(b) + '}' if text(b) else ''
            tabs = ''.join(table2tex(x) for x in TABLES.get(b['id'], [])) if t == 'table' else ''
            if wide(g) and not SINGLE:
                setcols(True)
                body.append(r'\begin{figure*}[!tp]\setlength{\parindent}{0pt}{\centering ' + pcrop(g, TW) + r'\par}' + cap + tabs + r'\end{figure*}')
            elif SINGLE:
                body.append(r'\begin{figure}[!htbp]\setlength{\parindent}{0pt}{\centering ' + pcrop(g, TW) + r'\par}' + cap + tabs + r'\end{figure}')
            else:
                setcols(True); body.append(r'\zhfig{{\centering ' + pcrop(g, LW) + r'\par}' + cap + tabs + '}')
        elif t == 'equation':                          # 公式块的译文是解释，这一版不印
            full = wide(bx) and not SINGLE
            pi, x0, y0, x1, y1 = bx
            for l in LINES[pi]:                        # 框和上下相邻的正文行有一两磅重叠：收到邻行之外，不带进邻行的字母下沿
                if l['x1'] <= x0 or l['x0'] >= x1: continue
                c = (l['y0'] + l['y1']) / 2
                if c < y0 + 2 and l['y1'] > y0: y0 = l['y1'] + 0.3
                if c > y1 - 2 and l['y0'] < y1: y1 = l['y0'] - 0.3
            setcols(not full); body.append(r'\zheq{\hfill ' + pcrop([pi, x0, y0, x1, y1], TW if full else LW) + '}')
        elif t == 'meta':
            full = wide(bx) and not SINGLE
            setcols(not full)
            if text(b): body.append(r'\par{\small ' + text(b) + r'\par}')
            else: body.extend(metacrops(b, TW if full else LW))
        elif t == 'refs':
            setcols(True)
            for x in b['pdf']: body.extend(strips(x, LW if not wide(x) else TW))
    setcols(False)
    open(outtex, 'w', encoding='utf-8').write(PRE + '\n'.join(body) + '\n\\end{document}\n')
    nf = sum(1 for b in BL if b['type'] in ('figure', 'table')); ne = sum(1 for b in BL if b['type'] == 'equation')
    miss = [b['id'] for b in BL if b['type'] in ('para', 'figure', 'table') and b['id'] not in ZH]
    print(f'写出 {outtex}（PDF 模式）: 图表 {nf} 个，行间公式 {ne} 处，{"单栏" if SINGLE else "双栏"}，正文 {FS}pt/{BS}pt')
    if miss: print('缺译文、排了空段的块:', ' '.join(miss))
if PDFMODE:
    render_pdfmode(); sys.exit(0)

# ---------- 区域：单栏每页一个；双栏按 layout 的带划分，跨栏带一个、双栏带左右各一个 ----------
ORD = {'F': 0, 'L': 0, 'R': 1}
REG = []                                         # {pi, bi, col, xa, xb, ya, yb, lines}
for pi, p in enumerate(pages):
    bands = [{'y0': TOP[pi], 'y1': BOT[pi], 'full': True}] if SINGLE else p['bands']
    for bi, bd in enumerate(bands):
        ya, yb = max(TOP[pi], bd['y0'] - 2), min(BOT[pi], bd['y1'] + 2)
        cols = [('F', XL, XR)] if (SINGLE or bd['full']) else [('L', XL, CL), ('R', CR, XR)]
        for col, xa, xb in cols:
            REG.append({'pi': pi, 'bi': bi, 'col': col, 'xa': xa, 'xb': xb, 'ya': ya, 'yb': yb, 'lines': []})
def region_of(pi, l):
    c = (l['x0'] + l['x1']) / 2; cx = pages[pi]['w'] / 2
    for ri, r in enumerate(REG):
        if r['pi'] != pi or not (r['ya'] - 3 <= (l['y0'] + l['y1']) / 2 <= r['yb'] + 3): continue
        if r['col'] == 'F' or (r['col'] == 'L') == (c < cx): return ri
    return None
for pi, pl in enumerate(PL):
    for l in pl:
        ri = region_of(pi, l)
        if ri is not None: REG[ri]['lines'].append(l)
for r in REG: r['lines'].sort(key=lambda l: l['y0'])
def rkey(ri): r = REG[ri]; return (r['pi'], r['bi'], ORD[r['col']])
RIDX = {rkey(ri): ri for ri in range(len(REG))}
def mask(ri):
    """区域横向范围对应的墨迹位：页宽 32 格，格子中心落在范围内的才算"""
    r = REG[ri]; w = pages[r['pi']]['w']
    return sum(1 << k for k in range(32) if r['xa'] - 2 <= (k + 0.5) * w / 32 <= r['xb'] + 2)
MASK = [mask(ri) for ri in range(len(REG))]
# 参考文献范围按阅读顺序判断：双栏时右栏顶端的条目在页面上比左栏的“References”还高
REFRI = region_of(REF[0], {'x0': XL, 'x1': XL + 1, 'y0': REF[1], 'y1': REF[2]}) if REF else None
for ri, r in enumerate(REG if REF else []):
    for l in r['lines']:
        if r['pi'] == REF[0] and abs(l['y0'] - REF[1]) < 0.5: REFRI = ri
def in_refs_r(ri, y):
    if REFRI is None: return False
    r = REG[ri]
    return rkey(ri) + (y,) >= rkey(REFRI) + (REF[1] - 1,) and (REF_END is None or (r['pi'], y) < REF_END)
def inky(ri, y):
    ink = pages[REG[ri]['pi']].get('ink', []); y = int(y)
    return 0 <= y < len(ink) and bool(ink[y] & MASK[ri])

# ---------- 图表题锚点核对：锚点所在行必须以“Figure N / Fig. N / TABLE N”开头且文字与图表题吻合，
#            否则（anchor.py 的编号兜底可能落到正文里“Fig. 9 shows …”那一行）在全文里重找 ----------
LAB = re.compile(r'\s*(Table|TABLE|Figure|FIGURE|Fig\.?)\s*([IVXLC]+|\d+)\b')
def label(t):
    m = LAB.match(t)
    return (m.group(1).lower().startswith('tab'), m.group(2).lower()) if m else None
def capscore(pi, l, T):
    pl = PL[pi]; i = pl.index(l) if l in pl else -1
    nxt = ' '.join(x['t'] for x in pl[i + 1:i + 3] if abs(x['x0'] - l['x0']) < 60) if i >= 0 else ''
    return score(nrm(l['t'] + ' ' + nxt)[:120], T)
for b in D['blocks']:
    if b['type'] not in ('figure', 'table') or b['id'] in ABSENT: continue
    src = b.get('src') or (b['subcaps'][0]['src'] if b.get('subcaps') else '')
    lab = label(src); T = gtext([b['id']])
    if not lab: continue
    a = A.get(b['id'])
    cands = [(capscore(pi, l, T), pi, l) for pi, pl in enumerate(PL) for l in pl if label(l['t']) == lab]
    cands = [c for c in cands if c[0] > 0.3]
    if not cands: continue
    best, pi, l = max(cands, key=lambda c: c[0])
    if a and any(c[1] == a['page'] and abs(c[2]['y0'] - a['y']) < 1.5 and c[0] >= best - 0.05 for c in cands): continue
    ri = region_of(pi, l)
    if ri is None: continue
    A[b['id']] = {'page': pi, 'band': REG[ri]['bi'], 'col': REG[ri]['col'], 'y': l['y0']}
    print(f'{b["id"]} 图表题锚点改到第 {pi + 1} 页 y={l["y0"]:.1f}（原锚点 {a}）')

# ---------- 分组：锚点 + 其后未锚定的块归入同组（行间公式不排译文，自然不出现） ----------
order = []
for b in D['blocks']:
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): continue
    if b['type'] in ('bib', 'authors') or b['id'] in ABSENT: continue
    order.append(b['id'])
title_ids = [i for i in order if B[i]['type'] == 'heading' and B[i]['level'] == 1]
groups, owner = {}, None
for bid in order:
    if bid in title_ids: continue
    if bid in A:
        a = A[bid]
        if (a['page'], a['band'], ORD[a['col']]) not in RIDX: continue
        k = (a['page'], a['band'], ORD[a['col']], round(a['y'], 1))
        for g in list(groups):                     # 同一行上的多个锚点并为一组（行内小标题与正文同行）
            if g[:3] == k[:3] and abs(g[3] - k[3]) <= 2: k = g; break
        groups.setdefault(k, []).append(bid); owner = k
    elif owner is not None and B[bid]['type'] != 'equation':
        groups[owner].append(bid)                  # 没锚定上的段落：译文并到上一组
gl = sorted(groups.items())                        # [(键, 块号列表)]，按阅读顺序
GK = [g[0] for g in gl]; GI = [g[1] for g in gl]
def kind(g):
    ts = {B[i]['type'] for i in GI[g]}
    return 'fig' if ts & {'figure', 'table'} else 'head' if ts <= {'heading'} else 'text'
GT = [gtext(ids) for ids in GI]
FIRST = GK[0] if GK else None                      # 首页第一组之前是标题、作者、单位，统一不裁切

# ---------- 1. 文字行归属（沿用 render.py flow() 的规则，推广到每一栏） ----------
def ingroup(k):
    j = None
    for i, g in enumerate(GK):
        if g[:3] < k[:3] or (g[:3] == k[:3] and g[3] <= k[3] + 1.5): j = i
        else: break
    return j
EQNO = re.compile(r'\((\d+[a-z]?)\)\s*$')
OWN = [[] for _ in REG]                          # 每个区域 [(y0, y1, 组号, 行)]
last = {}
for ri, r in enumerate(REG):
    rk = rkey(ri); width = r['xb'] - r['xa']
    for li, l in enumerate(r['lines']):
        if in_refs_r(ri, l['y0']): continue
        k = rk + (l['y0'],)
        if FIRST and k < FIRST[:3] + (FIRST[3] - 1.5,): continue
        g = ingroup(k)
        if g is None: continue
        n = nrm(l['t'])
        if l['y1'] - l['y0'] > 2.5 * HBODY and l['y1'] - l['y0'] > l['x1'] - l['x0']: continue   # 竖排文字只会是图中标注
        anchor = GK[g][:3] == rk and abs(GK[g][3] - l['y0']) < 1.5
        wide = l['x1'] - l['x0'] >= 0.5 * width
        # 紧挨着这一组的上一行，且左端对齐或居中对齐（图表题常居中）；图中贴着正文的短标签不算
        def near(j): return (last.get(j, (None,))[0] == ri and l['y0'] - last[j][1] < 5
                             and (wide or abs(l['x0'] - last[j][2]) < 3 or abs((l['x0'] + l['x1']) / 2 - last[j][3]) < 3))
        cands = [g]
        if kind(g) == 'fig':                      # 图表题之后的正文续行归回图表之前的那一段
            p = g
            while p > 0 and kind(p) == 'fig': p -= 1
            if kind(p) != 'fig': cands = [g, p] if near(g) else [p, g]
        # 本栏还没有正文行时，第一行可以是上一栏那一段的续行（续行从栏左沿起排；图中的短标签不算）
        first = not any(kind(o[2]) != 'fig' for o in OWN[ri]) and abs(l['x0'] - r['xa']) < 3
        pick = g if anchor else next((j for j in cands if match(n, GT[j])
                                      and (near(j) or (first and kind(j) != 'fig') or (wide and kind(j) == 'text'))), None)
        if pick is None and OWN[ri] and kind(OWN[ri][-1][2]) == 'text' and OWN[ri][-1][3] is r['lines'][li - 1] \
                and not EQNO.search(l['t']):
            # 文字没对上（行里多是行内公式）但紧接着上一行：与上一行同一视觉行，或从栏左沿/上一行左端起排，算同一段
            o = OWN[ri][-1]
            if l['y0'] < o[1] - 2 or (l['y0'] - o[1] < 5 and (abs(l['x0'] - r['xa']) < 3 or abs(l['x0'] - o[3]['x0']) < 3)):
                pick = o[2]
        if pick is not None:
            OWN[ri].append((l['y0'], l['y1'], pick, l)); last[pick] = (ri, l['y1'], l['x0'], (l['x0'] + l['x1']) / 2)

def alpha_words(t): return len(re.findall(r'[A-Za-z]{3,}', t))
ALLT = ' '.join(GT[g] for g in range(len(GK)) if kind(g) != 'fig')
def prose(l, width):
    # 没归属上的正文行（多半是行内公式太多没对上）：宽、词多、文字大半能在正文里找到；表格脚注、图中文字不算
    return l['x1'] - l['x0'] >= 0.8 * width and alpha_words(l['t']) >= 6 and score(nrm(l['t']), ALLT) > 0.5
COV = []
for ri in range(len(REG)):
    c = set()
    for y0, y1, _, _ in OWN[ri]: c.update(range(int(y0), int(y1) + 2))
    COV.append(c)

# ---------- 2. 图表的图形：从图表题向图形一侧延伸，直到最近的一行正文/别的图表题（或栏边），再收到墨迹范围 ----------
GRAPH = {}                                       # 组号 -> (区域, y0, y1, 图形在题上方?)
USED = [set() for _ in REG]
for g in range(len(GK)):
    if kind(g) != 'fig': continue
    ri = RIDX[GK[g][:3]]; r = REG[ri]; width = r['xb'] - r['xa']
    cap = [o for o in OWN[ri] if o[2] == g]
    if not cap: cap = [(l['y0'], l['y1'], g, l) for l in r['lines'] if abs(l['y0'] - GK[g][3]) < 1.5]
    if not cap: print(f'{GI[g]}: 找不到图表题所在行，只排中文图表题'); continue
    ct, cb = min(o[0] for o in cap), max(o[1] for o in cap)
    bounds = [(o[0], o[1]) for o in OWN[ri] if o[2] != g]
    bounds += [(l['y0'], l['y1']) for l in r['lines'] if prose(l, width) and not any(o[3] is l for o in OWN[ri])]
    up = max([y1 for y0, y1 in bounds if y1 <= ct + 0.5] + [r['ya']])
    dn = min([y0 for y0, y1 in bounds if y0 >= cb - 0.5] + [r['yb']])
    def inkrows(a, b): return [y for y in range(int(a) + 1, int(b)) if inky(ri, y) and y not in COV[ri] and y not in USED[ri]]
    ra, rb = inkrows(up, ct - 1), inkrows(cb + 1, dn)
    isfig = any(B[i]['type'] == 'figure' for i in GI[g])
    if isfig: above = len(ra) >= 8 or len(rb) < 8
    else: above = len(ra) > len(rb)
    rows = ra if above else rb
    if len(rows) < 4: print(f'{GI[g]}: 图表题旁没有图形墨迹，只排中文图表题'); continue
    y0, y1 = rows[0], rows[-1] + 1
    for l in r['lines']:                          # 图中文字整行收进来，不切半个字
        if l['y1'] > y0 and l['y0'] < y1 and not any(o[3] is l for o in OWN[ri]):
            y0, y1 = min(y0, l['y0']), max(y1, l['y1'])
    y0, y1 = max(y0 - 1.5, up), min(y1 + 1.5, dn)
    GRAPH[g] = (ri, y0, y1, above)
    USED[ri].update(range(int(y0), int(y1) + 2))

# ---------- 3. 其余没归属的墨迹：行间公式（裁切）；没有数学符号的英文行（单位、脚注、页脚）丢弃 ----------
MATHCH = set('=<>≤≥±×∑∏∫√∂∇∈∉⊂⊆→←↦⊤⊥∞≈≠·∥|') | {chr(c) for c in range(0x391, 0x3CA)}
EQS = [[] for _ in REG]; DROPPED = []
for ri, r in enumerate(REG):
    runs, cur = [], None
    for y in range(int(r['ya']), int(r['yb']) + 1):
        if y in COV[ri] or y in USED[ri] or in_refs_r(ri, y): cur = None; continue
        if FIRST and rkey(ri) + (y,) < FIRST[:3] + (FIRST[3] - 1.5,): continue
        if inky(ri, y):
            if cur and y - cur[1] <= 6: cur[1] = y
            else: cur = [y, y]; runs.append(cur)
    for a, b in runs:
        ls = [l for l in r['lines'] if l['y1'] > a - 1 and l['y0'] < b + 2 and not any(o[3] is l for o in OWN[ri])]
        if not ls: continue                       # 只有横线、行内公式伸出的笔画，没有文字
        a, b = min([a] + [l['y0'] for l in ls]), max([b + 1] + [l['y1'] for l in ls])
        txt = ' '.join(l['t'] for l in ls)
        eq = any(EQNO.search(l['t']) for l in ls) or (any(c in MATHCH for c in txt) and
             sum(alpha_words(l['t']) >= 5 for l in ls) * 2 <= len(ls))
        if eq: EQS[ri].append((max(a - 1.5, r['ya'] - 1), min(b + 1.5, r['yb'] + 1)))   # 大括号等字形框偏大，别越过版心碰到页码
        else: DROPPED.append((r['pi'] + 1, round(a), txt[:70]))

# ---------- 输出 ----------
def crop(pi, x0, y0, x1, y1, width):
    H = pages[pi]['h']
    return (r'\includegraphics[page=%d,viewport=%.1f %.1f %.1f %.1f,clip,width=%s]{%s}'
            % (pi + 1, x0, H - y1, x1, H - y0, width, origpdf))
def rcrop(ri, y0, y1):
    r = REG[ri]; return crop(r['pi'], r['xa'] - 3, y0, r['xb'] + 3, y1, r'\linewidth')
def head_tex(b, runin=False):
    t = zh2tex(ZH.get(b['id'], b['en']))
    if runin: return r'{\sffamily\bfseries ' + t + r'}\quad '
    if b['level'] <= 2: return r'\zhsec{' + t + '}'
    if b['level'] == 3: return r'\zhsub{' + t + '}'
    return r'\zhsubsub{' + t + '}'
def text_tex(ids):
    out, runin = [], ''
    for k, i in enumerate(ids):
        b = B[i]; t = b['type']
        if t == 'heading':
            # 标题与下一段同组（同一行起排）时，按段首的行内小标题排
            nxt = ids[k + 1] if k + 1 < len(ids) else None
            if nxt and B[nxt]['type'] in ('para', 'footnote') and (b['level'] >= 4 or b['en'].strip().lower() == 'abstract'):
                runin = head_tex(b, True)
            else: out.append(head_tex(b))
        elif t == 'para':
            ind = r'\noindent ' if runin else ''
            out.append(r'\par ' + ind + (r'\textbullet\ ' if b.get('list') else '') + runin + zh2tex(ZH[i]) + r'\par'); runin = ''
        elif t == 'footnote':
            out.append(r'\par{\footnotesize\noindent\textsuperscript{' + str(b['num']) + '}' + zh2tex(ZH[i]) + r'\par}')
        elif t in ('figure', 'table'): out.append(cap_tex(i))
    return '\n'.join(out)
def cap_tex(i):
    b = B[i]
    cs = ([zh2tex(ZH[i])] if ZH.get(i) else []) + \
         [zh2tex(ZH[f'{i}.s{k}']) for k in range(len(b.get('panels', []))) if f'{i}.s{k}' in ZH]
    return (r'\zhcap{' + r'\\'.join(cs) + '}') if cs else ''
def fig_tex(g):
    ids = GI[g]; fids = [i for i in ids if B[i]['type'] in ('figure', 'table')]
    caps = ''.join(cap_tex(i) for i in fids)
    tabs = ''.join(table2tex(t) for i in fids if B[i]['type'] == 'table' for t in TABLES.get(i, []))
    gr = ''
    if g in GRAPH:
        ri, y0, y1, above = GRAPH[g]; gr = r'\zhgraph{' + rcrop(ri, y0, y1) + '}'
    else: above = True
    inner = (gr + caps if above else caps + gr) + tabs
    rest = text_tex([i for i in ids if i not in fids])
    return inner, rest

items = []                                       # (区域键, y, 类型, 内容)
for g in range(len(GK)):
    rk = GK[g][:3]
    if kind(g) == 'fig':
        y = min(GK[g][3], GRAPH[g][1]) if g in GRAPH else GK[g][3]
        items.append((rk, y, 'fig', g))
    else: items.append((rk, GK[g][3], 'text', g))
for ri in range(len(REG)):
    for a, b in EQS[ri]: items.append((rkey(ri), a, 'eq', rcrop(ri, a, b)))
# 参考文献：标题换成中文，条目按栏切成小条原样裁切（行间空隙处下刀）
def gap_cuts(ls, ya, yb, n):
    ls = sorted((l['y0'], l['y1']) for l in ls)
    gaps = [(ls[k][1] + ls[k+1][0]) / 2 for k in range(len(ls) - 1) if ls[k+1][0] > ls[k][1]]
    cuts = [ya]
    for k in range(1, n):
        t = ya + (yb - ya) * k / n
        c = min(gaps, key=lambda q: abs(q - t)) if gaps else t
        if c > cuts[-1] + 5: cuts.append(c)
    return cuts + [yb]
if REF:
    for ri, r in enumerate(REG):
        ls = [l for l in r['lines'] if in_refs_r(ri, l['y0']) and not (r['pi'] == REF[0] and abs(l['y0'] - REF[1]) < 1)]
        hd = [l for l in r['lines'] if r['pi'] == REF[0] and abs(l['y0'] - REF[1]) < 1]
        if hd: items.append((rkey(ri), REF[1], 'refhead', None))
        if not ls: continue
        ya, yb = min(l['y0'] for l in ls) - 1.5, max(l['y1'] for l in ls) + 1.5
        c = gap_cuts(ls, ya, yb, max(1, round((yb - ya) / 110)))
        for k in range(len(c) - 1): items.append((rkey(ri), c[k], 'ref', rcrop(ri, c[k], c[k + 1])))
items.sort(key=lambda t: (t[0], t[1]))

# 标题、作者
t = ''.join(r'{\centering\sffamily\bfseries\fontsize{%.1f}{%.1f}\selectfont %s\par}' % (FS * 1.8, FS * 2.5, zh2tex(ZH[i])) for i in title_ids)
au = [b for b in D['blocks'] if b['type'] == 'authors']
if au: t += r'\vspace{8pt}{\centering %s\par}' % esc(au[0]['en'])
body.append(t + r'\vspace{12pt}')
for rk, y, typ, x in items:
    full = REG[RIDX[rk]]['col'] == 'F'
    if typ == 'fig':
        inner, rest = fig_tex(x)
        if SINGLE: body.append(r'\begin{figure}[!htbp]\setlength{\parindent}{0pt}' + inner + r'\end{figure}')
        elif full:
            setcols(True); body.append(r'\begin{figure*}[!tp]\setlength{\parindent}{0pt}' + inner + r'\end{figure*}')
        else: setcols(True); body.append(r'\zhfig{' + inner + '}')
        if rest: body.append(rest)
    elif typ == 'text':
        setcols(not full); body.append(text_tex(GI[x]))
    elif typ == 'eq':
        setcols(not full); body.append(r'\zheq{' + x + '}')
    elif typ == 'refhead':
        setcols(not full); body.append(r'\zhsec{参考文献}')
    elif typ == 'ref':
        setcols(not full); body.append(r'\zhref{' + x + '}')
setcols(False)
open(outtex, 'w', encoding='utf-8').write(PRE + '\n'.join(body) + '\n\\end{document}\n')
nf = sum(1 for g in range(len(GK)) if kind(g) == 'fig')
print(f'写出 {outtex}: 图表 {nf} 个（裁到图形 {len(GRAPH)} 个），行间公式 {sum(map(len, EQS))} 处，'
      f'{"单栏" if SINGLE else "双栏"}，正文 {FS}pt/{BS}pt')
if DROPPED:
    print('没归属、也不像公式的英文行（已丢弃，核对一下有没有漏掉正文）:')
    for d in DROPPED: print('  第 %d 页 y=%d: %s' % d)
