"""Generate a shareable infographic figure summarizing the viet-causality list."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import yaml
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_table import categorize  # reuse the authoritative bucketing

DATA = ROOT / "_data" / "researchers.yml"
d = yaml.safe_load(DATA.read_text(encoding="utf-8"))

countries = Counter((e.get("affiliation") or {}).get("country", "?") for e in d)
subs: Counter = Counter()
for e in d:
    for s in e.get("sub_areas") or []:
        subs[s] += 1
cats = Counter(categorize(e) for e in d)

# Palette
NAVY = "#1a2a44"
RED = "#da251d"   # Vietnamese flag red
GOLD = "#ffcd00"  # Vietnamese flag yellow
GREY = "#8895a7"

plt.rcParams.update({"font.family": "DejaVu Sans"})

fig = plt.figure(figsize=(12, 7), dpi=200)
fig.patch.set_facecolor("white")
gs = GridSpec(2, 2, height_ratios=[0.9, 1.0], hspace=0.42, wspace=0.28,
              left=0.07, right=0.96, top=0.86, bottom=0.16)

# ---- Header ----
fig.text(0.5, 0.93, f"{len(d)} Vietnamese researchers worldwide  ·  Causal Inference · Discovery · Causal AI",
         fontsize=14.5, color=NAVY, fontweight="bold", ha="center")
# ---- Footer ----
fig.text(0.5, 0.025, "github.com/phamquiluan/viet-causality", fontsize=12,
         color=RED, ha="center", fontweight="bold")

# ---- Top-left: category donut ----
ax1 = fig.add_subplot(gs[0, 0])
order = ["Academic", "Industry", "PhD Students"]
labels = [c for c in order if cats.get(c)]
vals = [cats[c] for c in labels]
colors = [NAVY, RED, GOLD][: len(labels)]
wedges, _ = ax1.pie(vals, colors=colors, startangle=90, counterclock=False,
                    wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2))
ax1.text(0, 0, f"{len(d)}", ha="center", va="center", fontsize=30, fontweight="bold", color=NAVY)
ax1.text(0, -0.28, "researchers", ha="center", va="center", fontsize=11, color=GREY)
ax1.set_title("By career stage", fontsize=14, fontweight="bold", color=NAVY, pad=10)
leg = [f"{l}  ({v})" for l, v in zip(labels, vals)]
ax1.legend(wedges, leg, loc="center left", bbox_to_anchor=(0.92, 0.5),
           frameon=False, fontsize=11, handlelength=1.1)

# ---- Top-right: top countries ----
ax2 = fig.add_subplot(gs[0, 1])
top_c = countries.most_common(6)
names = [c for c, _ in top_c][::-1]
cvals = [v for _, v in top_c][::-1]
bars = ax2.barh(names, cvals, color=NAVY)
bars[-1].set_color(RED)  # highlight the top country
for b, v in zip(bars, cvals):
    ax2.text(b.get_width() + 0.4, b.get_y() + b.get_height() / 2, str(v),
             va="center", fontsize=10.5, color=NAVY, fontweight="bold")
ax2.set_title("Top countries", fontsize=14, fontweight="bold", color=NAVY, pad=10)
ax2.set_xlim(0, max(cvals) * 1.15)
for s in ("top", "right", "bottom"):
    ax2.spines[s].set_visible(False)
ax2.set_xticks([])
ax2.tick_params(axis="y", length=0, labelsize=11)

# ---- Bottom: sub-areas ----
ax3 = fig.add_subplot(gs[1, :])
top_s = subs.most_common(9)
snames = [s for s, _ in top_s]
svals = [v for _, v in top_s]
bars = ax3.bar(snames, svals, color=NAVY, width=0.66)
bars[0].set_color(RED)
for b, v in zip(bars, svals):
    ax3.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.4, str(v),
             ha="center", fontsize=10.5, color=NAVY, fontweight="bold")
ax3.set_title("By research sub-area", fontsize=14, fontweight="bold", color=NAVY, pad=10)
ax3.set_ylim(0, max(svals) * 1.18)
for s in ("top", "right", "left"):
    ax3.spines[s].set_visible(False)
ax3.set_yticks([])
ax3.tick_params(axis="x", length=0, labelsize=10.5)
plt.setp(ax3.get_xticklabels(), rotation=20, ha="right")

out = ROOT / "assets" / "summary.png"
out.parent.mkdir(exist_ok=True)
fig.savefig(out, facecolor="white", bbox_inches="tight")
print(f"wrote {out}")
