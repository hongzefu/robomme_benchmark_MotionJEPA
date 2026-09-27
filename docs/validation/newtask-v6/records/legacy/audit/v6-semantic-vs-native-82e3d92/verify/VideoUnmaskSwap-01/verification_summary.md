[内部产出，英文]
以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。

# Verification of finding VideoUnmaskSwap-01

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1, read only via `git show`.

## Independent reproduction (new tiers, 12 episodes in new-tier-index.json["VideoUnmaskSwap"])
Scanned all 12 xhard1-4 h5 files directly (info/simple_subgoal, info/grounded_subgoal,
info/is_subgoal_boundary). Result: total_picks=33, post_putdown_picks=21, missing-coordinate
picks=3 (all post-put-down): xhard2 seed10500000 step593 red, xhard2 seed10500600 step442 green,
xhard3 seed12500300 step657 blue. Exact match to finding's numeric claims (3/33, 3/21).

## Independent reproduction (native official HF file)
Located raw file /data/hongzefu/robomme_data_h5/record_dataset_VideoUnmaskSwap.h5 (23GB, 100
episodes) and scanned it directly (not the cached JSON). Result: total_picks=154, missing=2:
episode_21 step271 red, episode_81 step254 green. Exact match to finding (2/154). Seeds
extrapolated from base/B pattern (seed=5000+100*ep) give 7100/13100, matching finding exactly;
diff=easy per the (pre-existing, non-authoritative) official_hf_scan.json cache which matches
the file's own goal-chain-length structure.

## Independent reproduction (base/B, 9 episodes)
Scanned all 9 base/B h5 files. total_picks=12 (finding says 13 — minor arithmetic
discrepancy, does not affect the conclusion), missing=0. Confirms "0 missing" claim.

## Source-code mechanism (git show at AUDIT_BASE)
- segmentation_utils.py::process_segmentation: grounded text only recomputed when
  `current_subgoal_segment != previous_subgoal_segment` (i.e. once at subgoal switch, then
  cached); if the target's segmentation mask has zero visible pixels at that instant,
  `no_object_flag=True`, center=None, `missing_placeholder=True` -> the whole string falls
  back to `current_task_name` (the ungrounded text), exactly reproducing the observed
  "pick up the container that hides the X cube" (no `<y,x>`) output.
- RecordWrapper.py::step: `self.current_subgoal_segment_filled` persists across steps as
  `existing_subgoal_filled`; `no_object_video_frames` are dumped to
  `success_NO_OBJECT_{...}.mp4` / `FAILED_NO_OBJECT_{...}.mp4`; `grounded_subgoal` field in
  the h5 is exactly `self.current_subgoal_segment_filled`.
- VideoUnmaskSwap.py::_load_scene: subgoal_segment template for every pick (1st, 2nd, 3rd)
  is identically `f"pick up the container at <> that hides the {color} cube"` with
  `"segment": cur_bin` — same template, same segmentation-driven fill mechanism, used
  uniformly regardless of tier or pick position. No tier-specific code path.

## Video/visual check
Extracted front_rgb frames at steps 585/593/600/615/633/650 for xhard2 seed10500000
(saved to xhard2_10500000_occlusion_check.png in this dir): the Panda arm/gripper base
occupies the container cluster in frames 585-615, then withdraws by 633-650 revealing the
scene — consistent with "arm occludes container at boundary, visible ~40 steps later".
Confirmed `success_NO_OBJECT_*.mp4` for all 3 new-tier occurrences is exactly 1 frame
(cv2 CAP_PROP_FRAME_COUNT). Confirmed choice_action.point == [64, 122] at step 593 for
xhard2 seed10500000, exact match to finding.

## Plan basis check
`git show AUDIT_BASE:0925-newtask-release-v6-plan.md` has zero mentions of
no_object/occlusion/grounded_subgoal/coordinate handling — the plan does not touch this
mechanism at all, consistent with it being unmodified native behavior.

## Verdict
CONFIRMED. category=native_same is correct: identical code path, reproduced in native
easy-tier data (2/154 picks) and in new xhard1-4 tiers (3/33 picks); the higher new-tier
rate is plausibly attributable to xhard episodes having more post-put-down picks per
episode (task chains of 3 picks vs native chains of 1-2), not to any tier-specific code
change; the plan makes no mention of this mechanism. Not a duplicate of any excluded item
(F1-F6/D1-D7/left-right/website-text) — distinct mechanism from F4 (stale coordinates
after swap): this is missing coordinates due to occlusion at first-computation time, not
staleness of a previously-computed coordinate.
No new simulation needed or used; everything reproduced from already-delivered recorded
episode data and AUDIT_BASE source.
