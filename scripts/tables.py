"""把 arXiv(LaTeXML) 网页里的表格拆成网格，并列出需要翻译的文字单元格
用法: python3 tables.py <name>
输入: <name>.json（extract.py 的输出）
输出: <name>_tables.json      每张表的网格结构（行、单元格、跨行跨列、粗体、横线）
      <name>_tables_zh.txt    待翻译清单，每行“原文 ||| 译文”；已有译文会保留，只追加新出现的原文
译文规则：纯数字、X、- 之类不列入清单；方法名、数据集名可以原样照抄到右边。"""
import json, re, sys, html, os, copy
import lxml.html
from lxml import etree

name = sys.argv[1]
D = json.load(open(f'{name}.json', encoding='utf-8'))
SYM = {'✓': r'$\checkmark$', '✔': r'$\checkmark$', '✗': r'$\times$', '✘': r'$\times$', '†': r'$^\dagger$', '‡': r'$^\ddagger$'}

def cls(e): return (e.get('class') or '').split()

def cell_text(td):
    """单元格 → (纯文本键, 是否粗体, 是否下划线)。行内公式换成 $alttext$ 以便原样排出"""
    e = copy.deepcopy(td)
    for m in e.xpath('.//math'):
        alt = html.unescape(m.get('alttext') or '')
        tok = etree.Element('span'); tok.text = f'${alt}$'; tok.tail = m.tail
        m.getparent().replace(m, tok)
    for br in e.xpath('.//br'):
        br.tail = ' ' + (br.tail or '')
    txt = re.sub(r'\s+', ' ', e.text_content()).strip()
    bold = bool(td.xpath('.//*[contains(concat(" ",@class," ")," ltx_font_bold ")]')) or 'ltx_font_bold' in cls(td)
    und = any(k in cls(td) or td.xpath(f'.//*[contains(concat(" ",@class," ")," {k} ")]')
              for k in ('ltx_underline', 'ltx_framed_underline'))
    return txt, bold, und

def parse_tabular(t):
    rows = []
    for tr in t.xpath('./thead/tr|./tbody/tr|./tfoot/tr|./tr'):
        cells = []
        for td in tr.xpath('./td|./th'):
            txt, bold, und = cell_text(td)
            c = cls(td)
            cells.append({'t': txt, 'cs': int(td.get('colspan', 1)), 'rs': int(td.get('rowspan', 1)),
                          'b': bold, 'u': und, 'h': td.tag == 'th',
                          'al': 'l' if 'ltx_align_left' in c else ('r' if 'ltx_align_right' in c else 'c'),
                          'top': any(k in c for k in ('ltx_border_t', 'ltx_border_tt')),
                          'bot': any(k in c for k in ('ltx_border_b', 'ltx_border_bb'))})
        rows.append(cells)
    return rows

def needs_translation(s):
    s2 = re.sub(r'\$[^$]*\$', '', s)
    s2 = re.sub(r'\[[\d,\s–-]+\]', '', s2)            # 引用编号
    return re.search(r'[A-Za-z]{2,}', s2) is not None and not re.fullmatch(r'[A-Z]', s2.strip())

AF = f'{name}_anchors.json'          # 已做过锚定时，跳过不在 PDF 中的附录表格
ABSENT = set(json.load(open(AF)).get('absent', [])) if os.path.exists(AF) else set()
out, strings = {}, []
for b in D['blocks']:
    if b['type'] == 'heading' and b['en'].strip().lower().endswith('references'): continue   # 附录里的表格也要翻译
    if b['type'] != 'table' or b['id'] in ABSENT: continue
    grids = []
    for th in b.get('tables', []):
        t = lxml.html.fromstring(th)
        # 只取最外层表格；嵌在单元格里的小表格已被当作单元格文字处理
        grids.append(parse_tabular(t))
    out[b['id']] = grids
    for g in grids:
        for row in g:
            for c in row:
                if c['t'] and needs_translation(c['t']) and c['t'] not in strings: strings.append(c['t'])

json.dump(out, open(f'{name}_tables.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
zf = f'{name}_tables_zh.txt'
have = {}
if os.path.exists(zf):
    for line in open(zf, encoding='utf-8'):
        if '|||' in line:
            k, v = line.rstrip('\n').split('|||', 1); have[k.strip()] = v.strip()
with open(zf, 'w', encoding='utf-8') as f:
    for s in strings: f.write(f'{s} ||| {have.get(s, "")}\n')
todo = sum(1 for s in strings if not have.get(s))
print(f'{name}: {len(out)} 个表格块，{sum(len(g) for g in out.values())} 张表，待译文字 {len(strings)} 条（其中未译 {todo} 条）→ {zf}')
