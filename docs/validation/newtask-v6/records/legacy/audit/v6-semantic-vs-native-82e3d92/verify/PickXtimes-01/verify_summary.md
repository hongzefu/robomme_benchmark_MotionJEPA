[内部产出，英文]
以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。

# Verification of finding PickXtimes-01

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (git show only, working tree unread except my own evidence subdir).

## Mechanism check (source, PASS)
- `PickXtimes.py::_load_scene` button task: `"subgoal_segment": "press the button at <> to stop"`, `"segment": self.cap_link`. Confirmed byte-identical for all difficulties (the xhard/native branch only affects `_spawn_scene_objects_xhard` vs `_spawn_scene_objects_native`, not task-list construction).
- `segmentation_utils.py::process_segmentation`: `current_subgoal_segment_filled` is recomputed **only when** `current_subgoal_segment != previous_subgoal_segment` (i.e. once, on the first step of a new subgoal segment). If the placeholder can't be resolved (`no_object_flag` / `missing_placeholder`), it falls back to `current_task_name` (no coordinate), and this filled string is cached (`existing_subgoal_filled`) and reused verbatim for every remaining step of the same segment, even after the target becomes visible again later.
- This confirms the finding's causal story exactly: the bug is a segment-start-only occlusion snapshot, not a per-step re-check.

## Data check on xhard1 PickXtimes ep3 (h5, PASS)
- `grounded_subgoal` for `timestep_960..timestep_1079` (120 steps) is uniformly `'press the button to stop'` (no coordinate). `is_subgoal_boundary=True` fires exactly at t960 (segment start).
- Video frames extracted directly from `obs/front_rgb`:
  - t0 (task start): button (white/gray small object) clearly visible, unoccluded.
  - t960 (segment start, the moment the fallback fires): the gripper/arm is right above the button, fully occluding it — visually confirms "arm occludes the button at segment start".
  - t970: arm still overlapping the button.
  - t1000: arm has moved away, button fully visible again — yet `grounded_subgoal` at t1000 is still the coordinate-less text, proving the value is frozen from t960 and never re-evaluated even though the object becomes visible again mid-segment.
  - t1079 (final frame): button visible in the same position as t0.
- `videos/success_NO_OBJECT_PickXtimes_ep3_seed8100300_xhard1_...mp4` exists exactly for this episode, consistent with `no_object_flag` having fired.

## Minor correction to the finding text
The finding's evidence text says the button segment is "t960-t1033" / "74 steps"; the actual full button segment in the h5 runs t960-t1079 (120 steps), and the missing coordinate persists for the *entire* 120-step segment, not just 74. This does not weaken the finding — the real defect window is larger than stated — but the exact step range in the finding write-up is not byte-accurate and should be corrected if this finding is kept for the record.

## Scope check across all 12 new-tier PickXtimes episodes (h5, PASS)
Extracted the button-segment `grounded_subgoal` unique text for all 12 xhard1-4 episodes in `new-tier-index.json`: only xhard1 ep3 lacks the coordinate; the other 11 all have `press the button at <r, c> to stop` with concrete coordinates. Matches the finding's claim that "the other 11 new-tier episodes do have coordinates".

## Native-tier comparison (h5, PASS)
All 9 native PickXtimes episodes (`base/B/PickXtimes_episode_{0,1,2,3,4,6,7,10,11}`) have a coordinate-bearing button-segment `grounded_subgoal` text, zero missing — matches "In all 9 native PickXtimes episodes the button segment's grounded_subgoal reads ... at <r,c> ...".

## native_same category check (PASS)
Confirmed by directory listing that `success_NO_OBJECT_*` mp4 files exist in the **native** (`base/B`) tree for: SwingXtimes ep7, VideoPlaceButton ep7 & ep10, VideoPlaceOrder ep1/2/3/4/10/11, VideoRepick ep4 — i.e. the identical `no_object_flag` fallback mechanism (shared, unmodified `segmentation_utils.py` code) already fires in native tiers for other envs. Since this is a pre-existing generic occlusion-driven fallback bug in code untouched by the xhard-specific scene-spawning branch, and the plan (`0925-newtask-release-v6-plan.md` 三/四) does not claim xhard tiers change this grounding mechanism, `category=native_same` is the correct classification (not `native_vs_new_mismatch`, not `new_tier_only`).

## Duplicate-of-excluded check
Not a duplicate of F1-F7/D1-D7 (button/label/order/swap/text-window/VQA/left-right/website-text issues) — this is a distinct occlusion-triggered coordinate-dropping defect in the grounding pipeline, first observed here.

## Verdict
CONFIRMED (reproduced independently from AUDIT_BASE source + h5 + extracted video frames). category_corrected = native_same (agrees with submitted category). No new simulation needed — all evidence is from already-delivered runs.
