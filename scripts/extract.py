"""把 arXiv(LaTeXML) 网页拆成有序的块，供翻译与排版使用
用法: python3 extract.py <name>
输入: <name>.html（arXiv 论文的 HTML 版，https://arxiv.org/html/<编号>）
输出: <name>.json     所有块（标题、段落、脚注、公式、图表）及行内公式
      <name>_src.txt  待翻译清单，每行“块号 [类型] 原文”，翻译写进 <name>_zh.txt；
                      行间公式列成“块号 [式 (n)] LaTeX”，在 <name>_zh.txt 里写这条公式的解释
"""
import sys, json, re, copy, html as htmlmod
import lxml.html
from lxml import etree

name = sys.argv[1]
src, out, base = f'{name}.html', f'{name}.json', ''
doc = lxml.html.parse(src).getroot()
art = doc.find_class('ltx_document')[0]

def cls(e): return (e.get('class') or '').split()
def has(e, c): return c in cls(e)
def ohtml(e): return etree.tostring(e, encoding='unicode', method='html', with_tail=False)

HEAD = {'h1','h2','h3','h4','h5','h6'}
def is_block(e):
    t = e.tag
    if not isinstance(t, str): return None
    c = cls(e)
    if t in HEAD and 'ltx_title' in c: return 'heading'
    if t == 'p' and 'ltx_p' in c: return 'para'
    if t == 'table' and ('ltx_equation' in c or 'ltx_equationgroup' in c): return 'equation'
    if t == 'figure' and 'ltx_table' in c: return 'table'
    if t == 'figure' and 'ltx_figure' in c and 'ltx_figure_panel' not in c: return 'figure'
    if t == 'li' and 'ltx_bibitem' in c: return 'bib'
    if t == 'div' and 'ltx_authors' in c: return 'authors'
    return None

def tokenize(el, store):
    """复制元素：行内公式→⟦Mk⟧，引用→纯文本，粗体→**x**，返回待翻译文本"""
    e = copy.deepcopy(el)
    for m in e.xpath('.//math'):
        k = f"M{len(store)+1}"; store[k] = ohtml(m)
        tok = etree.Element('span'); tok.text = f"⟦{k}⟧"; tok.tail = m.tail
        m.getparent().replace(m, tok)
    for b in e.xpath('.//*[contains(concat(" ",@class," ")," ltx_font_bold ")]'):
        txt = b.text_content()
        if txt.strip():
            for ch in list(b): b.remove(ch)
            b.text = f"**{txt}**"
    s = e.text_content()
    return re.sub(r'\s+', ' ', s).strip()

def clean_en(el):
    e = copy.deepcopy(el)
    for a in e.xpath('.//a'):       # 内部链接在 PDF 里无意义，去掉超链接保留文字
        a.tag = 'span'; a.attrib.pop('href', None)
    return ohtml(e)

blocks, store = [], {}
emitted = set()
fn_count = [0]
for e in art.iter():
    kind = is_block(e)
    if not kind: continue
    if any(a in emitted for a in e.iterancestors()): continue
    # 跳过网页末尾的“报错说明”
    if kind == 'heading' and 'Instructions for reporting errors' in e.text_content(): break
    emitted.add(e)
    bid = f"B{len(blocks)+1}"
    if kind == 'authors':
        names = [n.text_content().strip() for n in e.find_class('ltx_personname')]
        names = [re.sub(r'\s+',' ', n.split('\n')[0]) for n in names]
        blocks.append({'id':bid,'type':'authors','en':', '.join(n for n in names if n)}); continue
    if kind == 'heading':
        lvl = int(e.tag[1]); txt = re.sub(r'\s+',' ', e.text_content()).strip()
        blocks.append({'id':bid,'type':'heading','level':lvl,'en':txt}); continue
    if kind == 'para':
        # 脚注：抽成独立块，正文里留上标
        notes = []
        pe = copy.deepcopy(e)
        for n in pe.xpath('.//*[contains(concat(" ",@class," ")," ltx_note ") and contains(concat(" ",@class," ")," ltx_role_footnote ")]'):
            fn_count[0] += 1
            content = n.find_class('ltx_note_content')
            if content:
                c = copy.deepcopy(content[0])
                for mk in c.find_class('ltx_note_mark'): mk.getparent().remove(mk)
                notes.append((fn_count[0], c))
            sup = etree.Element('sup'); sup.text = str(fn_count[0]); sup.tail = n.tail
            n.getparent().replace(n, sup)
        inli = any(a.tag == 'li' for a in e.iterancestors())
        txt = tokenize(pe, store)
        if txt:
            blocks.append({'id':bid,'type':'para','list':inli,'en_html':clean_en(pe),'src':txt})
        for k, c in notes:
            blocks.append({'id':f"B{len(blocks)+1}",'type':'footnote','num':k,
                           'en_html':clean_en(c),'src':tokenize(c, store)})
        continue
    if kind == 'equation':
        blocks.append({'id':bid,'type':'equation','html':clean_en(e)}); continue
    if kind in ('figure','table'):
        imgs = [base + i.get('src') for i in e.xpath('.//img') if i.get('src')]
        caps = [c for c in e.xpath('.//figcaption') if not any(p is not e and p.tag=='figure' and has(p,'ltx_figure_panel') for p in c.iterancestors())]
        subcaps = [c for c in e.xpath('.//figure[contains(@class,"ltx_figure_panel")]//figcaption')]
        tables = [ohtml(t) for t in e.xpath('.//table[contains(@class,"ltx_tabular")]')] if kind=='table' else []
        cap = caps[-1] if caps else None
        blk = {'id':bid,'type':kind,'imgs':imgs,'tables':tables,
               'cap_en_html': clean_en(cap) if cap is not None else '',
               'src': tokenize(cap, store) if cap is not None else '',
               'subcaps':[{'en_html':clean_en(s),'src':tokenize(s,store)} for s in subcaps],
               'panels':[{'imgs':[base+i.get('src') for i in p.xpath('.//img') if i.get('src')],
                          'cap': (lambda c: {'en_html':clean_en(c),'src':tokenize(c,store)} if c is not None else None)(
                                 (p.xpath('.//figcaption') or [None])[0])}
                         for p in e.xpath('.//figure[contains(@class,"ltx_figure_panel")]')]}
        blocks.append(blk); continue
    if kind == 'bib':
        blocks.append({'id':bid,'type':'bib','en_html':clean_en(e)}); continue

json.dump({'blocks':blocks,'math':store}, open(out,'w',encoding='utf-8'), ensure_ascii=False, indent=1)
from collections import Counter
print(out, Counter(b['type'] for b in blocks), '行内公式', len(store))

def eq_rows(h):
    """行间公式的每一行：(式号或 None, LaTeX)"""
    rows = []
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', h, re.S):
        alts = [htmlmod.unescape(a) for a in re.findall(r'alttext="([^"]*)"', r)]
        if not alts: continue
        no = re.search(r'ltx_eqn_eqno[^>]*>.*?\((\d+[a-z]?)\)', r, re.S)
        rows.append((no.group(1) if no else None, ' '.join(a.replace(r'\displaystyle', '') for a in alts)))
    return rows
def eq_label(h):
    nos = [n for n, _ in eq_rows(h) if n]
    if not nos: return '公式'
    return f'式 ({nos[0]})' if len(nos) == 1 else f'式 ({nos[0]})–({nos[-1]})'

# 待译清单：跳过参考文献条目，参考文献之后的附录照常列出；图表的子图题用“块号.s序号”；
# 行间公式不翻译，列出来是为了在译文栏同一位置写解释
TAG = {'para': 'P', 'footnote': '脚注', 'figure': '图题', 'table': '表题'}
with open(f'{name}_src.txt', 'w', encoding='utf-8') as f:
    for b in blocks:
        if b['type'] == 'heading':
            if b['en'].strip().lower().endswith('references'): continue   # 参考文献条目不译，其后的附录照常列出
            f.write(f"{b['id']} [H{b['level']}] {b['en']}\n")
        elif b['type'] == 'equation':
            rows = eq_rows(b['html'])
            if rows: f.write(f"{b['id']} [{eq_label(b['html'])}] " + ' ; '.join(re.sub(r'\s+', ' ', t) for _, t in rows) + "\n")
        elif b['type'] in TAG:
            if b.get('src'): f.write(f"{b['id']} [{TAG[b['type']]}] {b['src']}\n")
            for i, p in enumerate(b.get('panels', [])):
                if p.get('cap') and p['cap']['src']: f.write(f"{b['id']}.s{i} [子图题] {p['cap']['src']}\n")
print(f'{name}_src.txt 已写出')
