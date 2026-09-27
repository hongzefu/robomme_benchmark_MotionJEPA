# Verification: VideoPlaceOrder-01

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (read via `git show`, working tree untouched)

## Source confirmation (repo /data/hongzefu/robomme_benchmark_MotionJEPANewTask @ AUDIT_BASE)
- src/robomme/robomme_env/VideoPlaceOrder.py::_native_decision -> `"demo_return_policy": "native_random_goal_site"` (native tiers).
- Same file, line ~119-124: `XHARD_DEMO_DECISION` / `NEWVALUE_DECISION["xhard1..4"]` all set `"demo_return_policy": "return_to_origin"`.
- Branch selector (`_load_scene`, ~line 486-492): `if self.difficulty == "xhard" or is_newvalue: self._load_scene_xhard_tail(); return` else falls through to native path using `decision_cfg["demo_return_policy"]` (= native_random_goal_site) for easy/medium/hard alike (no special-casing of "hard").
- `_xhard_pick_place` (~line 857-861): home=="goal" -> subgoal text "drop the cube onto table"; home in (True,"home") -> "put the cube back to its original position".

## Plan text confirmation (0925-newtask-release-v6-plan.md @ AUDIT_BASE)
- §三 table row VideoPlaceOrder: columns are hard/xhard1/xhard2/xhard3/xhard4 (5 columns = "五档"), row label "总放台次数（都放回原位）".
- §四.9: "现行结构：...VPO hard = 1 块依次访问v∈[2,4]张台（按钮插在某次后）→放桌面；xhard4 = 2块各v∈[2,4]→各放回原位。定稿：五档 demo_return_policy = return_to_origin" — i.e. the plan explicitly states hard's *existing* behavior is "drop onto table" and the *finalized* decision changes all five (including hard) to return_to_origin. Code shows this was never implemented for hard/easy/medium.

## Independent data reproduction (new script, not reusing prior audit's analyze.py verbatim)
1. Subgoal-sequence dump (`/tmp/verify_scratch/dump_subgoals.py`, plain h5py read of `info/simple_subgoal`) on:
   - native easy ep0 (`artifacts/newtask-v6/v1/base/B/VideoPlaceOrder_episode_0/hdf5_files/VideoPlaceOrder_ep0_seed11003.h5`, confirmed easy tier by mp4 filename): demo ends at step 739→824 with subgoal **"drop the cube onto table"**, then "static".
   - new-tier xhard1 ep0 (`artifacts/newtask-v6/v6-01/xhard1/rollout/run1/episodes/VideoPlaceOrder_episode_0/hdf5_files/VideoPlaceOrder_ep0_seed9100001.h5`): both demo cubes' final block subgoal is **"put the cube back to its original position"** (steps 658 and 1148).
2. Independent pixel-centroid measurement (`/tmp/verify_scratch/indep_check.py`, raw blue-mask centroid, NOT copying prior audit's connected-component code): easy ep0 blue cube centroid at t0=(117.3,167.8) vs t=800 (during post-drop static)=(80.1,125.4) → distance **56.4px**, closely matching the prior audit's recorded 56.9px (small diff from frame-index choice, same order of magnitude, same conclusion: cube moved far from origin).
3. Cross-checked prior audit's `records.json::demo_blocks[].end_vs_t0_px` for all listed episodes: native tiers (easy/medium/hard) values range 7.9-75.7px; xhard1-4 values range 0.1-2.6px. Values match the finding verbatim.

## Verdict
CONFIRMED. Source code, plan text, and two independently-reproduced pieces of raw-data evidence (subgoal text sequence + pixel centroid) all corroborate the finding exactly as stated. Category native_vs_new_mismatch is correct: the plan explicitly intends all five tiers (hard+xhard1-4) to share `return_to_origin`, but only xhard1-4 implement it; hard (and easy/medium, which share the same native code path) still execute the pre-existing `native_random_goal_site` behavior. Not a duplicate of any excluded issue (F1-F6/D1-D7 do not concern demo_return_policy/goal_site placement, and this is not a left/right or pure-website-text issue). No new simulation needed — sufficient episodes already exist in delivered data for both native and new tiers.
