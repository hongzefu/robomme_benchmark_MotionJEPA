# Verification: crosscut-language-04 (PickHighlight)

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (read via `git show`, no working-tree/other-ref reads)

## Verdict: CONFIRMED (with one numeric correction)

## Independent evidence reproduced

1. **Source, subgoal color suffix** — `git show 82e3...:src/robomme/robomme_env/PickHighlight.py`
   - `XHARD_DECISION["subgoal_color_suffix"] = "omit"` (line ~104), shared by all 4 xhard tiers via `NEWVALUE_DECISION` (deepcopy for xhard1-3).
   - `_load_scene`: `if xhard_cfg["subgoal_color_suffix"] != "omit": raise ...` — only "omit" implemented.
   - xhard branch builds `task_name = subgoal_language.get_subgoal_with_index(cube_idx, "pick up the {idx} highlighted cube")` (no color kwarg) vs native branch `f"... which is {self.target_labels[cube_idx]}"` — confirms suffix is present in native, absent in xhard.

2. **Source, button failure predicate** —
   - xhard: `button_failure_func = lambda: is_any_obj_pickup(self, [cube for cube in self.all_cubes])` (re-evaluated every check).
   - native: `button_failure_func = is_any_obj_pickup(self,[cube for cube in self.all_cubes])` — called immediately at construction time (no cube picked up yet) → a frozen `False`.
   - `is_any_obj_pickup` (`utils/subgoal_evaluate_func.py`) returns a plain bool, confirming the native call yields a constant.
   - `sequential_task_check` (`utils/subgoal_evaluate_func.py`): `if callable(current_failure_func): failure_result = current_failure_func() ... else: failure_triggered = _coerce_failure_result(current_failure_func)`. Non-callable (native) path only ever coerces the frozen construction-time value → can never newly become True during the episode. Callable (xhard) path re-evaluates every step.
   - ⇒ Source-level proof that native's button-pick guard is dead code (an inert constant) while xhard's is live.

3. **Data, checks.json** (`artifacts/.../crosscut-language/checks.json`, pre-existing evidence file, read-only) — recomputed independently:
   - Native PickHighlight `color_suffix_present`: 18/18 chunks have suffix (not 9/9 as the finding states — see correction below).
   - New-tier (xhard1-4) `color_suffix_present`: 66/66 chunks have **no** suffix (not 12/12 — same correction).
   - Qualitative claim (100% native has suffix, 0% xhard has suffix) reproduced exactly; only the raw counts cited in the finding are wrong.

4. **Data, HDF5 ground truth** — read directly with h5py (read-only, no robomme/gym import):
   - xhard4 `PickHighlight_ep0_seed7200000.h5`: `setup/task_goal` = `"first press the button, then pick up all cubes that have been highlighteted with white areas on the table"` (byte-identical goal text also present in native `PickHighlight_ep2_seed12200.h5`, confirming the language layer is shared across tiers).
   - xhard4 ep0 `simple_subgoal` boundary sequence: `press the button` → `pick up the first highlighted cube` → ... → `pick up the seventh highlighted cube` (7 picks, ordinals only, zero color words) — matches finding's video/HDF5 claim, including the `t=785` boundary (`pick up the fifth highlighted cube`, matching the referenced frame filename `nocoord_PH_xhard4_ep0_t785.png`).
   - Native `PickHighlight_episode_2` (`ep2_seed12200.h5`): `pick up the first highlighted cube, which is green` — confirms native carries the `, which is {color}` suffix on the identical goal template.

5. **Plan-basis check** — `git show 82e3...:0925-newtask-release-v6-plan.md`:
   - Line 4 preface: "V5 决策除本文明确改动的以外全部延续" (all V5 decisions continue except what this document explicitly changes) — matches the finding's "inherited via plan preface 'V5 决策延续'".
   - Section "### 7. BinFill / PickXtimes / SwingXtimes / PickHighlight" (the section covering PickHighlight numeric/mechanism deltas) discusses spawn/pick counts, HSV color policy, OBB precision and reset rates — it does **not** mention `subgoal_color_suffix` or the button failure-predicate change at all. Confirms finding's claim "the V6 plan text itself does not describe either difference."

## Correction to the finding

The cited counts "(9/9 native with suffix)" and "(12/12 new, 0 with suffix)" are **not** the actual totals in `checks.json` — actual totals are 18/18 native (all with suffix) and 66/66 new (none with suffix). The qualitative claim these counts are meant to support is fully reproduced and correct; only the specific numerals are wrong (likely miscounted from a subset of entries). This does not change the verdict.

## Category assessment

`new_tier_only` is correct: this is not `native_same` (behavior clearly differs), and not cleanly `native_vs_new_mismatch` ("without plan basis") since the difference does trace to an inherited V4/V5 decision (code comments: 2026-09-22 "omit"; D4 "only fix in xhard (H2)") carried forward by the V6 plan's blanket "V5 decisions continue" preface — it just isn't independently justified or even mentioned in the V6 plan's own PickHighlight section. This is exactly the "new_tier_only" bucket's intended meaning (mechanic exists only in xhard1-4).

## Duplicate check

Not a duplicate of any EXCLUDED item (F1-F6, D1-D7): none of those concern PickHighlight's color-suffix omission or the button-pick failure-predicate liveness. Not a left/right wording issue, not a pure website-text issue.

## needs_new_simulation

No new simulation needed — the source-code proof (non-callable vs callable failure_func, `sequential_task_check`'s branch) is sufficient by itself to prove native's guard can never fire regardless of episode content; the existing xhard4/native HDF5 files already show the video/text-layer half of the claim. (If the user still wants a live demonstration of a native episode where a cube is picked before the button and the episode does NOT fail, that would need new native-tier rollouts — e.g. 2-3 episodes of PickHighlight easy/medium/hard with an out-of-order pick-then-button demo policy — but this is optional confirmation, not required for the source-level proof.)
