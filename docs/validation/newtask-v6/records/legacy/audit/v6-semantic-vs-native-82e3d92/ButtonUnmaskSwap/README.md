# ButtonUnmaskSwap — semantic vs visual, native vs new tier (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

[Internal output, English. The main agent must still report to the user in Simplified Chinese.]

## Method
- Source was read only via `git show 82e3d92:<path>`: `src/robomme/robomme_env/ButtonUnmaskSwap.py`
  (`configs`, `_load_scene`, `_plan_inner_swaps_v6`, `_initialize_episode`, `_solve_press_then_wait_swaps`, `step`),
  `utils/task_goal.py::get_language_goal` (ButtonUnmaskSwap branch), `utils/vqa_options.py::_options_button_unmask_swap`,
  `scripts/configs/newtask-v6/sampling_config.json` (tasks.ButtonUnmaskSwap), and plan `0925-newtask-release-v6-plan.md` §二, §三, §四.2 and §四.4.
- Data (read-only, h5py/numpy/cv2 only, no simulation):
  - all 12 delivered new-tier HDF5+mp4 files (xhard1..4 × ep 0/3/6), plus their delivered specs from `artifacts/newtask-v6/v6-01/<tier>/specs.jsonl` (`selected=true`)
  - all 9 native HDF5+mp4 files in `artifacts/newtask-v6/v1/base/B/ButtonUnmaskSwap_episode_{0,1,4 easy | 2,6,10 medium | 3,7,11 hard}`.
- Scripts (all in this directory): `extract.py` (goal/subgoal/choice timeline -> `records_raw.json`), `specs_extract.py` (n_swaps, picks, swap pairs, net slot permutation -> `specs_newtier.json`),
  `color_track.py` (R/G/B cube centroids at t=5 vs where each named colour is revealed during its pick segment -> `color_track.json`),
  `spec_vs_pixels.py` (spec-predicted final slot vs revealed pixel -> `spec_vs_pixels.json`), `distractor_count.py`, `button_press.py`, `idle_check.py` (static eef span inside "press the second button"), `mp4_check.py`, `montage.py`, `build_records.py` -> `records.json`.

## Per-tier table (source @82e3d92)
| tier | bins | swaps | picks | swap steps | outer distractor bins / cubes | language template |
|---|---|---|---|---|---|---|
| easy | 3 | [1,2] | [1,2] | 50 | 0 | "first press both buttons on the table, then pick up the container hiding the {c0} cube[, finally pick up another container hiding the {c1} cube]" |
| medium | 4 | [1,2] | 1 | 50 | 0 | same, 1 pick |
| hard | 4 | [2,3] | 2 | 50 | 0 | same, 2 picks |
| xhard1 | 4 | 4 | 2 | 50 | 4 / 2 | same as hard (2 picks) |
| xhard2 | 4 | 5 | 3 | 33 | 6 / 3 | "... then pick up the container hiding {c0}, next pick up another container hiding {c1}, finally pick up another container hiding {c2}" |
| xhard3 | 4 | [6,7] | 3 | 33 | 8 / 4 | 3-pick template |
| xhard4 | 4 | [8,9] | 3 | 33 | 10 / 5 | 3-pick template |

Task chain: press first button (right) -> press second button (left) -> pick selected_bins[0] -> [put down -> pick selected_bins[1]] -> [put down -> pick selected_bins[2]].
Predicates identical across tiers (`is_any_button_pressed_removelist`, `is_bin_pickup`, `is_bin_putdown`, failure = lifting any other inner bin); new tiers additionally fail on lifting any distractor bin (`add_distractor_misgrasp_failure`) and the second-button solve waits until the last swap ends (`_solve_press_then_wait_swaps`). Choice labels a/b/c/d identical in all tiers.

## What was verified (all PASS unless listed under findings)
- Language goal == HDF5 `setup/task_goal` == mp4 filename (prefix; xhard2-4 names truncated with `__HASH__`) for 21/21; pick count in text == number of pick subgoals == spec `objects.n_picks` (2/3/3/3 for xhard1-4).
- Spec values inside config: n_swaps xhard1 4,4,4; xhard2 5,5,5; xhard3 6,6,7; xhard4 8,8,8; swap window 64+50k (xhard1) / 64+33k (xhard2-4); first pick subgoal starts 0-5 steps after spec swap end in all 12.
- Named colour revealed under every picked container in 33/33 new-tier picks and 13/13 native picks; no other primary colour revealed (`color_track.json`).
- Spec swap sequence -> predicted final slot matches the revealed pixel location 24/24 checkable picks; 9 picks ended in the originally-empty bin_3 slot (consistent: >=30 px from every initial cube) (`spec_vs_pixels.json`).
- Distractor cube blobs at t=5/t=30: yellow/cyan/magenta counts equal spec `distractors.cube_colors` in 12/12 (2/3/4/5 cubes); native 0.
- Both buttons physically pressed (eef z min 0.024 m) at y≈+0.1 (first) and y≈-0.1 (second) in 21/21.
- mp4 frame count == HDF5 step count 21/21.

## Findings
1. **N1 (new_tier_only, task_chain/labels)**: in all 12 new-tier episodes the "press the second button" segment ends with a long static hold (eef static at z≈0.148 above the left button) while swaps finish: xhard1 52-54, xhard2 18-28, xhard3 48-94, xhard4 118-124 steps; native 0-1 step. Segment length xhard 111-220 vs native 91-99. Caused by `ButtonUnmaskSwap::_initialize_episode` replacing `tasks[1]["solve"]` with `_solve_press_then_wait_swaps` for new-value tiers. Plan §四.4 does not describe the wait nor its effect on subgoal labels. Evidence `second_button_idle.json`, `frames/xhard4_ep0_idle_press2_t175-333.png` (native `frames/hard_ep7_press2_t170-209.png`).
2. **N2 (native_same, swap semantics)**: swap sequences can have net-zero effect on the target containers, so ignoring all swaps and picking the initial cube positions still succeeds. New tiers: xhard1 ep0 (4 swaps (3,2),(0,1),(2,3),(1,0) = identity) and xhard4 ep3 (8 swaps alternating only {0,3} and {1,2} = identity) — 2/12 episodes, all picked targets revealed within 4.8-6.6 px of their t=5 position. Native: hard ep3/7/11 and medium ep2/6 all picked targets revealed ≤6.3 px from initial position (5/9 native episodes, 3/3 hard). Plan §二 口径 8 / §四.2 defines S5 (balanced participation, forbid *immediate* undo) but says nothing about net permutation; the gradient “swap count” is therefore not monotone in tracking difficulty. Evidence `specs_newtier.json` (`identity_perm`), `color_track.json`, `frames/xhard4_ep3_identity_t5_414_549_703.png`, `frames/xhard1_ep0_t0-264.png`, `frames/hard_ep3_identity_t5_401_543.png`, `frames/hard_ep7_t0-360.png`.

Excluded items seen: F3 (button first/second label vs VQA binding; demo presses right then left, confirmed eef y), F4 (stale grounded coordinates, e.g. final `All tasks completed` rows), D3-analog (reveal is time-window not button-triggered), D7 (VQA `available` only inner bins).

## Not checked
- Native per-episode swap count / pairs (no native spec on disk); native net permutation inferred only for picked targets from pixels.
- Frame-by-frame bin tracking through each swap (only start/end state checked); collision/penetration during swaps; outer-ring swap count per window (spec only).
- Failure/recovery (FailRecover) branches of native easy episodes; undelivered candidates (indices other than 0/3/6).
