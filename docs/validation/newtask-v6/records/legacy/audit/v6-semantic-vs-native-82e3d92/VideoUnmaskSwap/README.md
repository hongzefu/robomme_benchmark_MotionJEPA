# VideoUnmaskSwap — semantic-vs-visual and native-vs-new-tier audit

[内部产出，英文] Internal workflow record. AUDIT_BASE = `82e3d922b78d48ec1e825b168cccc0e1b8c690c1` (source read only via `git show <AUDIT_BASE>:<path>`).
Read-only; all helper scripts and outputs live in this directory. No simulation, no robomme/gym/sapien import.

## Sources read (at AUDIT_BASE)
- `src/robomme/robomme_env/VideoUnmaskSwap.py` (configs, `_native_decision`, `_load_scene` task list, `step`, `evaluate`)
- `src/robomme/robomme_env/utils/task_goal.py::get_language_goal` (VideoUnmaskSwap branch)
- `src/robomme/robomme_env/utils/vqa_options.py::_options_video_unmask_swap`
- `src/robomme/robomme_env/utils/subgoal_evaluate_func.py` (`static_check`, `is_bin_pickup`, `is_bin_putdown`, `is_any_bin_pickup`)
- `src/robomme/robomme_env/utils/unmask_swap_xhard.py`, `unmask_distractor_sampler.py`, `unmask_distractors.py::add_distractor_misgrasp_failure`, `xhard.py::DISTRACTOR_COLORS`
- `src/robomme/robomme_env/utils/segmentation_utils.py::process_segmentation`, `src/robomme/env_record_wrapper/RecordWrapper.py::step` (grounded-subgoal fill / NO_OBJECT)
- `0925-newtask-release-v6-plan.md` sections 二/三/四.2/四.4 (copy: `plan_82e3d92.md`)
- `subgoal_language.py` has no VideoUnmaskSwap branch; `sampling_config.json` not needed beyond the class `configs` (plan 四.1: VUS swap/pick counts live in `native.parameters.configs[<tier>]`).

## Per-tier table (code at AUDIT_BASE, confirmed by plan table 三)
| tier | inner bins | hidden cubes | swaps | steps/swap | picks | outer distractor bins (with cube, Y/C/M) | inner partner | language template |
|---|---|---|---|---|---|---|---|---|
| easy | 3 (region3 tri/line) | 3 (R/G/B perm) | [1,2] | 50 | [1,2] | 0 | nearest XY at swap start | 1 pick: "watch the video carefully, then pick up the container hiding the A cube"; 2 picks: "..., finally pick up another container hiding the B cube" |
| medium | 4 (bin_3 always empty) | 3 | [1,2] | 50 | 1 | 0 | nearest | 1-pick |
| hard | 4 | 3 | [2,3] | 50 | 2 | 0 | nearest | 2-pick |
| xhard1 | 4 | 3 | [4,5] | 50 | 2 | 4 (2) | S5 reset plan | 2-pick |
| xhard2 | 4 | 3 | [6,7] | 33 | 3 | 6 (3) | S5 | 3-pick "..., next pick up another container hiding the B cube, finally pick up another container hiding the C cube" |
| xhard3 | 4 | 3 | [8,9] | 33 | 3 | 8 (4) | S5 | 3-pick |
| xhard4 | 4 | 3 | [10,12] | 33 | 3 | 10 (5) | S5 | 3-pick |

Task chain (all tiers): `static` (video demo, `static_check(static_steps=last_swap_end)`) → pick color_names[0] → [put down → pick color_names[1]] → [put down → pick color_names[2]].
Predicates (all tiers): pick = `is_bin_pickup` (bin z > 0.15); put down = `is_bin_putdown` (bin z <= 0.07, not grasped, tcp z > 0.05); failure = any other inner bin z > 0.15. New tiers additionally fail on any outer distractor bin lifted (`add_distractor_misgrasp_failure`, inherited xhard mechanism). Choice labels identical in all tiers (`pick up the container` / `put down the container`).
Timeline (all tiers): cubes visible t in [0,32), containers drop at t=32, swaps from t=64, hidden cubes parked during swaps and set under final bin XY at last swap end. Outer cubes are yellow/cyan/magenta only, never red/green/blue.

## Data covered
- New tiers: all 12 delivered HDF5 + main MP4 (`new-tier-index.json`, xhard1..3 from `v6-01`, xhard4 from `v6-01-infra-recovery-01`), plus the 40 frozen specs in `v6-01/xhard*/specs.jsonl` (config compliance) and each delivered episode's `spec_replay.json` (mismatches = [] for all 12).
- Native: all 9 VideoUnmaskSwap episodes in `v1/base/B` (easy seeds 5000/5100/5400, medium 5200/5600/6000, hard 5300/5700/6100), plus a text-only scan of the official HF native file `/data/hongzefu/robomme_data_h5/record_dataset_VideoUnmaskSwap.h5` (100 episodes, 154 pick subgoals) for grounded-subgoal comparison (`official_hf_scan.json`).

## Checks and results (all 21 episodes unless noted)
1. Config compliance (`spec_check_stdout.txt`): 40/40 new-tier specs have n_swaps in range, n_picks, outer count, outer cube count = half, steps/swap per plan; len(inner pairs) = len(outer pairs) = n_swaps.
2. Language vs subgoals vs spec: goal colors = subgoal colors = spec color_names[:n_picks] in 12/12; native goal = subgoal colors in 9/9; MP4 filename slug matches goal and tier in 21/21 (`motion_check.json`).
3. Reveal frame t5 (`color_check.json`): exactly one red, green, blue cube; outer Y/C/M cube counts equal spec in 12/12; native 9/9 show only R/G/B.
4. Covered frames t50, demo end, first exec +2/+10: zero colored cube pixels in 21/21 (all cubes hidden before and after swaps; `post_swap_check.json`).
5. Swap timing (`motion_check.json`): motion present in every scheduled window (xhard1 50 steps, xhard2-4 33 steps); native motion runs match easy/medium [1,2], hard [2,3] swaps.
6. Swap identity (`swap_pair_check.json`): at the mid-step of each of the 92 new-tier windows, the two lowest white-occupancy inner slots are exactly the spec pair (92/92).
7. Pick reveal (`color_check.json`, `track_check.json`): 33/33 new-tier and 13/13 native picks reveal exactly the named color when the container is lifted; for new tiers the revealed blob is 0.2–3.8 px from the projection of the spec-propagated position of that color (nearest other slot >= 24.7 px). Initial projection error <= 1.23 px.
8. Grounded subgoals: see finding below.

Key images: `sheets/<tier>_ep<k>_seed<s>.png` (per episode: t5 reveal, t50 covered, demo end, each pick start/lifted with the expected position circled), `frames/tier_compare_t5_t50.png`, `frames/xhard4_s6500000_front_*.png`, occlusion evidence `frames/xhard2_s10500000_front_592-593-600-640.png`, `frames/xhard2_s10500600_front_441-442-460-500.png`, `frames/xhard3_s12500300_front_656-657-680-720.png`, `frames/xhard2_s10500000_mp4_150_593.png`.

## Findings
- **VUS-N1 (native_same, low)**: a post-put-down pick subgoal can lose its `<y, x>` location in `grounded_subgoal` / `grounded_subgoal_online` for the whole segment, because at the boundary step the arm fully occludes the target container in the front-camera segmentation (`segmentation_utils.py::process_segmentation` sets `no_object_flag` and the text falls back to the plain task name; `RecordWrapper.step` then writes a `success_NO_OBJECT_*` 1-frame video). New tiers: xhard2 seed10500000 steps 593-706 (red), xhard2 seed10500600 steps 442-555 (green), xhard3 seed12500300 steps 657-749 (blue) — 3/33 picks, 3/21 post-put-down picks. Native: official HF episode_21 (easy, step 271, red) and episode_81 (easy, step 254, green) — 2/154 picks, 2/54 post-put-down picks; base/B native 0/13. `choice_action.point` is still present in these segments. Same code path in all tiers; the higher new-tier rate is plausibly due to more post-put-down picks per episode (small samples, not tested).
- No new-tier-only or native-vs-new mismatch found in language template, task chain, choice labels, predicates or visual content beyond what the plan documents (S5 partner planning, 33-step swaps from xhard2, outer ring distractors with Y/C/M cubes, distractor misgrasp failure, 3 picks from xhard2).

## Seen but excluded
- F4 (stale grounded coordinates after swap) — not re-measured.
- D7 (VQA `available` = `spawned_bins`, outer ring not selectable) — seen in `_options_video_unmask_swap`.
- `success_NO_OBJECT_*` tail videos are site-excluded debug clips (website issue) — only used as a pointer to VUS-N1.

## Not checked / limits
- No per-frame instance-ID tracking; identity check uses mid-window slot occupancy and end-state color projection (the earlier audit `v6-semantic-evidence-01a0e086/swap_video` did denser tracking).
- Outer-ring swap identity per window not checked visually (only spec length and motion).
- `is_bin_pickup` has no grasp condition (z > 0.15 only), identical in all tiers; no false-success instance observed, so not reported as a finding.
- Native easy episodes in base/B are all single-pick; native 2-pick easy was only covered through the text scan of the official HF file.
- No undelivered candidates' HDF5 (none exist); no new rollouts.
