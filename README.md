# K1 leg odometry vs Booster odometer

Two estimates, recorded together while the robot walks in Booster's normal walking mode on the remote:
1. Booster odometer (`/odometer_state`)
2. Our leg odometry (`legodom.py`: joint angles + IMU, the stance foot stays fixed on the floor)

The robot side only listens. It never sends commands.

**Full write-up with figures: [REPORT.md](REPORT.md).**

## Main run: `runs/lobby_1025_151300` (2026-10-25)
The run that counts (named in `runs/MAIN`, ★ on the site). Tape-measured out-and-back legs from START:
9 m, turn, 6 m, then 12 m (54 m in total), back on START at the end. 110 s, 200 steps.

Each leg is measured between the Mark presses (m1..m6), straight line, against the tape:

| Estimate | 9 out | 9 back | 6 out | 6 back | 12 out | 12 back | Mean abs error | Path (54 m) | End error |
|---|---|---|---|---|---|---|---|---|---|
| Booster odometer | 7.39 | 7.63 | 5.75 | 5.35 | 10.42 | 9.63 | 13.5% | 48.5 m | 0.96 m |
| Legs (sole) | 7.57 | 7.71 | 6.00 | 5.60 | 10.65 | 10.52 | 10.1% | 49.6 m | 0.29 m |
| **Legs (lowest)** | 8.52 | 8.67 | 6.47 | 6.17 | 12.05 | 11.81 | **3.6%** | 55.3 m | 0.32 m |

Booster and legs (sole) both under-count distance by ~10-15%. Legs (lowest) (heel / sole / toe pivot) is within
~4% and the best of the three, so it is the default everywhere since 2026-10-26 (live numbers, site, tables). Going back to START, both leg variants end ~0.3 m off against ~1 m for Booster.

## Other lobby tests (2026-10-26)
Every run ended back about where it started (within ~1 ft / 0.3 m, eyeballed), except `turn_5_left_5_right`
(~1.5 ft forward-right). End error = distance between the estimated and the real end point, m:

| Run | What | s | Booster | Legs (lowest) | Legs (sole) |
|---|---|---|---|---|---|
| `lobby_1025_151300` | 9 / 6 / 12 m out-and-back (tape) | 110 | 0.96 | 0.32 | 0.29 |
| `lobby_1025_150458` | out-and-back legs | 79 | 0.88 | 0.20 | 0.42 |
| `turn_5_left_5_right` | 5 turns on the spot, 5 back | 57 | 0.28 | 0.12 | 0.20 |
| `orientation_stress` | pushed, blocked, turned, stepped in one spot | 81 | 2.59 | 0.18 | 0.46 |
| `standing` | 67 s standing still | 67 | 0.00 | 0.00 | 0.00 |
| `continuous_collision` | walking into an obstacle the whole time | 83 | 7.74 | 0.25 | 0.32 |
| `side_pull` | pulled sideways | 48 | 0.91 | 0.40 | 0.20 |
| `5m_front_back` | 6x 5 m forward + 5 m backward, no turning | 108 | 11.4 | 0.57 | 0.46 |
| `mix_walk_and_turn` | chaotic walking and turning at once, back on START | 70 | 1.22 | 0.12 | 0.16 |

With the truth good to ~0.3 m, the leg estimates are within that on every run; Booster is off by up to 7.7 m.
Booster counts steps the robot tries to take, so it keeps "walking" when the robot is blocked or held.
`5m_front_back`, per 5 m leg (mean of 6): Booster forward 4.74 m (-5%) but backward 6.65 m (+33%), so it ends 11.4 m
behind START. Legs are the same both ways: sole 4.85 / 4.92 m (-3% / -2%), lowest 5.38 / 5.39 m (+8%). Here sole is
closer, on the 9/6/12 m run lowest was (-4% vs -10%): the true value sits between the two leg variants.
Heading (IMU, shared by both): -0.4° after 5 turns, -1° after 2300° of turning, 0.05°/min standing.

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

## What the September runs already show
- Without heels: legs give 5-8% more distance than Booster (median ×1.06). No tape back then.
- With heels Booster's odometer shrinks a lot (40 mm: ~3.0 m against ~4.7 m without heels), legs stay ~5.1 m.
- Booster's odometer stays at ~0 under custom policies: it only works in Booster's own walking mode.
