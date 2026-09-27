# InsertPeg audit — AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1

Scope: InsertPeg has no gradient; plan (0925-newtask-release-v6-plan.md, §二 口径5, §三 table row "InsertPeg / StopCube", §四.10) says
native easy/medium/hard share `config_native` and the old xhard is renamed **xhard4 with values unchanged**. Source rejects xhard1-3
(`InsertPeg.__init__` -> `require_xhard4_only`). Pure static/read-only audit; no simulation run.

## Per-tier table (source @ AUDIT_BASE)

| item | easy / medium / hard | xhard4 |
|---|---|---|
| language goal (`task_goal.py`, env=="InsertPeg") | 2 fixed templates, no parameters | identical |
| pegs | `peg_count` 3, all share one head color + complementary tail (`_load_scene`) | 4, same color rule |
| peg yaw | ±45° | ±180° (planner grasp flip `_xhard_reduce_peg_grasp_q`, insert offset compensation in `insert_peg`) |
| peg placement | native loop (x∈[-0.2,0.2], root-root >0.075, root-box >0.06) | `_xhard_sample_pegs`: x∈[-0.2,0.1], + footprint gaps peg-peg >0.03, peg-box >0.01 |
| target peg | peg_0 (randint overridden to 0) | peg_0 |
| grasp end / side | obj_sample→obj_flag (head/tail), dir_sample→direction (left/right) | same |
| task chain | demo: Pick(end) → Insert(side, "...of the box") → reset → static hold; exec: Pick(end) → Insert(side) | identical |
| predicates | `is_A_pickup_notB` (z>0.1, closer to tcp); `is_A_insert_notB` (end within 0.05 m of box, other end farther, tcp y side vs direction); exec failure: wrong end, wrong side, any other peg picked (`is_any_obj_pickup`) | identical |
| choice labels (`vqa_options._options_insertpeg`) | a pick one end (available = all heads+tails), b insert right, c insert left | identical |

## Data coverage
- New tier: all 3 delivered xhard4 (ep6 seed 7300600, ep2 seed 7300200, ep4 seed 7300400), every timestep's info/action/obs scalars read.
- Native: all 9 base/B InsertPeg episodes (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11).
- xhard4 world geometry from the episode `rng_trace.json` (initialization 1 = recorded layout; verified because the grasp waypoint
  matches the expected end of peg_0 to 3e-5..6e-5 m and the text side/end match init1's obj/dir samples, while init0 differs for ep2/ep4).
- Front camera projection (K, extrinsic from HDF5) verified: projected grasp point equals grounded `<row,col>` within 1 px.

## Checks and results (records.json)
1. Language claims "same peg / same end / same side": for all 12 episodes the demo and exec grasp waypoints are identical (0.0 m),
   final eef poses agree within 0.0066 m; xhard4 grasped link = peg_0's expected end (head for ep2, tail for ep4/ep6), wrist frames show
   the grasped end's color = spec head_rgb / 1-head_rgb (`frames/xhard4_ep*_montage.png`).
2. Side: tcp_y − box_y at insertion end: ep6 −0.089 (right, dir=+1), ep2 +0.071 (left), ep4 +0.067 (left) → consistent with text and predicate.
3. Pegs reset between demo and exec: front frame at exec start vs step 0 mean abs diff ≤0.27 for all 12 episodes; non-target pegs
   (xhard4) have 0.0 patch diff at every key step except arm occlusion (ep6 peg1 at t=218/437, `frames/xhard4_ep6_peg1_box_crop_series.png`).
4. Counts / config: xhard4 shows 4 identical-colored pegs, yaws up to ±177°, root x ≤0.075, recorded min gaps 0.060/0.097/0.113 (pair) and
   0.018/0.043/0.015 (box) — satisfy config; native shows 3 pegs.
5. Box red highlight (visual insertion cue) appears in the last frames of demo and exec for xhard4 and most native episodes
   (`red_highlight_runs.json`; missing in native hard ep11/easy ep4 due to arm occlusion; noisy early hits are magenta peg colors).
6. near/far (D6, excluded): in all 3 delivered xhard4 the x-axis rule and Euclidean distance agree ("far") — D6 not triggered.
7. Planner flip (xhard4-only mechanism, documented as V4 B11): ep6 engaged (eef yaw 0.55 rad vs peg yaw −148.6°), insertion still on the stated side.

## Findings
- Only one low-severity native_same item: demo insert subgoal text "Insert the peg from the X side of the box" vs exec "Insert the peg
  from the X side" (InsertPeg._initialize_episode task list) — present in every tier; semantic meaning identical.
- No semantic-vs-visual mismatch and no undocumented xhard4-vs-native divergence found.

Not checked: object world poses per step (not in HDF5); mp4 frames were not decoded separately (HDF5 front/wrist images used, same stream);
init0 purpose (double reset) not re-derived; no physical check of hole depth/axis (known gap from previous audit).
Helper scripts: extract.py, analyze.py, redhl.py, distractor_disturb.py, crop_ep6.py, eef.py, cam.py, h5_keys.py.
