# ButtonUnmask audit (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Pure read-only audit. Source read only via `git show 82e3d92…:<path>`; data opened with h5py/numpy/cv2 only
(helper scripts in this directory: `h5_layout*.py`, `extract.py`, `annot.py`, `count_bins.py`, `mp4_frames.py`, `ep6_x4.py`).

## Sources read
- `src/robomme/robomme_env/ButtonUnmask.py` (configs, `_load_scene`, `_append_xhard_pick_tasks`, `step`, `evaluate`)
- `utils/task_goal.py` (`_unmask_pick_count`, `_unmask_multi_pick_clause`, `get_language_goal`), `utils/subgoal_language.py`,
  `utils/vqa_options.py::_options_button_unmask`, `utils/subgoal_evaluate_func.py` (`is_bin_pickup` z>0.15, `is_bin_putdown` z<=0.07,
  `is_button_pressed` depth>0.005), `utils/unmask_distractors.py::add_distractor_misgrasp_failure`,
  `utils/unmask_distractor_sampler.py` (presets, parked reveal), `utils/xhard.py::DISTRACTOR_COLORS`,
  `env_record_wrapper/RecordWrapper.py` + `utils/segmentation_utils.py::process_segmentation` (grounding), `DemonstrationWrapper` (online grounding)
- `scripts/configs/newtask-v6/sampling_config.json` tasks.ButtonUnmask; plan `0925-newtask-release-v6-plan.md` §二/三/四.3

## Per-tier table (source + config)
| tier | inner bins (cfg) | pick | distractor bins / with cube | goal template | chain |
|---|---|---|---|---|---|
| easy | 3 | 1 | – | "first press the button, then pick up the container hiding the C0 cube" | press → pick bin_0 |
| medium | 5 | 1 | – | same as easy | same |
| hard | 15 (realised 6, see F-BU-2) | 2 | – | "... C0 cube, finally pick up another container hiding the C1 cube" | press → pick bin_0 → put down → pick bin_1 |
| xhard1 | 8 (fail-loud) | 2 | 8 / 4 | identical to hard template (pick=2 goes through native elif branch) | same as hard, built by `_append_xhard_pick_tasks` |
| xhard2 | 8 | 3 | 10 / 5 | "... C0 cube, next pick up another container hiding the C1 cube, finally ... C2 cube" | press → pick b0 → put → pick b1 → put → pick b2 |
| xhard3 | 8 | 3 | 12 / 6 | same as xhard2 | same |
| xhard4 | 8 | 3 | 14 / 7 | same as xhard2 | same |
Colors of hidden cubes: randperm of red/green/blue under bin_0..2; distractor cubes yellow/cyan/magenta balanced cycle. Choices a/b/c
(press / pick up the container / put down the container) identical in all tiers. Predicates identical except new tiers add
"any distractor bin lifted (z>0.15) => fail" to every pick/put-down task (plan §二 口径6 "all xhard mechanisms"). Reveal window steps 0–64,
drop back at step 32 (D3, excluded) in all tiers.

## Data coverage
All 12 delivered new-tier HDF5+mp4 (xhard1..4 × ep0/3/6) and all 9 native HDF5+mp4 in `newtask-v6/v1/base/B` (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11).
Per episode (`records.json`): goal vs mp4 filename, HDF5 difficulty, segments with simple/grounded text, completion step,
reveal-frame (t16) colored-cube blobs, each pick's grounded <row,col> vs reveal cube, eef projection at grasp (front intrinsic×extrinsic),
colour exposed at the named cube location at segment end, last-frame blobs. mp4 frame counts == HDF5 steps for all 21.

Results: 21/21 pick order == goal colour order; 21/21 grounded/online coordinate, grasp projection (7–18 px) and exposed colour all hit
the named colour; distractor cubes seen at t16 = 4/5/6/7 for xhard1..4 (= config half of distractors), 0 for native; distractor cubes never
visible after reveal (no distractor lifted); all episodes completed.

## Findings
- **F-BU-1 (new tier only observed; low)** xhard4 ep6 seed 6800600: whole segment t280–385 "pick up the container that hides the blue cube"
  has `info/grounded_subgoal` WITHOUT coordinates (fallback text), while `grounded_subgoal_online` = `<78, 111>` (blue cube reveal blob at
  (82.4,112.1)), choice point [75,112], grasp at t356 projects to (72.1,111.5). A 1-frame `success_NO_OBJECT_…mp4` sits in the delivered videos dir.
  Cause: at subgoal switch (t280) the target container is occluded by the arm in the front camera (`annotated/xhard4_ep6_blue_segment_t0280.png`);
  `RecordWrapper` → `segmentation_utils::process_segmentation` computes the fill only on subgoal change, so the fallback sticks for the segment.
  Native 0/9 affected; mechanism is shared (RecordWrapper frozen). Evidence: `mp4_frames/xhard4_ep6_mp4_f0368.jpg` (planner row no coords, online row coords).
- **F-BU-2 (native vs new; low)** sampling_config `decision.bin_layout_policy.count` says hard=15, medium=5, but native `_load_scene` catches
  `RuntimeError` and `break`s silently (`min_gap_factor` 2): delivered native hard ep3/7/11 each show 6 containers at t33, medium ep10 shows 4
  (`annotated/native_hard_vs_xhard1_t0033.png`, `annotated/native_easy_medium_t0033.png`). New tiers raise `SceneGenerationError` on shortfall and
  show the configured 8+N (xhard4 ep0: 22 visible, `annotated/xhard4_ep0_t0033_big.png`). Same phenomenon as excluded D1 (VideoUnmask) — may be merged with it.

## Seen, excluded
D3 (reveal at absolute steps 0–31 before the button press; press ends t110–122 in all 21 episodes), D7 (VQA `available=env.spawned_bins` only).

## Not checked
Physical plausibility beyond pixels (no simulation); segmentation masks not stored in HDF5 so container count is visual (spot-checked hard×3,
medium×3, easy×1, xhard4 ep0 exact; other new tiers only via distractor-cube count); FailRecover variants exist only in native ep0–4 (generation
setting, not audited); undelivered candidates; website text.

Note: `container_count_t33.json` is an automatic white-blob count that over/under-segments container facets; it is NOT used as evidence (visual counts in `records.json::visual_container_count_t33` are manual from the annotated images).
