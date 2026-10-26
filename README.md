# paper-decoder · 论文翻译解读

一个 Claude Code skill：把 arXiv 论文做成可以直接打印的中英双语精读版 PDF。

## 成品包含什么

- **段首对齐的双语正文**：左半页是原版 PDF 按段落矢量裁切（图、公式、表格保持原样），右半页是中文译文，每段译文的第一行和原文这一段的第一行齐平。被分栏或分页切开的段落会拼回一段再对照，不会出现半段原文、右边空着的行。行间公式不在译文里重抄，右栏同一位置写这条公式的解释。单栏论文改为按阅读顺序重排：一段原文完整排完再接译文，原文不会被译文或原版分页切断，图表保持原样、位置不变。
- **表格译文**：每张表按原表结构重排成一张中文表（表头、行名、单位译成中文，数字、粗体、下划线、横线保留），放在中文表题下面。
- **概念注释**：生僻术语在段旁加灰底注释框；需要大段解释的概念单独插一整页“延伸讲解”，带示意图和数值例子。
- **参考文献**：按原文顺序重排成两栏，不浪费版面。
- **论文解读**：全文最后附一份篇幅与原文正文相当的解读，10–15 张 TikZ/pgfplots 图，包括逐节导读、方法原理、公式逐个讲解、实验结果怎么读、局限与可做的方向、常见疑问、复现要点。

全部灰度配色，黑白打印可读。

## 安装

```bash
git clone https://github.com/Jonty-Zhang/paper-decoder ~/.claude/skills/paper-decoder
```

装好后在 Claude Code 里直接说，例如：“把 arXiv 2412.12392 这篇论文做成打印版”。

## 依赖

- macOS（版面分析用系统自带的 PDFKit，通过 `swift` 运行）
- Python 3 与 `lxml`
- [tectonic](https://tectonic-typesetting.github.io)（`brew install tectonic`）
- 字体：Times New Roman、Songti SC、Heiti SC（macOS 自带）
- 论文需要有 arXiv HTML 版（`https://arxiv.org/html/<编号>`）

## 目录

| 路径 | 作用 |
|---|---|
| `SKILL.md` | skill 主文件：成品规格、十步流程、文字要求 |
| `scripts/extract.py` | 把 arXiv HTML 拆成标题、段落、公式、图表等块，并生成待译清单 |
| `scripts/tables.py` | 抽出每张表的网格结构，列出需要翻译的单元格文字 |
| `scripts/layout.swift` | 分析原版 PDF 每页的跨栏带与双栏带，判断单栏还是双栏，记录逐行墨迹分布 |
| `scripts/lines.swift` | 按行提取原版 PDF 的文字及坐标 |
| `scripts/pdfblocks.py` | 没有 arXiv 网页版时，直接从 PDF 拆出标题、段落、图表题、公式和图形区域（PDF 模式） |
| `scripts/terms.py` | 抽候选术语建术语表；译完检查术语是否统一、数字有没有漏 |
| `scripts/latexzh.py` | 纯中文版：把 arXiv LaTeX 源码里的正文换成译文后重新编译 |
| `scripts/render_zh.py` | 纯中文版：没有源码时按原版版式重排中文，图和公式从原版裁切 |
| `scripts/anchor.py` | 把每个段落定位到原版 PDF 中它第一行的位置，这是段首对齐的依据 |
| `scripts/render.py` | 生成打印版 LaTeX：原文切片、译文、中文表格、注释、整页讲解、参考文献、解读；单栏论文按阅读顺序重排 |
| `scripts/topng.swift` | 把 PDF 页面渲染成 PNG，用于逐页检查 |
| `scripts/findtext.swift` | 查某段文字出现在 PDF 的哪几页 |
| `assets/preamble.tex` | 版式：页面、字体、字号、注释框、表格、解读的全部宏 |
| `references/translation.md` | 翻译规范：文件格式、术语、标点、译注、表格译文 |
| `references/notes.md` | 概念注释与整页讲解怎么选、怎么写 |
| `references/interpretation.md` | 文末解读的章节模板、配图规范、pgfplots 的坑 |
| `references/typography.md` | 全部版式参数的说明 |
| `references/troubleshooting.md` | 锚定、版面分析、编译中遇到过的问题与修法 |
| `examples/` | VGGT-SLAM 2.0、MASt3R-SLAM 两篇论文的注释文件和解读全文，作为篇幅和写法的参考 |

仓库里不含论文原文、译文和生成的 PDF。

## 流程概览

```bash
K=~/.claude/skills/paper-decoder
python3 $K/scripts/extract.py <name>                      # 需要 <name>.html
# 翻译：写 <name>_zh.txt
python3 $K/scripts/tables.py <name>                        # 然后填 <name>_tables_zh.txt
swift $K/scripts/layout.swift <name>orig.pdf <name>_layout.json
swift $K/scripts/lines.swift  <name>orig.pdf <name>_lines.json
python3 $K/scripts/anchor.py <name>
# 写 <name>_notes.txt 和 <name>_interp.tex
python3 $K/scripts/render.py <name> <name>orig.pdf <name>_print.tex
tectonic -X compile --keep-logs <name>_print.tex
```

每一步的细节和检查点见 `SKILL.md`。
