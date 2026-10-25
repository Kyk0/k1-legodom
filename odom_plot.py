#!/usr/bin/env python3
"""Compare Booster's odometer and our leg odometry for one recorded run (on the Mac).

    python3 odom_plot.py runs/lobby_01                 # plot + table
    python3 odom_plot.py runs/lobby_01 --far 5.0       # tape distance start -> far mark
    python3 odom_plot.py runs/lobby_01 --far 5.0 --end 0 0   # where it really ended (m, start frame)

Ground truth from the floor tape:
    --far D     real distance from the start mark to the farthest point (e.g. the 5 m mark)
    --end X Y   real end position relative to the start, x = forward at start (there-and-back: 0 0)

Leg odometry is recomputed here from joints.csv + imu.csv for both contact models
(sole = flat-foot point, lowest = heel/sole/toe pivot). Writes compare.png and compare.json.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from legodom import LEG, LegOdom  # noqa: E402


def load(run):
    J = np.genfromtxt(run / "joints.csv", delimiter=",", names=True)
    I = np.genfromtxt(run / "imu.csv", delimiter=",", names=True)
    O = np.genfromtxt(run / "odometer.csv", delimiter=",", names=True)
    # genfromtxt strips the dot: "pos.Left_Hip_Pitch" -> "posLeft_Hip_Pitch"
    q = np.stack([J["pos" + n] for _, n in LEG], 1)
    rpy = np.stack([I["roll"], I["pitch"], I["yaw"]], 1)
    marks = []
    if (run / "marks.csv").exists():
        with open(run / "marks.csv") as f:
            next(f)
            for line in f:
                t, m = line.rstrip("\n").split(",", 1)
                marks.append((float(t), m))
    return J["t"], q, rpy, O, marks


def clean_odom(O):
    """Drop odometer glitches: stale queued messages at the start and single-sample spikes in
    theta / position (both seen in the September runs). Median over 9 samples is the reference."""
    th = np.unwrap(O["theta"])
    win = np.lib.stride_tricks.sliding_window_view
    pad = lambda v: np.pad(v, 4, mode="edge")
    med = [np.median(win(pad(v), 9), axis=1) for v in (O["x"], O["y"], th)]
    bad = (np.abs(th - med[2]) > 0.2) | (np.hypot(O["x"] - med[0], O["y"] - med[1]) > 0.1)
    bad[:20] = True     # anything older than the first 40 ms may be from the DDS queue
    return O[~bad], int(bad[20:].sum())


def to_start_frame(x, y, th):
    c, s = math.cos(-th[0]), math.sin(-th[0])
    dx, dy = x - x[0], y - y[0]
    yaw = (th - th[0] + math.pi) % (2 * math.pi) - math.pi
    return c * dx - s * dy, s * dx + c * dy, yaw


def legs(q, rpy, contact):
    lo = LegOdom(contact=contact)
    out = np.empty((len(q), 3))
    for k in range(len(q)):
        lo.update(q[k], rpy[k])
        out[k] = lo.x, lo.y, lo.yaw
    return to_start_frame(out[:, 0], out[:, 1], out[:, 2]), lo.switches


def path_len(t, x, y, step=0.5):
    """Length on a 0.5 s grid, so the trunk's side-to-side sway per step does not count."""
    g = np.arange(t[0], t[-1], step)
    xs, ys = np.interp(g, t, x), np.interp(g, t, y)
    return float(np.sum(np.hypot(np.diff(xs), np.diff(ys))))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("run")
    ap.add_argument("--far", type=float, help="tape distance start -> farthest point, m")
    ap.add_argument("--end", type=float, nargs=2, metavar=("X", "Y"), help="true end position, m")
    ap.add_argument("--no-show", action="store_true")
    a = ap.parse_args()
    run = Path(a.run)

    t, q, rpy, O, marks = load(run)
    est = {}
    O, n_bad = clean_odom(O)
    bx, by, bth = to_start_frame(O["x"], O["y"], O["theta"])
    est["Booster odometer"] = (O["t"], bx, by, bth)
    switches = {}
    for c in ("sole", "lowest"):
        (x, y, th), switches[c] = legs(q, rpy, c)
        est[f"legs ({c})"] = (t, x, y, th)

    rows = {}
    for name, (tt, x, y, th) in est.items():
        d = np.hypot(x, y)
        r = {"end_x": float(x[-1]), "end_y": float(y[-1]), "end_yaw_deg": math.degrees(th[-1]),
             "far": float(d.max()), "path": path_len(tt, x, y)}
        if a.far:
            r["far_err"] = r["far"] - a.far
            r["far_err_pct"] = 100 * r["far_err"] / a.far
        if a.end:
            r["end_err"] = math.hypot(r["end_x"] - a.end[0], r["end_y"] - a.end[1])
            r["end_err_pct_of_path"] = 100 * r["end_err"] / max(r["path"], 1e-6)
        r["marks"] = {m: [float(np.interp(tm, tt, x)), float(np.interp(tm, tt, y))] for tm, m in marks}
        rows[name] = r

    print(f"\n{run.name}: {t[-1] - t[0]:.0f} s, {switches['sole']} steps, "
          f"{n_bad} odometer glitches dropped")
    hdr = f"{'':18s} {'end x':>7s} {'end y':>7s} {'yaw':>6s} {'far':>6s} {'path':>6s}"
    if a.far:
        hdr += f" {'far err':>12s}"
    if a.end:
        hdr += f" {'end err':>15s}"
    print(hdr)
    for name, r in rows.items():
        line = (f"{name:18s} {r['end_x']:7.2f} {r['end_y']:7.2f} {r['end_yaw_deg']:6.0f} "
                f"{r['far']:6.2f} {r['path']:6.2f}")
        if a.far:
            line += f" {r['far_err']:+6.2f} ({r['far_err_pct']:+4.0f}%)"
        if a.end:
            line += f" {r['end_err']:6.2f} ({r['end_err_pct_of_path']:4.1f}%)"
        print(line)
    if a.far or a.end:
        print("far err = estimate - tape;  end err = distance from the true end, % of path walked")
    (run / "compare.json").write_text(json.dumps(
        {"far_truth": a.far, "end_truth": a.end, "estimates": rows}, indent=2))

    import matplotlib
    if a.no_show:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    colors = {"Booster odometer": "#d62728", "legs (sole)": "#1f77b4", "legs (lowest)": "#7fb3e0"}
    fig = plt.figure(figsize=(13, 6))
    ax = fig.add_subplot(1, 2, 1)
    for name, (tt, x, y, th) in est.items():
        ax.plot(x, y, color=colors[name], lw=2 if "lowest" not in name else 1, label=name)
        ax.plot(x[-1], y[-1], "o", color=colors[name])
        for tm, m in marks:
            ax.plot(np.interp(tm, tt, x), np.interp(tm, tt, y), "x", color=colors[name])
    ax.plot(0, 0, "ks", label="start")
    if a.end:
        ax.plot(*a.end, "k*", ms=14, label="true end")
    if a.far:
        ax.add_patch(plt.Circle((0, 0), a.far, fill=False, ls="--", color="gray", label=f"{a.far} m"))
    ax.set_aspect("equal", adjustable="datalim")
    ax.set_xlabel("x forward at start (m)")
    ax.set_ylabel("y left (m)")
    ax.set_title(f"{run.name}: trajectory")
    ax.grid(alpha=0.3)
    ax.legend(fontsize=8)

    ax2 = fig.add_subplot(2, 2, 2)
    ax3 = fig.add_subplot(2, 2, 4, sharex=ax2)
    t0 = t[0]
    for name, (tt, x, y, th) in est.items():
        ax2.plot(tt - t0, np.hypot(x, y), color=colors[name], label=name)
        ax3.plot(tt - t0, np.degrees(th), color=colors[name])
    for tm, m in marks:
        for axx in (ax2, ax3):
            axx.axvline(tm - t0, color="gray", lw=0.6)
        ax2.text(tm - t0, ax2.get_ylim()[1], m, fontsize=7, rotation=90, va="top")
    if a.far:
        ax2.axhline(a.far, color="gray", ls="--")
    ax2.set_ylabel("distance from start (m)")
    ax2.grid(alpha=0.3)
    ax3.set_ylabel("yaw (deg)")
    ax3.set_xlabel("time (s)")
    ax3.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(run / "compare.png", dpi=130)
    print(f"saved {run / 'compare.png'}")
    if not a.no_show:
        plt.show()


if __name__ == "__main__":
    main()
