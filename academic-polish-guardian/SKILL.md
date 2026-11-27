---
name: academic-polish-guardian
description: 学术语言润色（中英文学术文本）。按"最小编辑"原则逐句修正语法、术语、语气与表达问题，同时用机器校验保证事实不变（数字、单位、引用、图表指向）与结论强度守恒（限定词不升级不降级）。每处修改带原文/改文/类型/理由，第三方可复核。适用：论文摘要与正文、学位论文、基金申请书、审稿回复的润色与校对任务。纯内容问答、翻译整写或重写任务不要触发本 Skill。
---

# 学术语言润色：改得对、说得像、没改坏、讲得清

## 四条硬标准（来自评分点，违反任何一条即失败）

1. **改得对**：真实消除语法/句法/搭配/标点错误，不允许"换一种说法掩盖"——每处修改必须能说出是什么错误、为什么错。
2. **说得像**：符合目标文体与语域（见 `assets/style_guide.md`）；同一概念全篇一种写法，以术语表为准。
3. **没改坏**：数字、单位、引用编号、图表指向**逐字守恒**；限定强度守恒——`may` 不能变 `demonstrate`，`correlated` 不能变 `lead to`，数据不能"顺手优化"。这条由 `scripts/check_preservation.py` 机器校验，不是自觉。
4. **讲得清**：每处修改 = 原文片段 + 改文片段 + 类型（`assets/edit_types.json`）+ 理由，四要素齐全；拿不准的不改，列入 `human_review`。

## 九步工作流

### 1. 读取任务与约束

读 `/input/case.json` 与 `task.md`，确认：目标产物（润色后全文+修改说明）、目标文体（期刊/学位论文/基金/审稿回复/摘要）、目标语言、指定章节范围、任务自带术语表或风格规则。工作区 `/app/work`，最终产物放 `/app/output`。

### 2. 读取原文，建立事实基线

把要润色的原文（纯文本/Markdown/LaTeX/段落包）存到工作区，运行：

```
python scripts/extract_facts.py --text work/original.txt --out work/facts_original.json
```

得到数字+单位、引用、图表、缩写四类清单——这是"没改坏"的对照基线。**读实际文件，不要凭标签猜内容。**

### 3. 建立术语表

任务给了术语表就用任务的；没给就边读边建：每个专业概念记 canonical 写法、缩写、可接受变体、禁用写法，格式见 `assets/example_glossary.json`。特别注意：同一材料/方法的多种写法（如 `Co(CO3)0.5OH` vs 全水合式）、中英术语对照、缩写首次定义。

### 4. 逐句诊断，先列问题再动手

逐句读原文，为每处问题建一条修改记录（格式见 `assets/example_edits.json`）：

- `original_span`：原文中**逐字唯一**的片段（不够唯一就加长上下文）；
- `type`：从 `assets/edit_types.json` 选（主谓一致/时态/语态/冠词/介词/单复数/悬垂/拼写/标点/长句/术语/缩写/语气/人称/冗余/中式英语/清晰度/一致性）；
- `severity`：error（硬错误，必改）/ style（文体，应改）/ choice（可选，需额外说明）；
- `reason`：一句话说清为什么错、为什么这么改。

**最小编辑原则**：只改有问题的部分，不重写整段；句式没问题的句子不动。拿不准是否算错误的（如作者风格选择），不改，记入 `human_review`。

### 5. 守住强度与事实

改每一句时对照 `assets/hedging_lexicon.json`：限定词只许同 tier 内替换（如 `indicate→suggest`，并在理由中注明）；禁止跨 tier（`may→show`、`suggest→demonstrate` 都是改坏）。因果词（therefore/due to/lead to）与相关词（correlate/accompany）的区分保持原样。数字、单位、化学式、引用编号、图表号一律逐字保留。

### 6. 应用修改（机器逐字核验）

```
python scripts/assemble_polish.py --case /input/case.json --original work/original.txt \
    --edits work/edits.json --glossary work/glossary.json \
    --lexicon assets/hedging_lexicon.json --out /app/output
```

每处 `original_span` 必须在当前文本中逐字唯一命中才替换——摘录有误或被前序修改覆盖时会报 failed，**回去核对原文重新摘录**，不许凭印象改写。

### 7. 跑两道机器校验（assemble 自动执行，也可单独跑）

- `check_preservation.py`：数值+单位多重集、引用集合、图表指向集合、限定词 tier、因果/方向词、缩写定义——任一 error 都必须修；
- `check_terminology.py`：同一概念多种写法、缩写重复定义/未定义、禁用写法。

出现 error：回到第 4 步修对应 edit，直到 0 error。warning 逐条过目，合理的在报告中说明。

### 8. 回读改后全文

机器校验通过后，自己通读 polished 全文一遍：语气是否统一、连接是否顺、有没有改出新错误。发现新问题 → 补 edit 记录，重跑第 6–7 步（修改记录必须与实际文本一致，不许改完文本忘记录）。

### 9. 组装交付

`/app/output` 应包含：

- `result.json`：case_id、status（success/partial/needs_fix/failed）、统计、文件清单、human_review、uncertainty、sources；
- `polished.md`：润色后完整文本（可直接使用）；
- `edits.csv`：逐条修改清单（id/位置/类型/严重级/原文/改文/理由/是否生效）；
- `preservation_report.json` + `terminology_report.json`：两道校验的全量结果；
- `report.md`：人读报告（修改对照 + 校验结论 + 需人工确认项）。

## 异常处理

| 情况 | 处置 |
|---|---|
| 输入含公式/LaTeX/引用混杂 | 公式、参考文献列表、图表标题默认**不润色**，只润色正文句；在 uncertainty 注明范围 |
| 超长输入 | 按章节分批，每批独立走第 4–7 步，术语表跨批共享并累积 |
| 术语表内部冲突（任务给的表自相矛盾） | 不擅自选择，列入 human_review，按首次出现写法暂统一并注明 |
| 目标文体不明 | 按期刊论文处理，记入 uncertainty |
| 材料不足/事实存疑（如数字疑似笔误） | **不改数字**，列入 human_review 让作者确认 |
| 原文与任务要求冲突（如要求删某段但事实在段中） | 先保事实，冲突写入 uncertainty |
| 编码混乱/乱码 | 先修编码再处理；无法修复的片段原样保留并注明 |

## 提交前自查清单

- [ ] 每处修改四要素齐全，type 来自受控词表
- [ ] preservation 校验 0 error（数字/引用/图表/强度全部守恒）
- [ ] terminology 校验 0 error（全篇一种写法）
- [ ] 失败的 edit 全部修复或在报告中说明原因
- [ ] human_review 列出所有拿不准的（宁可多列，不可擅自改）
- [ ] result.json 含 case_id，status 诚实（有未解决问题就写 partial/needs_fix）
- [ ] 没有新增材料外的事实、数字、引用
