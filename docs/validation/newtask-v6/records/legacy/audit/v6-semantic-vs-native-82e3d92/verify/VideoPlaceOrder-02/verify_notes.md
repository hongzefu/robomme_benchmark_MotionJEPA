# Verify: VideoPlaceOrder-02 (AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

## Mechanism located (independent, from AUDIT_BASE source)
- src/robomme/robomme_env/VideoPlaceOrder.py::_build_xhard_task_list (line ~830-831) and
  ::_initialize_episode native branch (line ~1021-1022): BOTH define the "place the cube onto
  the correct target" task with the identical subgoal_segment template
  `"place the cube onto the correct target at <>"` and identical `segment=self.target_target`.
  No xhard-specific difference in this task's definition.
- src/robomme/robomme_env/utils/segmentation_utils.py::process_segmentation: the coordinate is
  computed ONCE, only at the frame where `current_subgoal_segment != previous_subgoal_segment`
  (the subgoal-boundary frame), from the live segmentation mask. If the target's segmentation id
  has zero visible pixels at that exact frame, `no_object_flag=True`, `center=None`, and the
  whole filled text falls back to bare `current_task_name` (placeholder dropped, not just left
  blank) via `missing_placeholder` branch. This fallback is then cached in
  `current_subgoal_segment_filled` / `current_subgoal_segment_online_filled` and reused for every
  subsequent step of that same subgoal (RecordWrapper.step, existing_subgoal_filled passthrough)
  until the next subgoal boundary. This code path is shared by every task in every difficulty
  tier -- nothing here is xhard-specific.

## HDF5 reproduction (xhard1 ep3)
File: artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/VideoPlaceOrder_episode_3/hdf5_files/VideoPlaceOrder_ep3_seed9100302.h5
- t=1422 (boundary): grounded_subgoal = "pick up the cube at <134, 173>" (coordinate present)
- t=1532 (boundary): simple_subgoal = "place the cube onto the correct target",
  grounded_subgoal = "place the cube onto the correct target" (coordinate DROPPED) -- reproduced
  verbatim from raw H5, matches finding's claim exactly.
- t=1532..1605 unchanged (cached fallback), t=1606 boundary to "All tasks completed" (still
  carries the stale "place the cube onto the correct target" grounded text, expected/no bug).
- action/choice_action at t=1532/1540/1600 = `{"choice": "B", "point": [105, 170]}` -- i.e. the
  per-step VQA choice_action DOES carry a valid target coordinate even though grounded_subgoal
  lost it. This matches the audit tooling's own documented fallback
  (scripts/parity/v6_site_catalog.py::_read_atomic_subgoals docstring: "坐标取 grounded_subgoal
  的 <行, 列>，缺失时用同帧 choice_action.point") -- so downstream consumers that already use this
  documented fallback are not blocked by this particular occurrence.

## Visual confirmation (frames saved in this dir, t{NNNN}_front.png)
- t1420_front.png: red cube resting near the bottom-right target ring, ring clearly visible.
- t1532_front.png / t1533_front.png / t1534_front.png: gripper holding the red cube directly
  above the bottom-right target ring at the subgoal-boundary frame -- ring occluded by
  gripper+held-cube exactly at the frame process_segmentation samples. Matches finding's
  "the frame shows the answer target under the gripper".
- t1600_front.png / t1615_front.png: cube placed down on the same bottom-right ring (visually
  matches finding's "final red cube is on the correct post-swap target").

## Independent reproduction of a native-tier instance (native_same check)
File: artifacts/newtask-v6/v1/base/B/VideoPlaceOrder_episode_1/hdf5_files/VideoPlaceOrder_ep1_seed11103.h5
(tier = easy, confirmed via mp4 filename: "...FailRecoverZ_easy_watch_the_video...")
- t=389 (boundary): simple_subgoal = "drop the cube onto target", grounded_subgoal =
  "drop the cube onto target" (coordinate dropped) -- reproduces finding's cited
  "easy ep1 steps 389-497 drop" instance exactly (t=389..497 all boundary-cached, t=498 boundary
  back to "pick up the cube at <70, 163>" with coordinate restored).
- This is the SAME code mechanism producing the SAME kind of missing-coordinate behavior in a
  native tier, confirming category=native_same is correct: nothing about xhard1-4 mechanics
  changes this behavior, it is incidental to where the arm happens to be at each subgoal's first
  frame.

## Verdict
CONFIRMED. Not a duplicate of any excluded item (F1-F6, D1-D7, left/right wording, website-text
issues all describe different phenomena). category=native_same is correct as originally labeled
(mechanism is generic, shared, and reproduces identically in native tiers; xhard1 ep3 hitting the
answer segment specifically is incidental to this one episode's arm trajectory geometry, not a
tier-specific design difference -- no plan-basis divergence found in
0925-newtask-release-v6-plan.md sections 三/四, which do not mention grounded_subgoal / coordinate
occlusion behavior at all). No new simulation needed; fully verified from existing rollout data.
