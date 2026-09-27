# SwingXtimes — semantic vs visual / native vs new-tier audit (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Pure read-only audit. Source read only via `git show 82e3d92:<path>`; data read with h5py/numpy/cv2 only
(scripts in this dir: `h5_keys.py`, `extract.py`, `seqcheck.py`, `identity.py`, `frames.py`). No simulation.

## Source facts (82e3d92)
| tier | rounds (`configs`/`number_range`) | colored cubes (`color`) | distractors (`decision.<tier>.distractor.colors`) |
|---|---|---|---|
| easy | [1,3] | 1 | none |
| medium | [1,2] | 3 | none |
| hard | [3,3] | 3 | none |
| xhard1 | [4,5] | 3 | yellow |
| xhard2 | [6,7] | 3 | yellow, cyan |
| xhard3 | [8,9] | 3 | yellow, cyan, magenta |
| xhard4 | [10,11] | 3 | yellow, cyan, magenta |

Matches plan 0925 §三 row SwingXtimes (hard 3/0, xhard1 [4,5]/1, xhard2 [6,7]/2, xhard3 [8,9]/3, xhard4 [10,11]/3).
Language (`task_goal.py`, env SwingXtimes): repeats>1 → two templates ("...back-and-forth motion {num2words[N]} times, finally press
the button to stop" / "...right-to-left swing motion N times, then put down the cube and press the button to stop");
repeats==1 → "put it down on the left-side target" templates (native easy/medium only).
Task chain (`SwingXtimes.py::_load_scene`): pick → N×(right, left) `is_obj_swing_onto(distance 0.03, z 0.12)` → `is_obj_dropped`
→ `is_button_pressed`; failure = pick non-target (incl. distractors in xhard, rebuilt at end of `_spawn_distractors_xhard`),
button pressed early, `too_many_swings` (max_swings = 2N). Predicates/thresholds identical across all 7 tiers.
Subgoal ordinal: `ordinals` list stops at "tenth"; `i>=10` falls back to `f"{i+1}th"`.
VQA (`vqa_options.py::_options_swingxtimes`): a pick (available all_cubes, incl. distractors), b move to top of target, c put on table, d press button — same for all tiers.

## Coverage
- New tier: all 12 delivered HDF5 + mp4 (xhard1..4 × ep 0/3/6).
- Native: all 9 HDF5 + mp4 in `newtask-v6/v1/base/B/SwingXtimes_episode_{0,1,2,3,4,6,7,10,11}` (easy 0/1/4, medium 2/6/10, hard 3/7/11).
- Per episode (`records.json`): goal text & count word, target colour, full subgoal chain (simple + grounded, planner + online),
  equality with source-derived expected chain (21/21 equal), collapsed choice letters (A,B,C,D in all 21), frame-0 colour blob census
  (xhard1 +yellow, xhard2 +yellow+cyan, xhard3/4 +yellow+cyan+magenta, native none; easy only the target cube),
  grounded pick coordinate vs target-colour blob (≤1.2 px, nearest blob is always the goal colour),
  displacement frame0→last of every blob (only the goal colour moves; distractors/non-targets 0.0–0.2 px),
  target-colour blob at the last frame of every swing segment vs that segment's grounded disk (20.4–26.6 px, i.e. held above the named disk;
  disks are ≥100 px apart), N right + N left segments with N = goal word in 21/21.
- Key frames with annotation: `frames/` (xhard1/2/3/4 ep0, xhard4 ep6, easy ep0, medium ep2, hard ep3; frame0, first two swing ends, last swing end, 11th-round frames, last frame).

## Findings
1. **new_tier_only — "11th" ordinal in xhard4 subgoals** (`SwingXtimes.py::_load_scene`, `ordinals` list + `f"{i+1}th"` fallback).
   xhard4 ep0 (`SwingXtimes_ep0_seed6300000.h5`, frames 1000–1088) and ep6 (`seed6300600`) print
   "move to the top of the right/left-side target for the 11th time" (also in grounded/online subgoal and video overlay,
   `frames/xhard4_ep0_f1005.png`, `f1049.png`), while rounds 1–10 use words ("tenth") and the goal says "eleven times";
   `task_goal.py::num2words_2` already has "eleventh". Native tiers never exceed 3 rounds, xhard1–3 never exceed 9, so this only appears in xhard4; plan §三/四.7 do not mention it. Cosmetic/format inconsistency, low severity.
2. **native_same — goal template 0 omits the required put-down step.** Template 0 (also the mp4 filename) says
   "... repeating ... N times, finally press the button to stop", but every chain (21/21) contains
   "put the <c> cube on the table" before "press the button", and that put-down task's `failure_func` includes
   `is_button_pressed` — pressing the button while still holding the cube (literal reading of template 0) is a failure.
   Template 1 does mention "put down the cube". Identical in native hard/medium/easy (N>1) and all xhard tiers.

## Checked, no issue
Counts (goal word = number of right/left pairs, 21/21), colour identity, target-cube identity, alternating right→left order,
terminal put-down + button press, distractor count/colours per tier, distractors never moved, choice letters/labels,
tier/seed attributes. Two extra 1-frame `success_NO_OBJECT_*` mp4 files (native hard ep7, xhard4 ep6) are recorder
artefacts, not semantics. `grounded_subgoal_online` occasionally lacks `<>` coordinates (native medium ep6, hard ep3; xhard2 ep6) — same pattern in both, occlusion-related, not re-reported.

## Seen but excluded
D2 (left/right robot frame). Native-only (not new-tier): N==1 template "put it down on the left-side target" (medium ep2) — chain
only requires hover over left disk + `is_obj_dropped` anywhere; video shows the cube put down next to the left disk, so no visible mismatch.
Source comment on `config_xhard4` says "摆动轮数 [4,10]" but value is [10,11] (plan agrees with value) — stale comment only.

## Not checked
No actor poses in HDF5 → contact/grasp continuity only inferred from pixels; `too_many_swings` failure path and recovery (FailRecover) variants not exercised; only 12 new-tier episodes exist (not all 30 candidates).
