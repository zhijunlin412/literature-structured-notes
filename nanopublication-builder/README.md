# nanopublication-builder

把科研论文的关键结论拆成**原子断言**，绑定逐字证据片段与页码锚点，记录来源元数据，导出机器可读的 nanopub 结构（JSON-LD / CSV / 人读报告）。

## 依赖

- Python 3（脚本仅用标准库）
- `pdftotext` / `pdftoppm`（poppler）；`tesseract`（可选，扫描件 OCR）

## 使用流程（详见 SKILL.md）

```bash
# 1. 提取带段号锚点的源单元
python scripts/pdf_extract.py --pdf paper.pdf --out work/extract

# 2.（Agent）修序 → extract_fixed.json；填来源元数据；拆断言写 nanopub.json
#    格式见 assets/fields.json；关系词表见 assets/relations.json；示例见 assets/example_nanopub.json

# 3. 校验：字段/词表/证据逐孔子串/粒度/来源完整性
python scripts/validate_nanopub.py --nanopub nanopub.json --extract work/extract/extract.json \
    --relations assets/relations.json --out work/validate_report.json

# 4. 组装导出
python scripts/assemble_nanopub.py --case /input/case.json --extract work/extract/extract.json \
    --nanopub nanopub.json --validation work/validate_report.json \
    --change-record work/change_record.json --out /app/output
```

## 文件说明

| 文件 | 作用 |
|---|---|
| `SKILL.md` | 方法、输入输出契约、拆解与证据绑定规则、异常处理、自查清单 |
| `scripts/pdf_extract.py` | PDF → 带段号/页码/bbox 锚点的源单元 |
| `scripts/validate_nanopub.py` | 确定性校验（证据引用逐孔子串核验是核心） |
| `scripts/assemble_nanopub.py` | 组装 result.json / nanopub.jsonld / assertions.csv / report.md |
| `assets/fields.json` | 字段字典（输入与四种导出物） |
| `assets/relations.json` | 受控关系词表、证据类型、置信度定义 |
| `assets/example_nanopub.json` | 格式示意（非正式案例答案） |
| `assets/sample_assertions_feco.json` | 22 条真实演示断言样例（Dalton Trans., 2024, 53, 1870） |
| `assets/demo_validation.md` | 校验器实跑记录：22 条全过 + 篡改一个数字即被逐字核验抓住（演示证据） |

## 设计要点

- **拆得细**：一条断言 = 一个主体 + 一个关系（受控词表）+ 一个客体；数值进 object，条件进 conditions；`context` 解读（非证据）让卡片对人有用。
- **对得上**：证据 quote 必须逐字摘自源单元，脚本做子串核验，改写一个字都过不了。
- **追得回**：断言 id → 证据段号/页码 → 论文 DOI 全链路。
- **读得懂**：四种导出物字段固定，下游程序无需清洗。

## 限制

- 断言拆解与证据选择由 Agent 完成，脚本负责确定性核验；关系词表未覆盖时用 `reports` 兜底。
- 混排页需按 SKILL.md 第 2 步裁剪修复；图内数值（figure_table 证据）以文字指引句为准并标注。
