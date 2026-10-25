from enum import Enum


class ReliabilityPolicy(Enum):
    BEST_EFFORT = 1


class DurabilityPolicy(Enum):
    VOLATILE = 1


class HistoryPolicy(Enum):
    KEEP_LAST = 1


class QoSProfile:
    def __init__(self, **kw):
        pass
