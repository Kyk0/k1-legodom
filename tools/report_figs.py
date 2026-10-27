#!/usr/bin/env python3
"""Figures for REPORT.md -> report/img/. Reads the site's per-run data (site/data/Lobby__*.json), so run
make_site.py first.  python3 tools/report_figs.py
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
OUT = ROOT / "report" / "img"

# categorical slots 1-3 of the reference palette (validated all-pairs, light)
SERIES = [  # key, label, color, width, dash
    ("lowest", "Legs (lowest)", "#2a78d6", 2.0, "-"),
    ("booster", "Booster odometer", "#eb6834", 2.0, "-"),
    ("sole", "Legs (sole)", "#1baf7a", 1.3, "--"),
]
INK, MUTED, GRID, SURF = "#0b0b0b", "#52514e", "#e8e7e3", "#fcfcfb"

RUNS = [  # name, title
    ("lobby_1025_151300", "9 / 6 / 12 m out-and-back (tape)"),
    ("lobby_1025_150458", "Out-and-back legs"),
    ("5m_front_back", "6x 5 m forward + 5 m backward"),
    ("turn_5_left_5_right", "5 turns on the spot, then 5 back"),
    ("mix_walk_and_turn", "Chaotic walking + turning"),
    ("orientation_stress", "Pushed, blocked, turned in one spot"),
    ("continuous_collision", "Walking into an obstacle"),
    ("side_pull", "Pulled sideways"),
    ("standing", "Standing still"),
]

plt.rcParams.update({
    "font.family": "sans-serif", "font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF,
    "legend.frameon": False, "axes.titlesize": 11, "axes.titlecolor": INK,
})


def load(name):
    return json.loads((DATA / f"Lobby__{name}.json").read_text())


def run_figure(name, title):
    d = load(name)
    t = np.array(d["t"])
    fig = plt.figure(figsize=(12, 5.2))
    ax = fig.add_subplot(1, 2, 1)
    for k, label, c, w, ls in SERIES:
        s = d["series"][k]
        ax.plot(s["y"], s["x"], color=c, lw=w, ls=ls, label=label, zorder=3 if k == "lowest" else 2)
        ax.plot(s["y"][-1], s["x"][-1], "o", color=c, ms=7, mec=SURF, mew=2, zorder=4)
    ax.plot(0, 0, "s", color=INK, ms=8, label="START", zorder=5)
    tr = d.get("truth") or {}
    if tr.get("end"):
        ax.plot(tr["end"][1], tr["end"][0], "*", color=INK, ms=15, mec=SURF, label="real end", zorder=6)
    ax.invert_xaxis()                     # y = left, drawn to the left, so the map is seen from above
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("y, left (m)")
    ax.set_ylabel("x, forward at START (m)")
    ax.set_title("Map (seen from above, forward = up)", loc="left")
    ax.legend(loc="best", fontsize=9)

    a2 = fig.add_subplot(2, 2, 2)
    for k, label, c, w, ls in SERIES:
        s = d["series"][k]
        a2.plot(t, np.hypot(s["x"], s["y"]), color=c, lw=w * 0.8, ls=ls, label=label)
    if tr.get("far"):
        a2.axhline(tr["far"], color=MUTED, lw=1, ls=":")
    a2.set_ylabel("distance from START (m)")
    a2.set_title("Distance from START", loc="left")
    a3 = fig.add_subplot(2, 2, 4, sharex=a2)
    yaw = np.degrees(np.unwrap(np.array(d["series"]["lowest"]["yaw"])))
    a3.plot(t, yaw - yaw[0], color=INK, lw=1.2)
    a3.set_ylabel("heading (deg)")
    a3.set_xlabel("time (s)")
    a3.set_title("Heading (IMU, the same for all three)", loc="left")
    for m in d["marks"]:
        for a in (a2, a3):
            a.axvline(m["t"], color=GRID, lw=1, zorder=0)
    fig.suptitle(f"{title}   ·   {name}", x=0.01, ha="left", fontsize=12, color=INK, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.png", dpi=110)
    plt.close(fig)


def end_errors():
    rows = []
    for name, title in RUNS:
        d = load(name)
        if not (d.get("truth") or {}).get("end"):
            continue
        rows.append((title, [d["stats"][k]["end_err"] for k, *_ in SERIES]))
    rows.reverse()
    cap = 3.0
    fig, ax = plt.subplots(figsize=(10, 0.62 * len(rows) + 1.4))
    h = 0.26
    for j, (k, label, c, *_r) in enumerate(SERIES):
        ys = np.arange(len(rows)) + (1 - j) * h
        vals = [r[1][j] for r in rows]
        ax.barh(ys, [min(v, cap) for v in vals], height=h - 0.04, color=c, label=label, edgecolor=SURF, lw=1)
        for y, v in zip(ys, vals):
            if v > cap:
                ax.text(cap - 0.05, y, f"{v:.1f} m →", va="center", ha="right", fontsize=9, color=SURF, fontweight="bold")
            elif k != "sole":
                ax.text(v + 0.04, y, f"{v:.2f}", va="center", fontsize=8.5, color=MUTED)
    ax.axvspan(0, 0.3, color=GRID, alpha=0.6, zorder=0, lw=0)
    ax.text(0.15, len(rows) - 0.45, "truth ±0.3 m", ha="center", fontsize=8.5, color=MUTED)
    ax.set_yticks(np.arange(len(rows)), [r[0] for r in rows])
    ax.set_xlim(0, cap)
    ax.set_xlabel("end-point error (m)   ·   bars cut at 3 m")
    ax.grid(axis="y", visible=False)
    ax.set_title("Where each estimate thinks the robot ended vs where it really ended", loc="left")
    ax.legend(loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "end_errors.png", dpi=110)
    plt.close(fig)


def tape_segments():
    """% distance error per tape-measured leg: the 9/6/12 m run (between marks) and the 5 m run (between
    turning points)."""
    labels, errs = [], {k: [] for k, *_ in SERIES}
    d = load("lobby_1025_151300")
    t = np.array(d["t"])
    ms = sorted(d["marks"], key=lambda m: m["t"])
    for n, (truth, lab) in enumerate(zip([9, 9, 6, 6, 12, 12], ["9 m out", "9 m back", "6 m out", "6 m back",
                                                               "12 m out", "12 m back"])):
        i, j = (int(np.argmin(np.abs(t - ms[n + q]["t"]))) for q in (0, 1))
        labels.append(lab)
        for k in errs:
            s = d["series"][k]
            errs[k].append(100 * (math.hypot(s["x"][j] - s["x"][i], s["y"][j] - s["y"][i]) - truth) / truth)
    d = load("5m_front_back")
    x = np.array(d["series"]["lowest"]["x"])
    k_ = 20
    xs = np.convolve(x, np.ones(k_) / k_, mode="same")
    pts = [0]
    for i in range(k_, len(xs) - k_):
        w = xs[i - k_:i + k_ + 1]
        if ((xs[i] == w.max() and xs[i] > 2.5) or (xs[i] == w.min() and xs[i] < 2.5)) and i - pts[-1] > 3 * k_:
            pts.append(i)
    segs = list(zip(pts, pts[1:]))[:12]          # 6 forward + 6 backward legs
    for name, sl in (("5 m fwd (x6)", slice(0, None, 2)), ("5 m back (x6)", slice(1, None, 2))):
        labels.append(name)
        for k in errs:
            s = d["series"][k]
            L = [math.hypot(s["x"][b] - s["x"][a], s["y"][b] - s["y"][a]) for a, b in segs[sl]]
            errs[k].append(100 * (np.mean(L) - 5) / 5)
    fig, ax = plt.subplots(figsize=(11, 4.6))
    w = 0.26
    xs = np.arange(len(labels))
    for j, (k, label, c, *_r) in enumerate(SERIES):
        ax.bar(xs + (j - 1) * w, errs[k], width=w - 0.03, color=c, label=label, edgecolor=SURF, lw=1)
    for xi, v in zip(xs, errs["booster"]):
        if abs(v) > 20:
            ax.text(xi, v + 1, f"+{v:.0f}%", ha="center", fontsize=9, color=MUTED)
    ax.axhline(0, color=INK, lw=1)
    ax.set_xticks(xs, labels)
    ax.set_ylabel("distance error vs tape (%)")
    ax.grid(axis="x", visible=False)
    ax.set_title("Distance per tape-measured leg (0 = exactly right)", loc="left")
    ax.legend(loc="upper left", fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT / "tape_segments.png", dpi=110)
    plt.close(fig)
    return labels, errs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, title in RUNS:
        run_figure(name, title)
    end_errors()
    labels, errs = tape_segments()
    for i, lab in enumerate(labels):
        print(f"{lab:18s}", "  ".join(f"{k} {errs[k][i]:+5.1f}%" for k in errs))
    print("figures ->", OUT)


if __name__ == "__main__":
    main()
