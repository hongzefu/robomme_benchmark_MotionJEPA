# VideoPlaceOrder audit: semantic vs visual, native vs new tiers (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Read-only audit. Source was read only via `git show 82e3d92:<path>`, snapshotted into `src/`. HDF5 was read with h5py, numpy and cv2 only; no simulation and no robomme import.

## Coverage
- New tiers: all 12 delivered VPO HDF5 (xhard1..4, episodes 0/3/6), listed in `new-tier-index.json`.
- Native tiers: all 9 native VPO HDF5 under `newtask-v6/v1/base/B` (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11).
- Scripts: `extract.py` (subgoal segments, texts, choices -> `raw_extract.json`), `analyze.py` + `analyze_lib.py` (visual checks -> `records.json`), `extra_checks.py` (visit uniqueness, cube-on-target px, cube shift across swap), `swap_montage.py`, `dump_frames.py`.
- Visual evidence is in `frames/`. `swap_montage_{0,1,2}.png` has one row per swap episode (12 xhard + 3 hard) with 6 panels: t0 (answer target circled yellow), swap start, +15, +30, exec start and final frame. The expected post-swap answer target is circled green.

## Per-tier table (source at AUDIT_BASE)
| tier | colors | demo cubes | visits per cube | return | swap | language |
|---|---|---|---|---|---|---|
| easy | 1 | 1 | randint[2,4] | drop onto table (hidden goal_site, `native_random_goal_site`) | no | "place the {color} cube on the {nth} target it was previously placed on" / "...{nth} target where it was placed" |
| medium | 3 | 1 | [2,4] | table | no | same |
| hard | 3 | 1 | [2,4] | table | yes (2 of 4 targets, 50 steps) | same |
| xhard1 | 3 | 2 | {2,3} (the cube with more visits is chosen at random) | put back to original position (hidden home site) | yes | same |
| xhard2 | 3 | 2 | {3,3} | origin | yes | same |
| xhard3 | 3 | 2 | {3,4} | origin | yes | same |
| xhard4 | 3 | 2 | {4,4} | origin | yes | same |

The execution chain and predicates are identical for every tier (`VideoPlaceOrder::_build_xhard_task_list` vs the inline native list):
- pick target_cube; fail on picking any other cube.
- place onto target_target; fail on placing onto any other target.
- `is_obj_dropped_onto`: XY <= 0.05, and in non-demo mode z <= 0.2 with the gripper open.
- `which_in_subset` is drawn from `randint(1, len(visits of the answer cube))`.
- Choice set is a/b/c = pick / drop onto / press button, identical across tiers.

## Automated and visual checks (all 21 episodes; values in `records.json`)
1. **Language colour matches the executed cube.** The colour is sampled at the exec pick coordinate. Result: 21/21.
2. **The answer cube was demonstrated.** The visit counts per cube match the config multiset in 12/12 new-tier episodes (xhard1 [3,2]/[2,3]/[2,3], xhard2 [3,3], xhard3 [4,3]/[4,3]/[3,4], xhard4 [4,4]). Native tiers are in [2,4] in 9/9.
3. **Ordinal <= visits of the answer cube.** 21/21. No cube revisits a target (`unique_per_cube` is all True).
4. **Every demo drop visually lands on the target named by grounded_subgoal.** The cube centroid is 1.6 to 7.3 px from the target centroid.
5. **Home return is exact.** Each xhard cube's "put back" end position is 0.1 to 2.6 px from its t0 position. Native "drop onto table" moves the cube 7.9 to 75.7 px away from t0.
6. **The answer target is tracked through the swap.** The nth-visited target is carried through the swap. The final answer-colour cube sits on the post-swap location of that target in 21/21 episodes. The automated pair detection was ambiguous (occlusion) for xhard1 ep0 and hard ep3, so both were checked by eye in `swap_montage_0.png` (row 1) and `swap_montage_2.png` (row 4). Final cube to expected target is 2.3 to 6.1 px. The exec grounded target coordinate is within 2.3 px of the expected target.
7. **Cubes at home or spawn are not pushed by the swapping targets.** Max shift is 2.2 px (xhard2 ep6 blue). The non-demo cube never moves before exec (0.0 px).
8. **Subgoal vocabulary is the same except for the return step.** Native uses "drop the cube onto table"; xhard uses "put the cube back to its original position".

## Findings
- **VPO-1 (native_vs_new_mismatch, task_chain, low/medium).** The plan says all five tiers use `return_to_origin` (§二 口径10; §三 table header "都放回原位", which includes the hard column; §四.9 定稿). In the delivered data the native tiers still end the demo with "drop the cube onto table": the goal_site is hidden and the cube is moved 7.9 to 75.7 px. The native decision value is `demo_return_policy: native_random_goal_site`. Only xhard1-4 return to origin (0.1 to 2.6 px). The code keeps the native tiers frozen, as 口径1 requires. So the plan text overstates the uniformity, and the end-of-demo state and subgoal text differ between native and new tiers.
  - Evidence: `frames/easy_ep0_demo_end_state.png`, `frames/hard_ep3_demo_end_state.png`, `frames/xhard1_ep0_demo_end_state.png`, `frames/xhard4_ep0_demo_end_state.png`.
- **VPO-2 (native_same, other, low).** grounded_subgoal sometimes drops the `at <r, c>` coordinate when the point is occluded by the arm.
  - New tiers: 6/12 episodes (1-2 segments each).
  - Native tiers: 6/9 episodes (1 segment each).
  - Only in xhard1 ep3 does this hit the execution answer segment ("place the cube onto the correct target", steps 1532-1617). There the answer target is under the arm, see `frames/xhard1_ep3_exec_nocoord.png`.
  - The mechanism is the same in native and new tiers. The cause was inferred from frames only; the recorder code was not read.

No semantic-vs-visual mismatch was found in xhard1-4. Colour, ordinal, target identity across the swap and the terminal placement all agree with the video.

## Excluded items seen
The D5 site "static" label (the platform swaps during the second static) was observed in the swap montages. The left/right wording rule was not relevant.

## Not checked
- Object poses: the HDF5 has none, so all positions are image-space.
- Frame-by-frame continuity of the whole swap: only 4 sampled swap frames per episode.
- Cube z / "mid-air" completion: judged visually on the final frame only.
- Wrist camera and the mp4 files: the HDF5 front_rgb was used, not the mp4 decode.
- RecordWrapper grounding code.
- The 10-candidate pool beyond the 3 delivered episodes per tier.
