# Verification: crosscut-language-02

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (verified via `git rev-parse HEAD` at start of task).

## Method
1. Read source at AUDIT_BASE only (`git show <sha>:<path>`), never working tree:
   - `src/robomme/robomme_env/utils/task_goal.py` VideoPlaceButton branch — confirmed 4 language_goals
     entries; index [2] = "...where it was previously placed {before|after} the button was pressed"
     (no ordinal qualifier), index [3] disambiguates only for the side matching
     `target_target_language` ("last placed before" / "first placed after").
   - `src/robomme/robomme_env/VideoPlaceButton.py` V6_DEMO_DECISIONS table — confirmed
     xhard1={demo=1, before=0, after=1}, xhard2={demo=1, before=1, after=1},
     xhard3={demo=2, before=1, after=0}, xhard4={demo=2, before=1, after=1}.
   - `_extra_place_owners`: when demo_count==1 (xhard1/xhard2), owner is forced to index 0 for every
     extra-place side, i.e. always the sole demo cube (also always the answer cube since
     `answer_index = randint(0, demo_count)` = 0 when demo_count==1).
   - `_load_scene_xhard_tail`: task order is
     before-placements → extra-before → button → after-placements(demo_after_targets) → extra-after → home.
     `target_target` (the graded answer) = `demo_after_targets[answer_index]` for after-questions,
     i.e. the placement that happens BEFORE the extra-after placement in time (= "first placed after").
2. Independently re-derived, from raw `specs.jsonl` records (not copying the audit's own script logic
   blindly — recomputed side-aware owner mapping myself first, caught my own initial mistake of
   ignoring before/after side alignment of `extra_place_owner_ids`, then corrected), which of the 12
   delivered VPB xhard1-4 episodes satisfy: question_side==after AND extra_place_after present AND
   after-side owner == answer_demo_index. Result: exactly
   **xhard1 ep0, xhard1 ep6, xhard2 ep0, xhard2 ep3, xhard2 ep6** (5 episodes) — matches the finding's
   claimed "5/12" set exactly. xhard3 never has extra_after (config after=0). xhard4 ep3 has
   after-side owner belonging to the *other* demo cube (not the answer), so it is NOT ambiguous
   (contra a naive owner-set-membership check, which is why the side-aware recomputation matters).
   This matches the pre-existing audit script's own output in
   `../../crosscut-language/vpb_alt_ambiguity.json` (cross-check, not sole evidence).
3. Opened the actual delivered artifacts for xhard1 ep0 (seed 9000000) directly with h5py:
   - `.../xhard1/specs.jsonl`: task_flag=false (after), answer_demo_index=0, extra_place_owner_ids=[0],
     extra_place_target_ids.after={"0":2}, target_target_id=1. Matches finding's specs.jsonl claim.
   - `.../hdf5_files/VideoPlaceButton_ep0_seed9000000.h5`, `episode_0/setup/task_goal`:
     index [2] literal text = "watch the video carefully, then place the red cube on the target where
     it was previously placed after the button was pressed" — byte-for-byte matches finding's
     `what_language_says`.
   - Subgoal-boundary scan (`info/is_subgoal_boundary`) over all 1160 timesteps reproduces the
     finding's claimed event sequence almost exactly: t=104 drop (before-target, no coord in text),
     t=210 press button, t=308 pick, **t=418 drop onto target at <78,90>** (first after-placement =
     demo_after_targets[0] = target_target, matches target_target_id=1's target coords), t=517 pick,
     **t=591 drop onto target at <132,165>** (second/extra after-placement, at target index 2, matches
     extra_place_target_ids.after=2), t=687 pick, t=756 return home, t=953 pick (execution phase),
     **t=1057 place onto the correct target at <78,90>** (execution matches the FIRST after-placement,
     confirming the code's "first placed after" binding is internally consistent — it is only the
     3rd-variant wording that fails to say "first").
   - One inaccuracy found in the finding's narrative: it states "red cube dropped at <80,153> (t104)";
     the actual data at t=104 has grounded_subgoal text with **no coordinate** ("drop the cube onto
     target"), and <76,153> (not <80,153>) is the *pick* coordinate at t=308, not a t=104 drop
     coordinate. This looks like a minor transcription slip in the finding (likely mixed up a
     manually-read frame-space coordinate with the pick event), not a defect in the core claim, and
     does not affect the substantive conclusion (T1=<78,90>@418, T2=<132,165>@591, exec=<78,90>@1057
     all check out exactly).

## Duplicate check against excluded list
- Not F6 ("VideoPlaceButton extra-place occupancy conflict" — a different topic, about target
  candidate selection avoiding already-occupied targets, not about language-template ambiguity).
- Not the excluded "VPB 'last placed before the button' answer binding (xhard3 ep3/6)" item: that
  excluded issue is about the BEFORE-side 4th variant ("last placed before") potentially binding to
  the wrong (temporally-last) placement when the extra-before owner equals the answer cube — a
  binding-correctness issue on the before side. This finding is about the AFTER-side 3rd variant
  ("previously placed after", no ordinal) being ambiguous between two correct-by-construction
  after-placements — a phrasing-ambiguity issue on the after side, with the binding itself (to the
  first after-placement) being internally consistent. Different side, different mechanism (ambiguous
  wording vs. wrong temporal binding). The audit's own `vpb_alt_ambiguity.py` script explicitly
  tags before-side ambiguous rows with note "before 侧属已排除的 VPB last-placed-before 绑定问题" and
  excludes them from what it reports — consistent with treating them as separate/already-known.
- No other excluded item concerns VideoPlaceButton language templates.

## Category check
"new_tier_only" is correct: `extra_place_before`/`extra_place_after` only exist in
`V6_DEMO_DECISIONS` (xhard1-4); native tiers (easy/medium/hard) use `demo_object_count=1`,
`additional_place` (a different, boolean flag unrelated to the extra-place-owner mechanism) and have
no equivalent of a demo cube being placed on two different after-button targets. The ambiguity cannot
occur in native tiers by construction.

## Verdict
CONFIRMED — independently reproduced from AUDIT_BASE source and the referenced specs.jsonl/H5 data,
including catching and correcting an error in my own first-pass reproduction, which increases
confidence that the 5/12 count is exactly right (not just copied from the pre-existing audit script).
One minor, non-substantive numeric inaccuracy noted in the finding's frame-coordinate transcription
(<80,153> vs actual <76,153> pick coordinate at t=308; no drop coordinate exists at t=104).
category=new_tier_only confirmed correct. Not a duplicate of any excluded item.
No new simulation needed — all evidence exists in already-delivered v6-01 episodes.
