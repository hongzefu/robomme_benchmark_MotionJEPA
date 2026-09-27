# StopCube audit (xhard4 + native easy/medium/hard) — AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1

Pure static audit of delivered data; source read only via `git show 82e3d92:<path>`. No simulation, no robomme import.

## Per-tier table (source)

| tier | language template (utils/task_goal.py, `env == "StopCube"`) | move_interval choices | stop_time (N) | motion segments | stop window / success | task chain |
|---|---|---|---|---|---|---|
| easy/medium/hard (identical, `_CONFIG_CURRENT`) | "press the button to stop the cube just as it reaches the target for the {num2words_2[N]} time" / "... exactly at the target on its {N-th} visit" | [60,80,120] | randint(2,6) → 2..5 | hard-coded `range(5)` in `StopCube.step` | `correct_timestep`: stop_timestep in [mi*(N-1), mi*N]; `is_obj_stopped_onto`: horizontal dist ≤ 3*cube_half_size (0.06 m) and stop; press-before-on-target → fail; timeout `elapsed > mi*N` → fail | hover button → k× "remain static" (checkpoints 100,200,…, steps_press-30) → "press the button to stop the cube on the target" |
| xhard4 (`_CONFIG_XHARD`, decision key `xhard4`) | same template, N up to fifteenth (num2words_2 covers ≤20) | [60] | randint(6,16) → 6..15 | `max(5, N)` (`_initialize_episode`) | identical predicates | identical chain |
| xhard1..3 | not supported: `require_xhard4_only` raises (plan 2.13/M2; plan table: "InsertPeg / StopCube 不加档 … 原 xhard 改名 xhard4, 数值不动") | | | | | |

Choice labels (all tiers, HDF5 setup/available_multi_choices + vqa_options.py::_options_stopcube): a "move to the top of the button to prepare", b "remain static", c "press button to stop the cube".

## Data read
- New tier (all delivered): xhard4 ep0 (seed 6200000, N=6), ep3 (6200300, N=14), ep6 (6200600, N=15); per-episode spec values from `artifacts/newtask-v6/v6-01/xhard4/rollout/run1/_rounds/round_00/specs.json` (move_interval 60, motion_segments 6/14/15, stop_window [300,360]/[780,840]/[840,900]).
- Native: all 9 native StopCube HDF5 in `artifacts/newtask-v6/v1/base/B/StopCube_episode_{0,1,2,3,4,6,7,10,11}` (3 easy, 3 medium, 3 hard).
- For each: every timestep's simple/grounded subgoal (planner + online), choice_action, boundaries, task_goal, difficulty; all front_rgb frames; mp4 frame count (equal to HDF5 steps for all 12) and two mp4 frames of xhard4 ep6.

## Visual method
Median-background subtraction on HDF5 `front_rgb` → cube blob centroid per frame (`track.py`); signed offset along the route's principal axis relative to the target pixel taken from the press subgoal's grounded point `<row, col>`; target crossings, cube-stop frame (speed < 0.3 px/frame thereafter), pass index at stop = #crossings earlier than stop−mi/4 + 1 (`annotate.py`). move_interval inferred from crossing period and cross-checked against online press-subgoal onset = mi*(N−0.5)−30 (exact match in all 12).

## Results (records.json)
| ep | N (language) | visual pass at stop | mi | stop frame | code window | final cube–target px |
|---|---|---|---|---|---|---|
| xhard4 ep0 | 6 | 6 | 60 | 328 | [300,360] | 8.3 |
| xhard4 ep3 | 14 | 14 | 60 | 809 | [780,840] | 5.8 |
| xhard4 ep6 | 15 | 15 | 60 | 868 | [840,900] | 7.1 |
| easy ep0/1/4 | 4/3/2 | 4/3/2 | 120/60/120 | 422/150/178 | in window | 4.6/1.6/4.5 |
| medium ep2/6/10 | 3/4/3 | 3/4/3 | 80/60/80 | 203/212/200 | in window | 8.3/7.7/2.0 |
| hard ep3/7/11 | 4/5/3 | 4/5/3 | 120/80/120 | 418/363/297 | in window | 3.8/9.3/6.2 |

All 12 episodes: ordinal in language == visually counted pass at which the cube stops; stop within code window; cube visibly on the purple/white target; grounded target/button points land on the target/button; subgoal texts and choice labels identical across tiers. Evidence PNGs: `frames/<tier>_ep<n>_passes_stop<frame>.png` (key frames at crossings + stop + last frame, and a timeline plot), `peek_*.png`, `mp4_xhard4_ep6_f*.png`.

## Findings
1. (low, new_tier_only, config description) `scripts/configs/newtask-v6/sampling_config.json` `tasks.StopCube.native.parameters.motion_segments = 5` (mirrors `StopCube.py::NATIVE_SAMPLING`) but xhard4 actually runs `max(5, stop_time)` segments (spec: 6/14/15); the key is descriptive only (not consumed), and the xhard4 override is not described in the config.
2. (low, native_same, predicate vs visual) success radius 3×cube_half_size = 0.06 m (`subgoal_evaluate_func.py::is_obj_stopped_onto`) vs visible target disc radius 1.8×cube_half_size = 0.036 m (`NATIVE_SAMPLING.positions.target.radius_factor`); ~260 px/m → 15.6 px vs 9.4 px. No delivered episode stops outside the disc (max offset 9.3 px native hard ep7, 8.3 px xhard4 ep0). Already noted by previous audit 01a0e086 (peg_stop).

## Not checked
Failure-path behaviour (no failed episodes read); button depth (not stored in HDF5; press inferred from cube stop + completion); wrist camera; xhard1–3 (not supported by design).
