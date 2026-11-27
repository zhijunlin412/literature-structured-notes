# bilingual-literature-translator

把科研论文 PDF 翻译成**可核验的双语对照结果**：术语表锁定并强制执行、段号一一对应、数字/单位/公式/引用逐段核验、每段译文可指回原文页码。

## 依赖

- Python 3（脚本仅用标准库）
- `pdftotext` / `pdftoppm`（poppler）：文字层提取与页面渲染
- `tesseract`（可选）：扫描件 OCR，无文字层时自动启用；缺失则如实报告

## 使用流程（详见 SKILL.md）

```bash
# 1. 提取带段号与页码锚点的源单元
python scripts/pdf_extract.py --pdf paper.pdf --out work/extract

# 2.（Agent）修序补段 → extract_fixed.json + change_record.json
# 3.（Agent）建术语表 glossary.json，逐段翻译写 alignment.json

# 4. 术语执行核验：锁定译名是否全篇落实
python scripts/glossary_check.py --glossary glossary.json --alignment alignment.json --out work/glossary_report.json

# 5. 译文核验：覆盖率、数字单位、引用、图表引用、上下标式、长度比
python scripts/verify_translation.py --extract work/extract/extract.json --alignment alignment.json --out work/verify_report.json --checklist human_checklist.md

# 6. 组装交付
python scripts/assemble_result.py --case /input/case.json --extract work/extract/extract.json --glossary glossary.json --alignment alignment.json --verify work/verify_report.json --glossary-report work/glossary_report.json --change-record work/change_record.json --out /app/output
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 方法、输入输出契约、异常处理与自查清单 |
| `scripts/pdf_extract.py` | PDF → 编号源单元（栏检测、阅读顺序、段落合并、页边/串栏标记） |
| `scripts/glossary_check.py` | 术语执行核验（最长匹配优先） |
| `scripts/verify_translation.py` | 译文确定性核验 + 人工复核清单 |
| `scripts/assemble_result.py` | 校验并组装 `result.json` 与 `bilingual.md` |
| `assets/example_glossary.json` | 术语表格式示意（非正式案例答案） |
| `assets/example_alignment.json` | 对齐文件格式示意（非正式案例答案） |
| `assets/demo_feco_glossary.json` | 真实演示术语表（40 条，公开论文 Dalton Trans., 2024, 53, 1870；可复用为电催化领域术语表起点） |

## 中间产物格式

- `glossary.json`：`{"terms": [{"en","abbr","zh","note"}]}`；译名锁定后全篇统一，脚本强制校验。
- `alignment.json`：`{"units": [{"id","type","page","source","translation","status","note"}]}`；`status ∈ translated|partial|untranslated|skipped`；页眉页脚标 `skipped`，参考文献默认保留原文。
- `change_record.json`：修序、合并、剔除噪声的记录（哪个单元、改了什么、依据）。

## 限制

- 混排页（通栏摘要 + 双栏正文）坐标无法完全区分栏，提取器标 `order_suspect`，需按 SKILL.md 第 3 步用 `pdftotext` 裁剪参数按栏重取。
- 图片型公式/表格无法转写，标 `partial` 并说明，不猜。
- 中文译文与原文同段对照时，专有名词、材料代号、方法缩写默认保留原文（见术语表 conventions）。

## 维护

术语表可持续增补；新增术语后重跑 `glossary_check.py` 即可发现未落实处。脚本确定性、无模型依赖，可重复运行。
