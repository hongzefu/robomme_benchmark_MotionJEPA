# PatternLock audit — semantic vs visual, native vs new tiers (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

[内部产出，英文] Workflow-internal English record; the consuming main agent must still talk to the user in Simplified Chinese.

## Method
- Source read only via `git show 82e3d92:<path>`: `src/robomme/robomme_env/PatternLock.py`, `utils/task_goal.py` (PatternLock branch), `utils/subgoal_evaluate_func.py::{is_obj_swing_onto,direction}`, `utils/adjacent.py::find_path_0_to_8`, `utils/vqa_options.py::_options_patternlock`, `scripts/configs/newtask-v6/sampling_config.json` (tasks.PatternLock), plan `0925-newtask-release-v6-plan.md` §三 table row + §四.8. `utils/subgoal_language.py` has no PatternLock entry (labels come from `PatternLock._load_scene` task list `"move {direction(...)}"`).
- Data: all 12 delivered new-tier HDF5+mp4 (xhard1..4 × ep0/3/6) and all 9 native HDF5+mp4 (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11) from `artifacts/newtask-v6/v1/base/B/`. Also `artifacts/newtask-v6/v6-01/<tier>/specs.jsonl` PatternLock spec rows (10 candidates per tier) for node counts / path_attempts.
- Scripts (h5py/numpy/cv2 only): `pl_extract.py` (per-step eef, subgoal labels, boundaries, choice_action; node contacts reproduce `is_obj_swing_onto` horizontal<=0.01 & z<0.1 on the known grid geometry `center(-0.1,0)+(idx-(n-1)/2)*0.1`), `pl_visual.py` (projects grid nodes with the stored front camera intrinsic/extrinsic and checks the red highlight disk is present at the contacted node in `front_rgb` 4 frames after each contact and that no non-recent node is lit), `pl_annotate.py` (PNG per episode), `pl_mp4meta.py` (mp4 frame count == HDF5 steps).

## Per-tier table (source @ 82e3d92)
| tier | grid | path_length_range | search budget | exhaustion | language goal | subgoal/choice labels | success |
|---|---|---|---|---|---|---|---|
| easy | 3 | [2,4] | 1000 (native.path_selection.max_attempts) | silent last path | "watch the video carefully, then use the stick attached to the robot to retrace the same pattern" (+ "... shown in the video") | `move <8-dir>`; 8 fixed options a..h | exec chain of swing-onto in order + `match` (last len(path) achieved == path), `_wrong_button_touch` failure |
| medium | 4 | [3,5] | 1000 | silent | same | same | same |
| hard | 5 | [4,8] | 1000 | silent | same | same | same |
| xhard1 | 5 | [9,12] | 20000 (decision.xhard1) | real SceneGenerationError | same | same | same (+ `_check_xhard_path`) |
| xhard2 | 5 | [13,16] | 20000 | raise | same | same | same |
| xhard3 | 5 | [17,20] | 20000 | raise | same | same | same |
| xhard4 | 5 | [21,25] | 20000 | raise | same | same | same |
sampling_config.json values are identical to source. Plan §三: PatternLock [4,8]/[9,12]/[13,16]/[17,20]/[21,25], exec ≤ ~850 steps — matches.

## Results (records.json)
| tier | ep | N nodes | demo/exec frames | checks |
|---|---|---|---|---|
| xhard1 | 0/3/6 | 11/10/12 | 356/333/377 | all pass |
| xhard2 | 0/3/6 | 14/14/16 | 430/470/528 | all pass |
| xhard3 | 0/3/6 | 17/17/17 | 571/518/549 | all pass |
| xhard4 | 0/3/6 | 21/21/23 | 680/679/762 | all pass |
| easy | 0/1/4 | 3/3/2 | 48/63/33 | all pass |
| medium | 2/6/10 | 5/3/4 | 130/82/108 | all pass |
| hard | 3/7/11 | 5/6/5 | 153/179/137 | all pass |

"All pass" = node count in tier range; no revisit; consecutive nodes 8-adjacent; exec node sequence == demo node sequence == spec `actions.path_nodes`; every demo & exec `simple_subgoal` equals `direction()` recomputed from node geometry; every `choice_action` letter maps to the same label in `available_multi_choices`; `setup/difficulty` == tier; mp4 frames == HDF5 steps; red highlight visually present at every contacted node (458 contacts: 386 new-tier + 72 native, 0 anomalies, `visual_highlight_check.json`); final segment `All tasks completed` with `is_completed=True`. Exec max 762 steps (< plan ~850, < eval 1300).

Spec candidate node counts (10 per tier): xhard1 {9:1,10:1,11:2,12:6}; xhard2 {14:3,15:2,16:5}; xhard3 {17:6,18:1,19:2,20:1}; xhard4 {21:6,22:2,23:2} (never 24/25). Mean path_attempts xhard1 4.6, xhard2 4.2, xhard3 4.1 (plan: ≤5.3), xhard4 27.5.

## Findings
- PL-1 (low, new_tier_only, source description): `PatternLock.config_xhard4` comment and `XHARD_DECISION` comment still describe V5 "node count fixed 25 / [25,25] / 25-node hit rate 1.000", but value is [21,25] (V6 plan) and delivered xhard4 are 21/21/23 nodes; 0/10 candidates reach 24–25 because the search stops at the first in-range path. Not a data error (values within plan); stale code documentation and an effective range narrower than the nominal one.
- Seen-excluded: D4 (PatternLock budget text). No left/right issue reported (robot frame by decision).
- No semantic-vs-visual mismatch found in any tier.

## Evidence
- `records.json`, `visual_highlight_check.json`, `frames/*_path_and_exec_contacts.png` (top: path overlay on last demo contact frame with node ids, magenta = start; bottom: exec contact frames with expected node circled + label), `frames/raw_xhard1_ep0_f23.png` / `f400.png` (mp4 composite with overlay text).

## Not checked
- Wrist-camera frames were not pixel-checked (front camera only); arm occlusion of far rows in xhard4 front view was only eyeballed (touched node still visible in all contacts).
- Undelivered candidates (7 per tier) only via spec node counts, not via HDF5.
- No simulation; failure predicates (`_wrong_button_touch`, `match` false path) only read in source — no failing rollout exists in delivered data.
