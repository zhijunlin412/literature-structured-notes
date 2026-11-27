---
name: pdf-document-parser
description: 把科研论文 PDF 解析成**结构化结果**（章节层级、段落、表格、公式、图表题注、参考文献），修正双栏/多栏阅读顺序、分离页眉页脚，并把每个解析块回链到原文页码与区块坐标。当任务要求"文献文档解析 / PDF 解析 / 文字提取 / 多栏阅读顺序修正 / 表格解析 / 章节结构识别 / 公式与特殊字符提取 / 扫描版 OCR"时使用；输入是一份真实科研 PDF，输出是可复核、可继续处理的结构化解析结果。不用于理解论文科学含义、生成笔记总结、学术写作或语言润色。
---

# pdf-document-parser

## 用途

把一份真实科研 PDF 解析成结构化结果：正文逐字提取、多栏阅读顺序修正、章节层级识别、表格/公式/图表题注/参考文献结构化，并把每块内容回链到原文页码与区块坐标。核心不是"给一段看起来像全文的文本"，而是让解析结果**可复核、可继续处理**。

## 何时使用 / 何时不使用

- 使用：任务要求"文献文档解析 / PDF 解析 / 文字提取 / 多栏顺序修正 / 表格解析 / 章节识别 / 公式提取 / OCR"。
- 不使用：理解论文科学含义、做笔记总结、学术写作、语言润色。这些交给相邻工具。

## 四条硬标准（对应评分，做对与否就看这四条）

1. **提得全**：正文、图表题注、脚注、参考文献逐字提取；不把页眉页脚混进正文。
2. **排得对**：双栏/多栏/跨栏/跨页内容按原版面顺序输出，不串栏、不错行、不把相邻段落拼成一句。
3. **拆得清**：章节层级、表格行列与单元格、公式上下标与希腊字母还原成可继续处理的结构。
4. **核得回**：每段文字、每张表格、每张图指回原文页码与区块；读不出的部分如实标注，不靠猜补齐。

## 输入契约（执行时按路径实际读取）

- `/input/case.json`：`case_id`、任务说明、材料路径、模板/格式约束、`output_contract` 字段。
- `/input/task.md`：本题提交约定（以它为准）。
- 论文 PDF：按 `case.json` 给的真实路径读取。**PDF 直接给原文件，没有预提取的文字层。**

## 输出契约（全部落在 `/app/output`）

1. `result.json`：结构化主结果，含 `case_id`、`status`、`document_meta`、`sections`、`paragraphs`、`tables`、`figures`、`formulas`、`references`、`headers_footers`、`sources`、`uncertainty`、`change_record`，并补齐 `task.md` 要求的全部 `output_contract` 字段。
2. `parsed.md`：按阅读顺序重排后的正文，每块带 `<!-- 块id 页码 -->` 注释（供人核对、供机器定位）。
3. `layout.json`：确定性解析中间结果——每个块有稳定 `id`（H 标题 / P 段落 / C 题注 / T 表格 / F 公式 / R 参考文献）、类型、`page + bbox` 锚点与三种标记：`margin`（页眉/页脚）、`order_suspect`（可能串栏）、`continues_next_page`（跨页未完）。供独立复核。

字段与锚点规范见 `assets/fields.json`。

## 方法（七步，先想后做）

1. **读输入**：读 `case.json` 与 `task.md`，确认 PDF 真实路径与输出字段要求。
2. **确定性解析**：`python scripts/pdf_parse.py --pdf <PDF> --out work/parse` 产出 `layout.json` 与 `parsed.md`。脚本完成：词级坐标提取（`pdftotext -bbox` stdout 模式；全文无文字层时自动走 `pdftoppm` + `tesseract` OCR）→ 栏检测（中部区域 x 坐标间隙聚类，滤除旋转水印与左边缘词）→ 阅读顺序（栏内自上而下、栏间自左而右）→ 行合并成段（纵向间距 + 首行缩进 + 断词连接）→ 题注续行吸收 → 标题/题注/表格/公式/参考文献识别 → 上下标 Unicode 重建（Fe³⁺、H₂O、CO₃²⁻）→ 页眉页脚行级分离。
3. **修序补段**：逐个检查 `order_suspect` 块（混排页"通栏标题/摘要 + 双栏正文"坐标无法区分，会发生串栏）。修法：用 `pdftotext` 裁剪参数按栏重取——`-f <页> -l <页> -x <左> -y <上> -W <宽> -H <高>` 分别取左栏、右栏文本，按"左栏读完再读右栏"重排，替换串栏块的文本并拆分/合并块；被题注吸收误吞的正文行还回原位。栏边界从 `layout.json` 的 bbox 估计（栏间空隙通常在页面中部）。**所有修改写进 `change_record`**（哪个块、改了什么、依据），修复后的块集记为 `layout_fixed.json`，后续以它为准。无法确定栏边界的块标 `column_ambiguous`，不猜顺序。
4. **结构精修**：在修复后的块集上核对章节层级（编号与缩进）、表格行列归属（合并单元格、跨页续表如实标注）、公式编号；参考文献逐条保留原文，不补造缺失条目。三个已知坑要专门核对：
   - **真图注 vs 假图注**：`Fig. 4 | …` 开头的整段是图注；但正文中"Figure 4a contains…"这样以图号开头的完整句子是正文（字号与正文相同），不能划进题注，也不能因它重复而把内容删重。
   - **坐标轴上标丢失**：图内坐标轴 `10⁰ 10¹ 10²…` 从文字层抽出来常变成 `100 101 102…`，这不是原文如此，如实标注"上标可能丢失"，不猜数值。
   - **跨页续段**：某栏正文开头是上一页最后半句的延续（无句首大写/无缩进），与上一页 `continues_next_page` 的块合并，合并记入 `change_record`。
5. **填 `parse_spec.json` + 答题**：按 `assets/fields.json` 填 `document_meta`、`sections`、`paragraphs`、`tables`、`figures`、`formulas`、`references`、`headers_footers`、`sources`、`uncertainty`、`change_record` 与 `task.md` 要求的 `output_contract` 字段；每块带 `page + bbox` 锚点与来源块 `id`；读不出的部分如实标注，不靠猜补齐。**若 case 附带问题**（"回答问题，也给出依据"）：逐题回答并带证据（块 id + 页码 + 原文引文，含单位、定义、置信区间等完整口径）；原文没点名、补充材料没给的，如实写"未报告"，不猜。**增量存盘**：解析完成后立即先写一版全字段占位 `result.json`（未做的部分标 `partial`），再按正文结构→问题回答→表格公式细节的优先级填充——排在最后的东西最先被超时砍掉，占位版保证任何时刻都有诚实可交的结果。
6. **校验组装**：`python scripts/validate_parse.py --spec parse_spec.json --out /app/output --case-id <case_id>`；校验失败逐项修复重跑，直至通过。
7. **自查交付**：把 `layout.json`/`layout_fixed.json`、`parsed.md` 一并放入 `/app/output` 供复核；按下文自查清单逐项过。

## 使用脚本

- `scripts/pdf_parse.py`：确定性解析器 v2（仅标准库）。`pdftotext -bbox` 走 stdout 模式（无中间文件，自动暂存非 ASCII 路径）；字节捕获后手动 UTF-8 解码（避免区域编码问题）；OCR 中间件放临时目录根、带进程号前缀、用完即删。产出带块 id、锚点与 `margin`/`order_suspect`/`continues_next_page` 标记的 `layout.json` 与 `parsed.md`。
  - 调用：`python scripts/pdf_parse.py --pdf <file.pdf> --out <dir>`
  - 可选 `--ocr`：强制 OCR 流程（扫描件）。
- `scripts/validate_parse.py`：读 Agent 产出的 `parse_spec.json`，校验必填字段与锚点，组装 `result.json`。

## 异常处理

- 加密/权限受限 → 说明无法解析；不补造数据。
- 无文字层扫描件 → 脚本自动渲染 + OCR；OCR 错字后处理，仍不确定的如实标注。
- 乱码/缺字/特殊字符 → Unicode 规范化；读不出的标 `U+XXXX` 或占位，不猜。
- 双栏错序/跨页续表/图片型表格 → 记录到 `change_record`，结论降级为"部分完成"。
- 混排页串栏（`order_suspect` 块）→ 按第 3 步用 `pdftotext -f/-l/-x/-y/-W/-H` 裁剪重取并记入 `change_record`；无法确定栏边界的块如实标 `column_ambiguous`，不猜。
- 题注续行吸收把正文行卷进题注（`order_suspect` 同时出现）→ 还原文本到正文块并记录。
- 预算紧张（64 次请求 / 900 秒）→ 先交全字段占位版 `parse_spec.json`（未完成部分标 `partial`），再按章节标题→正文→表格公式→参考文献的优先级填充；任何时刻保证可交的诚实部分结果。
- 非中文论文 → 按原文语言输出，不翻译改写。

## 自查（提交前逐项过）

1. 是否逐字提取？页眉页脚/页码是否都标了 `margin` 且没混进正文？
2. 每个 `order_suspect` 块是否都检查过？串栏是否按栏裁剪修复并记入 `change_record`？
3. 章节层级、表格行列、公式上下标、希腊字母是否还原？参考文献是否逐条保留？
4. 每块是否回链页码 + 区块坐标 + 来源块 id？读不出的部分是否如实标注而不是靠猜？
5. `result.json` 是否含 `case_id` 与 `task.md` 要求的全部字段？是否只提交 Skill 与资源、不含预制正式答案？

## 最小调用示例

见 `assets/example_parse.json`（**示意示例**，非任何正式案例答案）。流程：读 PDF → `pdf_parse.py` 做版式分析 → 按字段字典产出 `parse_spec.json` → `validate_parse.py` 校验组装 → 自查 → 交付。
