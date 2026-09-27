# crosscut-values-03 verification verdict

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1

## Verdict: CONFIRMED (high confidence)

## Independent evidence reproduced by this verification pass

1. Source code (git show, not working tree):
   - `src/robomme/robomme_env/SwingXtimes.py::_load_scene` (grep hit at the
     `ordinals = [...]` / `ordinal = ordinals[i] if i < len(ordinals) else f"{i+1}th"`
     lines): local hardcoded list of only 10 words (first..tenth), naive numeric
     fallback for index >= 10.
   - `src/robomme/robomme_env/utils/subgoal_language.py::_ordinal_word` /
     `_ORDINALS`: shared utility with a 20-word list (first..twentieth) plus a
     proper "11th/12th/13th/21st..." suffix fallback only past index 20.
   - `src/robomme/robomme_env/PickXtimes.py`: imports and calls
     `subgoal_language.get_subgoal_with_index(i, ...)` for its per-repeat
     subgoal text, i.e. PickXtimes reuses the correct shared ordinal utility;
     SwingXtimes does not import `subgoal_language` at all and keeps its own
     stunted local list.
   - `SwingXtimes.configs["xhard4"] = {'number_min': 10, 'number_max': 11}` vs
     hard/easy/medium all capped at number_max<=3. Confirmed against
     `0925-newtask-release-v6-plan.md` line 66 / lines 224-231: the [10,11]
     xhard4 swing-count range is deliberately planned, but the plan text does
     not mention or authorize the ordinal-word-vs-numeric-fallback side effect.

2. Data evidence, reproduced independently by THIS verification (not reused
   from the audit's precomputed scan_raw.json) by opening the raw HDF5 file
   directly with h5py:
   - File: `artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/SwingXtimes_episode_0/hdf5_files/SwingXtimes_ep0_seed6300000.h5`
   - `episode_0/setup/task_goal[0]` = "...repeating this back-and-forth motion
     **eleven** times..." (word form in the goal sentence).
   - Walking `episode_0/timestep_*/info/simple_subgoal` boundary-by-boundary
     (26 unique subgoal segments) shows subgoal 1..10 use word ordinals
     (first..tenth) and subgoal 11 (timesteps 1000 and 1044) uses the numeric
     fallback "11th" — exactly the finding's claim, reproduced from the raw
     per-step HDF5 field, independent of the audit's own scan output.
   - Cross-checked against `scan_raw.json` entries [93] (ep0, 11 swings,
     "eleven"/"11th") and [95] (ep6, 11 swings, same pattern) and [94] (ep3,
     10 swings, "ten"/"tenth" — stays within the 10-word list, so no fallback
     fires). Also checked the `choices` arrays in scan_raw.json[93]/[95]:
     22 "B" (move-to-target) actions = 11 right/left pairs, matching the
     stated swing count and the goal-text "eleven times" (this substitutes
     for a full video frame count and is sufficient corroboration of "video
     shows 11 pairs", so no video decoding was needed).

## Category check

- `new_tier_only` is correct: number_range only reaches >=11 in xhard4
  (`number_min/max = [10,11]`); native hard/easy/medium cap at number_max<=3,
  so index never exceeds 2 and the local 10-word list never overflows in any
  native tier. This bug structurally cannot occur outside the new xhard4
  mechanic (extended number_range). Not `native_same` (native never hits it)
  and not really a "native_vs_new_mismatch" in the strict sense used for
  other findings (native tiers have no equivalent text at all to diverge
  from) — `new_tier_only` is the best fit of the three given categories.

## Duplicate check against excluded list

Not a duplicate of any of F1-F6, D1-D7, VPB-answer-binding, left/right-frame
issues, or website-text-only issues. This is a task-language generation bug
in `SwingXtimes.py` present in the delivered simulation data (HDF5 + goal
text + mp4 filename), not a website rendering issue.

## needs_new_simulation

false — the delivered artifacts (ep0, ep3, ep6 of SwingXtimes xhard4) already
contain full before/after evidence (10-swing "tenth" vs 11-swing "11th"); no
additional simulation is needed to confirm or further characterize this bug.
