# RouteStick — semantic vs visual / native vs new-tier audit

AUDIT_BASE = `82e3d922b78d48ec1e825b168cccc0e1b8c690c1` (source read only via `git show AUDIT_BASE:<path>`). Pure read-only audit; no simulation, no robomme import.

## Sources read (at AUDIT_BASE)
- `src/robomme/robomme_env/RouteStick.py` (config_easy/medium/hard/xhard1-4, `_load_scene`, `evaluate`, `direction_fail`, `step`, `_wrong_button_touch`, `_xhard_segment_count_range`)
- `utils/task_goal.py` (RouteStick branch), `utils/subgoal_language.py` (no RouteStick entry), `utils/subgoal_evaluate_func.py` (`is_obj_swing_onto`, `reset_check`), `utils/route.py::generate_dynamic_walk`, `utils/vqa_options.py::_options_routestick`
- `scripts/configs/newtask-v6/sampling_config.json` (tasks.RouteStick), `0925-newtask-release-v6-plan.md` (table row RouteStick, §四.8)

## Per-tier table (source)
| tier | L range | backtrack | language goal | subgoal/choice labels | predicates |
|---|---|---|---|---|---|
| easy | [2,3] | False | identical 2 strings, no parameters | 4 fixed labels: {left,right} x {clockwise,counterclockwise} | success: TCP xy <=0.03 m of target, z<0.15, avg-cross sign == expected dir; failure: touching other target (xy<=0.01, z<0.1) |
| medium | [4,5] | False | same | same | same |
| hard | [4,7] | True | same | same | same |
| xhard1 | [8,10] | True | same | same | same |
| xhard2 | [11,13] | True | same | same | same |
| xhard3 | [14,16] | True | same | same | same |
| xhard4 | [17,21] | True | same | same | same |
Only difference across tiers is L (read from `decision.<tier>.segment_count_range` for new tiers, frozen in spec header), exactly as plan §三 row and §四.8 state. Layout (1x9, rotation U(-30,30) deg, 4 random-RGB obstacles at odd slots), walk rule, direction threshold 0.5, highlight/trail parameters are shared.

## Data covered
- New tiers: all 12 delivered HDF5+mp4 (xhard1..4 x ep 0/3/6) from `new-tier-index.json`, plus spec lines in `artifacts/newtask-v6/v6-01/<tier>/specs.jsonl` and `spec_replay.json` (0 mismatches, 0 unused for all 12).
- Native: all 9 base/B RouteStick episodes (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11).
- 21 episodes, 486 segments (demo+exec), every frame's info fields.

## Checks and results (all 21 episodes)
- Language goal and `available_multi_choices`: 1 distinct value each across all 7 tiers.
- L within tier range (new: 10/9/10, 13/11/13, 16/14/15, 18/18/18; native 2/2/3, 4/5/4, 4/5/5); all 10 candidates per new tier also in range. Easy/medium: no non-endpoint backtrack; hard/xhard: backtracks present (allowed).
- Every segment exactly 50 frames; demo = exec = 50·L frames; total = 100·L (plan "RS 每段恒 50 帧" holds).
- Node sequence reconstructed from TCP xy at segment ends (theta fit; new tiers use spec rotation, fit agrees within 0.2 deg; max node error <=3 mm): demo nodes == exec nodes == spec `actions.nodes` (new tiers); label direction == spec `actions.directions`.
- Label side vs geometry and label direction vs world TCP trajectory (same avg-cross formula as `direction_fail`): all OK.
- Visual (front_rgb, projected with stored intrinsic/extrinsic): at every segment end frame the red highlight is on the expected target and on no other even target (min red fraction 0.22); rotation sense of projected path on screen (chord at TCP height) matches the label clockwise/counterclockwise in 486/486 segments. "left" in labels = image-right (robot frame; excluded topic, recorded only).
- `choice_action` letter per segment == label a-d mapping: 0 mismatches.
- Exec starts at demo start pose (<0.5 mm); last frame is_completed=True; TCP z 0.069-0.070 throughout.
- mp4 frame counts == HDF5 frame counts (1280x768 composite, 30 fps).

Evidence: `records.json` (per-episode facts), `records_raw.json` (per-segment), `visual_checks.json`, `subgoal_runs.json`, `frames/*.png` (segment-end montages with projected path/targets; `probe_*` raw mp4 frames). Scripts: `rs_extract.py`, `rs_visual.py`, `rs_online.py`, `rs_inspect.py`.

## Findings
- **RS-N1 (native_same, low)**: in every episode (all 7 tiers) the last 6 demo frames (e.g. xhard1 ep0 frames 494-499, easy ep0 94-99, xhard4 ep6 894-899) have `info/simple_subgoal_online` = `info/grounded_subgoal_online` = `"NO RECORD"` — the internal name of the unrecorded "place the stick into the tube" task leaks into the online subgoal field (visible in the mp4 overlay, `frames/probe_xhard1_ep0_mp4_f0499.png`). Source: `RouteStick::_load_scene` tasks list (name "NO RECORD" after the demo swing tasks). Identical across tiers.
- No new-tier-only or native-vs-new mismatch found: new tiers differ from native only in L, as the plan specifies.

## Not checked
Evaluation-time behaviour (VQA option execution, `_wrong_button_touch` trips, 1301-step budget truncation) — no rollouts run. Wrist/segmentation views not analysed. Obstacle colour visibility not assessed (language makes no colour claim). Only 3 delivered episodes per new tier.
