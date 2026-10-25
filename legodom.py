"""Leg-kinematic odometry for the Booster K1. numpy only, so it runs on the robot as is.

Idea: the stance foot does not move on the floor. Joint angles give the foot's position relative
to the trunk (forward kinematics), the IMU gives the trunk's orientation, so

    trunk_xy = foot_anchor - R(imu) @ fk(stance leg)

and the anchor is re-set each time the other foot becomes the stance foot. Heading = IMU yaw.

Leg chain from the official K1 MJCF (sonic_k1_kit/assets/k1.xml): the leg bodies have no rotation
offsets, only translations, so FK is translations + one joint rotation per link. The IMU site sits
at the trunk origin.
"""
from __future__ import annotations

import math

import numpy as np

# Robot serial motor indices of the 12 leg joints (same as walk.py / heel_recorder.py)
LEG = [
    (10, "Left_Hip_Pitch"), (11, "Left_Hip_Roll"), (12, "Left_Hip_Yaw"),
    (13, "Left_Knee_Pitch"), (14, "Left_Ankle_Pitch"), (15, "Left_Ankle_Roll"),
    (16, "Right_Hip_Pitch"), (17, "Right_Hip_Roll"), (18, "Right_Hip_Yaw"),
    (19, "Right_Knee_Pitch"), (20, "Right_Ankle_Pitch"), (21, "Right_Ankle_Roll"),
]

# (offset from parent in parent frame, joint axis) per link, hip pitch -> ankle roll
_AXES = ["y", "x", "z", "y", "y", "x"]


def _chain(side):
    s = 1.0 if side == "L" else -1.0
    offs = [
        (0.0, s * 0.096, -0.077),          # trunk -> hip pitch
        (0.0, 0.0, -0.026),                # -> hip roll
        (0.012, 0.0, -0.0485),             # -> hip yaw
        (-0.014, 0.0, -0.117),             # -> knee
        (0.00019706, s * 0.0002, -0.24519),  # -> ankle pitch
        (0.0, 0.0, 0.0),                   # -> ankle roll
    ]
    return [np.array(o) for o in offs]


CHAIN = {"L": _chain("L"), "R": _chain("R")}
# Contact points in the ankle-roll frame: sole centre, toe and heel of the collision box
# (box pos 0.026 0 -0.02, half size 0.09 0.035 0.018 -> sole at z = -0.038)
SOLE = np.array([0.026, 0.0, -0.038])
TOE = np.array([0.116, 0.0, -0.038])
HEEL = np.array([-0.064, 0.0, -0.038])


def _rot(axis, a):
    c, s = math.cos(a), math.sin(a)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    if axis == "y":
        return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def foot_frame(q6, side):
    """Ankle-roll frame (R, p) in the trunk frame for 6 leg joint angles."""
    R = np.eye(3)
    p = np.zeros(3)
    for off, ax, a in zip(CHAIN[side], _AXES, q6):
        p = p + R @ off
        R = R @ _rot(ax, a)
    return R, p


def rpy_to_R(roll, pitch, yaw):
    return _rot("z", yaw) @ _rot("y", pitch) @ _rot("x", roll)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class LegOdom:
    """Feed it (q12, rpy) at any rate; read .x .y .yaw (world frame, yaw = IMU yaw).

    contact="sole": a fixed point under the ankle (flat-foot assumption)
    contact="lowest": the lowest of heel / sole / toe, so heel strike and toe-off pivot correctly
    """

    def __init__(self, contact="lowest", switch_margin=0.005):
        self.contact = contact
        self.margin = switch_margin
        self.stance = None          # "L" / "R"
        self.point = None           # contact point index on the stance foot
        self.anchor = None          # world position of the stance contact point
        self.base = np.zeros(3)
        self.yaw = 0.0
        self.switches = 0

    def _points(self, q6, side, R_w):
        Rf, pf = foot_frame(q6, side)
        pts = [SOLE] if self.contact == "sole" else [HEEL, SOLE, TOE]
        return [R_w @ (pf + Rf @ c) for c in pts]

    def update(self, q12, rpy):
        R_w = rpy_to_R(*rpy)
        self.yaw = rpy[2]
        feet = {"L": self._points(q12[:6], "L", R_w), "R": self._points(q12[6:], "R", R_w)}
        low = {s: min(range(len(p)), key=lambda i: p[i][2]) for s, p in feet.items()}

        if self.stance is None:
            self.stance = min("LR", key=lambda s: feet[s][low[s]][2])
            self.point = low[self.stance]
            self.anchor = self.base + feet[self.stance][self.point]
            return self

        # trunk from the current stance contact, BEFORE any switch, so the new anchor continues it
        self.base = self.anchor - feet[self.stance][self.point]

        other = "R" if self.stance == "L" else "L"
        z_st = feet[self.stance][self.point][2]
        if feet[other][low[other]][2] < z_st - self.margin:
            self.stance, self.point = other, low[other]
            self.anchor = self.base + feet[other][self.point]
            self.switches += 1
        elif low[self.stance] != self.point and \
                feet[self.stance][low[self.stance]][2] < z_st - self.margin:
            # rolling heel -> sole -> toe on the same foot
            self.point = low[self.stance]
            self.anchor = self.base + feet[self.stance][self.point]
        return self

    @property
    def x(self):
        return float(self.base[0])

    @property
    def y(self):
        return float(self.base[1])


def relative(x, y, th, x0, y0, th0):
    """Pose relative to a start pose, in the start heading frame (x = forward at start)."""
    c, s = math.cos(-th0), math.sin(-th0)
    dx, dy = x - x0, y - y0
    return c * dx - s * dy, s * dx + c * dy, wrap(th - th0)
