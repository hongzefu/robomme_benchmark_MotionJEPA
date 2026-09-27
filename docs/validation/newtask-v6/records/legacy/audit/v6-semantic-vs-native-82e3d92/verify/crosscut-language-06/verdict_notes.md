# Verification notes — crosscut-language-06

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (read via `git show`; note this repo's
working tree HEAD already equals AUDIT_BASE, confirmed clean by `git status --porcelain`).

## 1. Independent data reproduction (verify_repro.py, output in verify_repro_output.txt)

Re-derived the "missing <r,c> coordinate" counts directly from
`crosscut-language/records.json` with my own script (not reusing `nocoord.json`'s
cached output, only reusing its column-extraction logic which I re-typed independently):

| kind/seg | missing/total | rate |
|---|---|---|
| native/exec | 2/407 | 0.49% |
| native/demo | 9/177 | 5.08% |
| new/exec | 11/1011 | 1.09% |
| new/demo | 12/352 | 3.41% |

Exact match to the finding's `native_behavior` and `new_tier_behavior` fields, including
the specific (task, difficulty, episode, t) tuples listed in the finding
(SwingXtimes hard ep7 t106, VideoRepick easy ep4 t497 for native exec; all 11 new-tier
exec rows for new/exec).

`choice_action.point` is present in all 13 missing-coordinate exec rows (2 native + 11
new) — confirms "choice_action.point is still present in every case".

## 2. Statistical claim ("rates not materially different")

Fisher's exact test on 2/407 (native exec) vs 11/1011 (new exec): p=0.37 (scipy
`fisher_exact`). Not significant — supports the finding's claim that the higher raw new
count is consistent with sampling noise around a shared underlying rate, not a
new-tier-specific behavior change.

## 3. Root-cause / mechanism confirmation (source anchors)

Traced the fill path: `RecordWrapper.py::_get_obs_extra` (or equivalent step hook) calls
`process_segmentation()` (src/robomme/robomme_env/utils/segmentation_utils.py) which
computes the target's pixel center from `segmentation_2d` via
`compute_center_from_ids()`:

```python
mask = np.isin(segmentation_mask, ids)
if not np.any(mask):
    no_object_flag = True
    return None   # -> subgoal template's "<r, c>" placeholder stays unfilled
```

This only runs `if current_subgoal_segment != previous_subgoal_segment` (i.e. exactly at
subgoal-boundary steps, matching the finding's "boundary step" framing), and the target
object's segmentation ids going fully absent from the base-camera mask (occlusion by the
gripper/arm, or the object temporarily out of camera view) is the only path that sets
`no_object_flag=True` and drops the coordinate.

Critically, `process_segmentation()` takes no difficulty/tier parameter and is called
identically for every task/tier (native easy/medium/hard and new xhard1-4) — the
mechanism is purely a per-frame segmentation-visibility computation, not tier-specific
logic. This independently supports the finding's `source_anchors` claim ("not
tier-specific") and its `category: native_same` classification: any tier can hit this
whenever the target's segmentation mask is momentarily empty at a boundary step, and the
data above shows it happens in both native and new tiers at statistically indistinguishable
rates.

## 4. Visual spot-check

Viewed `frames/nocoord_PH_xhard4_ep0_t785.png` and `frames/nocoord_Swing_hard_ep7_t106.png`
(already-extracted evidence frames, not regenerated). Both show the gripper fingers
directly over/holding a cube consistent with "target occluded by arm at boundary step";
visual occlusion from a single 2D frame is corroborating but not dispositive on its own —
downgraded to independent-plus-corroborating rather than fully independently reproduced
occlusion pixel-by-pixel (would need the actual segmentation_id_map + per-frame mask,
which requires simulation replay, out of scope for pure audit).

## 5. Duplicate check

Not a duplicate of any excluded item (F1–F7, D1–D7): none of the excluded findings
concern segmentation-driven coordinate omission in grounded_subgoal text.

## Conclusion

CONFIRMED. Category `native_same` is correct (mechanism is generic, non-tier-specific,
and native tiers exhibit the same behavior at a statistically indistinguishable rate).
No new simulation needed — everything was reproducible from already-delivered data
(records.json, source code at AUDIT_BASE).
