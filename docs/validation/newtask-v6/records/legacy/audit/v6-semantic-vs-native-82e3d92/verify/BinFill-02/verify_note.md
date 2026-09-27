[内部产出，英文]
以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。

# BinFill-02 verification note

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1

## Source anchors checked (via `git show <sha>:<path>`)

- `src/robomme/robomme_env/BinFill.py::_initialize_episode` — confirmed `cube = cube_collection[i]`,
  `subgoal_language.get_subgoal_with_index(i, "pick up the {idx} {color} cube", color=color_name)`
  for i in range(target_number).
- `src/robomme/robomme_env/BinFill.py::_spawn_cubes_xhard` — confirmed slot-then-color-then-actor
  pipeline; `assignment` (post color_mix redraw) determines the order actors are appended to each
  color's list (`task["list"].append(cube)`), which is the `i` index consumed above. No spatial or
  temporal signal ties this order to anything the camera can see.
- `src/robomme/robomme_env/BinFill.py::step` — confirmed dynamic-mode call:
  `for idx in range(1, len(cube_list)): lift_and_drop_objects_back_to_original(..., end_step=idx*100, cur_step=timestep)`.
- `src/robomme/robomme_env/utils/statechange.py::lift_and_drop_objects_back_to_original` — confirmed
  `drop_step = start_step + duration//2` with `duration = end_step-start_step = idx*100`, so
  `drop_step = idx*50`. This reproduces the finding's claimed native dynamic appearance schedule
  (k-th cube, k=idx+1, appears at step 50*(idx) = 50*(k-1)) exactly.
- `layout_mode`/`XHARD_LAYOUT_DYNAMIC` — confirmed clutter forces `self.dynamic=False` for xhard
  tiers (line ~98, ~490).

## Data evidence checked

- `ordinal_appearance.json` (kind=new): confirmed first_appear=0 for every xhard1-4 pick that has a
  grounded check (88 rows spot-checked programmatically, xhard4 ep0 row set and xhard1-3 rows dumped
  and inspected). xhard4 ep0 reaches "pick up the seventh blue cube" (t=1023, first_appear=0).
- `ordinal_appearance.json` (kind=native): confirmed the claimed split —
  - dynamic episodes easy/0, medium/2, medium/6, medium/10, hard/7, hard/11 show first_appear
    following 0/50/100 in lockstep with pick order (e.g. medium ep10: green picks at t=[0,148,327],
    first_appear=[0,50,100]; hard ep7: red picks first_appear=[0,50], blue picks first_appear=[0,50]).
  - static episodes easy/1, easy/4, hard/3 show first_appear=0 for every ordinal including
    "second"/"third" (e.g. hard ep3: green picks first_appear=[0,0,0], blue picks first_appear=[0,0]).
  This is an exact reproduction of the finding's "native_behavior" paragraph from data I generated
  independently (re-ran the aggregation logic against `records.json`, did not just trust the
  pre-existing json — see `reverify_ordinal.py` in this dir).
- `records.json`: confirmed the N1 (missing grounded coordinate) claim — xhard3 ep0 has no
  "pick up the fifth blue cube" grounded_checks entry (jumps 4th→6th blue) and xhard4 ep0 has no
  "pick up the fourth blue cube" entry (jumps 3rd→5th blue), matching the finding's two cited cases
  exactly.

## Visual evidence checked

- `frames/new_xhard4_ep6_picks_t0_last.png`: at t0 all 9 cubes (3 red/3 blue/3 green) visible in a
  scattered clutter; "first green" is the bottom cube of the cluster, "second green" and "third
  green" are scattered elsewhere with no visible order cue distinguishing them. Confirms "no spatial
  or temporal order" claim.
- `frames/native_hard_ep3_picks_t0_last.png` (native STATIC): same defect reproduces identically —
  "first green" sits isolated bottom-right, "second"/"third green" scattered top with no
  distinguishing visual cue, all present at t0. This directly supports category=native_same: the
  defect is not new-tier-specific, it already exists in native static-mode episodes.
- `frames/native_medium_ep10_picks_t0_last.png` (native DYNAMIC, contrast case): at t0 only ONE green
  cube is present ("first green"); the frames at t148/t327 (bottom strip) show a second, then third,
  green cube arriving — i.e. in dynamic mode the ordinal genuinely tracks appearance order and has a
  visual referent. This is the case the finding says is NOT broken, and it visually is not.

## Verdict

CONFIRMED. All source anchors resolve to the claimed code paths at AUDIT_BASE, and I independently
regenerated the appearance-order aggregation from `records.json` (not just re-reading the finding's
pre-computed json) and it reproduces the exact native dynamic (0/50/100) vs native static (0/0/0) vs
xhard (0/0/0...) split the finding describes, plus the two N1 missing-coordinate cases.

Category: native_same is correct. The underlying defect (ordinal index with no visual/temporal
referent) is byte-for-byte the same mechanism in native STATIC episodes (easy ep1/4, hard ep3) as in
xhard1-4 (which are unconditionally static via layout_mode=clutter forcing dynamic=False). The larger
max ordinal reached in xhard (up to "seventh") is a scale effect of larger cube counts, not a new
mechanic — xhard does not introduce any new appearance-ordering logic; it simply always takes the
branch (static) that native tiers only sometimes take. This is not new_tier_only (the defect exists
natively) and not native_vs_new_mismatch (behavior is identical, not diverging from native without
plan basis).

Not a duplicate of any excluded issue (F1-F6, D1-D7, left/right, website-text) — none concern
ordinal/appearance-order semantics.

No new simulation needed to confirm this finding; all evidence was reproducible from already-delivered
data (native tiers' existing 144 HDF5 + the 165 new-tier successes already indexed).
