# Verification of MoveCube-01 (new_tier_only)

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (read-only, git show only)

## Verdict: CONFIRMED

## Independent evidence reproduced

1. Source (`git show $AUDIT_BASE:src/robomme/robomme_env/MoveCube.py`):
   - `_initialize_episode`: `self.ways=["peg_push","gripper_push","grasp_putdown"]`;
     `way_idx = self._spec.value(f"initializations.{idx}.way_idx", torch.randint(...))`.
     Confirms selection of the delivered way is driven by a spec-lookup keyed on
     `initializations.<idx>.way_idx`, defaulting to random only when unspecified.
   - `__init__`: `if self.difficulty == "xhard4": self._xhard_peg_yaw_reduction = True`
     — confirms peg-yaw reduction (B11) is xhard4-only, as claimed.

2. Plan (`git show $AUDIT_BASE:0925-newtask-release-v6-plan.md`):
   - 二.12: "每格10候选、取 index 0/3/6 三局正式" — confirms S4 delivered-set
     selection is fixed at candidate index 0/3/6 for every 10-candidate cell,
     independent of which `way` those indices happen to produce.
   - 五 (line ~193): "MoveCube三方法以4／4／4为覆盖目标" appears only in the
     description of S2 (144 fixed demo probes), not in S4/delivery section
     (二.12, 六 MoveCube-xhard4 subsection). The MoveCube xhard4 subsection
     (六.6) only specifies the annulus region geometry, not way-coverage
     for the delivered set. So the plan does not commit to peg_push coverage
     in the delivered xhard4 set — the finding's framing is accurate.

3. Data — `xhard4_candidates_way.json` (10 xhard4 candidates, MoveCube):
   - `effective_way` by episode index: 0=gripper_push(selected), 1=grasp_putdown,
     2=grasp_putdown, 3=gripper_push(selected), 4=peg_push, 5=grasp_putdown,
     6=grasp_putdown(selected), 7=peg_push, 8=grasp_putdown, 9=peg_push.
   - peg_push occurs only at indices 4/7/9 — none of which is in the fixed
     selection set {0,3,6}. Exactly reproduces the finding's claim.

4. Data — `records.json` (delivered set, re-derived independently):
   - Native (easy/medium/hard, 9 episodes): peg_push=4 (easy_ep0, medium_ep2,
     medium_ep10, hard_ep7), gripper_push=2 (hard_ep3, hard_ep11),
     grasp_putdown=3 (easy_ep1, easy_ep4, medium_ep6). Matches finding exactly.
   - Delivered xhard4 (3 episodes): xhard4_ep0=gripper_push, xhard4_ep3=gripper_push,
     xhard4_ep6=grasp_putdown. Zero peg_push. Matches finding exactly.

5. Visual — keyframe grids opened directly:
   - `xhard4_ep0_keyframes.png`, `xhard4_ep6_keyframes.png`: peg (red stick) is
     visible on the table throughout every frame in both episodes and is never
     picked up; ep0 is a direct gripper-push, ep6 is grasp-and-putdown of the
     cube. No hooking motion with the peg is visible in either delivered xhard4
     video reviewed.
   - `s2_6100001_pegpush_keyframes.png` (S2 probe, non-delivered, seed 6100001,
     path under `artifacts/newtask-v6/v6-s2-20260926-01/`, NOT under the
     delivered `v6-01/xhard4/rollout/`): shows the gripper picking up the red
     peg (t=193) and later using it to push/hook the cube toward the target
     (t=426–537, "Hook the cube to the target with the peg"). This confirms
     peg_push is mechanically present and renders correctly in xhard4, it is
     simply absent from the delivered/selected set.

## Category check

`new_tier_only` is correct: the fixed index-0/3/6 candidate-selection scheme
(plan 二.12) is a new-tier delivery mechanism that does not exist for native
tiers (native easy/medium/hard episodes are not drawn from a 10-candidate pool
selected by fixed index); the resulting skew (no peg_push in the delivered
xhard4 triplet, despite peg_push being the method most affected by the xhard4-
specific peg-yaw and annulus-region changes) is a direct, new-tier-only
consequence of that mechanism. `native_vs_new_mismatch` is a plausible
secondary label (native proportionally includes all 3 ways, xhard4 delivered
does not) but the root cause anchor is squarely in the new-tier-only selection
mechanism, so `new_tier_only` as filed is kept.

## Duplicate check

Not a duplicate of any excluded item (F1–F6, D1–D7, VPB binding, left/right,
website-text-only). None of those concern MoveCube way/method selection.

## Simulation

No new simulation needed to confirm this finding — all evidence is already
present in delivered artifacts, S2 probe artifacts, and the AUDIT_BASE source/
plan text.
