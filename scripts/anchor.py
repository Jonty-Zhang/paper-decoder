"""把每个段落/标题/图表题锚定到原版 PDF 中它“第一行”的精确位置，输出按段切分的版面
用法: python3 anchor.py <name>"""
import json, re, sys, unicodedata
name = sys.argv[1]
D = json.load(open(f'{name}.json')); LAY = json.load(open(f'{name}_layout.json'))
LINES = json.load(open(f'{name}_lines.json')); pages = LAY['pages']
OVR = json.load(open(f'{name}_anchor_override.json')) if __import__('os').path.exists(f'{name}_anchor_override.json') else {}

CITE = re.compile(r'\[[\d,\s–-]+\]')
def norm(s):
    # 引用编号不参与匹配：补充材料常用另一套编号，HTML 与 PDF 会对不上；ﬁ、ﬃ 等连字先拆开
    return re.sub(r'[^a-z0-9]', '', CITE.sub('', unicodedata.normalize('NFKC', s)).lower())
def region(pi, x, y):
    p = pages[pi]; cx = p['w'] / 2
    for bi, bd in enumerate(p['bands']):
        if bd['y0'] - 4 <= y <= bd['y1'] + 4:
            return (bi, 'F' if bd['full'] else ('L' if x < cx else 'R'))
    return (None, None)
ORD = {'F': 0, 'L': 0, 'R': 1}
def key(a): return (a['page'], a['band'], ORD[a['col']], a['y'])

# 所有行（附带其后两行的拼接文本，处理跨行的开头）
L = []
for pi, pl in enumerate(LINES):
    for i, l in enumerate(pl):
        bi, col = region(pi, (l['x0'] + l['x1']) / 2 if l['x1'] - l['x0'] < 60 else l['x0'], l['y0'])
        if bi is None: continue
        nxt = ''.join(x['t'] for x in pl[i+1:i+3])
        L.append({'page': pi, 'band': bi, 'col': col, 'y': l['y0'], 'x0': l['x0'],
                  'n': norm(l['t']), 'n3': norm(l['t'] + nxt)})

blocks, POST, seen = [], set(), False      # POST：参考文献之后的块（附录、补充材料）
for b in D['blocks']:
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): seen = True; continue
    if b['type'] == 'bib': continue
    blocks.append(b)
    if seen: POST.add(b['id'])
# PDF 中参考文献标题的位置：附录的块只能锚定在它之后
REFPOS = next(((l['page'], l['y']) for l in L if l['n'] == 'references'), None)

def src_text(b):
    # 图表块的主标题为空时（几张子表共用一个块），用第一个子标题
    t = b.get('src', '')
    if not t and b.get('subcaps'): t = b['subcaps'][0]['src']
    return t.replace('**', '')

def label_keys(b):
    """图表题的编号标签，如 Table 4 / TABLE II / Fig. 3，用于正文匹配失败时的兜底"""
    m = re.match(r'\s*(Table|TABLE|Figure|FIGURE|Fig\.?)\s*([IVXLC]+|\d+)\b', src_text(b))
    if not m: return []
    num = m.group(2).lower()
    return ['table' + num] if m.group(1).lower().startswith('tab') else ['fig' + num, 'figure' + num]

def pattern(b):
    if b['type'] == 'heading':
        t = re.sub(r'^(Appendix\s+[A-Z]\.?\s+|[IVX]+(-[A-Z]\d*)?\s+|\d+(\.\d+)*\s+)', '', b['en'].strip())   # 含 III-F1 这种编号
        return ('head', norm(t))
    text = src_text(b)
    segs = re.split(r'⟦M\d+⟧', text)
    s0 = norm(segs[0])
    if len(s0) >= 14 or len(segs) == 1: return ('start', re.escape(s0[:26]))
    s1 = norm(segs[1])[:12] if len(segs) > 1 else ''
    return ('start', re.escape(s0) + r'[a-z0-9]{0,30}?' + re.escape(s1))

anchors, prev, fails, absent = {}, None, [], []
for b in blocks:
    if b['type'] in ('equation', 'authors') or (b['type'] == 'heading' and b['level'] == 1): continue
    if b['id'] in OVR: anchors[b['id']] = OVR[b['id']]; prev = OVR[b['id']]; continue
    post = b['id'] in POST
    if post and absent:                       # 附录第一个标题都没找到：整个附录不在这份 PDF 里
        absent.append(b['id']); continue
    kind, pat = pattern(b)
    if not pat: continue
    cands = []
    for l in (x for x in L if not post or REFPOS is None or (x['page'], x['y']) > REFPOS):
        if kind == 'head':
            ok = (l['n'].endswith(pat) and len(l['n']) - len(pat) <= 6) or \
                 (pat == 'abstract' and l['n'].startswith('abstract'))
        else:
            ok = bool(l['n']) and re.match(pat, l['n3']) is not None   # 只有引用编号的行（如上一段末尾的“[1, 2].”）不能当段首
        if ok: cands.append(l)
    # 行内小标题（IEEE 的“1) Master Tool Manipulator: As seen …”“Abstract— Robotic …”）：
    # 标题在行首、正文接在同一行，标题按行首匹配，正文在行首 40 个字符以内匹配
    if not [c for c in cands if prev is None or key(c) >= key(prev)]:
        for l in (x for x in L if not post or REFPOS is None or (x['page'], x['y']) > REFPOS):
            if kind == 'head':
                ok = len(pat) >= 6 and re.match(r'[a-z]?\d{0,2}' + re.escape(pat), l['n']) is not None
            else:
                m = re.search(pat, l['n3'][:40 + len(pat)])
                ok = bool(l['n']) and m is not None and m.start() <= 40
            if ok: cands.append(l)
    if not cands and b['type'] in ('figure', 'table'):
        for key_ in label_keys(b):
            cands += [l for l in L if l['n'].startswith(key_) and not l['n'][len(key_):len(key_) + 1].isdigit()]
    after = [c for c in cands if prev is None or key(c) >= key(prev)]
    pick = min(after, key=key) if after else (min(cands, key=key) if cands else None)
    if pick:
        a = {k: pick[k] for k in ('page', 'band', 'col', 'y')}; anchors[b['id']] = a; prev = a
    elif post and not any(x in anchors for x in POST):
        absent.append(b['id'])                # 附录开头就对不上，按“不在 PDF 中”处理
    else:
        fails.append(b['id'])
if absent:                                    # 附录不在 PDF 中时，其后的块统统不用翻译、不排版
    absent = [b['id'] for b in blocks if b['id'] in POST]

json.dump({'anchors': anchors, 'fails': fails, 'absent': absent}, open(f'{name}_anchors.json', 'w'), indent=1)
print(f'{name}: 锚定 {len(anchors)} 个，失败 {len(fails)} 个: {fails}')
if absent:
    print(f'参考文献之后的 {len(absent)} 个块（{absent[0]}–{absent[-1]}）不在这份 PDF 中，不用翻译，已从 {name}_src.txt 中删去')
    sf = f'{name}_src.txt'
    if __import__('os').path.exists(sf):
        keep = [l for l in open(sf, encoding='utf-8') if l.split(' ', 1)[0].split('.')[0] not in absent]
        open(sf, 'w', encoding='utf-8').writelines(keep)
# 检查：锚点是否按文档顺序单调（不单调说明可能匹配错位置）
seq = [(bid, anchors[bid]) for bid in [b['id'] for b in blocks] if bid in anchors]
bad = [(seq[i][0], seq[i+1][0]) for i in range(len(seq)-1) if key(seq[i+1][1]) < key(seq[i][1])]
print('顺序倒挂(可能是浮动的图表题，需人工确认):', bad)
