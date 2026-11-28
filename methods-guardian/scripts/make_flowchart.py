#!/usr/bin/env python3
# make_flowchart.py — 技术路线图排版脚本（确定性布局，纯标准库输出 SVG）
#
# Agent 只写一份小 flow.json（节点文字 + 行结构 + 连接关系）；
# 脚本负责：文本宽度估算与换行、纵向主链 + 分支行的布局、折线箭头连接，
# 输出学术风格（灰框黑箭头白底）的 SVG 矢量图；若环境有 matplotlib
# 且能找到中文字体，附带渲染 PNG 预览（找不到字体则诚实跳过）。
#
# flow.json 契约：
# {
#   "title": "图题（可空）",
#   "nodes": [{"id": "n1", "text": "主标题", "sub": "补充说明（可空）"}],
#   "rows":  [{"label": "行标签（可空）", "nodes": ["n1"]},
#             {"nodes": ["n2a", "n2b"]}],          # 同一行多框即分支
#   "edges": [{"from": "n1", "to": "n2a"}, ...]     # 只连接相邻两行
# }
#
# 若给 --draft draft.json：节点文字中的每个数字必须已在 draft 的 claim
# 数字集合中（或为其子串），防止路线图出现材料外的数值。
#
# 用法：python make_flowchart.py --flow flow.json --out route.svg [--png route.png] [--draft draft.json]
import argparse, json, os, re, sys

FS_MAIN, FS_SUB, FS_LABEL = 15.0, 12.5, 13.0
PAD_X, PAD_Y = 16, 10
LINE_H_MAIN, LINE_H_SUB = 22, 18
ROW_GAP, COL_GAP, MARGIN = 64, 26, 40
MAX_TEXT_W = 340.0
BOX_FILL, BOX_STROKE, LINE_COLOR = "#f5f5f5", "#444444", "#222222"

NUM_RE = re.compile(r'(?<![\w.)])(\d+(?:\.\d+)?)(?![\w.@])')


def char_w(ch, fs):
    return fs if ord(ch) > 0x2E7F else fs * 0.56


def wrap_text(s, fs, max_w):
    lines, cur, w = [], "", 0.0
    for ch in s:
        cw = char_w(ch, fs)
        if w + cw > max_w and cur:
            lines.append(cur)
            cur, w = ch, cw
        else:
            cur += ch
            w += cw
    if cur:
        lines.append(cur)
    return lines or [""]


def line_w(s, fs):
    return sum(char_w(c, fs) for c in s)


def layout(flow):
    """计算所有几何元素；返回 (elements, width, height)。"""
    nodes = {n["id"]: n for n in flow["nodes"]}
    # 1) 每个节点：换行、盒尺寸
    geom = {}
    for nid, n in nodes.items():
        main_lines = []
        for part in str(n["text"]).split("\n"):
            main_lines += wrap_text(part, FS_MAIN, MAX_TEXT_W)
        sub = str(n.get("sub") or "")
        sub_lines = wrap_text(sub, FS_SUB, MAX_TEXT_W) if sub else []
        w = max([line_w(l, FS_MAIN) for l in main_lines]
                + [line_w(l, FS_SUB) for l in sub_lines]) + 2 * PAD_X
        h = 2 * PAD_Y + len(main_lines) * LINE_H_MAIN \
            + (len(sub_lines) * LINE_H_SUB + 4 if sub_lines else 0)
        geom[nid] = {"main": main_lines, "sub": sub_lines, "w": w, "h": h}
    # 2) 行布局：x 居中，y 累加
    rows = flow["rows"]
    row_label_h = 24 if any(r.get("label") for r in rows) else 0
    y = MARGIN + (30 if flow.get("title") else 0)
    row_info = []
    max_w = 0.0
    for r in rows:
        ids = r["nodes"]
        rw = sum(geom[i]["w"] for i in ids) + COL_GAP * (len(ids) - 1)
        rh = max(geom[i]["h"] for i in ids)
        row_info.append({"ids": ids, "label": r.get("label"),
                         "w": rw, "h": rh, "y": y})
        y += rh + ROW_GAP + (row_label_h if r.get("label") else 0)
        max_w = max(max_w, rw)
    width = max_w + 2 * MARGIN
    height = y - ROW_GAP + MARGIN
    for ri in row_info:
        x = (width - ri["w"]) / 2
        ri["y"] += (row_label_h if ri["label"] else 0)
        for i in ri["ids"]:
            geom[i]["x"] = x
            geom[i]["y"] = ri["y"] + (ri["h"] - geom[i]["h"]) / 2
            x += geom[i]["w"] + COL_GAP
    # 3) 元素列表
    elems = []
    if flow.get("title"):
        elems.append(("text", width / 2, MARGIN, flow["title"], 17, "middle"))
    for ri in row_info:
        if ri["label"]:
            elems.append(("text", width / 2, ri["y"] - row_label_h + 14,
                          ri["label"], FS_LABEL, "middle"))
        for nid in ri["ids"]:
            g = geom[nid]
            elems.append(("box", nid, g["x"], g["y"], g["w"], g["h"]))
            ty = g["y"] + PAD_Y + FS_MAIN
            for l in g["main"]:
                elems.append(("text", g["x"] + g["w"] / 2, ty, l, FS_MAIN, "middle"))
                ty += LINE_H_MAIN
            ty += 2
            for l in g["sub"]:
                elems.append(("text", g["x"] + g["w"] / 2, ty, l, FS_SUB, "middle"))
                ty += LINE_H_SUB
    # 4) 边：相邻行间折线连接（下中点→水平→上中点）
    row_of = {}
    for idx, ri in enumerate(row_info):
        for nid in ri["ids"]:
            row_of[nid] = idx
    for e in flow.get("edges", []):
        a, b = e["from"], e["to"]
        if a not in geom or b not in geom:
            print("FATAL: edge 引用了不存在的节点: %s -> %s" % (a, b))
            sys.exit(2)
        if row_of[b] <= row_of[a]:
            print("FATAL: 边必须自上而下（%s 在第 %d 行，%s 在第 %d 行）"
                  % (a, row_of[a], b, row_of[b]))
            sys.exit(2)
        ga, gb = geom[a], geom[b]
        x1, y1 = ga["x"] + ga["w"] / 2, ga["y"] + ga["h"]
        x2, y2 = gb["x"] + gb["w"] / 2, gb["y"]
        ymid = (y1 + y2) / 2
        elems.append(("edge", x1, y1, x2, y2, ymid))
    return elems, width, height


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_svg(elems, width, height):
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%.0f" height="%.0f" '
           'viewBox="0 0 %.0f %.0f" font-family="SimSun, 宋体, serif">'
           % (width, height, width, height),
           '<defs><marker id="arr" markerWidth="9" markerHeight="9" refX="7" '
           'refY="4.5" orient="auto"><path d="M0,0 L8,4.5 L0,9 z" fill="%s"/>'
           '</marker></defs>' % LINE_COLOR,
           '<rect width="100%%" height="100%%" fill="white"/>']
    for el in elems:
        if el[0] == "box":
            _, _nid, x, y, w, h = el
            out.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%.1f" '
                       'fill="%s" stroke="%s" stroke-width="1.2"/>'
                       % (x, y, w, h, BOX_FILL, BOX_STROKE))
        elif el[0] == "text":
            _, x, y, s, fs, anchor = el
            out.append('<text x="%.1f" y="%.1f" font-size="%.1f" '
                       'text-anchor="%s" fill="#111">%s</text>'
                       % (x, y, fs, anchor, esc(s)))
        elif el[0] == "edge":
            _, x1, y1, x2, y2, ymid = el
            if abs(x1 - x2) < 1:
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" '
                           'stroke="%s" stroke-width="1.2" '
                           'marker-end="url(#arr)"/>' % (x1, y1, x2, y2 - 2,
                                                         LINE_COLOR))
            else:
                out.append('<path d="M%.1f,%.1f L%.1f,%.1f L%.1f,%.1f '
                           'L%.1f,%.1f" fill="none" stroke="%s" '
                           'stroke-width="1.2" marker-end="url(#arr)"/>'
                           % (x1, y1, x1, ymid, x2, ymid, x2, y2 - 2,
                              LINE_COLOR))
    out.append("</svg>")
    return "\n".join(out)


def render_png(elems, width, height, path):
    """有 matplotlib 且能找到中文字体时渲染 PNG 预览；否则诚实返回 False。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import font_manager, pyplot as plt
        from matplotlib.patches import FancyArrowPatch, Rectangle
    except ImportError:
        print("PNG 预览跳过：环境无 matplotlib")
        return False
    cjk = None
    for f in font_manager.fontManager.ttflist:
        if any(k in f.name for k in ("Hei", "YaHei", "Song", "CJK", "WenQuanYi",
                                     "Noto Sans SC", "SimSun", "Kai")):
            cjk = f.name
            break
    if not cjk:
        print("PNG 预览跳过：未找到中文字体（SVG 已生成，可用浏览器查看）")
        return False
    plt.rcParams["font.family"] = cjk
    dpi = 100
    pt = 72.0 / dpi  # 布局坐标为像素，matplotlib 字号为磅，需换算保持一致
    fig = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, width)
    ax.set_ylim(height, 0)
    ax.axis("off")
    for el in elems:
        if el[0] == "box":
            _, _nid, x, y, w, h = el
            ax.add_patch(Rectangle((x, y), w, h, facecolor=BOX_FILL,
                                   edgecolor=BOX_STROKE, lw=1.0))
        elif el[0] == "text":
            _, x, y, s, fs, _a = el
            ax.text(x, y + fs * 0.35, s, ha="center", va="center",
                    fontsize=fs * pt)
        elif el[0] == "edge":
            _, x1, y1, x2, y2, ymid = el
            if abs(x1 - x2) < 1:
                ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2 - 3),
                                             arrowstyle="-|>",
                                             mutation_scale=12, lw=1.0,
                                             color=LINE_COLOR))
            else:
                ax.plot([x1, x1, x2, x2], [y1, ymid, ymid, y2 - 3],
                        color=LINE_COLOR, lw=1.0)
                ax.add_patch(FancyArrowPatch((x2, ymid), (x2, y2 - 3),
                                             arrowstyle="-|>",
                                             mutation_scale=12, lw=1.0,
                                             color=LINE_COLOR))
    fig.savefig(path, dpi=dpi, facecolor="white")
    plt.close(fig)
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--png", default=None)
    ap.add_argument("--draft", default=None)
    args = ap.parse_args()
    try:
        with open(args.flow, encoding="utf-8") as f:
            flow = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        print("FATAL: 无法读取 flow.json: %s" % e)
        sys.exit(2)
    if not isinstance(flow.get("nodes"), list) or not flow["nodes"]:
        print("FATAL: flow.nodes 缺失或为空")
        sys.exit(2)
    if not isinstance(flow.get("rows"), list) or not flow["rows"]:
        print("FATAL: flow.rows 缺失或为空")
        sys.exit(2)
    ids = {n.get("id") for n in flow["nodes"]}
    for r in flow["rows"]:
        for nid in r.get("nodes", []):
            if nid not in ids:
                print("FATAL: rows 引用了不存在的节点: %s" % nid)
                sys.exit(2)
    placed = {nid for r in flow["rows"] for nid in r.get("nodes", [])}
    if placed != ids:
        print("FATAL: 有节点未放入任何行: %s" % ",".join(sorted(ids - placed)))
        sys.exit(2)

    # 数字一致性：路线图中的数字必须来自 draft 的 claim 集合
    if args.draft:
        try:
            with open(args.draft, encoding="utf-8") as f:
                draft = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
            print("FATAL: 无法读取 draft.json: %s" % e)
            sys.exit(2)
        claim_nums = [str(c.get("number", "")) for c in draft.get("claims", [])]
        bad = []
        for n in flow["nodes"]:
            txt = str(n.get("text", "")) + " " + str(n.get("sub") or "")
            for m in NUM_RE.finditer(txt):
                tok = m.group(1)
                if not any(tok == cn or (len(tok) >= 1 and tok in cn)
                           for cn in claim_nums if cn):
                    bad.append((n["id"], tok))
        if bad:
            for nid, tok in bad:
                print("ERROR: 节点 %s 中数字 %s 不在 draft claim 集合中"
                      "（路线图不许出现材料外数值）" % (nid, tok))
            sys.exit(1)

    elems, width, height = layout(flow)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(render_svg(elems, width, height))
    print("SVG -> %s (%.0fx%.0f, %d 节点, %d 行)"
          % (args.out, width, height, len(flow["nodes"]), len(flow["rows"])))
    if args.png:
        ok = render_png(elems, width, height, args.png)
        print("PNG -> %s" % args.png if ok else "PNG 未生成（见上）")


if __name__ == "__main__":
    main()
