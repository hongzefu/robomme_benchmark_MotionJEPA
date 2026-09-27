[Internal artifact, English]

# MoveCube-04 独立验证

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (read via `git show`, working tree untouched).

## Source verification (git show AUDIT_BASE)
- `src/robomme/robomme_env/MoveCube.py::evaluate` has **no `self.difficulty` branch** anywhere in the
  task-list construction; the `if self.difficulty == "xhard4":` branches in `reset()` only touch
  bookkeeping flags (`self._peg_grasp_flipped`), not the evaluate/task-list logic. Confirms
  "evaluate has no difficulty branch" for native_behavior == new_tier_behavior.
- `peg_push` task "Hook the cube to the target with the peg": `func = is_obj_pushed_onto(..., must_gripper_open=True)`,
  `failure_func = lambda: None` (no manner check at all).
- `gripper_push` task "Close the gripper and push the cube to the target": same `func`;
  `failure_func` only checks `is_obj_pickup(cube)`, `is_obj_pickup(peg_tail)`, `is_obj_pickup(peg_head)`
  (catches "accidentally picked something up", nothing about gripper state during the push).
- `subgoal_evaluate_func.py::is_obj_pushed_onto`: `must_gripper_open` branch only checks
  `qpos[-2:] > 0.02` (both fingers "open" reading) at the instant `evaluate()` is called; no peg
  contact/force check, no history of gripper state during the push. Matches finding's native_behavior
  claim exactly.

## Independent data reproduction (fresh reads, not just consuming prior audit JSON)
- Wrote `tail_gripper.py` (adapted from prior audit's copy) and ran it against the **raw HDF5** for
  `xhard4_ep0` (`.../xhard4/rollout/run1/episodes/MoveCube_episode_0/hdf5_files/MoveCube_ep0_seed7400000.h5`)
  and `hard_ep3` (`.../v1/base/B/MoveCube_episode_3/hdf5_files/MoveCube_ep3_seed14300.h5`).
  - xhard4_ep0 exec "Close the gripper and push" segment: steps 273-279 gripper fully closed
    (`gs=[0.0,0.0]`, `is_gripper_close=True`, `joint_action=-1.0`); steps 280-281 gripper opens
    (`jointA=+1.0`, `gs` rises to 0.0252) exactly at `info/is_completed` flipping True at step 281.
  - hard_ep3 exec segment: identical pattern, closed 253-259, opens 260-261, `is_completed=True` at 261.
  - This reproduces the finding's cited frame ranges (xhard4 ep0 273-281, hard ep3 253-261) from raw
    bytes, independent of the prior audit's JSON.
- Wrote `verify_peg_grip.py`, re-derived segment boundaries for S2 xhard4 episode `MoveCube-xhard4-6100001`
  purely from `info/simple_subgoal` transitions (not copying the prior script's boundary list), and
  computed `is_gripper_close` fraction over the "Hook the cube..." segments myself:
  - demo hook (steps 145-241): grip-closed fraction = 0.958
  - exec hook (steps 426-537): grip-closed fraction = 1.0 (my range ends at 537; prior audit's JSON
    used range(426, n_steps=542) giving 0.966 — same conclusion, trivial range-boundary difference)
  - Matches (within rounding/range-boundary noise) the prior audit's `s2_pegpush_check.json` entries
    for 6100001/6100002/6100006 (0.954-0.968 demo, 0.964-0.966 exec).
- Read `gripper_state_by_segment.json` (prior audit artifact) for native peg_push episodes
  (easy_ep0, medium_ep2, medium_ep10, hard_ep7): "Hook the cube..." segment gripper-closed fraction
  is 0.95-1.0 for both demo and exec halves in every one — i.e. natives also perform the "closed
  gripper holding the peg" manner even though the predicate would accept picking the peg up,
  dropping it, and pushing with the bare hand.

## Duplicate check
Not listed in the excluded set (F1-F6, D1-D7, left/right, website-text). Concerns predicate/failure_func
manner-verification gap, unrelated to any excluded item.

## Category check
`evaluate()` code path is byte-identical across easy/medium/hard/xhard4 (no difficulty branch at all,
confirmed above) — this matches `native_same` exactly: the gap is present and behaves identically in
native tiers and is untouched (not newly introduced, not fixed) in xhard4. tiers_affected list
(easy/medium/hard/xhard4, no xhard1-3) is consistent with MoveCube's `require_xhard4_only` guard
restricting the new-tier branch to xhard4 only (no xhard1/2/3 variant of this env exists), so xhard1-3
are correctly absent from tiers_affected rather than omitted by oversight.

## Verdict
CONFIRMED. All claims (predicate weakness for "manner", failure_func coverage, absence of a
difficulty branch, and that delivered episodes happen to perform the stated manner anyway) are
reproduced independently from AUDIT_BASE source and from raw HDF5 bytes across native and new-tier
episodes. category=native_same is correct as filed; not a duplicate.

No new simulation needed — this is a low-severity latent policy-evaluation gap (a policy could exploit
it during evaluation rollouts, but no delivered demonstration/generation episode does), verifiable
entirely from AUDIT_BASE source plus already-delivered data.
