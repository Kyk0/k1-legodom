#!/usr/bin/env python3
"""Record the K1 while you walk it with the Booster remote / app; compare two odometries live.

    1. Booster's own odometer   (/odometer_state, from the stock walking controller)
    2. Our leg odometry         (legodom.py: joint angles + IMU, stance foot fixed on the floor)

This script only LISTENS. It sends no commands, so walk the robot with the remote as usual.

Run (on the robot, or a laptop on its network):
    source /opt/ros/humble/setup.bash
    source /opt/booster/BoosterRos2Interface/install/setup.bash
    python3 odom_walk.py lobby_01

    Enter      drop a mark (e.g. "at the far tape mark", "back at start")
    q + Enter  stop and save          (Ctrl+C works too)

Output: runs/<name>/  joints.csv imu.csv odometer.csv legodom.csv marks.csv run.json
Then on the Mac:  python3 odom_plot.py runs/<name> --far 5.0

--stream (used by the Mac's server.py / site): prints "P {json}" pose lines at 10 Hz instead of the
status line; marks and "q" still come on stdin, and stdin closing also stops and saves the run.
"""
from __future__ import annotations

import argparse
import json
import math
import signal
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from legodom import LEG, LegOdom, relative, wrap  # noqa: E402

ANKLE_PAR = [(14, "Left_Ankle_Pitch"), (15, "Left_Ankle_Roll"),
             (20, "Right_Ankle_Pitch"), (21, "Right_Ankle_Roll")]
# same schema as walk.py / heel_recorder.py, so old runs and new runs read the same way
JOINTS_HEADER = (["t"] + [f"{p}.{n}" for _, n in LEG for p in ("pos", "vel", "eff")]
                 + [f"par_eff.{n}" for _, n in ANKLE_PAR])
IMU_HEADER = ["t", "roll", "pitch", "yaw", "gx", "gy", "gz", "ax", "ay", "az"]


def g(v):
    return f"{v:.6g}"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("name", nargs="?", default=datetime.now().strftime("odom_%Y%m%d_%H%M%S"))
    ap.add_argument("--outdir", default=str(Path(__file__).resolve().parent / "runs"))
    ap.add_argument("--contact", default="lowest", choices=["sole", "lowest"],
                    help="leg-odometry contact model for the LIVE numbers (the plot computes both)")
    ap.add_argument("--stream", action="store_true", help="machine-readable pose lines for the site")
    args = ap.parse_args()

    run_dir = Path(args.outdir) / args.name
    if run_dir.exists() and any(run_dir.iterdir()):
        sys.exit(f"{run_dir} already exists, pick another name")
    run_dir.mkdir(parents=True, exist_ok=True)

    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.qos import DurabilityPolicy, HistoryPolicy, QoSProfile, ReliabilityPolicy
    import booster_interface.msg as bmsg

    # BEST_EFFORT + VOLATILE: never back-pressures the robot's publishers (as in walk.py)
    qos = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT, durability=DurabilityPolicy.VOLATILE,
                     history=HistoryPolicy.KEEP_LAST, depth=200)

    f_j = open(run_dir / "joints.csv", "w")
    f_i = open(run_dir / "imu.csv", "w")
    f_o = open(run_dir / "odometer.csv", "w")
    f_l = open(run_dir / "legodom.csv", "w")
    f_m = open(run_dir / "marks.csv", "w")
    f_j.write(",".join(JOINTS_HEADER) + "\n")
    f_i.write(",".join(IMU_HEADER) + "\n")
    f_o.write("t,x,y,theta\n")
    f_l.write("t,x,y,yaw,stance\n")
    f_m.write("t,mark\n")

    lock = threading.Lock()
    stop = threading.Event()
    odom = LegOdom(contact=args.contact)
    st = {"n_low": 0, "n_odom": 0, "booster": None, "booster0": None, "legs0": None,
          "t0": None, "marks": []}

    def on_low(msg):
        t = time.time()
        ms, mp, imu = msg.motor_state_serial, msg.motor_state_parallel, msg.imu_state
        q12 = [ms[i].q for i, _ in LEG]
        rpy = (imu.rpy[0], imu.rpy[1], imu.rpy[2])
        j = [f"{t:.6f}"]
        for i, _ in LEG:
            j += (g(ms[i].q), g(ms[i].dq), g(ms[i].tau_est))
        j += [g(mp[i].tau_est) for i, _ in ANKLE_PAR]
        w, a = imu.gyro, imu.acc
        u = [f"{t:.6f}", g(rpy[0]), g(rpy[1]), g(rpy[2]), g(w[0]), g(w[1]), g(w[2]),
             g(a[0]), g(a[1]), g(a[2])]
        with lock:
            odom.update(q12, rpy)
            if st["legs0"] is None:
                st["legs0"] = (odom.x, odom.y, odom.yaw)
                st["t0"] = t
            st["n_low"] += 1
            f_j.write(",".join(j) + "\n")
            f_i.write(",".join(u) + "\n")
            f_l.write(f"{t:.6f},{odom.x:.5f},{odom.y:.5f},{odom.yaw:.5f},{odom.stance}\n")

    def on_odom(msg):
        t = time.time()
        p = (msg.x, msg.y, msg.theta)
        with lock:
            st["n_odom"] += 1
            f_o.write(f"{t:.6f},{g(msg.x)},{g(msg.y)},{g(msg.theta)}\n")   # raw, glitches and all
            # live view only: skip the DDS queue's stale messages at the start and single-sample
            # spikes; a jump that persists for 25 messages (50 ms) is taken as real
            if st["n_odom"] <= 20:
                return
            last = st["booster"]
            jump = last is not None and (abs(wrap(p[2] - last[2])) > 0.2 or
                                         math.hypot(p[0] - last[0], p[1] - last[1]) > 0.1)
            st["rejects"] = st.get("rejects", 0) + 1 if jump else 0
            if jump and st["rejects"] < 25:
                return
            st["booster"] = p
            if st["booster0"] is None:
                st["booster0"] = p

    def rel_now():
        """(booster, legs) poses relative to their own start, in the start heading frame."""
        b = l = None
        if st["booster"] is not None:
            b = relative(*st["booster"], *st["booster0"])
        if st["legs0"] is not None:
            l = relative(odom.x, odom.y, odom.yaw, *st["legs0"])
        return b, l

    def add_mark(label):
        t = time.time()
        with lock:
            b, l = rel_now()
            st["marks"].append({"t": t, "mark": label, "booster": b, "legs": l})
            f_m.write(f"{t:.6f},{label}\n")
            f_m.flush()
        print(f"\n[mark] {label}   booster {fmt(b)}   legs {fmt(l)}", flush=True)

    def read_keys():
        n = 0
        for line in sys.stdin:
            if line.strip().lower() in ("q", "quit", "exit"):
                break
            if not ready_evt.is_set():
                continue
            n += 1
            add_mark(line.strip() or f"m{n}")
        stop.set()     # q, or stdin closed (the Mac side went away): save and exit

    ready_evt = threading.Event()
    threading.Thread(target=read_keys, daemon=True).start()
    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, lambda *_: stop.set())

    rclpy.init()
    node = rclpy.create_node("k1_odom_walk")
    node.create_subscription(bmsg.LowState, "/low_state", on_low, qos)
    node.create_subscription(bmsg.Odometer, "/odometer_state", on_odom, qos)
    ex = SingleThreadedExecutor()
    ex.add_node(node)

    period = 0.1 if args.stream else 0.5
    print(f"[rec] writing to {run_dir}", flush=True)
    print("[rec] waiting for /low_state and /odometer_state ...", flush=True)
    ready = False
    t_print = time.monotonic()
    prev = (0, 0)
    try:
        while not stop.is_set():
            ex.spin_once(timeout_sec=0.02)
            now = time.monotonic()
            if now - t_print < period:
                continue
            dt, t_print = now - t_print, now
            with lock:
                hz = ((st["n_low"] - prev[0]) / dt, (st["n_odom"] - prev[1]) / dt)
                prev = (st["n_low"], st["n_odom"])
                b, l = rel_now()
                el = time.time() - st["t0"] if st["t0"] else 0.0
            if not ready:
                waited = time.time() - (st["t0"] or time.time())
                if hz[0] > 100 and (hz[1] > 50 or waited > 10):
                    ready = True
                    if hz[1] <= 50:
                        print("\n[rec] WARNING: no /odometer_state, recording legs only", flush=True)
                    print("[rec] data flowing. Start the video, then walk.  Enter = mark,  q+Enter = stop",
                          flush=True)
                    add_mark("start")
                    ready_evt.set()
                elif args.stream:
                    print(f"[rec] /low_state {hz[0]:.0f} Hz  /odometer_state {hz[1]:.0f} Hz", flush=True)
                else:
                    print(f"\r[rec] /low_state {hz[0]:4.0f} Hz  /odometer_state {hz[1]:4.0f} Hz ",
                          end="", flush=True)
                continue
            if args.stream:
                r3 = lambda p: None if p is None else [round(p[0], 3), round(p[1], 3), round(p[2], 3)]
                print("P " + json.dumps({"t": round(el, 2), "b": r3(b), "l": r3(l), "st": odom.stance,
                                         "hz": [round(hz[0]), round(hz[1])]}), flush=True)
                continue
            diff = math.hypot(b[0] - l[0], b[1] - l[1]) if b and l else float("nan")
            warn = "  LOW RATE" if hz[0] < 300 else ""
            print(f"\r{el:6.1f}s  booster {fmt(b)}   legs {fmt(l)}   gap {diff:5.2f} m{warn}   ",
                  end="", flush=True)
    except KeyboardInterrupt:
        pass
    except Exception as e:  # rclpy's own SIGINT handling can surface as ExternalShutdownException
        print(f"\n[rec] stopped: {type(e).__name__} {e}")

    if ready:
        add_mark("stop")
    with lock:
        for f in (f_j, f_i, f_o, f_l, f_m):
            f.close()
        summary = {
            "name": args.name, "started": datetime.fromtimestamp(st["t0"] or time.time()).isoformat(),
            "seconds": (time.time() - st["t0"]) if st["t0"] else 0.0,
            "rows": {"low_state": st["n_low"], "odometer": st["n_odom"]},
            "live_contact": args.contact, "leg_switches": odom.switches, "marks": st["marks"],
        }
    (run_dir / "run.json").write_text(json.dumps(summary, indent=2))
    try:
        node.destroy_node()
        rclpy.shutdown()
    except Exception:
        pass

    print(f"\n\n[done] {run_dir}   {summary['seconds']:.0f} s, {st['n_low']} low_state rows, "
          f"{st['n_odom']} odometer rows, {odom.switches} steps")
    for m in st["marks"]:
        print(f"   {m['mark']:>12s}   booster {fmt(m['booster'])}   legs {fmt(m['legs'])}")
    print(f"copy it to the Mac and run:  python3 odom_plot.py {run_dir.name}", flush=True)
    print("DONE", flush=True)


def fmt(p):
    if p is None:
        return "   --     --      -- "
    return f"x{p[0]:6.2f} y{p[1]:6.2f} yaw{math.degrees(p[2]):5.0f}"


if __name__ == "__main__":
    main()
