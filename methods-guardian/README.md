# methods-guardian

把散落的实验材料（配置、日志、代码、实验记录）整理成**可复核**的方法与实验章节：写得全、写得准、做得着、说得住。

## 工作原理

```
材料目录 ──scan_materials.py──> 参数台账 inventory.json（覆盖率外部分母、冲突清单）
              │
              ▼
Agent 定点读材料，写 draft.json（每个数字一条 claim：number + 逐字 evidence + chapter_span）
              │
              ▼
check_chapter.py --stage draft   证据逐字核验 / 台账覆盖 / 冲突裁定 / 六类要素声明
              │
              ▼
Agent 写章节正文 prose.md（每个数字落在 claim span 内；缺口以【待作者确认】标注）
              │
              ▼
check_chapter.py --stage final   正文数字逐个审计（无来源数字报错）/ gap 标注核对
              │
              ▼
assemble_chapter.py ──> chapter.md（正文 + 参数溯源表 + 复现清单 + 待确认清单）+ result.json
```

## 目录

| 路径 | 说明 |
|---|---|
| `SKILL.md` | 使用说明（含运行预算纪律、工作流程、输出契约、异常处理） |
| `scripts/scan_materials.py` | 材料清点与参数台账构建（纯标准库） |
| `scripts/check_chapter.py` | 草稿/成稿两阶段机器核验（纯标准库） |
| `scripts/assemble_chapter.py` | 成稿与 result.json 组装（纯标准库） |
| `assets/draft_schema.json` | draft.json 契约 |
| `assets/element_checklist.json` | 六类要素清单（步骤/设置/参数/数据/对照/复现与限制） |
| `example/` | 最小调用示例（示意输出，非正式案例结果） |

## 设计要点

- **防补造数值**：正文每个数字必须绑定一条 claim，claim 的 evidence 必须逐字存在于材料文件，数字必须与证据、台账一致。
- **覆盖分母来自外部**：台账由脚本从材料构建，tier A 每条必须被引用或显式说明不用。
- **冲突不猜测**：同名参数不同取值由台账检出，Agent 裁定并说明依据，无法裁定则上报作者。
- **缺口显式**：材料缺失一律登记 gap 并在正文标注；有未解决 gap 时 result.json 状态为 partial。
- **损坏输入不崩溃**：畸形 JSON、缺失目录等以退出码 2 干净失败。

## 已验证

- 真实演示：以 PMC8429493（CC-BY）实验记录为材料生成中文方法章节，12/12 claim 通过证据核验，正文 15/15 数字有来源，注入的记录冲突被检出并裁定。
- 破坏测试：8 类注入错误（写错数字、编造证据、数字与证据不符、与台账不一致、缺 gap 标注、冲突未裁定、台账漏交代、要素未声明）全部被拦截；2 项损坏输入测试干净退出。
