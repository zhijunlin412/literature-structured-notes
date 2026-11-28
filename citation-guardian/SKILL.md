---
name: citation-guardian
description: 参考文献与引用管理（中文学术稿件为主，兼容英文）。完成文献去重（可解释判据）、编号重排与正文—列表双向同步、GB/T 7714 格式转换、来源核验与一致性检查。清单由脚本从原文独立清点，编号重排与格式化由脚本确定性完成，Agent 只做结构化、审定与语义判断。适用：稿件参考文献整理、引用编号修复、文献库去重与格式转换。纯文献调研、写作扩写任务不要触发本 Skill。
---

# 参考文献与引用管理：挂得对、编得顺、收得净、对得上

## 运行预算纪律（先读，违反会被超时砍成白卷）

平台预算：64 次模型请求、900 秒、单次回复 16384 token。

1. **必读只有本文件**；`assets/` 按需查阅（查格式模板只读 `citation_styles.json` 对应 type 一节；去重判据只读 `dedup_rules.md` 一次）。
2. **模型只写小补丁**：结构化条目 entries.json、去重决定 plan.json、claim_map.json。编号重排、正文改写、GB/T 格式化、报告全部由脚本确定性生成——**不要自己誊写重排后的正文或文献表**。
3. **脚本产物只读**：inventory、候选对、校验报告不许改写；有异议改输入 JSON 重跑。
4. 命令输出已压缩；不要 cat 大文件进对话。

## 四条硬标准

1. **挂得对**：引用标记挂在真正需要支撑的论断句后，不是整段末尾；一句多引、多句一引要分清。段末引用由脚本自动标出，处置（移动/保留+说明）必须留记录，拿不准列入 human_review。
2. **编得顺**：插入、删除、合并后编号按**首次出现顺序**重排且连续，正文标记与文末列表双向一致——由 `sync_refs.py` 完成，禁止手工改编号。
3. **收得净**：重复条目按 `assets/dedup_rules.md` 的分层判据合并，每条合并/不合并都有命中的判据编号和对比证据；同名作者的不同文献**不得**合并；预印本→正式版合并须以正式版为主条目。
4. **对得上**：每条条目尽力核验（有网络用 Crossref/DOI 查询，无网络标 unverified）；`verified` 必须附渠道+时间+比对字段，空口标 verified 会被校验报 error；正文论断与所引文献的匹配逐条写入 claim_map，证据不足的句子明确标出。

## 七步工作流（按价值落盘）

### 1. 读任务，备输入

读 `/input/case.json` 与 `task.md`：目标规范（GB/T 7714 / APA / 著者—出版年制）、指定范围、稿件与文献库文件位置。把稿件与文献库放进 `/app/work`。

### 2. 独立清点（外部分母）

```
python scripts/parse_refs.py --manuscript work/manuscript.md --library work/library.txt --out work/inventory.json
```

清单来自原文本身：引用标记（含所在句、是否段末）、条目数、**未被引用条目**、**悬空引用**——这两个数字就是后续工作的分母，不许自报。

### 3. 结构化条目（Agent 的语义工作）

把每条文献写成结构化字段（authors/title/journal/year/volume/issue/pages/doi/type），存 `work/entries.json`。有 DOI 或条件允许的，用可用工具（Crossref API、检索）核验元数据，核验记录写进 `verification` 字段（status/channel/date/evidence）；**核验不了就写 unverified，不许编**。

### 4. 第一批落盘：去重 + 重排 + 校验

```
python scripts/dedup_refs.py --entries work/entries.json --out work/dedup_candidates.json
```

审定候选对，写 `work/plan.json`（merges 带判据编号与依据；未被引用条目的取舍）。然后：

```
python scripts/sync_refs.py --manuscript work/manuscript.md --entries work/entries.json --plan work/plan.json --out-dir work/sync
python scripts/check_refs.py --manuscript work/sync/manuscript_updated.md --entries work/sync/entries_synced.json --styles assets/citation_styles.json --out work/check_report.json
python scripts/assemble_refs.py --case /input/case.json --synced work/sync/entries_synced.json --change-log work/sync/change_log.json --manuscript work/sync/manuscript_updated.md --check work/check_report.json --styles assets/citation_styles.json --out /app/output
```

跑一次完整组装，让 `/app/output/result.json` 尽早是完整的部分结果。

### 5. 第二批增强：论断匹配与位置处置

写 `work/claim_map.json`：逐条说明"这个引用支撑哪句论断、主题是否匹配"；处理段末引用告警（移动或保留+理由）；补做未完成条目的核验。把 claim_map 传进 assemble 重跑（加 `--claim-map work/claim_map.json`），覆盖 result.json。

### 6. 修复校验 error 直到归零

check 报 error（悬空、断号、缺字段、假核验）必须修：改 entries/plan 重跑第 4 步。warning 逐条过目，合理的写进报告的说明里。

### 7. 交付核对

`/app/output`：`result.json`（case_id、status、stats 含 renumber_map、merge_records、uncited_entries）、`manuscript_updated.md`、`references_gbt7714.txt`、`check_report.json`、`report.md`。status 诚实：有 error 是 needs_fix，有未决项写进 human_review。

## 异常处理

| 情况 | 处置 |
|---|---|
| 文献库字段缺失（无年份/页码） | 保留原样并在条目 note 注明；缺 GB/T required 字段会报 error，确实无法补的列入 human_review 并在 uncertainty 说明 |
| DOI 查询失败/无网络 | 标 `unverified`，不许编 DOI 或编核验结论 |
| 条目歧义（两候选都像同一篇） | decision 写 `unresolved`，不猜 |
| 编号冲突（正文 [3] 与列表第 3 条对不上语义） | 按 claim_map 语义判断后纠正映射，记录到 change_log；判断不了列 human_review |
| 稿件含图表注中的引用 | 同样纳入清点与重排；在报告中单列说明 |
| BibTeX/RIS/CNKI 导出混杂 | parse_refs 尽量解析；**BibTeX 的 key 不是正文编号**——结构化 entries.json 时必须把 key 改成正文引用号（按语义对应）；解析失败的条目原样保留并手工结构化，不丢条目 |
| plan 指向不存在的条目号 | sync_refs 会明确报 FATAL 并列出错误号；检查 entries.json 的 key 与正文引用号是否一致 |
| 同一文献中英文题名重复 | 按 dedup_rules 特殊情形合并，主条目语言按目标规范 |

## 提交前自查清单

- [ ] 第一批已落盘过完整 result.json（防超时白卷）
- [ ] 悬空引用 0、编号连续、每个标记有条目、每条目有着落（被引或列入未引用区）
- [ ] 每组合并有判据编号 + 对比证据；没有误并同名作者的不同文献
- [ ] verified 条目都有渠道+时间+比对字段；编不出的标 unverified
- [ ] 段末引用全部有处置记录或列入 human_review
- [ ] claim_map 覆盖每个引用标记；证据不足的句子已标出
- [ ] 没有手改脚本产物；result.json 的 status 诚实
