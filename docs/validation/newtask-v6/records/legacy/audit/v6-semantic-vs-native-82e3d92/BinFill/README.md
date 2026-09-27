# BinFill audit — semantic vs visual, native (easy/medium/hard) vs new tiers (xhard1-4)

AUDIT_BASE = `82e3d922b78d48ec1e825b168cccc0e1b8c690c1`. Source read only via `git show AUDIT_BASE:<path>`.
Pure read-only: h5py / numpy / cv2 / json on delivered HDF5 + mp4; no robomme import, no simulation, no generation.
All helper scripts and outputs live in this directory.

## Coverage

* Source: `src/robomme/robomme_env/BinFill.py` (configs, `_load_scene`, `_spawn_cubes_xhard`, `_initialize_episode`, `evaluate`, `step`),
  `utils/task_goal.py::get_language_goal` (BinFill branch), `utils/subgoal_language.py`, `utils/subgoal_evaluate_func.py`
  (`is_any_obj_pickup_flag_currentpickup`, `is_obj_pickup`, `is_any_obj_dropped_onto_delete`, `is_obj_dropped_onto(_delete)`,
  `is_obj_dropped`, `is_button_pressed`, `check_in_bin_number`), `utils/vqa_options.py::_options_binfill`,
  `utils/statechange.py::lift_and_drop_objects_back_to_original`, `utils/segmentation_utils.py::process_segmentation`,
  `env_record_wrapper/DemonstrationWrapper.py::_compute_segmentation_and_fill_subgoal`, `RecordWrapper.py` (online grounded path),
  `scripts/configs/newtask-v6/sampling_config.json` (`tasks.BinFill`), plan `0925-newtask-release-v6-plan.md` (D10, table row BinFill, §7, §269).
* Data: all 12 delivered new-tier HDF5 (xhard1..4 × ep0/3/6) + their `rng_trace.json`; all 9 native HDF5 under
  `artifacts/newtask-v6/v1/base/B/BinFill_episode_*` (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11). Every timestep read.
  mp4 composite spot-checked (xhard4 ep0 frames 500/1747).

## Per-tier table (from source + sampling_config)

| tier | colors spawned | spawn total | put_in_color | put_in total | layout | color_mix | language template | chain |
|---|---|---|---|---|---|---|---|---|
| easy | 1 | [4,6] | [1,1] | [1,3] | native_dynamic (randint → dynamic True/False) | – | `put <n color cube(s)> ... into the bin, then press the button to stop` (+ALT "and press") ; colors listed in fixed red,blue,green order | per color in `color_order` (randperm): N×(pick up the {ordinal} {color} cube → put it into the bin) → press the button |
| medium | 2 | [8,10] | [1,2] | [2,4] | same | – | same | same |
| hard | 3 | [10,12] | [2,3] | [3,5] | same | – | same | same |
| xhard1 | 3 | 12 | [2,3] | 6 | clutter (dynamic False, D6) | max_component 3, link 0.09 m, 64 redraws | same | same |
| xhard2 | 3 | 12 | [2,3] | 7 | clutter | same | same | same |
| xhard3 | 3 | 12 | [2,3] | 8 | clutter | same | same | same |
| xhard4 | 3 | 12 | [2,3] | 9 | clutter | same | same | same |

Predicates identical across tiers: pick = any cube in `all_cubes` lifted z>0.05 and grasped (color NOT checked);
put = any cube within 0.05 m XY of board and dropped (z≤0.2, not grasped, tcp z>0.05) → teleported to [10,10,0] and per-color counter++ (F5, excluded);
press = button depth>0.005; failure at press stage = per-color in-bin count ≠ target, or any further drop; pick/put failure = button pressed early.
Choice labels a/b/c identical (`setup/available_multi_choices`). No video-demo segment in any tier (is_video_demo = 0 steps everywhere).

## Checks and results (records.json, cube_projection_check.json, ordinal_appearance.json, nocoord_scan.json)

1. Language counts vs target_numbers (rng_trace) vs chain: 12/12 new + 9/9 native match exactly; ordinals contiguous per color (first..seventh).
2. Grounded pick point color (front_rgb at `<row,col>` of `grounded_subgoal_online`, segment start frame): 88/88 new-tier picks that carry coordinates (90 picks total; 2 lack coordinates, see N1) and 26/26 native picks land on a cube of the named color. (Coordinate convention verified: `<row, col>`.)
3. Put-into-bin identity: for every put segment the color whose pixels vanish above the hole (depth back-projection, board center from rng_trace or grounded point) equals the color named in the preceding pick subgoal: 90/90 new, 26/26 native.
4. Spawn counts: each rng_trace cube projected into t0 front frame shows its own color 12/12 in all 12 new episodes; remaining cubes at their original positions on the last frame equal spawn−target per color in 12/12 episodes.
5. Same-color cluster bound (plan: ≤3): recomputed from traced positions, max component 1–3, no fallback, in all 12.
6. Episode lengths: new 1140–1748 steps (xhard2 ep3 = 1306, xhard3 1403–1550, xhard4 1591–1748) > eval `max_steps=1300`; covered by plan D10 / row BinFill ("允许超 1301") → not reported.
7. Native dynamic vs xhard static: native 6/9 episodes are dynamic (k-th same-color cube appears at step 50·(k−1)); xhard all static (plan D6) → not reported as divergence.

## Findings (all native_same; nothing new-tier-only found)

* **N1 `grounded_subgoal_online` has no coordinates for a whole segment when the target is occluded at the switch frame.**
  `segmentation_utils::process_segmentation` only recomputes centers when `current_subgoal_segment != previous_subgoal_segment`; if the target has no visible pixels on that one frame the text falls back to `current_task_name` for the entire segment, while the offline `grounded_subgoal` has coordinates.
  Evidence: xhard3 ep0 t698–827 "pick up the fifth blue cube" (offline `<65, 135>`), xhard3 ep3 t1344–1478 "press the button" (offline `<62, 164>`), xhard4 ep0 t498–632 "pick up the fourth blue cube" (offline `<63, 161>`); switch frames show the arm covering the target: `nocoord_*.png`, mp4 frame `frames/mp4_xhard4_ep0_f500.png` (ONLINE row empty target panel). 3/192 new-tier segments, 0/61 native segments in this sample; mechanism is the frozen native recorder.
* **N2 Ordinal in "pick up the {k-th} {color} cube" has no visual referent in static layouts.** k is the index in the per-color actor list (xhard: slot order after color_mix). In native dynamic episodes the k-th cube appears at step 50(k−1) (`ordinal_appearance.json`: easy0, medium2/6/10, hard7/11), so "second/third" is observable; in native static episodes (easy1/4, hard3) and in every xhard episode all cubes are present at t0 and the ordinal is arbitrary (ordinals up to "seventh" in xhard4 ep0). Only the grounded coordinate disambiguates (and see N1 when it is missing).
* **N3 Pick predicate is color- and identity-agnostic.** `is_any_obj_pickup_flag_currentpickup(objects=self.all_cubes)` accepts any cube although the subgoal names a color+ordinal; wrong-color picks/drops are only caught at the button stage via `check_in_bin_number`. No delivered episode exhibits a wrong pick (checks 2–3 all pass), so this is a predicate-level gap, identical in all tiers.

Excluded/seen: F5 (mid-air deletion above the hole, z≈0.17–0.21) — observed again in the drop pixel sequences, not re-reported.

## Files

* `records.json` — per-episode facts (goal, segments with start/end/simple/grounded/offline, boundaries with choice_action, grounded color checks, drop pixel sequences, blob counts, rng_trace subset).
* `cube_projection_check.json`, `ordinal_appearance.json`, `nocoord_scan.json`.
* `frames/<kind>_<tier>_ep<n>_picks_t0_last.png` — t0 with every grounded target labelled, last frame, and each pick-segment start frame with target circled (nearest-neighbour ×3).
* `nocoord_xhard3_ep0_t698_fifth_blue.png`, `nocoord_xhard3_ep3_t1344_button.png`, `nocoord_xhard4_ep0_t498_fourth_blue.png` — front|wrist at the switch frame, circle = offline coordinate.
* Scripts: `extract.py`, `summarize.py`, `cube_projection_check.py`, `native_dynamic_ordinal.py`, `nocoord_scan.py`, `offline_check.py`, `make_frames.py`, `peek.py`, `mp4_frame.py`, `h5_layout_dump.py`.

Rerun: `cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask && UV_CACHE_DIR=$PWD/artifacts/cache/uv uv run --no-sync python artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/extract.py` (then the others).
