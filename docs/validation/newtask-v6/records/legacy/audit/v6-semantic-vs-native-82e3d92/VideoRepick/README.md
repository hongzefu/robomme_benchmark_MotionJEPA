# VideoRepick — semantic vs visual / native vs new-tier audit (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Pure read-only audit. Source read only via `git show 82e3d92:<path>` (copies in `src/`). Data read with h5py/cv2 only; no env import, no simulation.

## Coverage
- Source: `VideoRepick.py` (configs, `_load_scene`, `_load_cubes_newvalue`, `_plan_swaps_newvalue_v6`, `_initialize_episode` task list, `step` swap loop), `utils/task_goal.py` (VideoRepick branch), `utils/subgoal_language.py`, `utils/subgoal_evaluate_func.py` (`sequential_task_check`, `timewindow`, `is_obj_pickup`, `is_obj_dropped`, `static_check`, `is_button_pressed`), `utils/vqa_options.py::_options_videorepick`, `utils/swap_uniform.py`, `scripts/configs/newtask-v6/sampling_config.json` (tasks.VideoRepick), plan `0925-newtask-release-v6-plan.md` sections 一/二/三/四.2/四.5.
- HDF5: all 12 delivered new-tier (xhard1-4 ep0/3/6) + all 9 native (base/B VideoRepick ep0,1,2,3,4,6,7,10,11 = easy×3, medium×3, hard×3). Specs from `artifacts/newtask-v6/v6-01/<tier>/specs.jsonl`.
- Video: all 21 mp4 (+ native ep4 1-frame `success_NO_OBJECT` clip). Per pick segment (demo + every exec pick) frames at segment start and gripper-close+15 were analysed on seg/target panels (`identity_check.json`), 21 contact sheets (`frames/contact_*.jpg`) eyeballed for the 12 new tier (xhard3 ep6, xhard4 ep3 read in full here).

## Per-tier table (source + data)
| tier | cubes | colors | swaps (cfg / delivered) | repeats (cfg / delivered) | swap partner rule | language |
|---|---|---|---|---|---|---|
| easy | 3 | one of red/blue/green, all same | [1,2] | randint[1,4) (1..3) | target is 1st initiator; dynamic nearest neighbour | 2-3 templates via num_repeats |
| medium | 3 | same | [2,3] | 1..3 | same | same |
| hard | 15 (5 rounds × r/g/b) | 3 colors | 0 | 1..3 | no swap | same ("another task", plan 口径11) |
| xhard1 | 4 | same, HSV S≥0.5 V≥0.4 | [3,4] / 4,3,4 | 2 / 2,2,2 | S5 balanced pairs, planned at reset | "two times"/"twice" |
| xhard2 | 5 | same | [5,6] / 6,6,6 | 3 / 3,3,3 | S5 | "three times" |
| xhard3 | 6 | same | [7,8] / 7,8,7 | 4 / 4,4,4 | S5 | "four times" |
| xhard4 | 7 | same | [9,12] / 12,12,10 | [5,6] / 5,6,5 | S5 | "five/six times" |

Task chain (all tiers identical): demo `pick up the cube` → `drop the cube on the table` → `static` (+ n_swaps × `static` swap windows of 50 steps; none in hard) → N × (`pick up the correct cube for the <ordinal> time` + `put it down`) → `press the button to finish`. Choice labels a/b/c = pick up the cube / put it down / press the button to finish in all tiers.

## Verified OK (new tiers)
- Language number word == spec num_repeats == number of exec pick segments == number of exec gripper-close intervals before the button (12/12).
- Cube count on frame 0 (hue mask + eye check) == spec cube_count (12/12; 3 automatic outliers resolved by eye, see `cube_count_check.json`).
- Swap windows: 1 + n_swaps static boundaries, 54-step spacing, count equals spec n_swaps (12/12).
- Identity: in every demo pick and every exec pick (12 demo + 43 exec) the env target-mask actor is lifted (2.4–7.5 px displacement at close+15), the grounded point lies ≤2.6 px from the target mask centroid, and the target seg color is identical between demo and all exec picks. Other cubes stay (≤8.1 px, arm-occlusion noise, checked visually in xhard3 ep6).
- Target participates in ≥2 swaps in all 12 new-tier episodes (spec swap_pairs); S5 range ≤1 in all.

## Findings
1. **Button-press failure guard is an absolute 50–500 step window that does not scale with repeats (native_vs_new_mismatch, medium).** `VideoRepick::_initialize_episode` pick/put tasks use `timewindow(..., min_steps=50, max_steps=500, timewindow_timer=2/3)`; `subgoal_evaluate_func::timewindow` starts the timer at the first exec pick (timer 2) / first put-down (timer 3) and returns False (no failure) once elapsed>500. In all 3 delivered xhard4 episodes the oracle's own later repeats fall outside: ep0 pick steps 1384–1453, put 1477–1503; ep3 picks 1363–1434, 1490–1562, puts 1435–1489, 1563–1616; ep6 picks 1300–1373, put 1374–1423 (`timewindow_analysis.json`, `frames/finding_timewindow_xhard4_ep3.png`). The button is spring-return (`object_generation::build_button` drive target 0), so a premature press in the 5th/6th cycle is simply ignored instead of failing. Native oracle episodes (N≤3) are fully inside the window except native hard ep3 (FailRecoverXY, slow retries). Plan 三/四.5 do not mention scaling this guard.
2. **Target ends in its original slot after all swaps (native_same, low).** Spec permutation replay and grounded coordinates: xhard2 ep0 (<73,180>→<72,181>), xhard2 ep3 (<58,90>→<57,90>, swaps 0 and 3 are the same pair (bin_1,bin_4) = delayed undo), xhard4 ep3 (<86,88>→<84,87>), xhard4 ep6 (<88,183>→<87,181>): 4/12 new-tier episodes are solvable by remembering the demo location without tracking swaps. Native easy ep0, medium ep2, medium ep6 show the same (≤2.3 px). S5 only forbids *immediate* undo (plan 口径8). `target_return.json`, `frames/finding_target_return_xhard2_ep3.png`.
3. **Goal template 1 says "repeatedly pick up and put down ... N times, finally put it down" while the chain has exactly N put-downs (native_same, low).** Distinct from excluded F2 (count attached to "previously picked up"); same text in all tiers.

## Excluded items seen
F2 (goal template "previously picked up for N times / twice") present in all 12 new-tier and 6 native N>1 goals — not re-reported.

## Not checked
Physical 3D contact/penetration during swaps (no poses in HDF5; previous audit did seg-color tracking of swap phase); non-oracle policy behaviour (finding 1 is from source + oracle timing); native ep4's `success_NO_OBJECT` clip and its grounded subgoal without coordinates (native-only); website text.
