"""术语表：翻译前抽出候选术语统一译法，翻译后检查译文是否照用、数字有没有漏
用法: python3 terms.py <name>            从 <name>_src.txt 抽候选术语，写入/补充 <name>_glossary.txt
      python3 terms.py <name> --check    检查 <name>_zh.txt：术语是否按术语表翻译、原文里的数字译文里是否都在
术语表每行“英文 ||| 中文”。中文留空的行不参与检查；右边写 - 表示这个词不需要统一（删掉也行）。
重跑抽取不会丢已填的译法。"""
import re, sys, os
from collections import Counter

name = sys.argv[1]
CHECK = '--check' in sys.argv
SRC, GL, ZHF = f'{name}_src.txt', f'{name}_glossary.txt', f'{name}_zh.txt'

def load_src():
    out = {}
    for line in open(SRC, encoding='utf-8'):
        m = re.match(r'(B[\d.s]+) \[([^\]]*)\] (.*)', line.rstrip('\n'))
        if m: out[m.group(1)] = (m.group(2), m.group(3))
    return out
def clean(s):
    s = re.sub(r'⟦M\d+⟧', ' ', s)                 # 行内公式
    s = re.sub(r'\[[\d,\s–-]+\]', ' ', s)         # 引用编号
    return s.replace('**', '')

def load_glossary():
    g = {}
    if os.path.exists(GL):
        for line in open(GL, encoding='utf-8'):
            if '|||' in line:
                k, v = line.rstrip('\n').split('|||', 1); g[k.strip()] = v.strip()
    return g

STOP = set('''a an the of and or in on at to for with by from as is are was were be been being this that these those
it its their his her our we they which who whom whose than then there here into onto over under between within without
can could would should may might must will shall not no nor also such each per via using used use based both all any some
more most less least very same other another one two three four five six first second third new figure fig table section
eq eqs equation et al ie eg however therefore thus hence while where when'''.split())
def candidates(src):
    texts = [clean(t) for k, (typ, t) in src.items() if not typ.startswith('式')]
    words = [re.findall(r"[A-Za-z][A-Za-z\-']*", t) for t in texts]
    cnt = Counter()
    for ws in words:
        for n in (2, 3, 4):                       # 多词术语：在全文出现两次以上的 2–4 词短语
            for i in range(len(ws) - n + 1):
                ph = ws[i:i + n]
                if ph[0].lower() in STOP or ph[-1].lower() in STOP: continue
                if any(w.lower() in ('and', 'or', 'of', 'the') for w in ph[1:-1]) and n == 2: continue
                cnt[' '.join(w.lower() for w in ph)] += 1
    terms = {p: c for p, c in cnt.items() if c >= 3}
    # 被更长短语完全覆盖、且次数相同的短语去掉
    for p in list(terms):
        if any(p != q and p in q and terms[q] >= terms[p] for q in terms): terms.pop(p, None)
    acr = Counter(a for t in texts for a in re.findall(r'\b[A-Z][A-Za-z]*[A-Z][A-Za-z0-9]*\b', t))
    for a, c in acr.items():                      # 缩写与专名（含两个以上大写字母的词）
        if c >= 2 and len(a) >= 2: terms[a] = c
    return sorted(terms.items(), key=lambda kv: -kv[1])

def numbers(s):
    s = re.sub(r'⟦M\d+⟧', ' ', s)
    s = re.sub(r'\[[\d,\s–-]+\]', ' ', s)          # 引用编号另行处理，不在这里查
    s = re.sub(r'\b(Fig(ure)?s?|Eqs?|Table|Section|Sec)\.?\s*[\dA-Z.]+', ' ', s)   # 图号、式号、节号
    s = re.sub(r'(?<=[A-Za-z])-\d', ' ', s)                       # 单位里的指数，如 Nm-1
    return [n.replace(',', '') for n in re.findall(r'(?<![A-Za-z\d])\d[\d,]*(?:\.\d+)?', s)]

if not CHECK:
    src = load_src(); g = load_glossary()
    new = [(t, c) for t, c in candidates(src) if t not in g]
    with open(GL, 'a' if g else 'w', encoding='utf-8') as f:
        if not g: f.write('# 英文 ||| 中文译法（留空不检查；写 - 表示不需要统一）\n')
        for t, c in new: f.write(f'{t} ||| \n')
    print(f'{GL}: 新增候选术语 {len(new)} 条，已有 {len(g)} 条。先把需要统一的填上译法，再动笔翻译')
    sys.exit()

src = load_src(); g = {k: v for k, v in load_glossary().items() if v and v != '-' and not k.startswith('#')}
zh = {}
for line in open(ZHF, encoding='utf-8'):
    if '|||' in line: k, v = line.rstrip('\n').split('|||', 1); zh[k] = v
bad_terms, bad_nums = [], []
for bid, (typ, en) in src.items():
    if bid not in zh or typ.startswith('式'): continue
    t, e = zh[bid], clean(en).lower()
    for term, target in g.items():
        pat = r'(?<![a-z])' + re.escape(term.lower()) + r's?(?![a-z])'
        alts = [x.strip() for x in target.split('/')]          # 允许“中文/另一写法”
        if re.search(pat, e) and not any(a and a in t for a in alts):
            bad_terms.append((bid, term, target))
    tn = set(numbers(t))
    miss = [n for n in numbers(en) if n not in tn and n.rstrip('0').rstrip('.') not in tn]
    if miss: bad_nums.append((bid, sorted(set(miss))))
print(f'术语：检查 {len(g)} 条，不一致 {len(bad_terms)} 处')
for bid, term, target in bad_terms: print(f'  {bid}: “{term}” 应译作“{target}”')
print(f'数字：{len(bad_nums)} 个块里有原文数字没出现在译文中（核对是否漏译；改写成中文数字的可忽略）')
for bid, ms in bad_nums: print(f'  {bid}: {", ".join(ms)}')
