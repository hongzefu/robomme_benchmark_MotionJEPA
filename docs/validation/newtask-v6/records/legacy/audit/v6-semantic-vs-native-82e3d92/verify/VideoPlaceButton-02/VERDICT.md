[Internal produce, English]

# Verification of finding VideoPlaceButton-02

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (read via `git show`, source tree only).

## Source confirmation
- `git show AUDIT_BASE:src/robomme/robomme_env/utils/task_goal.py` (VideoPlaceButton branch): four
  templates are appended for every episode — "target right {before|after}", "placed immediately
  {before|after}", "previously placed {before|after}", and (only when before) "last placed before"
  / (only when after) "first placed after". All four point at the SAME target_target/target_target_language,
  confirmed exactly as the finding states.
- `git show AUDIT_BASE:src/robomme/robomme_env/VideoPlaceButton.py::_load_scene_xhard_tail`: task order is
  `[base-before pick/drop per demo cube in demo_cubes order] -> [extra_place_before pick/drop, owner drawn
  independently] -> button -> [base-after per demo cube] -> [extra_place_after]`. `target_target` for a
  "before" answer = `demo_before_targets[answer_index]` = that cube's OWN base-before target, independent of
  where it falls in the timeline once any other demo cube or extra-before placement is also scheduled before
  the button.
- Native tiers (`_load_scene`, non-xhard branch): single demo cube, single pre-button placement, single
  post-button placement — the "before the button" wording is unambiguous there. Confirms this ambiguity is
  structurally impossible in easy/medium/hard, i.e. `category=new_tier_only` is correct.

## Independent data verification (self-derived, not reusing the audit's own PNGs)
Read HDF5 directly (`h5py`, per-timestep `info/is_subgoal_boundary`, `info/grounded_subgoal`,
`obs/front_rgb`), classified cube color at each pick/drop coordinate by sampling `front_rgb` pixels
(coordinate order in `grounded_subgoal` text is `<row, col>`, verified empirically:
`img[125,181] == [4,231,4]` (green) for ep0 t=0, matching the "green" task_goal target color; using
`(col,row)` instead lands on bare wood, ruling out that ordering).

- `VideoPlaceButton_ep0_seed7000000.h5` (xhard4, delivered, task_goal="...place the green cube on the
  target right before the button was pressed"): boundary/pick-color timeline before the button:
  `t=0 pick GREEN -> t=111 drop -> t=206 pick BLUE -> t=328 drop -> t=418 pick BLUE -> t=492 drop -> t=590
  press button`. I.e. GREEN (the answer cube) is placed FIRST, and BLUE is placed twice after it, with
  BLUE's second placement (ending ~t=590) immediately preceding the button press. The program's answer
  target is still GREEN's t=111 placement (confirmed: the final "place the cube onto the correct target"
  action at t=1835 relocates a GREEN cube back onto the exact same coordinate `<100,89>` used at t=111).
  See `ep0_full_timeline_v2.txt`, `pre_pick_t*.png`.
- `VideoPlaceButton_ep6_seed7000600.h5` (xhard4, task_goal="...place the blue cube on the target right
  before the button was pressed"): `t=0 pick BLUE -> t=121 drop -> t=212 pick GREEN -> t=332 drop -> t=424
  pick GREEN -> t=492 drop -> t=581 press button`. Same pattern: BLUE (answer cube) placed first, GREEN
  placed twice afterward, GREEN's second placement immediately precedes the button. See `ep6_timeline.txt`.

Both independently-reproduced episodes confirm the finding's central claim: for 2-cube-before xhard tiers,
"right before / immediately before / last placed before the button" is temporally false for the answer
cube whenever another demo cube (or an extra-before placement) is scheduled after the answer cube's own
before-placement but still before the button. The per-cube reading ("this cube's own designated
before-target") matches the program; the natural-language global-temporal reading ("the cube placed right
before the button was pressed") does not.

## Duplicate check
EXCLUDED list contains: "VPB 'last placed before the button' answer binding (xhard3 ep3/6)". This is the
same underlying mechanism (temporal-vs-per-cube binding mismatch for the "before" wording in VideoPlaceButton
xhard tiers with >=2 demo cubes), just anchored to different episodes (xhard3 ep3/ep6 there vs xhard4 ep0/ep6
here) and templates ("last placed before" vs all four "before" templates here, which per the source code
are semantically identical - all four point at the same `target_target`). Treating this as a duplicate of
the excluded issue rather than a new independent finding.

## Category
`new_tier_only` is correct (verified: native tiers cannot exhibit this, only one demo cube/one before-slot).

## Verdict: CONFIRMED (but duplicate of an already-excluded issue)
No new simulation needed — evidence already exists in the delivered xhard4 ep0/ep6 files (and presumably in
the already-excluded xhard3 ep3/ep6 files).
