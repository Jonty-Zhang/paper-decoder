"""纯中文版：把 arXiv LaTeX 源码里的正文就地换成已审定的译文，再重新编译，得到版式与原文一致的中文 PDF
用法: python3 latexzh.py <name> <srcdir> <out.pdf>
需要: <name>.json <name>_zh.txt；可选 <name>_glossary.txt（翻关键词）
源码含 EPS 而本机没有 gs 时，从原版 PDF 裁出同一张图，需要 <name>orig.pdf <name>_lines.json <name>_layout.json
做法（借鉴 gpt_academic“Latex翻译中文并重新编译PDF”，但不做机器翻译）：
  1. 展开 \\input/\\include、去注释、把 .bbl 内联进来；
  2. 正文切成“保留区”（导言、公式、浮动体除图题外、表格、作者单位、参考文献）和“替换区”（段落、标题、图题、摘要、关键词）；
  3. 替换区按英文 8-gram 相似度对到 <name>.json 的块，换成译文：⟦Mk⟧ 优先换回源码里同一处的数学式，
     [n] 换回 \\cite，图 n / 式 n / 第 n 节 换回 \\ref（编号取自先编一遍英文版得到的 .aux）；
  4. 注入 xeCJK 与中文名称，用 tectonic 编译；出错就按日志行号把出错的那一段退回英文再编，最多 20 次。"""
import json, re, sys, os, html, shutil, subprocess
from difflib import SequenceMatcher
name, srcdir, outpdf = sys.argv[1], sys.argv[2], os.path.abspath(sys.argv[3])
D = json.load(open(f'{name}.json')); BL = D['blocks']; B = {b['id']: b for b in BL}
ZH = dict(l.rstrip('\n').split('|||', 1) for l in open(f'{name}_zh.txt', encoding='utf-8') if '|||' in l)
ALT = {k: html.unescape(re.search(r'alttext="([^"]*)"', v).group(1)) for k, v in D['math'].items()}
GLOS = {}
if os.path.exists(f'{name}_glossary.txt'):
    for l in open(f'{name}_glossary.txt', encoding='utf-8'):
        if '|||' in l and not l.startswith('#'):
            en, zh = (x.strip() for x in l.split('|||', 1))
            if zh and zh != '-': GLOS[en.lower()] = zh.split('/')[0]
WORK = os.path.splitext(outpdf)[0] + '_build'

# ---------- 1. 读源码：展开 input、去注释、内联 bbl ----------
def grab(s, j, o='{', c='}'):          # s[j] 是左括号，返回配对右括号之后的位置
    d = 0
    for k in range(j, len(s)):
        if s[k] == '\\': continue
        if s[k] == o and s[k-1] != '\\': d += 1
        elif s[k] == c and s[k-1] != '\\':
            d -= 1
            if d == 0: return k + 1
    return len(s)
def uncomment(t):
    out = []
    for l in t.split('\n'):
        if re.match(r'\s*%', l): continue                    # 整行注释连换行一起删，免得多出空行把段落切开
        out.append(re.sub(r'(?<!\\)%.*', '', l))
    return '\n'.join(out)
def inline(path):
    t = uncomment(open(path, encoding='utf-8', errors='replace').read())
    def rep(m):
        f = os.path.join(srcdir, m.group(1)); f = f if os.path.exists(f) else f + '.tex'
        return inline(f) if os.path.exists(f) else m.group(0)
    return re.sub(r'\\(?:input|include)\{([^}]*)\}', rep, t)
mains = [f for f in os.listdir(srcdir) if f.endswith('.tex') and '\\documentclass' in open(os.path.join(srcdir, f), errors='replace').read()]
main = 'main.tex' if 'main.tex' in mains else mains[0]
TEX = inline(os.path.join(srcdir, main))
bbl = os.path.join(srcdir, main[:-4] + '.bbl')
if os.path.exists(bbl):
    TEX = re.sub(r'\\bibliography\{[^}]*\}', lambda m: open(bbl, encoding='utf-8').read(), TEX)
    TEX = re.sub(r'\\bibliographystyle\{[^}]*\}', '', TEX)

# ---------- EPS 图：tectonic 不支持 PostScript ----------
def fix_eps(tex):
    gs = shutil.which('gs'); figk = 0; caps = {}; gap = None
    if not gs and os.path.exists(f'{name}orig.pdf'):
        L = json.load(open(f'{name}_lines.json')); P = json.load(open(f'{name}_layout.json'))['pages']
        shutil.copy(f'{name}orig.pdf', os.path.join(WORK, '_orig.pdf'))
        for pi, pg in enumerate(L):
            for ln in pg:
                m = re.match(r'(?:Fig\.|Figure)\s*(\d+)[.:]', ln['t'])
                if m and int(m.group(1)) not in caps:
                    ink = P[pi]['ink']; y = int(ln['y0']) - 1
                    while y > 0 and not ink[y]: y -= 1
                    caps[int(m.group(1))] = (pi, ln['y0'], ln['y0'] - y - 1)
        gap = min(c[2] for c in caps.values()) if caps else 0   # 图底到图题顶的标准间距，取最紧的那张
    def fig(m):
        nonlocal figk
        figk += 1
        def inc(g):
            opts, f = g.group(1) or '', g.group(2)
            p = os.path.join(srcdir, f if f.endswith('.eps') else f + '.eps')
            if not os.path.exists(p) or (not f.endswith('.eps') and any(os.path.exists(os.path.join(srcdir, f + e)) for e in ('.pdf', '.png', '.jpg'))):
                return g.group(0)
            if gs:
                out = os.path.join(WORK, os.path.splitext(f)[0] + '.pdf'); os.makedirs(os.path.dirname(out), exist_ok=True)
                subprocess.run([gs, '-q', '-dNOPAUSE', '-dBATCH', '-dEPSCrop', '-sDEVICE=pdfwrite', '-o', out, p])
                return r'\includegraphics%s{%s}' % (opts, os.path.splitext(f)[0] + '.pdf')
            if figk not in caps: print(f'  图 {figk}: 找不到原版图题，EPS 无法替换'); return g.group(0)
            bb = [float(x) for x in re.search(r'%%BoundingBox:\s*([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)', open(p, errors='replace').read()).groups()]
            bw, bh = bb[2] - bb[0], bb[3] - bb[1]; pi, y0, _ = caps[figk]; pg = P[pi]
            left, right = min(pg['xL']), max(pg['xR']); sc = 1.0
            ms = re.search(r'scale\s*=\s*([\d.]+)', opts); mw = re.search(r'width\s*=\s*([\d.]*)\\(?:text|line|column)width', opts)
            if ms: sc = float(ms.group(1))
            elif mw: sc = float(mw.group(1) or 1) * (right - left) / bw
            w, h = bw * sc, bh * sc; bot = y0 - gap
            x0 = left if w > right - left else (left + right - w) / 2
            H = pg['h']
            return r'\includegraphics[page=%d,viewport=%.1f %.1f %.1f %.1f,clip]{_orig.pdf}' % (pi + 1, x0, H - bot - 1, x0 + w, H - bot + h + 1.5)
        return re.sub(r'\\includegraphics(\[[^\]]*\])?\{([^}]*)\}', inc, m.group(0))
    return re.sub(r'\\begin\{figure\*?\}.*?\\end\{figure\*?\}', fig, tex, flags=re.S)

# ---------- 2. 切分保留区 / 替换区 ----------
MATHENV = r'equation|align|gather|multline|eqnarray|displaymath|flalign|alignat|math'
KEEPENV = re.compile(r'(?:%s|tabular\w*|algorithm\w*|lstlisting|verbatim|tikzpicture|thebibliography|minted)\*?' % MATHENV)
FLOAT = re.compile(r'(?:figure|table|wrapfigure|sidewaysfigure|sidewaystable)\*?')
HEAD = r'section|subsection|subsubsection|paragraph|title'
KEEPCMD = r'author|affiliation|address|ead|cortext|fntext|tnotetext|bibliographystyle|includegraphics|vspace|hspace|maketitle|appendix|newpage|clearpage|journal|date'
PAT = re.compile(r'\n[ \t]*\n|\\begin\{([a-zA-Z]+\*?)\}|\\end\{([a-zA-Z]+\*?)\}|\\(%s)\*?\s*(?=[\[{])|\\(%s)\b\*?|\$\$|\\\[|\\item\b' % (HEAD, KEEPCMD))
def scan(doc):
    segs, buf, i = [], [], 0
    keep = lambda t: t and segs.append(['keep', t, None, None])
    def flush():
        t = ''.join(buf); buf.clear()
        if len(re.sub(r'[^A-Za-z\u4e00-\u9fff]', '', re.sub(r'\\label\{[^}]*\}|\\[a-zA-Z@]+', '', t))) < 3: keep(t); return   # 只有命令，不算段落
        core = t.strip(); a = t.index(core[0]); keep(t[:a]); segs.append(['para', core, None, None]); keep(t[a + len(core):])
    while True:
        m = PAT.search(doc, i)
        if not m: buf.append(doc[i:]); flush(); return segs
        buf.append(doc[i:m.start()]); s = m.group(0); flush()
        if not s.strip(): keep(s); i = m.end()
        elif m.group(1):
            env = m.group(1); end = '\\end{%s}' % env
            if FLOAT.fullmatch(env) or KEEPENV.fullmatch(env) or env == 'keyword':
                e = doc.find(end, m.end()); e = len(doc) if e < 0 else e + len(end); body = doc[m.start():e]
                if FLOAT.fullmatch(env):                        # 浮动体只换图题
                    k = 0
                    for c in re.finditer(r'\\caption\*?(?:\[[^\]]*\])?\{', body):
                        if c.start() < k: continue
                        r = grab(body, c.end() - 1); keep(body[k:c.end()]); segs.append(['caption', body[c.end():r-1], None, None]); k = r - 1
                    keep(body[k:])
                elif env == 'keyword':
                    keep(s); segs.append(['kw', body[len(s):-len(end)], None, None]); keep(end)
                else: keep(body)
                i = e
            else: keep(s); i = m.end()                          # abstract、frontmatter、itemize 等只是边界
        elif m.group(2) or s == '\\item': keep(s); i = m.end()
        elif m.group(3):                                        # 标题：丢掉可选短标题，只换花括号里的
            j = m.end()
            if doc[j] == '[': j = grab(doc, j, '[', ']')
            r = grab(doc, j); keep('\\%s{' % s[1:].split('[')[0].split('{')[0].strip())
            segs.append(['heading', doc[j+1:r-1], None, None]); keep('}'); i = r
        elif m.group(4):                                        # 作者、单位等：连参数一起保留
            j = m.end()
            while j < len(doc) and doc[j] in '[{': j = grab(doc, j, doc[j], ']' if doc[j] == '[' else '}')
            keep(doc[m.start():j]); i = j
        else:                                                   # $$…$$ 与 \[…\]
            e = doc.find('$$' if s == '$$' else '\\]', m.end()) + 2; keep(doc[m.start():e]); i = e

# ---------- 3. 段落对块 ----------
def grams(s, n): return {s[k:k+n] for k in range(max(1, len(s) - n + 1))} if s else set()
def norm_tex(s):
    s = re.sub(r'\$[^$]*\$|\\\(.*?\\\)', '', s)
    s = re.sub(r'\\(?:cite\w*|[cC]ref|ref|eqref|autoref|label|url)\*?(?:\[[^\]]*\])*\{[^}]*\}', '', s)
    return re.sub(r'[^a-z]', '', re.sub(r'\\[a-zA-Z]+', '', s).lower())
def norm_blk(b):
    s = b.get('src') or b.get('en') or ''
    s = re.sub(r'⟦M\d+⟧|\[[\d,\s–-]+\]', '', s); s = re.sub(r'^(?:Figure|Fig\.|Table)\s*\d+[:.]\s*', '', s)
    s = re.sub(r'\b(?:Figs?|Eqs?|Sections?|Tables?)\.?\s*\(?\d+(?:\.\d+)*\)?', '', s)
    return re.sub(r'[^a-z]', '', s.lower())
KIND = {'heading': ('heading',), 'caption': ('figure', 'table'), 'para': ('para', 'footnote')}
def match(segs):
    cand = [(i, s) for i, s in enumerate(segs) if s[0] in KIND]; nb = len(BL); pairs = []
    for ci, (i, s) in enumerate(cand):
        n = 3 if s[0] == 'heading' else 8; a = grams(norm_tex(s[1]), n)
        for bi, b in enumerate(BL):
            if b['type'] not in KIND[s[0]] or not a: continue
            g = grams(norm_blk(b), n)
            sc = 2 * len(a & g) / (len(a) + len(g)) if g else 0
            if sc >= (0.6 if s[0] == 'heading' else 0.45):
                pairs.append((sc - 0.05 * abs(ci / len(cand) - bi / nb), i, b['id']))   # 文字相同时按先后顺序
    used_s, used_b = set(), set()
    for sc, i, bid in sorted(pairs, reverse=True):
        if i not in used_s and bid not in used_b: segs[i][2] = bid; used_s.add(i); used_b.add(bid)

# ---------- 译文 → LaTeX ----------
def esc(s):
    rep = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
           '~': r'\textasciitilde{}', '^': r'\textasciicircum{}', '°': r'\textdegree{}', '·': r'$\cdot$'}
    return ''.join(rep.get(c, c) for c in s)
def nm(s): return re.sub(r'\s|[{}]|\\[,;!]|\\left|\\right', '', re.sub(r'^\$|\$$|^\\\(|\\\)$', '', s))
def align(ph, srcm):                          # ⟦Mk⟧ 按顺序对到源码里的 $…$，源码可编译，比 HTML 的 alttext 稳
    res, j = {}, 0
    for p in ph:
        a, best = nm(ALT.get(p, '')), (0, None)
        for t in range(j, min(j + 4, len(srcm))):
            r = 1.0 if a == nm(srcm[t]) else SequenceMatcher(None, a, nm(srcm[t])).ratio()
            if r > best[0] + 1e-9: best = (r, t)
            if r == 1.0: break
        if best[0] >= 0.7: res[p] = srcm[best[1]]; j = best[1] + 1
    return res
CLS = {'figure': 'figure', 'table': 'table', 'equation': 'equation', 'AMS': 'equation'}
def to_tex(s, stat):
    kind, src, bid = s[0], s[1], s[2]; zh, b = ZH[bid], B[bid]
    if kind == 'heading':
        m = re.match(r'(?:[A-Z]|\d+)(?:\.\d+)*\s+', b.get('en', ''))
        if m: zh = re.sub(r'^(?:[A-Z]|\d+)(?:\.\d+)*\s*', '', zh)
    if kind == 'caption': zh = re.sub(r'^[图表]\s*\d+\s*[：:.]\s*', '', zh)
    mm = align(re.findall(r'⟦(M\d+)⟧', b.get('src', '')), re.findall(r'\$[^$]+\$|\\\(.+?\\\)', src))
    maths = []
    def ph(m):
        k = m.group(1); maths.append(mm.get(k) or '$%s$' % ALT.get(k, ''))
        stat['math_src' if k in mm else 'math_alt'] += 1
        return chr(0xE000 + len(maths) - 1)                    # 先换成私用区字符，免得被转义
    t = esc(re.sub(r'⟦(M\d+)⟧', ph, zh))
    t = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', t)
    def cite(m):                                                # [8, 13–15] → \cite{…}
        nums = []
        for part in re.split(r'\s*[,，]\s*', m.group(1)):
            a, _, c = part.partition('–') if '–' in part else part.partition('-')
            nums += list(range(int(a), int(c) + 1)) if c else [int(a)]
        keys = [NUM2KEY.get(n) for n in nums]
        if None in keys: stat['cite_plain'] += 1; return m.group(0)
        stat['cite'] += 1; return r'\cite{%s}' % ','.join(keys)
    t = re.sub(r'\[(\d+(?:\s*[,，–-]\s*\d+)*)\]', cite, t)
    refs = {k.strip() for g in re.findall(r'\\(?:[cC]ref|ref|eqref|autoref)\*?\{([^}]*)\}', src) for k in g.split(',')}
    def xref(cls, num, fmt):
        ks = [k for k in refs if LBL.get(k) == (cls, num)]
        if not ks: stat['ref_plain'] += 1; return None
        stat['ref'] += 1; return fmt % ks[0]
    t = re.sub(r'([图表])\s*(\d+)', lambda m: xref('figure' if m.group(1) == '图' else 'table', m.group(2), m.group(1) + r'~\ref{%s}') or m.group(0), t)
    t = re.sub(r'式\s*[（(]?\s*(\d+)\s*[)）]?', lambda m: xref('equation', m.group(1), r'式~(\ref{%s})') or m.group(0), t)
    t = re.sub(r'第\s*(\d+(?:\.\d+)*(?:\s*[、和与及]\s*\d+(?:\.\d+)*)*)\s*节', lambda m: '第~%s~节' % re.sub(       # 第 3.1.1、3.1.2 节
        r'\d+(?:\.\d+)*', lambda n: xref('section', n.group(0), r'\ref{%s}') or n.group(0), m.group(1)), t)
    for ch, sub in set(re.findall(r'(?<![A-Za-z\\])([A-Z])\$_\{?([0-9a-z])\}?\$', src)):       # 源码里的 K$_1$
        t = re.sub(r'(?<![A-Za-z0-9])%s%s(?![0-9A-Za-z])' % (ch, sub), r'%s$_%s$' % (ch, sub), t)
    t = re.sub(r'【译注[：:].*?】', lambda m: r'{\small\color{gray}%s}' % m.group(0), t)
    t = re.sub('[\uE000-\uF8FF]', lambda m: maths[ord(m.group(0)) - 0xE000], t)
    lb = ''.join(re.findall(r'\\label\{[^}]*\}', src))
    return (lb + ('\n' if kind == 'para' else '') if lb else '') + t
def kw_tex(src):                              # 关键词：先看“Keywords:”那一块译文冒号后有没有写，再查术语表
    items = [x.strip() for x in re.split(r'\\sep', src) if x.strip()]
    kb = [b['id'] for b in BL if b['type'] == 'heading' and re.fullmatch(r'keywords?:?', b.get('en', '').strip(), re.I)]
    rest = re.split(r'[：:]', ZH.get(kb[0], ''), maxsplit=1)[1:] if kb else []
    zk = [x.strip() for x in re.split(r'[；;，,、]', ''.join(rest)) if x.strip()]
    if len(zk) == len(items): return ' \\sep '.join(esc(x) for x in zk), []
    out = [esc(GLOS[x.lower()]) if x.lower() in GLOS else x for x in items]
    return ' \\sep '.join(out), [x for x in items if x.lower() not in GLOS]

# ---------- 4. 编译与出错回退 ----------
def compile(tex, job):
    open(os.path.join(WORK, job + '.tex'), 'w', encoding='utf-8').write(tex)
    r = subprocess.run(['tectonic', '-X', 'compile', '--keep-logs', '--keep-intermediates', job + '.tex'],
                       cwd=WORK, capture_output=True, text=True)
    lg = os.path.join(WORK, job + '.log')
    return r.returncode, open(lg, encoding='utf-8', errors='replace').read() if os.path.exists(lg) else r.stderr
def names():
    def h(pat, dflt):
        for b in BL:
            if b['type'] == 'heading' and re.fullmatch(pat, b.get('en', '').strip(), re.I) and b['id'] in ZH:
                USED.add(b['id']); return re.split(r'[：:]', ZH[b['id']])[0].strip()
        return dflt
    date = ''                                 # 页脚日期用原版的，不用今天
    if os.path.exists(f'{name}_lines.json'):
        d = re.findall(r'(?:January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}',
                       ' '.join(l['t'] for l in json.load(open(f'{name}_lines.json'))[0]))
        date = r'\def\today{%s}' % d[-1] if d else ''
    times = re.search(r'\\documentclass\[[^\]]*\btimes\b|\\usepackage(?:\[[^\]]*\])?\{(?:times|mathptmx|newtx\w*|txfonts)\}', TEX)
    return '\n'.join([r'\usepackage[no-math]{fontspec}', r'\usepackage{xeCJK}', r'\usepackage{xcolor}',
        r'\setmainfont{texgyretermes}[Extension=.otf,UprightFont=*-regular,BoldFont=*-bold,ItalicFont=*-italic,BoldItalicFont=*-bolditalic]' if times else '',
        r'\setCJKmainfont{Songti SC}[BoldFont={Songti SC Bold}]', r'\setCJKsansfont{Heiti SC}',
        r'\xeCJKsetup{CJKecglue={\hskip 0.15em plus 0.05em}}', r'\emergencystretch=1.5em', date, r'\makeatletter',
        r'\renewcommand{\figurename}{图}\renewcommand{\tablename}{表}\renewcommand{\refname}{%s}' % h(r'references|bibliography', '参考文献'),
        r'\@ifpackageloaded{caption}{\captionsetup[figure]{name={图},labelsep=quad}\captionsetup[table]{name={表},labelsep=quad}}{}',
        r'\@ifundefined{abstracttitle}{\renewcommand{\abstractname}{%s}}{\abstracttitle{%s}}' % ((h(r'abstract', '摘要'),) * 2),
        r'\@ifundefined{keywordtitle}{}{\keywordtitle{%s}}' % h(r'keywords?:?', '关键词'), r'\makeatother', ''])

os.makedirs(WORK, exist_ok=True)
for f in os.listdir(srcdir):
    p = os.path.join(srcdir, f)
    (shutil.copytree(p, os.path.join(WORK, f), dirs_exist_ok=True) if os.path.isdir(p) else shutil.copy(p, WORK))
TEX = fix_eps(TEX)
bd, ed = TEX.index('\\begin{document}'), TEX.rindex('\\end{document}')
PRE, DOC, POST = TEX[:bd], TEX[bd:ed], TEX[ed:]
print('第 0 遍：编译英文原文，取编号 …')
rc, _ = compile(PRE + DOC + POST, '_en')
aux = open(os.path.join(WORK, '_en.aux'), encoding='utf-8', errors='replace').read() if os.path.exists(os.path.join(WORK, '_en.aux')) else ''
if rc: print('  英文原文本身编不过，回退也救不了，先查 _en.log')
NUM2KEY = {int(re.search(r'\d+', v).group(0)): k for k, v in re.findall(r'\\bibcite\{([^}]*)\}\{(.*)\}', aux)}
LBL = {}
for k, num, rest in re.findall(r'\\newlabel\{([^}@]+)\}\{\{([^{}]*)\}(.*)', aux):
    c = re.search(r'\\newlabel\{%s@cref\}\{\{\[(\w+)\]' % re.escape(k), aux)
    a = re.search(r'\{(figure|table|equation|AMS|section|subsection|subsubsection|appendix)\.', rest)
    t = c.group(1) if c else a.group(1) if a else ''
    LBL[k] = (CLS.get(t, 'section' if 'section' in t or t == 'appendix' else t), num)

USED = set(); segs = scan(DOC); match(segs)
stat = dict.fromkeys(['math_src', 'math_alt', 'cite', 'cite_plain', 'ref', 'ref_plain'], 0)
miss_kw = []
for s in segs:
    if s[0] == 'kw': s[3], miss_kw = kw_tex(s[1]); continue
    if s[2] and s[2] in ZH: s[3] = to_tex(s, stat); USED.add(s[2])
PRE2 = PRE + names()
reverted = set()
for attempt in range(21):
    out, spans, line = [], {}, PRE2.count('\n') + 1
    for i, s in enumerate(segs):
        t = s[3] if s[3] is not None and i not in reverted else s[1]
        if s[3] is not None and i not in reverted: spans[i] = (line, line + t.count('\n'))
        out.append(t); line += t.count('\n')
    print(f'第 {attempt + 1} 遍：编译中文版 …')
    rc, log = compile(PRE2 + ''.join(out) + POST, '_zh')
    if rc == 0: break
    m = re.search(r'^!.*?\n(?:.*\n)*?l\.(\d+)', log, re.M)
    ln = int(m.group(1)) if m else -1
    hit = [i for i, (a, b) in spans.items() if a <= ln <= b] or [i for i, (a, b) in spans.items() if b <= ln][-1:]
    ra = re.search(r'Runaway argument\?\n(.{6,30})', log)     # 参数没收尾时日志没有行号，用失控参数的开头去找是哪一段
    if not m and ra: hit = [i for i in spans if ra.group(1)[:15] in segs[i][3]][:1]
    if not hit: print('  出错位置不在任何替换段里，停止：', (re.search(r'^!.*', log, re.M) or re.search('(.*)', log)).group(0)); break
    reverted.add(hit[0]); print(f'  {"第 %d 行" % ln if ln > 0 else "日志无行号，按失控参数定位"}出错，退回英文：', segs[hit[0]][1][:60].replace('\n', ' '))
if rc == 0:
    shutil.copy(os.path.join(WORK, '_zh.pdf'), outpdf)
    shutil.copy(os.path.join(WORK, '_zh.log'), os.path.splitext(outpdf)[0] + '.log')

# ---------- 报告 ----------
eng = [s for s in segs if s[0] in KIND and (s[3] is None)]
done = [s for i, s in enumerate(segs) if s[0] in KIND and s[3] is not None and i not in reverted]
print(f'替换区 {len(done) + len(eng) + len(reverted)} 段：换成中文 {len(done)}，没对上 {len(eng)}，回退 {len(reverted)}')
for s in eng: print(f'  [仍为英文 {s[0]}]', s[1][:70].replace('\n', ' '))
for i in sorted(reverted): print('  [回退]', segs[i][1][:70].replace('\n', ' '))
skip = {'equation', 'bib', 'authors'}
left = [k for k in ZH if (k not in USED or k in {segs[i][2] for i in reverted}) and B.get(k, {}).get('type') not in skip]
print('译文没放进去的块：', ', '.join(left) or '无')
if miss_kw: print('关键词术语表里没有、保留英文：', '; '.join(miss_kw))
print('数学式：源码 %(math_src)d，alttext %(math_alt)d；引用 \\cite %(cite)d（未换 %(cite_plain)d）；交叉引用 \\ref %(ref)d（未换 %(ref_plain)d）' % stat)
print('Overfull \\hbox：', len(re.findall(r'Overfull \\hbox', log)) if rc == 0 else '-', ' 输出：', outpdf if rc == 0 else '编译失败')
