# Verification: crosscut-values-02

[Internal work product, English] AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (git rev-parse HEAD matched at task start; no other refs/diffs read).

## Independent evidence gathered (all via `git show <sha>:<path>` for source, and direct h5py reads for data)

1. **Source**: `src/robomme/robomme_env/utils/task_goal.py` VideoPlaceButton branch — confirmed 4-entry `language_goals` list:
   idx0 "right {before|after}", idx1 "immediately {before|after}", idx2 "previously placed {before|after}"
   (no ordinal qualifier), idx3 disambiguated ("last placed before" / "first placed after"). Matches finding's `source_anchors`.
2. **Config**: `crosscut-values/sampling_config.json` tasks.VideoPlaceButton.decision — xhard1={extra_place_before:0, extra_place_after:1}, xhard2={before:1, after:1}. Matches finding.
3. **Measured data** (`crosscut-values/measured.json`, `vp_identity.json`): re-derived programmatically — exactly xhard1 ep0/ep6 and xhard2 ep0/ep3/ep6 (5 episodes, all `goal_which=after`) have `goal_color_after=2` and `checks.goal_placement_unique_for_alt3=False`. No other after-side new-tier episode qualifies (xhard1 ep3 is a before-goal; xhard3 has extra_place_after=0; xhard4 ep3's after-owner is not the answer cube).
4. **Direct H5 read (independent of any audit script)**, `.../xhard1/.../VideoPlaceButton_ep0_seed9000000.h5`:
   - `setup/task_goal[2]` literal bytes = "watch the video carefully, then place the red cube on the target where it was previously placed after the button was pressed" — byte-identical to finding's `what_language_says`.
   - Re-scanned `info/is_subgoal_boundary` + `simple_subgoal` over all 1160 steps myself: t=210 press button; t=418 drop onto target; t=591 drop onto target; t=1057 "place the cube onto the correct target" (execution/grading phase).
   - `info/grounded_subgoal` gives coordinates: t=418 -> `<78,90>`, t=591 -> `<132,165>`, t=1057 (execution, the graded correct placement) -> `<78,90>`. This proves the two after-button placements land on two **physically different** platforms, and that the temporally-first one (t=418) is the one actually graded as correct — i.e., templates "right after"/"immediately after"/"first placed after" are well-defined, but "previously placed after" (idx2, no ordinal) cannot distinguish t=418 from t=591.
5. **Code logic** (`VideoPlaceButton.py`): extra-place candidate selection explicitly excludes `self.target_target` and the demo before/after target sets (`candidates = [... if idx not in occupied and target is not self.target_target]`), and task ordering places the canonical after-target placement *before* the extra-after placement — consistent with (4)'s finding that the graded target is the temporally-first one.
6. Cross-checked against the audit's own per-env `VideoPlaceButton/README.md`, which independently states "xhard1/xhard2 delivered answers: per-cube first-after / only-before target == program answer, and the answer placement is temporally adjacent to the button" — consistent with (4).

## Duplicate check
- **Not a duplicate of any item in the given EXCLUDED list** (F1-F6, D1-D7, left/right, website-text). In particular it is NOT F6 ("extra-place occupancy conflict", a target-candidate-selection topic) and NOT the excluded "VPB 'last placed before the button' answer binding (xhard3 ep3/6)" — that excluded item is a BEFORE-side, wrong-temporal-binding defect; this finding is an AFTER-side, ambiguous-wording issue where the binding itself is internally consistent (confirmed by (4) above).
- **However, this finding duplicates another candidate finding already produced and independently verified within this SAME audit round**: `crosscut-language/README.md` finding **L2** ("VPB 第 3 句备选语言...在新档不唯一", same 5 episodes, same mechanism), which was separately submitted for verification as `crosscut-language-02` and already has a `verify/crosscut-language-02/verify_summary.md` with **verdict CONFIRMED**, reaching the identical conclusion (same 5/12 episode set, same category=new_tier_only, same "not excluded" determination), including the same t=418/<78,90> vs t=591/<132,165> coordinate evidence for xhard1 ep0. This is not one of the task-supplied EXCLUDED items, so `duplicate_of_excluded=false` in the strict sense of that field, but the two findings (crosscut-values-02 and crosscut-language-02) should be merged/deduplicated before final reporting — they describe the exact same defect discovered by two different sweep scripts.

## Category check
`new_tier_only` is correct: `extra_place_before`/`extra_place_after` keys only exist in the xhard1-4 decision table; native tiers (easy/medium/hard) never place the same demo cube on two different after-button (or before-button) targets, so the ambiguity is structurally impossible in native tiers.

## Verdict
**CONFIRMED** — fully reproduced from AUDIT_BASE source and the referenced/independently-read HDF5 data. category=new_tier_only is correct. Not a duplicate of the given EXCLUDED list, but IS a duplicate of another already-confirmed finding (crosscut-language-02 / crosscut-language README L2) from the same audit corpus — recommend the user merge/dedupe these two before finalizing the report. No new simulation needed (all evidence already exists in delivered v6-01 episodes; ≤10-episode limit not implicated).
