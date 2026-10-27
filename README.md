# K1 leg odometry: lobby evaluation

Comparison of Booster's built-in odometer and our joint-angle + IMU leg odometry on the real K1, operated with the remote in stock walking mode. Eight identified tests were recorded on October 25–26, 2026.

**[Full report: results, test descriptions, screenshots, plots and video slots →](REPORT.md)**

## Summary

Mean absolute distance error across the measured-distance comparison rows: **Booster 14.9%, legs (lowest) 4.7%, legs (sole) 8.1%**. Lowest fits the starred 9/6/12 m test better; sole fits the 5 m forward/backward test better. The average equally weights six individual long-route traversals and two direction averages from the 5 m test.

Across the seven moving tests, median endpoint discrepancy was **1.22 m for Booster, 0.25 m for lowest and 0.29 m for sole**. Final positions were approximate, generally within 0.3 m of START, so these are closure comparisons rather than precise ground-truth errors.

## Known tests at a glance

Endpoint discrepancies are in metres, relative to the reported final position. The starred recording is the main distance test.

| Test | Procedure | Time | Booster | Lowest | Sole |
| --- | --- | --- | --- | --- | --- |
| ★ 9/6/12 m out-and-back | Measured routes, turning between directions | 110 s | 0.96 | 0.32 | 0.29 |
| 5 m forward/backward | Repeated forward and reverse walking, no turnaround | 108 s | 11.42 | 0.57 | 0.46 |
| Five turns each way | On-the-spot turns; ~0.46 m actual diagonal drift | 57 s | 0.28 | 0.12 | 0.20 |
| Mixed walking and turning | Chaotic simultaneous walking and turning | 70 s | 1.22 | 0.12 | 0.16 |
| Push/block stress | Pushed and restrained while stepping | 81 s | 2.59 | 0.18 | 0.46 |
| Continuous obstruction | Repeated walking against an obstacle | 83 s | 7.74 | 0.25 | 0.32 |
| Sideways pulling | Pulled sideways while stepping | 48 s | 0.91 | 0.40 | 0.20 |
| Standing | Untouched for 67 s | 67 s | 0.00 | 0.00 | 0.00 |

## How we measured

The robot recorder only listens: it logs joint angles, IMU and Booster's `/odometer_state` while the operator controls walking. Our leg estimator computes body motion relative to a planted foot using joint kinematics and IMU orientation. **Sole** fixes one point under the ankle; **lowest** chooses the lowest heel/sole/toe point and is the current live default.

For distance accuracy, we compared estimated displacement with tape-measured **9 m, 6 m, 12 m and 5 m** traversals. Mark presses delimit the long-route legs; trajectory reversals identify the repeated 5 m legs. Distance error = `(estimate − measured length) / measured length × 100%`.

For endpoint closure, the operator aimed to finish where the robot started. The actual final position was judged by eye within roughly **1 ft (0.3 m)**; the turn test instead ended about **1.5 ft (0.46 m) forward-right**. Small heading differences around **5°** can look almost unchanged to the operator. Imperfect return/alignment may explain part of the residual; we retain the recorded numbers rather than subtract an arbitrary operator error. Accurate orientation error needs an independent heading reference.

The [full report](REPORT.md) gives each known test's procedure, basic statistics, app map screenshot, analytical plots and video placeholder, plus the limits of these measurements.

## Launch

```
cd ~/k1-legodom
./k1odom 192.168.2.152     # robot password once -> the site opens on Live
./k1odom                   # next time (last address)
./k1odom demo              # no robot: try the site on a replayed September run
./k1odom site              # no robot: browse runs
```
K1 addresses: Kim-Elecom-5G wifi `192.168.2.152`, go2_wifi_5G `192.168.50.250`, cable `192.168.10.102`.
A plain IP means `booster@IP`. Site: http://localhost:8790. Ctrl+C in the terminal closes it.

## In the lobby (all on the site)

1. Tape START and a far mark measured with the tape (e.g. 5.00 m). Robot on START in walking mode.
2. Live → **Start recording**. Start the phone video and press **Mark** on camera (sync point).
3. Walk with the remote to the far mark and back; both estimates draw on the map live. **Mark** at the far mark.
4. **Stop & save**: the run is copied to the Mac; type the tape numbers (far, end x y) and open the run.
5. On the run page: replay, tape errors, upload the phone video, sync it ("This frame = mark").

Runs worth doing (3x each): there and back 5 m, a 2x2 m square, a 360° turn on the spot.

## Files

- `k1odom` launcher. `server.py` local server (site + ssh to the robot + live stream).
- `odom_walk.py` robot recorder (also works by hand: `python3 odom_walk.py NAME`). `legodom.py` leg odometry (numpy).
- `make_site.py` + `site_template.html` -> `site/`. `odom_plot.py` one run -> png + table.
- `runs/` lobby runs, `runs_old/` 69 September stock-walk runs (heel study, 0/20/30/40 mm).
- `tools/fake_robot/` fake rclpy that replays a run, for `./k1odom demo`.
