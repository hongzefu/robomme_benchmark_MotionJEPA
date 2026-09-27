# VideoRepick-01 verification — CONFIRMED

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1

## Source reproduction (git show only)
- `src/robomme/robomme_env/VideoRepick.py::_initialize_episode`: the per-cycle pick/put
  `failure_func` calls `timewindow(..., min_steps=50, max_steps=500, timewindow_timer=2|3)`
  with a **fixed literal window**, identical for every cycle `i` in
  `for i in range(self.num_repeats)` — the loop index is not fed into the window bounds.
- `src/robomme/robomme_env/utils/subgoal_evaluate_func.py::timewindow`: "Counting starts
  from the first call" — `self._timewindow_timers[timewindow_timer]` is set once and never
  reset; because `timewindow_timer=2` (pick) and `=3` (put) are reused across all
  `num_repeats` cycles, the window is anchored to the very first pick/put of the episode,
  not to each cycle.
- `src/robomme/robomme_env/VideoRepick.py` `config_xhard4`: `num_repeats_low=5,
  num_repeats_high_exclusive=7` (5 or 6), vs native `NATIVE_SAMPLING.parameters.num_repeats`
  `low=1, high_exclusive=4` (1-3) used by easy/medium/hard.
- `0925-newtask-release-v6-plan.md` §三 VideoRepick row: xhard4 repick=[5,6] is explicitly
  planned, but the plan contains no mention of scaling the timewindow guard; nothing in the
  plan or code ties window width to `num_repeats`.
- `src/robomme/robomme_env/utils/object_generation.py::build_button`: `j.set_drive_target(0.0)`
  — spring-return revolute joint, corroborating "an early press is physically ignored, not a
  hard failure" (button just isn't held pressed).

## Independent data reproduction (own script, not copied from prior audit's JSON)
Script: `independent_check.py`, `native_check.py` in this dir. Read HDF5
`info/simple_subgoal_online` directly via h5py, no robomme/mani_skill import.

- xhard4 ep3 seed 6900300 (`.../VideoRepick_episode_3/hdf5_files/VideoRepick_ep3_seed6900300.h5`):
  first pick at step 816 → own script reproduces subgoal-boundary steps
  `816(pick1) 911(put1) 969(pick2) 1046(put2) 1102(pick3) 1178(put3) 1234(pick4) 1308(put4)
  1363(pick5) 1435(put5) 1490(pick6) 1563(put6) 1617(button)`.
  Pick-timer window = [816+50, 816+500] = [866, 1316]. Pick5 (1363) and pick6 (1490) start
  after 1316 → **unguarded**, matching the finding's claimed ranges exactly
  (pick5 1363-1434, pick6 1490-1562; put5 1435-1489, put6 1563-1616, computed the same way
  from the put timer window [911+50, 911+500]=[961,1411]). This exactly reproduces the
  prior audit's `timewindow_analysis.json` entry for xhard4/ep3 (145/467 pick steps,
  109/334 put steps unguarded) from raw data independently.
- Native tier check across all 9 delivered native episodes
  (`.../newtask-v6/v1/base/B/VideoRepick_episode_{0,1,2,3,4,6,7,10,11}`): reproduced
  subgoal-boundary timelines directly. Native `num_repeats` is 1-3 (matches
  `NATIVE_SAMPLING`), and for every episode except hard ep3 (seed 9301, `FailRecoverXY`),
  every pick/put lands inside its window (window widths [+50,+500] anchored at each task's
  own first pick/put). Native hard ep3: pick3 starts 598 inside window [264,714] but runs to
  811 (retry-lengthened) → steps 715-811 unguarded; put3 starts 812 inside window [385,835]
  but runs to 904 → steps 836-904 unguarded. This reproduces the finding's stated exception
  exactly ("pick 715-811, put 836-904 unguarded").
- xhard3 ep3 margin check: pick window [695,1145], last pick step ends at 1140 (5 steps of
  margin before the window closes) — matches the finding's claim that xhard1-3 stay inside
  only by a small margin, while xhard4 (more repeats → longer elapsed time) overflows it.

## Verdict
CONFIRMED. The fixed 50-500-step failure-detection window was calibrated against native
tiers' num_repeats∈{1,2,3} and was never widened when xhard tiers introduced num_repeats up
to 6 (xhard4) — a scaling mismatch not mentioned in the release plan. This is a genuine
native_vs_new_mismatch: in xhard3 native-equivalent load it already only barely survives
(5-step margin), and in xhard4 it structurally fails for the 5th/6th pick-put cycles in all
3 delivered episodes, meaning a premature button press during those late cycles is silently
ignored rather than flagged as a failure — differing from what the native tiers' (and the
task language's) semantics guarantee.

No new simulation is needed: the effect was reproduced from the 3 already-delivered xhard4
episodes (ep0/ep3/ep6, the only xhard4 successes in the corpus) and the 9 already-delivered
native episodes.
