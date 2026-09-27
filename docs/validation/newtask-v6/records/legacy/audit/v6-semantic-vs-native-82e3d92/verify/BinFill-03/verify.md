# Verification of BinFill-03

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (git show only).

## Source re-check (independent, from AUDIT_BASE)
- `src/robomme/robomme_env/BinFill.py::_initialize_episode`: pick task func =
  `lambda c=self.all_cubes: is_any_obj_pickup_flag_currentpickup(self, objects=c)` — passes
  `self.all_cubes` (all colors), not the target color's cube list. This construction is
  identical regardless of `self.difficulty` (no branch on tier inside the task-list builder);
  only `color_order` / `target_number` differ per tier.
- `utils/subgoal_evaluate_func.py::is_any_obj_pickup_flag_currentpickup`: loops `objects`
  (all_cubes) and returns True on the first grasped cube of ANY color — confirms predicate is
  color-agnostic exactly as claimed.
- `utils/subgoal_evaluate_func.py::is_any_obj_dropped_onto_delete` (put task, also called with
  `c=self.all_cubes`): loops all cubes; color is only used afterwards to increment the
  per-color in-bin counters (`red/blue/green_cubes_in_bin`).
- `check_in_bin_number` (button-stage failure_func): the only place count-per-color is checked
  against target — confirms "only caught at the final button stage" claim.

## Independent data re-check (own script, not trusting README numbers)
Re-parsed `artifacts/audit/v6-semantic-vs-native-82e3d92/BinFill/records.json` directly (own
throwaway script, not the audit's `summarize.py`):
- Pick-point color match (`grounded_checks`, expected != null): new-tier 88/88 match, 0
  mismatch, 0 no-coord; native 26/26 match, 0 mismatch. Reproduces the finding's "88/88" and
  "26/26" exactly.
- Drop color match (`drops`, named_color vs above_hole_color): new-tier 90/90 match; native
  26/26 match. Reproduces the finding's "90/90" exactly.

## Plan-basis check
`0925-newtask-release-v6-plan.md` BinFill section (row + §7, §269) covers only scene
generation (layout_mode, color_mix, spawn/put_in_color ranges) — it does not mention or change
the pick/put success predicate. So xhard1-4 do not diverge from native on this axis "without
plan basis" — the predicate was never touched by the v6 plan; it is preexisting behavior
identical in all 7 tiers => `native_same` is the correct category, not
`native_vs_new_mismatch`.

## Duplicate check
Not a duplicate of any excluded item (F1-F6, D1-D7, left/right wording, website-text-only).
This is the same underlying observation as N3 in the source audit's own
`BinFill/README.md` ("Findings" section), now formalized as a numbered finding — not a
duplicate of a *different, already-excluded* issue.

## Verdict
CONFIRMED. category=native_same is correct (identical code path, all 7 tiers, no plan
mention). No new simulation needed — fully verifiable from existing delivered data
(12 new-tier + 9 native HDF5, all already ingested in records.json).
