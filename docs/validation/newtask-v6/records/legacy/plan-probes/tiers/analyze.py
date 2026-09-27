#!/usr/bin/env python3
"""汇总 results.jsonl：每格成功率/失败类别/步数/墙钟/旋钮，输出 summary.json 与 markdown 表 tables.md，并画 tiers_summary.png。"""
import collections
import json
import statistics
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = Path(__file__).resolve().parent
TIERS = ["xhard1", "xhard2", "xhard3", "xhard"]
TASKS = ["BinFill", "PickXtimes", "SwingXtimes", "PickHighlight", "VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap",
         "ButtonUnmaskSwap", "VideoRepick", "PatternLock", "RouteStick", "VideoPlaceButton", "VideoPlaceOrder"]
ABBR = {"BinFill": "BinFill", "PickXtimes": "PickX", "SwingXtimes": "SwingX", "PickHighlight": "PH",
        "VideoUnmask": "VU", "ButtonUnmask": "BU", "VideoUnmaskSwap": "VUS", "ButtonUnmaskSwap": "BUS",
        "VideoRepick": "VR", "PatternLock": "PL", "RouteStick": "RS", "VideoPlaceButton": "VPB", "VideoPlaceOrder": "VPO"}
KNOB_NAME = {"BinFill": "投入块数", "PickXtimes": "抓放次数", "SwingXtimes": "轮数", "PickHighlight": "pick 数",
             "VideoUnmask": "干扰容器数", "ButtonUnmask": "干扰容器数", "VideoUnmaskSwap": "交换次数",
             "ButtonUnmaskSwap": "交换次数", "VideoRepick": "交换次数", "PatternLock": "节点数", "RouteStick": "段数 L",
             "VideoPlaceButton": "演示块数 k", "VideoPlaceOrder": "演示访问总数"}


def knob(r):
    o = r.get("spec_objects") or {}
    a = r.get("spec_actions_small") or {}
    t = r["task"]
    try:
        if t in ("PickXtimes", "SwingXtimes"):
            return o["num_repeats"]
        if t == "BinFill":
            return sum(o["target_numbers"])
        if t == "PickHighlight":
            return o["highlight_count"]
        if t in ("VideoUnmask", "ButtonUnmask"):
            return o["distractors"]["requested"]
        if t in ("VideoUnmaskSwap", "ButtonUnmaskSwap", "VideoRepick"):
            return o["n_swaps"]
        if t == "PatternLock":
            if "path_nodes" in a:
                return len(a["path_nodes"])
            return (r["n_tasks"] - 1) // 2 if r.get("n_tasks") else None
        if t == "RouteStick":
            return o["L"]
        if t == "VideoPlaceButton":
            return len(o["demo_ids"])
        if t == "VideoPlaceOrder":
            return sum(o["num_targets_by_object"].values())
    except (KeyError, TypeError):
        return None


def second_knob(r):
    o = r.get("spec_objects") or {}
    t = r["task"]
    try:
        if t in ("VideoUnmask", "ButtonUnmask", "VideoUnmaskSwap", "ButtonUnmaskSwap"):
            return o["n_picks"]
        if t == "VideoRepick":
            return o["num_repeats"]
        if t in ("PickXtimes", "SwingXtimes"):
            return o["distractor_count"]["actual"]
        if t == "PickHighlight":
            return o["n_cubes"]
        if t == "VideoPlaceButton":
            return None
    except (KeyError, TypeError):
        return None


def fclass(r):
    if r["ok"]:
        return "ok"
    et = r.get("error_type") or "?"
    if et == "SceneGenerationError":
        return "SceneGen(reset)"
    return et


def med(xs):
    return statistics.median(xs) if xs else None


def main():
    rows = [json.loads(l) for l in open(HERE / "results.jsonl")]
    cells = collections.defaultdict(list)
    for r in rows:
        cells[(r["task"], r["tier"])].append(r)
    summary = {}
    for (t, tier), rs in cells.items():
        ok = [r for r in rs if r["ok"]]
        reset_ok = [r for r in rs if fclass(r) != "SceneGen(reset)"]
        es = [r["elapsed_steps"] for r in ok if r.get("elapsed_steps") is not None]
        nd = [r["h5_nondemo"] for r in ok if r.get("h5_nondemo") is not None]
        dm = [r["h5_demo"] for r in ok if r.get("h5_demo") is not None]
        h5 = [r["h5_steps"] for r in ok if r.get("h5_steps") is not None]
        ks = [knob(r) for r in rs if knob(r) is not None]
        ks2 = [second_knob(r) for r in rs if second_knob(r) is not None]
        summary[f"{t}|{tier}"] = {
            "task": t, "tier": tier, "n": len(rs), "ok": len(ok), "reset_ok": len(reset_ok),
            "demo_ok": len(ok), "fail_classes": dict(collections.Counter(fclass(r) for r in rs if not r["ok"])),
            "elapsed_med": med(es), "elapsed_max": max(es) if es else None,
            "fail_elapsed_max": max([r["elapsed_steps"] for r in rs if not r["ok"] and r.get("elapsed_steps")] or [0]),
            "h5_med": med(h5), "h5_max": max(h5) if h5 else None,
            "demo_med": med(dm), "nondemo_med": med(nd), "nondemo_max": max(nd) if nd else None,
            "n_over_1301": sum(x > 1301 for x in nd),
            "wall_med": med([r["wall_s"] for r in ok]), "wall_max": max([r["wall_s"] for r in rs]) if rs else None,
            "knob_vals": ks, "knob_mean": (sum(ks) / len(ks)) if ks else None,
            "knob2_vals": ks2, "es_list": es, "nd_list": nd,
            "errors": [f"{r['seed']}:{r.get('error_type')}:{(r.get('error') or '')[:160]}" for r in rs if not r["ok"]],
        }
    (HERE / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1))
    # markdown 表
    lines = ["| 环境 | 档 | 成功/局 | reset 过 | 失败类别 | 旋钮（" + "各局实抽值）| 总步数 elapsed 中位/最大 | 演示帧中位 | 非演示步 中位/最大 | >1301 局 | 单局墙钟 中位/最大 s |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for t in TASKS:
        for tier in TIERS:
            s = summary.get(f"{t}|{tier}")
            if not s:
                continue
            fc = "、".join(f"{k}×{v}" for k, v in s["fail_classes"].items()) or "—"
            kv = ",".join(str(x) for x in s["knob_vals"])
            if s["knob2_vals"]:
                kv += " ／ " + ",".join(str(x) for x in s["knob2_vals"])
            f = lambda x: "—" if x is None else (f"{x:.0f}" if isinstance(x, float) else str(x))
            lines.append(f"| {ABBR[t]} | {tier} | {s['ok']}/{s['n']} | {s['reset_ok']}/{s['n']} | {fc} | {KNOB_NAME[t]}: {kv} | "
                         f"{f(s['elapsed_med'])}/{f(s['elapsed_max'])} | {f(s['demo_med'])} | {f(s['nondemo_med'])}/{f(s['nondemo_max'])} | "
                         f"{s['n_over_1301']} | {f(s['wall_med'])}/{f(s['wall_max'])} |")
    (HERE / "tables.md").write_text("\n".join(lines) + "\n")
    plot(summary)


def plot(summary):
    for fp in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",):
        if Path(fp).exists():
            font_manager.fontManager.addfont(fp)
    plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig = plt.figure(figsize=(22, 17))
    gs = fig.add_gridspec(3, 1, height_ratios=[1.0, 1.25, 1.1], hspace=0.38)
    # A 成功率热图
    top = gs[0].subgridspec(1, 2, width_ratios=[1.0, 1.0], wspace=0.25)
    ax = fig.add_subplot(top[0])
    import numpy as np
    M = np.full((len(TIERS), len(TASKS)), np.nan)
    R = np.full((len(TIERS), len(TASKS)), np.nan)
    for j, t in enumerate(TASKS):
        for i, tier in enumerate(TIERS):
            s = summary.get(f"{t}|{tier}")
            if s:
                M[i, j] = s["ok"] / s["n"]
                R[i, j] = s["reset_ok"] / s["n"]
    im = ax.imshow(M, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    for j, t in enumerate(TASKS):
        for i, tier in enumerate(TIERS):
            s = summary.get(f"{t}|{tier}")
            if s:
                ax.text(j, i, f"{s['ok']}/{s['n']}", ha="center", va="center", fontsize=10,
                        color="white" if M[i, j] > 0.6 else "#1a1a1a")
    ax.set_xticks(range(len(TASKS)), [ABBR[t] for t in TASKS], rotation=0, fontsize=10)
    ax.set_yticks(range(len(TIERS)), TIERS)
    ax.set_title("A. 端到端成功率（成功/局，含 reset 失败）", fontsize=13, loc="left")
    fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    ax2 = fig.add_subplot(top[1])
    Dm = np.full((len(TIERS), len(TASKS)), np.nan)
    for j, t in enumerate(TASKS):
        for i, tier in enumerate(TIERS):
            s = summary.get(f"{t}|{tier}")
            if s and s["reset_ok"]:
                Dm[i, j] = s["ok"] / s["reset_ok"]
    im2 = ax2.imshow(Dm, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    for j, t in enumerate(TASKS):
        for i, tier in enumerate(TIERS):
            s = summary.get(f"{t}|{tier}")
            if s:
                ax2.text(j, i, f"{s['ok']}/{s['reset_ok']}", ha="center", va="center", fontsize=10,
                         color="white" if (not np.isnan(Dm[i, j]) and Dm[i, j] > 0.6) else "#1a1a1a")
    ax2.set_xticks(range(len(TASKS)), [ABBR[t] for t in TASKS], fontsize=10)
    ax2.set_yticks(range(len(TIERS)), TIERS)
    ax2.set_title("B. 演示级成功率（成功/reset 通过局）", fontsize=13, loc="left")
    fig.colorbar(im2, ax=ax2, fraction=0.025, pad=0.01)
    # C 步数
    ax3 = fig.add_subplot(gs[1])
    pos, data_es, data_nd, labels = [], [], [], []
    x = 0
    ticks, ticklab = [], []
    for t in TASKS:
        for tier in TIERS:
            s = summary.get(f"{t}|{tier}")
            es = s["es_list"] if s else []
            nd = s["nd_list"] if s else []
            if es:
                b = ax3.boxplot([es], positions=[x - 0.18], widths=0.32, patch_artist=True, manage_ticks=False,
                                medianprops=dict(color="#1a1a1a"), flierprops=dict(markersize=3))
                b["boxes"][0].set_facecolor("#c9c9c9")
            if nd:
                b = ax3.boxplot([nd], positions=[x + 0.18], widths=0.32, patch_artist=True, manage_ticks=False,
                                medianprops=dict(color="#1a1a1a"), flierprops=dict(markersize=3))
                b["boxes"][0].set_facecolor("#4a86c5")
            ticks.append(x)
            ticklab.append(tier.replace("xhard", "x") if tier != "xhard" else "X")
            x += 1
        x += 0.8
    ax3.axhline(1301, color="#c0392b", lw=1.2, ls="--")
    ax3.axhline(5000, color="#7f3c8d", lw=1.2, ls="--")
    ax3.text(x - 0.5, 1301, " 评估 1301（非演示步）", va="bottom", ha="right", fontsize=10, color="#c0392b")
    ax3.text(x - 0.5, 5000, " 生成 fail_safe 5000（elapsed）", va="bottom", ha="right", fontsize=10, color="#7f3c8d")
    ax3.set_xticks(ticks, ticklab, fontsize=8)
    # 环境名放在组下方
    xg = 0
    for t in TASKS:
        ax3.text(xg + 1.5, -0.075, ABBR[t], transform=ax3.get_xaxis_transform(), ha="center", va="top", fontsize=11)
        xg += 4.8
    ax3.set_xlim(-0.8, x - 0.6)
    ax3.set_ylim(0, 5600)
    ax3.set_ylabel("步数")
    ax3.grid(axis="y", color="#e6e6e6")
    ax3.set_axisbelow(True)
    from matplotlib.patches import Patch
    ax3.legend(handles=[Patch(facecolor="#c9c9c9", label="总步数 elapsed_steps（含演示与 NO RECORD）"),
                        Patch(facecolor="#4a86c5", label="非演示步（h5 中 is_video_demo=False）")],
               loc="center left", fontsize=10, frameon=False)
    ax3.set_title("C. 成功局步数（每档左灰=总步数、右蓝=非演示步；x1/x2/x3=xhard1/2/3，X=现行 xhard 对照）", fontsize=13, loc="left")
    # D 旋钮单调性
    sub = gs[2].subgridspec(2, 7, hspace=0.75, wspace=0.45)
    for k, t in enumerate(TASKS):
        a = fig.add_subplot(sub[k // 7, k % 7])
        xs, ys, lo, hi = [], [], [], []
        for i, tier in enumerate(TIERS):
            s = summary.get(f"{t}|{tier}")
            if s and s["knob_vals"]:
                xs.append(i)
                ys.append(s["knob_mean"])
                lo.append(min(s["knob_vals"]))
                hi.append(max(s["knob_vals"]))
        a.plot(xs, ys, "-o", color="#2f6fb0", lw=2, ms=6)
        a.vlines(xs, lo, hi, color="#2f6fb0", alpha=0.35, lw=4)
        a.set_xticks(range(4), ["x1", "x2", "x3", "X"], fontsize=9)
        a.set_title(f"{ABBR[t]}：{KNOB_NAME[t]}", fontsize=10)
        a.grid(axis="y", color="#eeeeee")
        a.tick_params(axis="y", labelsize=8)
    fig.text(0.125, 0.345, "D. 各环境主难度旋钮：各档实抽均值（点）与最小～最大（竖条）", fontsize=13)
    fig.suptitle("V6 xhard1/2/3 三档 greatlakes A40 真演示实测（每格 6 局 + xhard 对照 3 局）", fontsize=16, y=0.925)
    fig.savefig(HERE / "tiers_summary.png", dpi=110, bbox_inches="tight")


if __name__ == "__main__":
    main()
