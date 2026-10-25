#!/usr/bin/env python3
"""Build the local replay site: site/index.html + site/data/*.json from runs/ and runs_old/.

    python3 make_site.py          # only rebuilds runs whose files changed

Per run: the three estimates (Booster odometer, legs sole, legs lowest) resampled to 20 Hz in the
start frame, marks, tape truth (truth.json) and the phone video (video.* + video.json) if present.
"""
from __future__ import annotations

import json
import math
import os
import shutil
from pathlib import Path

import numpy as np

from odom_plot import clean_odom, legs, load, path_len, to_start_frame

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
DATA = SITE / "data"
HZ = 20.0
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")


def find_runs():
    for d in sorted((ROOT / "runs").glob("*/joints.csv")):
        yield d.parent, "Lobby"
    for d in sorted((ROOT / "runs_old").glob("*/*/joints.csv")):
        yield d.parent, d.parent.parent.name.replace("_", " ")


def video_of(run):
    for p in sorted(run.iterdir()):
        if p.stem == "video" and p.suffix.lower() in VIDEO_EXT:
            return p
    return None


def stats(t, x, y, th, truth):
    d = np.hypot(x, y)
    r = {"end": [round(float(x[-1]), 3), round(float(y[-1]), 3)], "yaw": round(math.degrees(th[-1]), 1),
         "far": round(float(d.max()), 3), "path": round(path_len(t, x, y), 3)}
    if truth.get("far"):
        r["far_err"] = round(r["far"] - truth["far"], 3)
    if truth.get("end"):
        r["end_err"] = round(math.hypot(x[-1] - truth["end"][0], y[-1] - truth["end"][1]), 3)
    return r


def build(run, group, rid):
    t, q, rpy, O, marks = load(run)
    O, n_bad = clean_odom(O)
    est = {"booster": (O["t"], *to_start_frame(O["x"], O["y"], O["theta"]))}
    for c in ("sole", "lowest"):
        (x, y, th), _ = legs(q, rpy, c)
        est[c] = (t, x, y, th)

    truth = {}
    if (run / "truth.json").exists():
        truth = json.loads((run / "truth.json").read_text())

    t0 = t[0]
    grid = np.arange(0.0, t[-1] - t0, 1.0 / HZ)
    series, st = {}, {}
    for k, (tt, x, y, th) in est.items():
        g = grid + t0
        uth = np.unwrap(th)
        series[k] = {
            "x": np.round(np.interp(g, tt, x), 3).tolist(),
            "y": np.round(np.interp(g, tt, y), 3).tolist(),
            "yaw": np.round((np.interp(g, tt, uth) + math.pi) % (2 * math.pi) - math.pi, 3).tolist(),
        }
        st[k] = stats(tt, x, y, th, truth)

    out = {"id": rid, "name": run.name, "group": group, "seconds": round(float(t[-1] - t0), 2),
           "t": np.round(grid, 3).tolist(), "series": series, "stats": st, "truth": truth,
           "marks": [{"t": round(tm - t0, 3), "label": m} for tm, m in marks],
           "odom_glitches": n_bad, "video": None}

    v = video_of(run)
    if v is not None:
        dst = DATA / f"{rid}{v.suffix.lower()}"
        if dst.exists() or dst.is_symlink():
            dst.unlink()
        os.symlink(v, dst)
        meta = json.loads((run / "video.json").read_text()) if (run / "video.json").exists() else {}
        out["video"] = {"src": f"data/{dst.name}", "offset": meta.get("offset", 0.0)}
    (DATA / f"{rid}.json").write_text(json.dumps(out, separators=(",", ":")))
    return {k: out[k] for k in ("id", "name", "group", "seconds", "stats", "truth")} | {
        "video": out["video"] is not None, "marks": len(out["marks"])}


def main():
    DATA.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "site_template.html", SITE / "index.html")
    old = {}
    if (DATA / "index.json").exists():
        old = {r["id"]: r for r in json.loads((DATA / "index.json").read_text())}
    index, built = [], 0
    for run, group in find_runs():
        rid = (group + "__" + run.name).replace(" ", "_").replace("/", "_")
        js = DATA / f"{rid}.json"
        newest = max(p.stat().st_mtime for p in run.iterdir())
        if rid in old and js.exists() and js.stat().st_mtime >= newest:
            index.append(old[rid])
            continue
        print(f"  building {group} / {run.name}")
        index.append(build(run, group, rid))
        built += 1
    # runs/MAIN names the run that counts (the one to show first)
    main_run = (ROOT / "runs" / "MAIN").read_text().strip() if (ROOT / "runs" / "MAIN").exists() else ""
    for r in index:
        r["main"] = r["group"] == "Lobby" and r["name"] == main_run
    (DATA / "index.json").write_text(json.dumps(index, indent=1))
    print(f"site: {len(index)} runs ({built} rebuilt) -> {SITE / 'index.html'}")


if __name__ == "__main__":
    main()
