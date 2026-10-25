import time

import rclpy


class SingleThreadedExecutor:
    def __init__(self):
        self.r = None

    def add_node(self, node):
        pass

    def spin_once(self, timeout_sec=0.0):
        if self.r is None:
            self.r = rclpy._Replay()
        self.r.pump()
        time.sleep(min(timeout_sec, 0.005))
