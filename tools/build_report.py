#!/usr/bin/env python3
"""Rebuild REPORT.md, report/metrics.json and analytical figures from local replay data.
App screenshots are captured separately from the running app, at &t=end.
"""
import json
import math
from pathlib import Path
import numpy as np
import report_figs as figs

ROOT = Path(__file__).resolve().parent.parent
KEYS = ['booster', 'lowest', 'sole']
NAMES = ['Booster', 'Legs (lowest)', 'Legs (sole)']
DESCRIPTIONS = {
'lobby_1025_151300': ('The operator walked the K1 out and back along measured 9 m, 6 m and 12 m lines, turning between routes, then returned approximately to START. This is the starred main run; the intended route totals 54 m.', 'Lowest is closest on these measured legs. Booster and sole generally underestimate displacement. Its largest single-leg distance error is +7.9% on the 6 m outward traversal.'),
'5m_front_back': ('The operator repeatedly walked 5 m forward and 5 m backward without turning around, finishing approximately at START facing the original direction. Twelve traversals (six forward and six backward) are inferred from trajectory reversals; the repetition count was not independently counted by the operator.', 'Booster overestimates the backward traversals by about 33%, producing a large residual displacement. Sole is closest on the 5 m traversals; lowest overestimates them by about 8%.'),
'turn_5_left_5_right': ('The operator made five full turns one way and five the other, with little intended translation. The robot actually moved roughly 1.5 ft (0.46 m) diagonally forward-right. The operator added a small final steering correction.', 'The final +17° includes the operator’s deliberate correction and should not be called heading drift. At m1, after five turns, IMU heading is about -0.4° relative to its initial direction. That is an estimated residual, conditional on the actual alignment at m1.'),
'mix_walk_and_turn': ('The operator moved and turned simultaneously in a chaotic pattern many times, then returned approximately to the starting position. There was no measured ground-truth trajectory.', 'Both leg variants finish close to the reported endpoint; Booster retains a larger offset. The displayed +14° final heading is not an independently measured orientation error.'),
'orientation_stress': ('The operator pushed and restrained the robot, prevented its intended turns and walking, and let it step back and forth around one place. The operator finished approximately where you started.', 'Booster accumulates substantially more apparent translation than the leg estimates. This is consistent with an odometer that poorly accounts for blocked motion; its internal implementation was not inspected.'),
'continuous_collision': ('The operator repeatedly commanded walking into an obstacle, so the robot stepped under continuous obstruction, then finished approximately at the initial position.', 'Booster ends nearly 7.74 m from the reported endpoint; lowest ends about 0.25 m away. Lowest still wanders up to about 1.12 m from START during the test. Endpoint closure alone does not establish accuracy throughout the collision.'),
'side_pull': ('The operator pulled the robot sideways while it was stepping, aiming to finish at the starting point; the final position was within roughly 1 ft of START.', 'Sole has the smaller endpoint residual in this test. Sliding contact is a limitation: the leg estimator assumes its support point stays fixed, so foot slip can produce unobserved motion.'),
'standing': ('The operator left the robot standing still and untouched for about 67 seconds.', 'The replay data round the endpoint displacement to 0.000 m for all estimates; leg maximum displacement is below 1 mm in this recording. The IMU heading changes by about 0.05°. This short observation does not establish an hourly drift rate.'),
}

def table(headers, rows):
 return '\n'.join(['| ' + ' | '.join(headers) + ' |', '| ' + ' | '.join(['---']*len(headers)) + ' |'] + ['| ' + ' | '.join(map(str,row)) + ' |' for row in rows])

def build():
 figs.main()
 labels, errs = figs.tape_segments()
 ds={n:figs.load(n) for n,_ in figs.RUNS}
 means={k:float(np.mean(np.abs(errs[k]))) for k in KEYS}
 # Same eight comparison rows as the plot: six individual legs plus two direction means.
 metrics={'distance_error_definition':'100*(estimated straight-line leg displacement - tape length)/tape length', 'distance_comparison_rows':labels,'signed_distance_error_percent':errs,'mean_absolute_percent_across_8_rows':means,'runs':{n:{'seconds':d['seconds'],'stats':d['stats'],'reported_truth':d['truth']} for n,d in ds.items()}}
 (ROOT/'report/metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
 dynamic = [d for n,d in ds.items() if n != 'standing']
 endpoint_summary = {k: {'median_m': float(np.median([d['stats'][k]['end_err'] for d in dynamic])), 'maximum_m': max(d['stats'][k]['end_err'] for d in dynamic)} for k in KEYS}
 metrics['endpoint_summary_7_moving_tests'] = endpoint_summary
 metrics['operator_observation'] = {'endpoint_uncertainty_m_approx': 0.3, 'heading_note': 'Small differences around 5 degrees may be visually unnoticed; this is not a calibrated angular uncertainty or a correction.'}
 (ROOT/'report/metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
 parts=['''# K1 legged odometry: lobby evaluation report

Tests: October 25–26, 2026 · [code and recordings](https://github.com/Kyk0/k1-legodom)

## Summary

Eight identified lobby tests compared Booster's built-in odometer with joint-angle and IMU leg odometry while the K1 was operated by remote in stock walking mode. Leg odometry showed lower endpoint discrepancies during blocked motion, backward walking and combined walking/turning. Mean absolute distance error across the eight measured-distance comparison rows was **4.7% for lowest, 8.1% for sole and 14.9% for Booster**. Lowest performed better on the starred 9/6/12 m route; sole performed better on the repeated 5 m forward/backward route.

Final positions were judged by eye to about **0.3 m**. Small heading differences, around **5°**, can also look almost unchanged to the operator. Some observed residuals may therefore reflect imperfect physical return or alignment rather than estimator drift; no fixed amount has been subtracted from the measurements.

## Overall results
''']
 parts.append(table(['Overall statistic','Booster','Legs (lowest)','Legs (sole)'],[
 ['Mean absolute distance error, 8 comparison rows']+[f'{means[k]:.1f}%' for k in KEYS],
 ['Median endpoint discrepancy, 7 moving tests']+[f"{endpoint_summary[k]['median_m']:.2f} m" for k in KEYS],
 ['Largest endpoint discrepancy, 7 moving tests']+[f"{endpoint_summary[k]['maximum_m']:.2f} m" for k in KEYS]]))
 parts.append('The distance average equally weights six individual 9/6/12 m traversals and two direction averages from the repeated 5 m test. Endpoint statistics exclude standing and compare against approximate reported final positions. These summarize this test set; they are not a general accuracy guarantee.')
 parts.append('## Test overview\n\nEndpoint discrepancies below are in metres. All tests aimed to return to START except the turn test, whose reference includes the reported 0.46 m forward-right displacement.')
 parts.append(table(['Test','Duration','Booster','Legs (lowest)','Legs (sole)'],[[('★ ' if n == 'lobby_1025_151300' else '')+title,f'{ds[n]["seconds"]:.1f} s']+[f'{ds[n]["stats"][k]["end_err"]:.2f}' for k in KEYS] for n,title in figs.RUNS]))
 parts.append('''## Distance accuracy

Distance error is the estimated straight-line traversal displacement minus the tape-measured length, divided by that length. Endpoint discrepancy instead measures the separation between the estimated and reported final positions. Small closure residuals do not guarantee an accurate trajectory, because opposite errors can cancel.
''')
 parts.append(table(['Distance comparison','Booster','Legs (lowest)','Legs (sole)'],[
 ['9/6/12 m test, mean absolute percentage']+[f'{np.mean(np.abs(errs[k][:6])):.1f}%' for k in KEYS],
 ['5 m forward, signed distance error']+[f'{errs[k][6]:+.1f}%' for k in KEYS],
 ['5 m backward, signed distance error']+[f'{errs[k][7]:+.1f}%' for k in KEYS]]))
 parts.append('''The contact model affects distance scale differently across the two measured walking tests. Both variants are retained in the evaluation.

![Distance error against measured lengths](report/img/tape_segments.png)

## Measurement and estimation

Our estimator uses joint angles for forward kinematics and IMU orientation to infer body motion relative to a planted foot. On a support change, the anchor transfers to the other foot. It does not estimate distance by integrating IMU acceleration or multiplying a step count by a fixed step length.

- **Sole:** fixes a point under the ankle as the contact point.
- **Lowest:** chooses the lowest of heel, sole centre and toe to approximate foot rollover; this is the current live default. Both variants are retained in the comparisons.
- **Booster:** records `/odometer_state` directly. Its reported heading is separate from the IMU heading used by our leg estimator, although the recorded headings are often close.

The robot recorder only listens. Joints and IMU are recorded at approximately 500 Hz; topic rates can differ. Replay trajectories are resampled to 20 Hz. Estimated path length is evaluated on a 0.5 s grid to reduce trunk sway. A trajectory plot is an estimator comparison, not a ground-truth tracking system.

Tape lengths were reported as 9 m, 6 m, 12 m and 5 m. Long-route boundaries use Mark presses; the repeated 5 m boundaries are inferred from trajectory reversals. Timing and imperfect stops affect these distance comparisons. For the turning test, the approximate final reference is (0.32, -0.32) m: forward-right relative to the initial heading.

## Measured-distance results
''')
 truth_lengths=[9,9,6,6,12,12,5,5]
 rows=[]
 for i,label in enumerate(labels):
  D=truth_lengths[i]
  rows.append([label,f'{D} m']+[f'{D*(1+errs[k][i]/100):.2f} m ({errs[k][i]:+.1f}%)' for k in KEYS])
 parts.append(table(['Traversal','Tape','Booster','Legs (lowest)','Legs (sole)'],rows))
 parts.append('''## Endpoint results

All values below are discrepancies from the approximate reported endpoint, in metres. For turning, the reference includes the reported 0.46 m diagonal drift; other references are START. Differences near or below 0.3 m are unresolved by the endpoint measurements. Returning close to, rather than exactly onto, START can account for part of the observed discrepancy. For example, a 0.25 m residual could be entirely explained by a physical return within 0.3 m of START. Without a measured final position, the size and direction of this contribution are unknown; the report therefore retains the observed residuals.

![Approximate endpoint discrepancies](report/img/end_errors.png)
''')
 # Endpoint numbers are listed once in the overview above.
 parts.append('''## Test descriptions and evidence

Each screenshot was captured from the local app with the playback at the end. The analytical figure underneath adds a clearer map, distance-from-start trace and leg IMU heading. The video's placeholder belongs to that specific test.
''')
 for num,(n,title) in enumerate(figs.RUNS,1):
  d=ds[n]; desc,result=DESCRIPTIONS[n]
  parts.append(f'### {num}. '+('★ ' if num==1 else '')+title+f'\n\nRecording: [`{n}`](runs/{n}) · duration: **{d["seconds"]:.1f} s**.\n\n**Procedure:** {desc}\n\n**Result:** {result}\n')
  rows=[]
  for k,label in zip(KEYS,NAMES):
   s=d['stats'][k];rows.append([label,f'{s["end_err"]:.2f} m',f'{s["far"]:.2f} m',f'{s["path"]:.2f} m',f'{s["yaw"]:+.1f}°'])
  parts.append(table(['Estimate','Endpoint discrepancy','Max distance from START','Estimated path','Final relative heading'],rows))
  parts.append(f'![App replay map and statistics: {title}](report/img/app_{n}.png)\n\n![Map, displacement and heading: {title}](report/img/{n}.png)\n\n**Video:** _to attach — {n}_\n')
 parts.append('''## Turns and orientation

Turning and walking simultaneously are included in the chaotic test, and repeated turns on the spot are included in the five-plus-five test. The leg estimates have small endpoint residuals in both, but there is no independent full-trajectory reference.

At m1 after the first five turns, the leg IMU heading is approximately -0.4° from its starting value. In the push/block test it ends around -1°. The operator reported that small differences around 5° are difficult to notice, so “facing the same way” does not establish exact alignment. These residuals cannot be assigned entirely to estimator error without an independent heading reference. The final +17° in the turn test includes the operator’s deliberate extra correction. Other final headings should be treated as recorded orientations, not measured errors. During standing, the observed change is about 0.05° over 67 s. A residual of roughly 5° can be consistent with visually similar start/end headings. This observation does not justify automatically deducting 5° from every reading.

## Collisions, pushes and slipping

During repeated obstruction, Booster's final discrepancy is 7.74 m, versus 0.25 m for lowest and 0.32 m for sole. Under pushing/blocking the corresponding values are 2.59 m, 0.18 m and 0.46 m. These trials show substantially less accumulated endpoint discrepancy for the leg estimates under the tested conditions. They do not prove Booster's internal algorithm or establish a general collision error rate.

Leg odometry depends on a stationary support contact. Sliding and rotating feet violate that assumption. A low final residual can also hide intermediate error: during continuous collision, lowest reaches about 1.12 m from START. Without a measured trajectory, we cannot separate true transient motion from estimator error.

## Limits and remaining tests

- One robot and one lobby floor; these exploratory tests do not establish repeatability across floors, speeds or robots.
- Most endpoints are approximate (about ±0.3 m); phone videos have not yet been attached or checked against the traces. There is no independent continuous position or heading reference.
- The 5 m repetition count and turning points are inferred from a leg-estimator trajectory, so this segmentation is not independent ground truth.
- Keep both contact variants until repeatable tape-measured trials resolve when each is better.
- Next measurements: three precisely marked forward, backward and sideways trials per speed; an independently measured square route; measured start/end foot positions; synchronized video for every run.

## App, replay and videos

Launch without a robot:

```bash
cd ~/k1-legodom
./k1odom site
```

Open [the local app](http://localhost:8790/#run=Lobby__lobby_1025_151300&t=end). Select a run to replay its map and statistics. To collect a new run, launch `./k1odom <robot-ip>`, then use **Start / Mark / Stop & save** on Live.

For each phone video, open the matching run, upload it, pause at a recorded Mark and use **This frame = mark** to synchronize. Uploading a video to the local app saves it locally; it does not put it in GitHub. Add the corresponding GitHub video link in the placeholder under that test when ready.

Rebuild the figures, tables and machine-readable results:

```bash
python3 make_site.py
python3 tools/build_report.py
```

Sources: the saved CSV recordings under `runs/`, each run's `truth.json` operator notes, and the local replay JSON generated by `make_site.py`. [Machine-readable metrics](report/metrics.json) record the values and distance-summary definition used here. App screenshots are stored in `report/img/app_*.png`.
''')
 (ROOT/'REPORT.md').write_text('\n\n'.join(part.strip() for part in parts).rstrip()+'\n')
 print('Updated REPORT.md and report/metrics.json')
if __name__=='__main__': build()
