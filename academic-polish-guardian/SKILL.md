---
name: academic-polish-guardian
description: 学术语言润色（中英文学术文本）。按"最小编辑"原则逐句修正语法、术语、语气与表达问题，同时用机器校验保证事实不变（数字、单位、引用、图表指向）与结论强度守恒（限定词不升级不降级）。每处修改带原文/改文/类型/理由，第三方可复核。适用：论文摘要与正文、学位论文、基金申请书、审稿回复的润色与校对任务。纯内容问答、翻译整写或重写任务不要触发本 Skill。
---

# 学术语言润色：改得对、说得像、没改坏、讲得清

## 运行预算纪律（先读，违反会被超时砍成白卷）

平台预算：64 次模型请求、900 秒、单次回复 16384 token。经验教训：Skill 每让模型多读一份材料、多走一轮流程，答题预算就少一份；单次工具返回要小，中间产物能不进上下文就不进。

1. **必读只有本文件**；`assets/` 下的词表、风格指南、示例是**按需查阅**，不要整个读进上下文（查 edit_types 用 grep 定位类型名即可）。`assets/sample_polish_fchem.json` 是格式参照，看一眼 edits 数组的第一条就够。
2. **模型只写 edits.json 这一小份"答案补丁"**；润色全文、CSV、报告全部由脚本确定性生成，不要自己誊写润色全文进 result.json。
3. **脚本输出是只读的**：fact 基线、校验报告由脚本生成，不许改写、不许誊抄；发现脚本结果与你的判断冲突，改 edits.json 重跑，不要改脚本产物。
4. 命令输出都已压缩（只打印摘要与错误）；不要把大文件 cat 进对话。

## 四条硬标准（来自评分点，违反任何一条即失败）

1. **改得对**：真实消除语法/句法/搭配/标点错误，不允许"换一种说法掩盖"——每处修改必须能说出是什么错误、为什么错。
2. **说得像**：符合目标文体与语域（查 `assets/style_guide.md` 对应一节）；同一概念全篇一种写法，以术语表为准。
3. **没改坏**：数字、单位、引用编号、图表指向**逐字守恒**；限定强度守恒——`may` 不能变 `demonstrate`，`correlated` 不能变 `lead to`。机器校验分两层：**片段级**（每处修改内部比对，数字不许搬家）与**全篇级**（多重集对照）。
4. **讲得清**：每处修改 = 原文片段 + 改文片段 + 类型（`assets/edit_types.json`）+ 理由，四要素齐全；拿不准的不改，列入 `human_review`。

## 九步工作流（按价值落盘：最值钱的先写进正式结果）

### 1. 读取任务与约束

读 `/input/case.json` 与 `task.md`，确认：目标产物、目标文体（期刊/学位论文/基金/审稿回复/摘要）、目标语言、**指定范围**（哪些章节必须逐段处理）、任务自带术语表或风格规则。工作区 `/app/work`，最终产物放 `/app/output`。

### 2. 建事实基线（一次脚本调用）

```
python scripts/extract_facts.py --text work/original.txt --out work/facts_original.json
```

只看打印的摘要行（数值/引用/图表/缩写各多少），不要打开整个 JSON。

### 3. 建术语表

任务给了就用任务的；没给就边读边建（格式见 `assets/example_glossary.json`，只读这一个示例）。重点：同一材料/方法的多种写法、缩写首次定义、任务给的风格规则中的禁用写法。

### 4. 第一批：硬错误修改（先落盘）

先只诊断 **severity=error** 的硬错误（语法、拼写、介词、单复数、缺谓语），写进 `work/edits.json`（格式见 `assets/example_edits.json`），并填 `reviewed_units`（已审阅的段落清单）。**立即跑一次组装**（第 6 步命令），让 `/app/output/result.json` 尽早是一份完整的部分结果——超时也能交。

### 5. 第二批：文体与一致性修改（增量增强）

再补 severity=style/choice 的修改（语气、冗余、中式英语、术语统一、长句），追加进 edits.json 的 edits 数组，重跑组装覆盖 result.json。每批都落盘，价值高的永远先落。

### 6. 应用修改（机器逐字核验 + 片段级绑定）

```
python scripts/assemble_polish.py --case /input/case.json --original work/original.txt \
    --edits work/edits.json --glossary work/glossary.json \
    --lexicon assets/hedging_lexicon.json --out /app/output
```

三层机器防线，任何一层报错都必须回改 edits.json 重跑，不许绕过：

- **逐字应用**：`original_span` 必须在当前文本中逐字唯一命中；找不到/不唯一 → 该修改 failed，回原文重新摘录；
- **片段级绑定**：每处修改的 original_span 与 revised_span 内部比对数值、引用、图表、限定 tier——数字不许搬位置、`may` 不许消失，违规的修改直接**拒绝应用**；
- **全篇级校验**：preservation（多重集对照）+ terminology（术语统一、禁用写法、次数对照）。

### 7. 覆盖率自查（分母来自原文，不来自你改了几处）

result.json 里的 `units_total` 是脚本按原文独立清点的段落数，`reviewed_units` 是你声明审阅过的。两者必须相等——没问题的段落也要列入 reviewed_units 并注明"看过、无需改"。**自报 100% 不算数，分母永远是原文本身。**

### 8. 回读改后全文（一轮即可）

机器校验通过后通读 polished.md 一遍：语气统一、连接顺、没改出新错误。发现新问题 → 补进 edits.json 重跑第 6 步。**不许直接改 polished.md**——文本与修改记录必须永远一致。

### 9. 交付核对

`/app/output`：`result.json`（case_id、status、stats 含 units_total/units_reviewed、human_review、uncertainty、sources）、`polished.md`、`edits.csv`、两份校验报告、`report.md`。确认 result.json 里的 status 诚实：有 failed 修改就是 partial，有校验 error 就是 needs_fix，不许写成 success。

## 异常处理

| 情况 | 处置 |
|---|---|
| 输入含公式/LaTeX/参考文献列表 | 这些默认**不润色**，只润色正文句；在 uncertainty 注明范围 |
| 超长输入 | 按章节分批，每批走完第 4–6 步立即落盘，术语表跨批共享累积 |
| 术语表内部冲突 | 不擅自选择，列入 human_review，按首次出现写法暂统一并注明 |
| 目标文体不明 | 按期刊论文处理，记入 uncertainty |
| 数字疑似笔误 | **不改数字**，列入 human_review 让作者确认 |
| 原文与任务要求冲突 | 先保事实，冲突写入 uncertainty |
| edits.json 字段缺失/类型错 | 脚本报 failed 并继续，不崩；修好重跑 |
| 编码混乱/乱码 | 先修编码再处理；无法修复的片段原样保留并注明 |

## 提交前自查清单

- [ ] 第一批硬错误已落盘过一份完整 result.json（防超时白卷）
- [ ] 每处修改四要素齐全，type 来自受控词表
- [ ] 片段级绑定 0 拒绝；全篇校验 0 error
- [ ] reviewed_units == units_total（含"看过无需改"的段落）
- [ ] human_review 列出所有拿不准的（宁可多列，不可擅自改）
- [ ] 没有誊写脚本产物、没有直接手改 polished.md
- [ ] 没有新增材料外的事实、数字、引用
