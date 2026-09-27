# VideoUnmask — semantic-vs-visual and native-vs-new-tier audit (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Pure read-only audit. Source read only via `git show 82e3d92:<path>`; data read with h5py/cv2 only (no robomme/sim imports).

## Sources read (at AUDIT_BASE)
- `src/robomme/robomme_env/VideoUnmask.py` (configs, `_load_scene`, `_append_xhard_pick_tasks`, `step`, `evaluate`)
- `src/robomme/robomme_env/utils/task_goal.py` (`get_language_goal` VideoUnmask branch, `_unmask_pick_count`, `_unmask_multi_pick_clause`)
- `src/robomme/robomme_env/utils/subgoal_evaluate_func.py` (`is_bin_pickup` z>0.15, `is_any_bin_pickup`, `is_bin_putdown` z<=0.07 & not grasping & tcp z>0.05, `static_check` 64 steps)
- `src/robomme/robomme_env/utils/unmask_distractors.py::add_distractor_misgrasp_failure`, `utils/unmask_distractor_sampler.py` (V5 presets, park points), `utils/xhard.py::DISTRACTOR_COLORS` (yellow/cyan/magenta)
- `src/robomme/robomme_env/utils/vqa_options.py::_options_video_unmask`, `utils/subgoal_language.py` (no VideoUnmask-specific entries)
- `src/robomme/env_record_wrapper/RecordWrapper.py` (NO_OBJECT video), `utils/segmentation_utils.py::process_segmentation`
- `scripts/configs/newtask-v6/sampling_config.json` tasks.VideoUnmask; `0925-newtask-release-v6-plan.md` §二, §三 (VU row), §四.3

## Per-tier definition table (AUDIT_BASE)
| tier | inner bins (`configs[t]['bin']`) | hidden target cubes | pick (`pick_count`) | ring distractor bins / with cube (`decision[t].distractor`) | min_gap_factor | language template |
|---|---|---|---|---|---|---|
| easy | 3 | 3 (bin_0..2, R/G/B perm) | 1 | 0 | 2 | `watch the video carefully, then pick up the container hiding the {c0} cube` |
| medium | 5 | 3 | 1 | 0 | 2 | same as easy |
| hard | 15 (requested; placement may break early — D1, excluded) | 3 | 2 | 0 | 2 | `... hiding the {c0} cube, finally pick up another container hiding the {c1} cube` |
| xhard1 | 8 | 3 | 2 | 8 / 4 (Y/C/M balanced cycle) | 0.75 | identical to hard |
| xhard2 | 8 | 3 | 3 | 10 / 5 | 0.75 | `... hiding the {c0} cube, next pick up another container hiding the {c1} cube, finally pick up another container hiding the {c2} cube` |
| xhard3 | 8 | 3 | 3 | 13 / [6,7] | 0.75 | same as xhard2 |
| xhard4 | 8 | 3 | 3 | 15 / [7,8] | 0.75 | same as xhard2 |

Task chain: `static`(64 steps, demo) → pick bin_0 → [put down → pick bin_k]*(pick-1). Pick fails if any other inner bin z>0.15; xhard tiers additionally fail if any ring bin is lifted (plan/V4 user decision "误抓即失败"). Choice labels: a=`pick up the container`, b=`put down the container` in all tiers. Reveal window: steps [0,64), containers away during [0,32) then dropped back (native: teleport to (10,10,10); xhard: per-object park points, same timeline). All differences above are stated in plan §三 VU row / §四.3.

## Data covered
- New tiers: all 12 delivered (xhard1..4 × ep 0/3/6) from `new-tier-index.json`.
- Native: all 9 in `artifacts/newtask-v6/v1/base/B/VideoUnmask_episode_*` (easy seeds 6000/6100/6400, medium 6200/6600/7001, hard 6300/6700/7100).
- 21 HDF5 read in full (every timestep: simple/grounded subgoal, online variants, boundary, video-demo flag, choice_action, gripper). mp4 frame counts equal HDF5 step counts for all 21.

## Checks performed (scripts in this dir)
1. `vu_extract.py` → `raw_extract.json`: goal, segments, boundaries, choices.
2. `vu_colorcheck.py` → `color_checks.json`: HSV blob detection on front_rgb.
   - Reveal frame t=10: exactly 1 red, 1 green, 1 blue cube in all 21 episodes; ring cube count (Y+C+M) = 4,4,4 / 5,5,5 / 6,6,6 / 7,7,8 for xhard1..4, all inside configured ranges; native 0.
   - t=40: no coloured cube visible in any episode (all covered after the reveal).
   - Goal colours == subgoal colours == order of picks, all 21 episodes.
   - For every pick segment (36 picks): at segment end exactly one new R/G/B cube becomes visible and it is the colour named in the subgoal; target not visible at segment start (put-downs never re-cover or pre-expose a target).
   - Grounded `<y, x>` point to the revealed cube of the named colour: 1.5–8.2 px (new) vs 1.9–4.5 px (native).
3. `vu_choice.py` → `choice_checks.json`: choice letter A for every pick, B for every put-down; pick choice point within 12 px of the named cube.
4. Contact sheets `frames/sheet_<tier>_ep<n>_seed<s>.png` (reveal, covered, every pick start/end, put-down end, last frame); visually inspected xhard2 ep0, xhard4 ep6, hard ep7.

## Findings
**VU-1 (low, new-tier sample only; mechanism shared with native):** `xhard2 ep0 seed10600000` third pick (`steps 388–483`, blue): `grounded_subgoal` = `pick up the container that hides the blue cube` (no `<y, x>`), because at the subgoal-change step 388 the target bin_2 is completely occluded by the arm that just put down bin_1 (`frames/xhard2_ep0_pick3_target_occluded_t388.png`; blue cube revealed at y93.5,x137). `segmentation_utils.process_segmentation` computes the point only on the change step and falls back to the task name; `RecordWrapper` wrote a 1-frame `success_NO_OBJECT_...mp4` that is listed in the delivered index. choice_action for the same steps still carries point [87,138]. 0/9 native episodes and 11/12 other new-tier episodes are unaffected; the code path is identical for native tiers, so the difference is frequency (3-pick chains, arm parks over dense layout), not code.

No colour/order/identity/terminal-action mismatch between language, subgoals, choices and video in any of the 21 episodes. No undocumented native-vs-new difference found in template, task chain, choice labels or predicates.

Excluded/seen: D1 (hard "15 containers", visible ~6–8 in native hard sheets) — seen, not re-reported. D7 (ring bins not in VQA `available`, `env.spawned_bins` = inner bins only) — seen.

## Not checked
- Exact on-table container counts per frame (no actor list in HDF5; white-blob component counts are not reliable).
- Failure-branch behaviour (misgrasp of ring/other bins) — no failed episodes delivered; predicates checked from source only.
- Other VideoUnmask candidates beyond the 12 delivered; FailRecover variants exist only in native base/B (generation setting, not a semantic difference).
