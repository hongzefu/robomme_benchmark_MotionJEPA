# MoveCube semantic-vs-visual / native-vs-xhard4 audit (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Pure read-only audit. Source read only via `git show 82e3d92:<path>`. No simulation, no robomme import.
Helper scripts in this directory only use h5py / numpy / cv2 / json.

## Sources read (at AUDIT_BASE)
- `src/robomme/robomme_env/MoveCube.py` (config_native / config_xhard4, `_load_scene`, `_load_scene_xhard4_region`, `_initialize_episode`, `evaluate`, `step`)
- `utils/task_goal.py` (MoveCube branch), `utils/vqa_options.py::_options_movecube`, `utils/subgoal_evaluate_func.py::is_obj_pushed_onto`
- `utils/subgoal_language.py` (no MoveCube-specific code)
- `scripts/configs/newtask-v6/sampling_config.json` tasks.MoveCube
- `0925-newtask-release-v6-plan.md` 二.5/二.9, 三 (MoveCube row), 四.6, 风险 4

## Per-tier table (MoveCube has only easy/medium/hard + xhard4; xhard1-3 rejected by `require_xhard4_only`)
| layer | easy / medium / hard | xhard4 |
|---|---|---|
| language goal (`task_goal.py`) | "watch the video carefully, then move the cube to the target in the same manner as before" / "... shown in the video" | identical (verified in HDF5 setup/task_goal) |
| parameters | none (no N / colors / ordinals). `way` ∈ {peg_push, gripper_push, grasp_putdown} via `initializations.<i>.way_idx`; last init is effective | same sampler |
| task chain (`evaluate`) | peg_push: Pick up the peg → Hook the cube to the target with the peg → static(30) → reset → same 2 exec subgoals; gripper_push: Close the gripper and push … → static(60) → reset → same; grasp_putdown: Pick up the cube → place the cube onto the target → static(60) → reset → same | identical (no difficulty branch in `evaluate`) |
| choice labels (`vqa_options`) | a pick up the peg / b hook … / c close gripper and push … / d pick up the cube / e place … | identical (HDF5 setup/available_multi_choices) |
| predicates | `is_obj_pushed_onto(dist ≤ cube_half_size·2·1.2 = 0.048 m, must_gripper_open=True)`; `is_obj_dropped_onto`; `is_obj_pickup`; failure funcs as in code | identical |
| layout | peg base_y ±0.2 + jitter ±0.05, yaw ±π/4; goal demo box half 0.15 / exec 0.10; cube centre ±0.1 + box 0.05, ≥0.10 from goal | annulus U: centre (−0.06,0), r ∈ [0.12,0.20], base dist [0.35,0.76], cube–goal ∈ [0.10,0.30], peg yaw ±π, peg_gap 0.04, goal_peg_gap 0.02 (matches plan 二.9 / 四.6) |

## Data covered
- New tier: all 3 delivered xhard4 (ep0 seed 7400000 gripper_push, ep3 7400300 gripper_push, ep6 7400600 grasp_putdown) — HDF5 + mp4, plus their frozen specs in `v6-01/xhard4/specs.jsonl` (world poses).
- Native: all 9 base/B MoveCube HDF5 + mp4 (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11; 4 peg_push, 2 gripper_push, 3 grasp_putdown).
- Supplementary (not delivered, launched at commit 38488db, not source-verified at AUDIT_BASE): S2 regression `v6-s2-20260926-01` MoveCube 9 HDF5 incl. 3 successful xhard4 peg_push.

## Checks and results
1. Language/choices/chain identical across all 12 episodes (`records.json`: language_goal, choices, demo_chain == exec_chain, `same_manner=True` for all 12).
2. Grounded subgoal coordinates vs detected objects (red cube mask R>120,G<35,B<35; purple target mask) at every boundary: max error ≤1.2 px in all 12 (`records.json.grounding_checks`). Grounded order is `<row, col>`. For xhard4 the grounded coordinates also match the projection of spec world poses through the HDF5 camera K/E to ≤2.5 px (`xhard4_spec_projection.json`).
3. Spec geometry of the 3 delivered xhard4: cube/goal/peg-grasp radii from centre all in [0.12,0.20], cube–goal 0.155–0.288 m (≤0.30). Consistent with plan.
4. Demo end (static) and execution completion: cube-to-target pixel distance 2.5–9.1 px (all tiers), no drift after completion (0–0.3 px) → no mid-air completion. Gripper opens at completion in both tiers (`gripper_state_by_segment.json`, `tail_gripper.py`), matching `must_gripper_open=True`.
5. Exec start: only one purple target visible (goal moved to goal2 pose via `step` reset branch), cube at exec pose; checked in keyframe PNGs `*_keyframes.png` and `frames/`.
6. S2 xhard4 peg_push (3 successes): gripper closed ≥95% of hook segments, cube ends 6.9–9.8 px from target (`s2_pegpush_check.json`, `s2_*_pegpush_keyframes.png`).

## Findings (details in structured output)
- MC-1 (native_same, low): front camera fully hides the cube at the end of the demo push (xhard4 ep3: 0 red px for all 60 static frames 98–157; native hard ep11: 20 px). Wrist view shows cube on target (`occlusion_xhard4_ep3_t0128.png`, `occlusion_hard_ep11_t0132.png`, `frames/mp4_xhard4_ep3_f0130.png`, `demo_end_occlusion.json`).
- MC-2 (new_tier_only, low, low confidence; S2 non-delivered only): grounded subgoal loses both `<>` coordinates when cube is occluded at the boundary frame (S2 seed 6100002 step 105 "Hook the cube to the target with the peg"). 0/9 native, 0/3 delivered xhard4 (`grounding_missing_coords_scan.json`).
- MC-3 (native_same, low): success predicates do not check the "manner" words themselves ("with the peg", "close the gripper"); manner is only partly enforced by failure_funcs. No delivered episode exploits this.
- MC-4 (new_tier_only, low, coverage): the 3 delivered xhard4 episodes contain no peg_push (effective ways of 10 candidates: 3 peg_push at unselected idx 4/7/9, `xhard4_candidates_way.json`); natives have 4/9 peg_push. The xhard4-specific peg path (yaw ±π, B11 grasp-yaw reduction) is unrepresented in the formal set.

## Excluded items seen
None of F1–F6 / D1–D7 apply to MoveCube. No left/right wording in MoveCube language.
