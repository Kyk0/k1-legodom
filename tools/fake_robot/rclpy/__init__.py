"""Fake rclpy for ./k1odom demo: replays a recorded run (FAKE_RUN) in real time,
then keeps publishing the last frame (the robot standing still).

Only what odom_walk.py uses. /low_state from joints.csv + imu.csv, /odometer_state from odometer.csv.
"""
import os
import time
from types import SimpleNamespace as NS

import numpy as np

_subs = {}


def init(*a, **k):
    pass


def shutdown(*a, **k):
    pass


class _Node:
    def create_subscription(self, typ, topic, cb, qos):
        _subs[topic] = cb

    def destroy_node(self):
        pass


def create_node(name):
    return _Node()


class _Replay:
    def __init__(self):
        run = os.environ["FAKE_RUN"]
        J = np.genfromtxt(f"{run}/joints.csv", delimiter=",", names=True)
        I = np.genfromtxt(f"{run}/imu.csv", delimiter=",", names=True)
        O = np.genfromtxt(f"{run}/odometer.csv", delimiter=",", names=True)
        legs = [c for c in J.dtype.names if c.startswith("pos")]
        self.t = J["t"] - J["t"][0]
        self.q = np.stack([J[c] for c in legs], 1)
        self.imu = np.stack([I[c] for c in ("roll", "pitch", "yaw", "gx", "gy", "gz", "ax", "ay", "az")], 1)
        self.to = O["t"] - J["t"][0]
        self.odom = np.stack([O["x"], O["y"], O["theta"]], 1)
        self.t0 = time.monotonic()
        self.k = self.ko = 0

    def pump(self):
        now = time.monotonic() - self.t0
        n, no = len(self.t), len(self.to)
        while self.k < n and self.t[self.k] <= now:
            self._low(self.k)
            self.k += 1
        while self.ko < no and self.to[self.ko] <= now:
            self._odom(self.ko)
            self.ko += 1
        if self.k >= n:        # replay over: stand still at ~500 Hz
            last = getattr(self, "_hold", now)
            for _ in range(int((now - last) * 500)):
                self._low(n - 1)
                self._odom(no - 1)
            self._hold = last + int((now - last) * 500) / 500

    def _low(self, k):
        q, u = self.q[k], self.imu[k]
        ms = [NS(q=0.0, dq=0.0, tau_est=0.0) for _ in range(22)]
        for i in range(12):
            ms[10 + i] = NS(q=float(q[i]), dq=0.0, tau_est=0.0)
        _subs["/low_state"](NS(motor_state_serial=ms, motor_state_parallel=[NS(tau_est=0.0)] * 22,
                               imu_state=NS(rpy=list(u[0:3]), gyro=list(u[3:6]), acc=list(u[6:9]))))

    def _odom(self, k):
        x, y, th = self.odom[k]
        _subs["/odometer_state"](NS(x=float(x), y=float(y), theta=float(th)))
