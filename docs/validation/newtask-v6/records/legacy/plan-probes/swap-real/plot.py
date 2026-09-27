"""swap_real.png：三行（VUS/BUS/VR）× 三列（成功率对照 / 成功局内极差分布 / 跨局参与频率）"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

for f in font_manager.findSystemFonts():
    if "NotoSansCJK" in f.replace(" ", "") or "Noto Sans CJK" in f:
        font_manager.fontManager.addfont(f)
plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

D = Path(sys.argv[1])
S = json.loads((D / "summary.json").read_text())
ENVS = [("VUS", "VideoUnmaskSwap"), ("BUS", "ButtonUnmaskSwap"), ("VR", "VideoRepick")]
C5, CV = "#2a6fdb", "#b0b0b0"
fig, axes = plt.subplots(3, 3, figsize=(15, 12.5))
for i, (ab, name) in enumerate(ENVS):
    s5, v5 = S.get(f"{ab}/s5"), S.get(f"{ab}/v5")
    ax = axes[i, 0]
    labels = ["reset 接受率", "演示成功率\n（通过 reset 的局）"]
    x = range(len(labels)); w = 0.36
    for j, (arm, d, col) in enumerate((("S5", s5, C5), ("V5 对照", v5, CV))):
        if not d:
            continue
        vals = [d["reset_rate"], d["success_rate"] or 0]
        bars = ax.bar([xx + (j - 0.5) * w for xx in x], vals, w, color=col, label=arm)
        txt = [f"{d['reset_ok']}/{d['attempts']}", f"{d['success']}/{d['reset_ok']}"]
        for b, t in zip(bars, txt):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02, t, ha="center", va="bottom", fontsize=9)
    ax.set_xticks(list(x)); ax.set_xticklabels(labels); ax.set_ylim(0, 1.38); ax.set_yticks([0, 0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_title(f"{ab}（{name}）成功率对照"); ax.legend(loc="upper center", ncol=2, fontsize=9)
    ax = axes[i, 1]
    ks = sorted({int(k) for d in (s5, v5) if d for k in d["spread_hist"]} | {0, 1, 2})
    for j, (arm, d, col) in enumerate((("S5", s5, C5), ("V5 对照", v5, CV))):
        if not d or not d["success"]:
            continue
        tot = sum(d["spread_hist"].values())
        vals = [d["spread_hist"].get(str(k), d["spread_hist"].get(k, 0)) / tot for k in ks]
        bars = ax.bar([k + (j - 0.5) * 0.38 for k in ks], vals, 0.38, color=col, label=f"{arm}（{tot} 局）")
        for b, k in zip(bars, ks):
            cnt = d["spread_hist"].get(str(k), d["spread_hist"].get(k, 0))
            if cnt:
                ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.02, str(cnt), ha="center", va="bottom", fontsize=8)
    ax.set_xticks(ks); ax.set_xlabel("局内各对象参与次数极差（max−min）"); ax.set_ylabel("局占比")
    ax.set_ylim(0, 1.15); ax.set_title(f"{ab} 成功局内极差分布"); ax.legend(fontsize=9)
    ax = axes[i, 2]
    for j, (arm, d, col) in enumerate((("S5", s5, C5), ("V5 对照", v5, CV))):
        if not d or not d["marginal"]:
            continue
        m = d["marginal"]
        ax.bar([k + (j - 0.5) * 0.38 for k in range(len(m))], m, 0.38, color=col,
               label=f"{arm}  χ² p={d['chi2_p']:.3f}")
    n = len((s5 or v5)["marginal"])
    ax.axhline(1 / n, color="k", lw=0.8, ls="--")
    ax.set_xticks(range(n)); ax.set_xticklabels([f"bin_{k}" for k in range(n)])
    ax.set_ylabel("参与频率"); ax.set_ylim(0, max(0.45, 1.6 / n)); ax.set_title(f"{ab} 跨局参与频率（虚线 = 1/{n}）")
    ax.legend(fontsize=9, loc="upper right")
fig.suptitle("S5 交换对象均匀化：greatlakes 真实演示（S5 补丁组 vs 原 V5 对照组）", fontsize=14)
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(D / "swap_real.png", dpi=110)
print("saved")
