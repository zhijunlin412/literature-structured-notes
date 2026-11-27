# pdf-document-parser

把科研论文 PDF 解析成**结构化结果**：正文逐字提取、双栏/多栏阅读顺序修正、章节层级识别、表格/公式/图表题注/参考文献结构化，并把每块内容回链到原文页码与区块坐标。

## 为什么需要它

`pdftotext` 直接输出有两个典型问题：

1. **双栏串栏**：左右两栏交错成一句，读者读不通。
2. **页眉页脚混入正文**：期刊名、页码、水印和正文混在一起。

本 Skill 用**词级坐标**（`pdftotext -bbox`）做版式识别，把这两类问题确定性地修正，再交给模型做语义判断。

## 四条硬标准

| 标准 | 含义 |
|------|------|
| 提得全 | 正文、题注、脚注、参考文献逐字提取，页眉页脚分离 |
| 排得对 | 多栏内容按原版面顺序输出，不串栏、不错行 |
| 拆得清 | 章节层级、表格行列、公式上下标还原成结构 |
| 核得回 | 每块回链页码 + 区块坐标，读不出的如实标注 |

## 结构

```
SKILL.md                      # 方法、输入/输出契约、异常处理、自查
scripts/pdf_parse.py          # 确定性解析器（纯标准库）：版式分析 + 阅读顺序修正 + 结构识别
scripts/validate_parse.py     # 校验 + 组装 result.json
assets/fields.json            # 输出字段字典与锚点格式
assets/example_parse.json     # 示意示例（非任何正式案例答案）
```

## 流程

```
PDF
  └─ pdf_parse.py  →  layout.json（块 id + 锚点 + margin/order_suspect 标记） + parsed.md（阅读顺序重排）
        └─ Agent 修序（order_suspect 块按 pdftotext -x -y -W -H 裁剪重取，记 change_record）
              └─ Agent 精修  →  parse_spec.json（章节/段落/表格/图/公式/参考文献）
                    └─ validate_parse.py  →  result.json（校验组装）
```

## 核心算法（scripts/pdf_parse.py，v2）

- **词级坐标**：`pdftotext -bbox` stdout 模式取每个词的 `(xMin, yMin, xMax, yMax)`（无中间文件、非 ASCII 路径自动暂存）；扫描件用 tesseract TSV 取同样坐标（中间件放临时目录根、带进程号前缀）。
- **栏检测**：对页面中部区域（避开页眉页脚）的词横坐标做**间隙聚类**，识别栏数。
- **阅读顺序**：栏内自上而下、栏间自左而右。
- **噪声过滤**：旋转文字（宽 ≪ 高）与左边缘水印单独剔除；页眉页脚按行级位置标记 `margin`，不会并入段落。
- **段落合并**：按纵向间距 + 首行缩进 + 断词连接把行并成段（`demon-strate` 正确接合）；题注续行自动吸收。
- **结构识别**：标题（编号模式 + 词高）、题注（`Fig.`/`Table`/`图`/`表`）、公式（数学符号密集）、参考文献（References 之后逐条）。
- **上下标重建**：按词高与基线偏移识别上下标，重建为 Unicode（Fe³⁺、H₂O、CO₃²⁻）。
- **串栏标记**：行起点分散在两个相距很远的 x 簇的块标 `order_suspect`，由 Agent 按 SKILL.md 第 3 步用 `pdftotext` 裁剪参数按栏重取修复，修复记入 `change_record`。
- **锚点**：每块保留 `id + page + bbox`，可独立复核。

## 已知限制

- 首页"通栏标题/摘要 + 下方双栏正文"的混排页，仅凭坐标无法区分通栏正文与双栏（两端对齐英文的词间距与栏间距量级相同）——提取器标 `order_suspect`，由 Agent 按栏裁剪重取修复。
- 表格检测偏保守（宁可漏表格，不把正文误判成表格）。
- OCR 依赖评测环境的 ocr-tool（tesseract）与语言包。

## 依赖

`pdftotext`（pdf-text-tool）；扫描件另需 `pdftoppm` + `tesseract`（pdf-render-tool + ocr-tool）。脚本仅用 Python 标准库。

## 许可证

MIT
