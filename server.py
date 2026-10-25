#!/usr/bin/env python3
"""Local server for the site: serves site/, runs recordings on the robot, streams the live poses.

    python3 server.py --robot booster@192.168.2.152     # normally started by ./k1odom
    python3 server.py --robot demo                      # replay a September run as if it were live
    python3 server.py                                   # no robot: browse runs only

The robot side is odom_walk.py --stream over the shared ssh connection that ./k1odom opened, so no
password is needed here. Stdlib only.
"""
from __future__ import annotations

import argparse
import collections
import json
import mimetypes
import os
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
RUNS = ROOT / "runs"
SSHO = ["-o", "ControlMaster=auto", "-o", f"ControlPath={Path.home()}/.ssh/k1-%r@%h:%p",
        "-o", "ControlPersist=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8"]
ROS = "source /opt/ros/humble/setup.bash && source /opt/booster/BoosterRos2Interface/install/setup.bash"
DEMO_RUN = ROOT / "runs_old" / "sept_stock_heel00mm" / "heel0test1"
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".webm")

site_lock = threading.Lock()


def rebuild_site():
    with site_lock:
        r = subprocess.run([sys.executable, str(ROOT / "make_site.py")], cwd=ROOT,
                           capture_output=True, text=True)
        if r.returncode:
            raise RuntimeError(r.stdout[-400:] + r.stderr[-800:])


class Live:
    """One recording at a time: idle -> starting -> recording -> pulling -> done (or error)."""

    def __init__(self, robot):
        self.robot = robot
        self.lock = threading.Lock()
        self.proc = None
        self.state = "idle" if robot else "offline"
        self.name = None
        self.samples = []
        self.marks = []
        self.logs = collections.deque(maxlen=40)
        self.error = None
        self.run_id = None

    def status(self):
        with self.lock:
            return {"robot": self.robot, "state": self.state, "name": self.name, "n": len(self.samples),
                    "marks": self.marks, "logs": list(self.logs)[-12:], "error": self.error,
                    "run_id": self.run_id}

    def start(self, name):
        with self.lock:
            if not self.robot:
                raise ValueError("no robot: start with ./k1odom <robot ip>")
            if self.state in ("starting", "recording", "pulling"):
                raise ValueError(f"busy ({self.state})")
            name = name or time.strftime("lobby_%m%d_%H%M%S")
            if not NAME_RE.match(name):
                raise ValueError("name: letters, digits, _ and - only")
            if (RUNS / name).exists():
                raise ValueError(f"run {name} already exists")
            self.name, self.samples, self.marks, self.error, self.run_id = name, [], [], None, None
            self.logs.clear()
            self.state = "starting"
            if self.robot == "demo":
                env = dict(os.environ, PYTHONPATH=str(ROOT / "tools" / "fake_robot"), FAKE_RUN=str(DEMO_RUN))
                cmd = [sys.executable, "-u", str(ROOT / "odom_walk.py"), name, "--stream",
                       "--outdir", str(RUNS)]
            else:
                env = None
                remote = f"{ROS} && cd ~/k1-legodom && python3 -u odom_walk.py {name} --stream"
                cmd = ["ssh", *SSHO, self.robot, f"bash -lc '{remote}'"]
            self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, text=True, bufsize=1, env=env)
            threading.Thread(target=self._read, args=(self.proc,), daemon=True).start()
            return name

    def _send(self, line):
        with self.lock:
            if self.proc is None or self.proc.poll() is not None:
                raise ValueError("not recording")
            self.proc.stdin.write(line + "\n")
            self.proc.stdin.flush()

    def mark(self, label):
        label = re.sub(r"[,\n\r]", " ", label or "").strip()[:40]
        with self.lock:
            if self.state != "recording":
                raise ValueError("not recording yet")
            t = self.samples[-1]["t"] if self.samples else 0.0
            self.marks.append({"t": t, "label": label or f"m{len(self.marks) + 1}"})
            label = self.marks[-1]["label"]
        self._send(label)

    def stop(self):
        self._send("q")

    def _read(self, proc):
        for line in proc.stdout:
            line = line.rstrip("\n")
            if line.startswith("P "):
                try:
                    p = json.loads(line[2:])
                except ValueError:
                    continue
                with self.lock:
                    self.samples.append(p)
                    if self.state == "starting":
                        self.state = "recording"
            elif line.strip():
                with self.lock:
                    self.logs.append(line.strip())
                    if "data flowing" in line and self.state == "starting":
                        self.state = "recording"
        rc = proc.wait()
        with self.lock:
            name = self.name
            got_data = bool(self.samples)
            if not got_data:
                self.state, self.error = "error", f"recorder exited ({rc}) before any data, see the log"
                return
            self.state = "pulling"
        try:
            if self.robot != "demo":
                RUNS.mkdir(exist_ok=True)
                r = subprocess.run(["scp", *SSHO, "-rq", f"{self.robot}:~/k1-legodom/runs/{name}", str(RUNS)],
                                   capture_output=True, text=True, timeout=300)
                if r.returncode:
                    raise RuntimeError("scp failed: " + r.stderr.strip()[-300:])
            rebuild_site()
            with self.lock:
                self.state, self.run_id = "done", f"Lobby__{name}"
        except Exception as e:  # keep the server alive, show the reason on the page
            with self.lock:
                self.state, self.error = "error", str(e)


def run_dir_of(rid):
    """Only lobby runs (runs/<name>) are editable from the site."""
    if not rid or not rid.startswith("Lobby__"):
        raise ValueError("only lobby runs can be edited")
    name = rid[len("Lobby__"):]
    if not NAME_RE.match(name) or not (RUNS / name).is_dir():
        raise ValueError(f"no run {name}")
    return RUNS / name


class Handler(SimpleHTTPRequestHandler):
    live: Live = None

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(SITE), **kw)

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/status":
            return self._json(self.live.status())
        if u.path == "/api/live":
            since = int(parse_qs(u.query).get("since", ["0"])[0])
            with self.live.lock:
                return self._json({"samples": self.live.samples[since:], "state": self.live.state,
                                   "marks": self.live.marks})
        if self.headers.get("Range") and u.path.startswith("/data/"):
            return self._range(u.path)
        return super().do_GET()

    def end_headers(self):
        if self.path.split("?")[0].endswith((".json", ".html", "/")):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def _range(self, path):
        """Byte ranges, so the browser can seek in the phone video."""
        f = Path(self.translate_path(path))
        if not f.is_file():
            return self.send_error(404)
        size = f.stat().st_size
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers["Range"])
        a = int(m.group(1)) if m and m.group(1) else 0
        b = int(m.group(2)) if m and m.group(2) else size - 1
        b = min(b, size - 1)
        if a > b:
            return self.send_error(416)
        self.send_response(206)
        self.send_header("Content-Type", mimetypes.guess_type(f.name)[0] or "application/octet-stream")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
        self.send_header("Content-Length", str(b - a + 1))
        self.end_headers()
        with open(f, "rb") as fh:
            fh.seek(a)
            left = b - a + 1
            try:
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/start":
                return self._json({"name": self.live.start(self._body().get("name", "").strip())})
            if u.path == "/api/mark":
                self.live.mark(self._body().get("label", ""))
                return self._json({"ok": True})
            if u.path == "/api/stop":
                self.live.stop()
                return self._json({"ok": True})
            if u.path == "/api/truth":
                b = self._body()
                d = run_dir_of(b.get("id"))
                t = {}
                if b.get("far") not in (None, ""):
                    t["far"] = float(b["far"])
                if b.get("end") and all(v not in (None, "") for v in b["end"]):
                    t["end"] = [float(b["end"][0]), float(b["end"][1])]
                (d / "truth.json").write_text(json.dumps(t))
                rebuild_site()
                return self._json({"ok": True, "truth": t})
            if u.path == "/api/offset":
                b = self._body()
                d = run_dir_of(b.get("id"))
                (d / "video.json").write_text(json.dumps({"offset": float(b["offset"])}))
                rebuild_site()
                return self._json({"ok": True})
            if u.path == "/api/video":
                q = parse_qs(u.query)
                d = run_dir_of(q.get("id", [""])[0])
                ext = "." + q.get("ext", ["mp4"])[0].lower().lstrip(".")
                if ext not in VIDEO_EXT:
                    raise ValueError(f"video must be one of {VIDEO_EXT}")
                for old in d.glob("video.*"):
                    if old.suffix.lower() in VIDEO_EXT:
                        old.unlink()
                left = int(self.headers.get("Content-Length") or 0)
                with open(d / f"video{ext}", "wb") as f:
                    while left > 0:
                        chunk = self.rfile.read(min(1 << 20, left))
                        if not chunk:
                            break
                        f.write(chunk)
                        left -= len(chunk)
                rebuild_site()
                return self._json({"ok": True})
            return self._json({"error": "unknown endpoint"}, 404)
        except (ValueError, RuntimeError, KeyError) as e:
            return self._json({"error": str(e)}, 400)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--robot", default="", help="user@ip, 'demo', or empty for browsing only")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--no-open", action="store_true")
    a = ap.parse_args()

    rebuild_site()
    Handler.live = Live(a.robot)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://localhost:{a.port}/" + ("#live" if a.robot else "")
    print(f"site: {url}   robot: {a.robot or 'none'}   (Ctrl+C to quit)")
    if not a.no_open:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        p = Handler.live.proc
        if p and p.poll() is None:
            print("\nstopping the recording on the robot (saves the run) ...")
            try:
                p.stdin.write("q\n")
                p.stdin.flush()
                p.wait(timeout=10)
            except Exception:
                p.terminate()


if __name__ == "__main__":
    main()
