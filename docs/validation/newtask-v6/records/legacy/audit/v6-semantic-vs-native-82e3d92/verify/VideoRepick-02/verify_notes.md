[internal, English] Adversarial verification of finding VideoRepick-02.
AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1

## Mechanism trace (source, read via `git show AUDIT_BASE:...`)
- `src/robomme/robomme_env/VideoRepick.py::_plan_swaps_newvalue_v6` calls
  `swap_uniform.plan_balanced_swaps(..., forbid_undo=True)` and later
  `swap_uniform.verify_swap_sequence(graph, pairs, forbid_undo=True)`.
- `src/robomme/robomme_env/utils/swap_uniform.py::_greedy_once`:
  `cands = [e for e in edges if not (forbid_undo and e == last)]` where `last`
  is only the SLOT PAIR of the immediately preceding swap. `verify_swap_sequence`
  likewise only flags `key == last` (previous step). Neither function tracks
  any object's slot history beyond one step back, so a 3+ step cycle that nets
  to identity (e.g. swap(1,4), swap(2,3), swap(3,0), swap(1,4) again) is legal:
  by the time slot pair (1,4) recurs at step k3, `last` = (0,2) from k2, so the
  immediate-undo check does not fire.
- Confirmed by hand-simulating xhard2 ep3 (seed 10900301) swap_pairs from
  `artifacts/newtask-v6/v6-01/xhard2/specs.jsonl`:
  k0 swap(1,4), k1 swap(2,3), k2 swap(3,0), k3 swap(1,4), k4 swap(0,2), k5 swap(2,3).
  Tracking slot_of[] exactly as `_greedy_once` does: object 1 (the recorded
  `objects.target`) is at slot 1 initially, moves to slot 4 at k0, and is moved
  back to slot 1 at k3 — i.e. objects 1 and 4 swap back at k3, 2 steps after
  k0, which the immediate-undo check cannot see. Final slot_of[1] = 1 (original
  slot). This is an exact reproduction of the finding's claimed mechanism.
- `scripts/configs/newtask-v6/sampling_config.json` `tasks.VideoRepick.decision.xhard2.swap_plan.s5.forbid_immediate_undo`
  = `true` — confirms only "immediate" undo is the documented/implemented
  guarantee. `0925-newtask-release-v6-plan.md` 表格行「口径8」explicitly says
  "禁止立即撤销" (forbid ONLY immediate undo) and its own validation section
  reports "撤销 0" for the immediate-undo statistic — i.e. the plan never
  promised delayed-undo protection; this is a documented design boundary, not
  an unplanned regression.

## Data reproduction (independent HDF5 reads, not the audit's own frame PNGs)
Script: `inspect_ep.py` in this dir (reads `info/is_subgoal_boundary`,
`info/is_video_demo`, `info/grounded_subgoal` from each episode HDF5, prints
every subgoal-boundary timestep's grounded text).

New-tier (xhard2/xhard4), reproduced independently from `new-tier-index.json` paths:
- xhard2 ep0 (seed10900000): demo `pick up the cube at <73, 180>` (t0), consistent
  with finding's target-return claim for this episode (slot cycle produces
  final slot == initial slot for target bin_4, per swap_pairs k0/k2/k5).
- xhard2 ep3 (seed10900301): demo `pick up the cube at <58, 90>` (t0) ->
  exec `pick up the correct cube at <57, 90> for the first time` (t589).
  Matches finding exactly.
- xhard4 ep3 (seed6900300): demo `<86, 88>` (t0) -> exec first pick `<84, 87>`.
  Matches finding exactly.
- xhard4 ep6 (seed6900600): demo `<88, 183>` (t0) -> exec first pick `<87, 181>`.
  Matches finding exactly.

Native tier (easy/medium), reproduced independently from
`artifacts/newtask-v6/v1/base/B/VideoRepick_episode_{0,2,6}/hdf5_files/*.h5`:
- ep0 (seed9000, easy): demo `<101, 179>` -> exec first pick `<100, 178>`.
  Matches finding exactly.
- ep2 (seed9200, medium): demo `<96, 139>` -> exec first pick `<94, 140>`.
  Matches finding exactly.
- ep6 (seed9600, medium): demo `<93, 93>` -> exec first pick `<92, 92>`.
  Matches finding exactly.

All six coordinate pairs cited in the finding were reproduced independently
(fresh h5py read, not copying the audit's own JSON/PNG artifacts) and match
to within 1-2 px (consistent with grounding-projection rounding, not a
different swap resolution).

## Native mechanism (for the native_same category check)
`scripts/configs/newtask-v6/sampling_config.json` `tasks.VideoRepick.native.parameters.swap_selection`:
`partner.selection = "nearest"`, `resolve_at = "swap_start"` — i.e. native
swaps are NOT planned against a fixed anti-undo graph at all; each swap event
independently recomputes the 2 nearest neighbours from real physical
positions at that instant and picks one uniformly at random
(`VideoRepick.py::_compute_dynamic_swap_candidates` / `_select_swap_pair_from_positions`).
There is no `forbid_undo`/`last` tracking anywhere in the native path. With
easy/medium using only 3 cubes and swap_min/max of 1-2/2-3, a short random
walk of transpositions among 3 objects has a substantial chance of returning
the target to its own slot purely by chance — which is exactly what the 3
sampled native episodes show. So native and new-tier arrive at the SAME
observable behavior (target back at/near its demo slot) via two structurally
different mechanisms: native has no undo protection of any kind (pure luck);
new-tier has a partial, explicitly-scoped protection (immediate-undo only)
that a multi-step cycle can defeat. The finding's category `native_same`
("identical behavior in easy/medium/hard") is judged correct at the
behavioral-outcome level, which is what the audit's own category
definitions are keyed on (language/task-chain/video-content match or
mismatch vs native), not at the mechanism-internals level.

## Duplicate-of-excluded check
Checked against F1-F6, D1-D7, VPB-button-binding, left/right-wording,
website-text exclusions in the task prompt: none reference VideoRepick target
return / delayed undo / swap-cycle identity. Not a duplicate. F2 (excluded)
is about the "previously picked up N times" phrase, an unrelated aspect of
the same env.

## Verdict
CONFIRMED. Both the source-code mechanism (immediate-only undo check, traced
by hand-simulating the recorded swap_pairs against `_greedy_once`'s own
slot-tracking logic) and every one of the 6 cited coordinate pairs (3 native +
3 new-tier, all re-derived independently from HDF5, not from the audit's own
evidence files) reproduce exactly as claimed. Category `native_same` is
judged correct: the phenomenon is present, with comparable frequency (3/6
native vs 4/12 new-tier), in both native and new tiers, via different but
equally uncontrolled-for mechanisms. Not a duplicate of any excluded item. No
new simulation needed — everything was verifiable from already-delivered
data and AUDIT_BASE source.
