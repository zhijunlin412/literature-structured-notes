---
name: intro-guardian
description: 引言与相关工作写作（中英文学术论文）。从事实底稿与文献库出发，按"背景—分组相关工作—空白推导—贡献对照"四段成稿。每条对他人工作的转述必须逐字绑定该文献原文，研究空白必须从已引文献缺口推出，每条贡献必须挂到底稿的真实结果锚点，空话套话与材料外数据由脚本拦截。适用：论文引言、相关工作、研究现状综述段落的起草与核对。纯翻译、润色、文献调研任务不要触发本 Skill。
---

# 引言与相关工作写作：立得住、分得清、说得实、对得上

## 运行预算纪律（先读）

平台预算：64 次模型请求、900 秒、单次回复 16384 token。

1. **必读只有本文件**；`assets/draft_schema.json` 是结构契约读一次，`boilerplate_phrases.json` 由脚本使用、不必读。
2. **模型只写 draft.json 一份补丁**（背景句、分组与转述、空白、贡献）；成稿排版、引用编号、文献表、报告全由脚本生成——不要自己誊写带编号的成稿。
3. **脚本产物只读**：清单、校验报告不许改写；有异议改 draft.json 重跑。
4. 写转述时从文献库 text 里**复制**证据句，不从记忆里写。

## 四条硬标准

1. **立得住**：背景必须指向真实研究脉络与具体问题。空话套话（"近年来受到广泛关注"类）单独出现 = error；要么删掉，要么同句带引用或具体对象。
2. **分得清**：相关工作必须按问题/方法路线/技术路线**分组**，每组有同维度比较句（取舍、适用条件、局限）；不接受逐篇摘要拼接。每条转述必须逐字绑定**被引那一篇**的原文（`evidence.quote` 逐孔子串核验，引错篇也是 error）。
3. **说得实**：空白必须 `derived_from` 已引文献的缺口并写明推导依据；属于作者判断的标 `author_judgment`，不许伪装成文献结论。
4. **对得上**：每条贡献挂到底稿锚点（方法/结果/图表），贡献中的**数字必须能在锚点事实中找到**——材料里没有的数据不许出现。

## 六步工作流（按价值落盘）

### 1. 读任务与材料

读 `/input/case.json` 与 `task.md`：体裁、语言、目标期刊、篇幅。把事实底稿与文献库放进 `/app/work`，读实际文件，不凭标签猜内容。材料缺什么（如文献库为空、某篇没有摘要文本）记入 uncertainty，不编。

### 2. 独立清点（外部分母）

```
python scripts/parse_materials.py --fact-draft work/fact_draft.json --library work/library.json --out work/inventory.json
```

清点底稿锚点、文献条目、元数据缺失、证据文本为空的篇目。若材料本身缺元数据或文本，列入 human_review，不补造。

### 3. 第一批落盘：骨架成稿

先写一版**完整但可粗**的 draft.json：背景 2-3 句、按路线分 2-3 组（每组至少 1 篇、转述带逐字 quote、写比较句）、1-2 条空白、全部贡献挂锚点。立即跑第 5 步的校验+组装，让 `/app/output/result.json` 尽早是完整部分结果。

### 4. 第二批增强：深化比较与覆盖

补充漏引的文献、深化组内比较（同一维度上各工作的取舍）、完善空白推导链与贡献-结果对照。每改一版重跑校验，覆盖 result.json。

### 5. 机器校验

```
python scripts/check_intro.py --draft work/draft.json --fact-draft work/fact_draft.json \
    --library work/library.json --phrases assets/boilerplate_phrases.json --out work/check_report.json
```

六类校验：转述逐字绑定（位置级）、空话检测、空白推导链、贡献数字锚定、引用覆盖（分母=库内全部文献）、分组质量。error 必须修到 0；warning 逐条在报告里说明。

### 6. 组装交付

```
python scripts/assemble_intro.py --case /input/case.json --draft work/draft.json \
    --library work/library.json --check work/check_report.json --out /app/output
```

产出：`introduction.md`（四段成稿+按首现顺序编号的文献表）、`result.json`（case_id、status、evidence_map、gap_derivations、contribution_anchors）、`report.md`（转述-证据对照、推导链）。

## 异常处理

| 情况 | 处置 |
|---|---|
| 文献库为空 | 不写相关工作，status=partial，在 uncertainty 说明；背景只写有底稿支撑的内容 |
| 某篇文献只有题录没有文本 | 可以引用（编号+题录），但**不许转述其内容**；在 uncertainty 注明"未能核验转述" |
| 底稿没有可挂的结果锚点 | 贡献只写方法层面并注明"结果待补"，不许编数据 |
| 空白推不出来 | 标 author_judgment 并写清是作者判断；不许硬凑 derived_from |
| 目标期刊格式未知 | 文献表按 GB/T 7714 期刊格式，记入 uncertainty |
| 材料与任务冲突（如要求引用库外文献） | 库外文献标"未核验"，列入 human_review |
| draft.json 结构不合法 | 脚本报 FATAL 不崩；按 draft_schema.json 修正重跑 |

## 提交前自查清单

- [ ] 第一批骨架已落盘过完整 result.json（防超时白卷）
- [ ] 每条转述的 quote 逐字来自被引那一篇（check 通过）
- [ ] 背景无空话句（或已带引用/具体对象）
- [ ] 每条空白有 derived_from 链或标 author_judgment
- [ ] 每条贡献挂锚点，数字全部能在锚点事实中找到
- [ ] 库内文献使用与否都有交代（未引用的在报告说明原因）
- [ ] 没有誊写脚本产物；status 诚实
