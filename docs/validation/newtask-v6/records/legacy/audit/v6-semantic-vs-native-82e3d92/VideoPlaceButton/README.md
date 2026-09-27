# VideoPlaceButton audit — AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1

Pure read-only audit. Source read only via `git show 82e3d92:<path>`; no simulation, no robomme import.

## Method
- Source: `src/robomme/robomme_env/VideoPlaceButton.py` (`_load_scene`, `_load_scene_xhard_tail`, `_extra_place_owners`,
  `_xhard_pick_place`, `_xhard_closing_tasks`, `V6_DEMO_DECISIONS`), `utils/task_goal.py` (VideoPlaceButton branch),
  `utils/vqa_options.py` (`_options_videoplacebutton`, `_videoplace_drop_available`), `utils/xhard_home_site.py`,
  `scripts/configs/newtask-v6/sampling_config.json` (tasks.VideoPlaceButton), plan `0925-newtask-release-v6-plan.md` §二/三/四.9/七.
- Data: all 12 delivered new-tier HDF5 (xhard1..4 × ep0/3/6) + all 9 native HDF5 in `artifacts/newtask-v6/v1/base/B/VideoPlaceButton_episode_*`.
  Per-episode `rng_trace.json` (new tiers) gives color_order, demo_ids, answer_demo_index, task_flag, extra-place owners/targets, swap pair.
- Scripts: `vpb_extract.py` (HDF5 → `raw_extract.json`), `vpb_track.py` (HSV cube centroid per segment → `cube_tracks.json`),
  `vpb_records.py` (→ `records.json`, plan sequence joined with HDF5 segment step spans + derived checks), `vpb_strip.py`/`vpb_crop.py` (annotated PNGs).
- Grounded coords are `<row, col>` in 256px front_rgb; cube tracker reports `[x, y]`.

## Per-tier table
| tier | color | targets | swap | demo cubes | extra before/after | target placements | final | language templates |
|---|---|---|---|---|---|---|---|---|
| easy | 1 | 3 | no | 1 | – | 2 | goal_site ("drop the cube onto table") | 4 templates, before/after, same for all tiers |
| medium | 3 | 4 | no | 1 | – | 2 | goal_site | same |
| hard | 3 | 4 | yes | 1 | – | 2 | goal_site | same |
| xhard1 | 3 | 4 | yes | 1 | 0/1 | 3 | home ("put the cube back to its original position") | same |
| xhard2 | 3 | 4 | yes | 1 | 1/1 | 4 | home | same |
| xhard3 | 3 | 4 | yes | 2 | 1/0 | 5 | home | same |
| xhard4 | 3 | 4 | yes | 2 | 1/1 | 6 | home | same |
Choices identical in all 21 files: a pick up the cube / b drop onto / c press the button. Success/failure predicates identical
(`is_obj_pickup` / `is_obj_dropped_onto(target_target)`; failures `is_any_obj_pickup(non_target_cubes)` / `is_obj_dropped_onto_any(targets_not_true)`).

## Verified OK
- Language color = answer cube color, and the cube moved in execution, in all 21 files (tracker + keyframes in `timelines/`).
- Answer target after the swap: execution drop pixel equals the demo pixel of the swapped partner whenever the answer target is in the swap pair (xhard3 ep0/ep6, xhard4 ep6), otherwise the original pixel.
- Home return: cubes end the demo within ~1–2 px of their start centroid (`cube_tracks.json`); home marker is not visible (`crop_x4e0_home_green.png`).
- xhard1/xhard2 delivered answers: per-cube first-after / only-before target == program answer, and the answer placement is temporally adjacent to the button.

## Findings
- **N1 (new_tier_only) extra-before target is always a demo "after" target in 2-cube tiers → same-target no-op re-placement.**
  `_load_scene_xhard_tail` candidates = targets − demo_before_targets{0,2} − target_target ⊆ {1,3} = demo_after_targets.
  When the owner is the cube whose after-target was drawn, its after-button "placement" lifts it off that target and puts it back (net 1–4 px):
  xhard3 ep0 green t3 steps 845–1002, xhard3 ep3 blue t3 879–1045, xhard3 ep6 blue t1 718–876, xhard4 ep0 blue t3 877–1030, xhard4 ep6 green t3 854–1023
  (`x3e0_noop_green_t3.png`, `x3e3_noop_blue_t3.png`, `x3e6_noop_blue_t1.png`, `x4e0_noop_blue_t3.png`, `x4e6_noop_green_t3.png`).
  Distinct target changes: xhard3 = 4/4/4 (nominal 5, same as xhard2), xhard4 = 5/6/5 (nominal 6). Plan §三/四.9 says the extra goes to an unrelated target with the native `additional_place` semantics (native uses target_2/target_3, never the answer's before/after targets). Same root as F6 (missing cross-button occupancy check) but the delivered, successful manifestation.
- **N2 (new_tier_only) "right/immediately before the button" wording vs 2-cube timeline.** In xhard4 ep0 (green, t0 @111–205) and xhard4 ep6 (blue, t0 @121–211) the other cube is placed twice (t2, t3) before the button (590 / 581). Templates 0/1 ("on the target right before…", "where it was placed immediately before…") are temporally false for the answer cube; template 3 ("last placed before") and the per-cube reading are correct. `x4e0_before_timeline.png`, `x4e6_before_timeline.png`. Native tiers have exactly one pre-button placement, immediately before the button.
- **N3 (new_tier_only, low) home-return subgoal never grounded.** Template `put the cube back to its original position at <>` (`_xhard_pick_place`) → all 18 home-return segments in the 12 files carry no coordinates (home site radius = cube half size, fully under the cube). Native "drop the cube onto table" has no `<>` by template.
- Seen / excluded: xhard3 ep3 & ep6 "last placed before" answer binding (records.json `per_cube_match=false`); F6 occupancy conflict (not present in delivered files).
