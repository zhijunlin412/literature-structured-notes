# 校验器实跑记录（演示证据，非任何正式案例答案）

以下是用 `scripts/validate_nanopub.py` 在真实演示产物上实跑的记录。
演示材料：公开论文 Dalton Trans., 2024, 53, 1870–1877（DOI 10.1039/d3dt03520d），
断言集为 `assets/sample_assertions_feco.json` 对应的完整版（22 条断言）。

## 1. 干净断言集：22 条全部通过

```
$ python scripts/validate_nanopub.py --nanopub nanopub.json \
    --extract work/extract/extract_fixed.json \
    --relations assets/relations.json --out work/report.json
OK assertions=22 errors=0 warnings=0
```

```json
{"assertions": 22, "errors": [], "warnings": [], "clean": true}
```

## 2. 篡改测试：引文改一个数字即被抓住

把断言 A3 的证据引文中的 `10 mA cm−2` 改成 `90 mA cm−2`（其余不动）：

```
篡改前: The overpotential of Fe–CoCH NT/CC at 10 mA cm −2 is 290 mV (Fig. 3b)
篡改后: The overpotential of Fe–CoCH NT/CC at 90 mA cm −2 is 290 mV (Fig. 3b)
```

```
$ python scripts/validate_nanopub.py --nanopub nanopub_tampered.json ...
OK assertions=22 errors=1 warnings=0
  ERROR A3 [evidence] 证据引用不是 P38 的逐字片段: The overpotential of Fe–CoCH NT/CC at 90 mA cm −2 is 290 mV (Fig. 3b)
exit=1
```

```json
{"assertions": 22,
 "errors": [{"id": "A3", "kind": "evidence",
             "detail": "证据引用不是 P38 的逐字片段: The overpotential of Fe–CoCH NT/CC at 90 mA cm −2 is 290 mV (Fig. 3b)"}],
 "warnings": [], "clean": false}
```

## 3. 缺失引文：同样报错而不是崩溃

引文被置空（`"quote": null`）时，校验器报"证据引用缺失或不是字符串"并退出 1，
不会产生未捕获异常。

## 说明

逐字核验的机制：每条 `evidence.quote` 必须是所引源单元文本的（空白规范化后）子串。
它保证"证据真实存在于原文的该段落"，是"对得上"这条硬标准的确定性兜底；
论断与引文的语义对应由 SKILL.md 的自查清单把关。
