# PickXtimes: semantic-vs-visual and native-vs-new-tier audit (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Pure audit, read-only. Source read only via `git show 82e3d92:<path>`. Data read with h5py/numpy/cv2. No simulation.

## Source per-tier table (git show 82e3d92)

| tier | N range (`PickXtimes.config_*` / sampling_config `decision.number_range`) | colours (`decision.color`) | distractors (`decision.<tier>.distractor.colors`) | spawn path | cube box half / min centre dist |
|---|---|---|---|---|---|
| easy | [1,3] | 1 | none | `_spawn_scene_objects_native` | 0.2 / none |
| medium | [1,3] | 3 | none | native | 0.2 / none |
| hard | [4,5] | 3 | none | native | 0.2 / none |
| xhard1 | [6,7] | 3 | yellow | `_spawn_scene_objects_xhard` + `_spawn_distractors_xhard` | 0.25 / 0.08 |
| xhard2 | [8,9] | 3 | yellow, cyan | xhard | 0.25 / 0.08 |
| xhard3 | [10,12] | 3 | yellow, cyan, magenta | xhard | 0.25 / 0.08 |
| xhard4 | [13,15] | 3 | yellow, cyan, magenta (`min(4,len(DISTRACTOR_COLORS))`=3) | xhard | 0.25 / 0.08 |

Matches plan 0925 section 三 row PickXtimes exactly.
Shared by all tiers: language template `task_goal.py` branch `env == "PickXtimes"` (num2words to 20); task chain in `PickXtimes._load_scene` (N x [pick "for the {ordinal} time", place "onto the target"] + "press the button to stop"); ordinals `subgoal_language._ORDINALS` to 20; choice labels a/b/c (`vqa_options._options_pickxtimes`); predicates `is_obj_pickup` (z>0.05 & grasp), `is_obj_dropped_onto` (xy<=0.05 + `is_obj_dropped`), `is_button_pressed` (depth>0.005); failure_func `is_any_obj_pickup(non_target_cubes)` / button, button failure `is_any_obj_pickup(all_cubes)`. In xhard, distractors join `all_cubes`/`non_target_cubes` (not `target_candidates`).

## Data coverage
- 12/12 delivered new-tier HDF5 + mp4 (xhard1..4 x ep 0/3/6) from new-tier-index.json.
- 9/9 native HDF5 + mp4 in `newtask-v6/v1/base/B` (easy ep0,1,4; medium ep2,6,10; hard ep3,7,11).
- Script `extract.py` -> `records.json` (per-episode facts); `annotate.py` -> `frames/*.png` (t0 colour census, first pick grounded point, button-segment start, final frame); `count_frames.py`; `disk_vs_magenta_hue.json`.

## Checks per episode (all 21 passed unless listed under findings)
1. goal number word == #pick segments == #place segments; ordinals first..Nth contiguous.
2. goal colour == subgoal colour == colour under the grounded pick point (5x5 HSV vote) at every pick-segment start (135 new-tier + 29 native picks, 0 mismatch).
3. after each place, next pick point (cube location) is within 1.0-4.24 px of the disk centre (256 px image); final frame target-colour blob within 1.4-3.6 px of disk.
4. frame-0 colour census: xhard1 R,G,B+yellow; xhard2 +yellow,cyan; xhard3/4 +yellow,cyan,magenta; easy 1 cube; medium/hard 3 cubes. Non-target blobs move <=0.14 px t0->final (none disturbed).
5. gripper-close rising edges = N+1 (N grasps + button) in all non-recovery episodes; recovery natives N+2.
6. mp4 frame count == HDF5 steps; goal in mp4 filename == setup/task_goal; is_video_demo all False; available_multi_choices identical across tiers.
7. N sampled in range: xhard1 6,7,6; xhard2 9,9,9; xhard3 11,11,11; xhard4 14,15,13.

## Findings
- PX-1 (native_same, low): xhard1 ep3 (seed 8100300) button segment t960-1033: `info/grounded_subgoal` = "press the button to stop" with NO `<r, c>` for the whole segment, because at t960 the retracted arm occludes the button (and the yellow distractor); RecordWrapper writes `success_NO_OBJECT_...mp4` (1 frame). choice_action point [60,129] still correct (button at <60,128> in t0). All other 20 episodes carry coordinates. Mechanism is frozen `RecordWrapper` no_object_flag path, also present in native base/B (SwingXtimes ep7, VPB ep7/10, VPO, VideoRepick ep4). Evidence: `frames/new_xhard1_ep3_t0-t0-t960-t1079.png`, `xhard1_ep3_NO_OBJECT_lastframe.png`.
- PX-2 (new_tier_only, low): plan 四.7 says only "PickX xhard3/4 ... 会超 1301 步"; delivered xhard2 ep0 (seed 10100000) completes at step 1350 (HDF5 1390 steps; ep3 1317/1281, ep6 1313/1275). PickXtimes has no demo segment, so all steps count toward `scripts/evaluation.py max_steps=1300`. Plan 口径2/D10 allow exceeding 1301 generally, so this is a documentation incompleteness, not a rule breach. Native max 897.

## Seen / not reported
- No FailRecover episodes in new tiers (native base has 5/9): spec `recovery_rule` "V4 全部不开 fail recover（用户 2026-09-22）" — documented decision.
- Magenta distractor hue (~150 OpenCV) close to the disk ring (142, S153) in xhard3/4; disk has white rings and is flat, visually distinguishable in all 6 episodes — noted only.
- Excluded list F1-F6/D1-D7: none applicable to PickXtimes observed (F5 checked previously: place is not mid-air here, cube on disk ≤4.24 px).

## Not checked
- Non-delivered candidates (only index 0/3/6 delivered), wrist-camera content, exact button depression depth (not recorded; relied on is_completed and "All tasks completed" segment), physical z of cube at place completion (no object pose in HDF5; used image-plane distance only).
