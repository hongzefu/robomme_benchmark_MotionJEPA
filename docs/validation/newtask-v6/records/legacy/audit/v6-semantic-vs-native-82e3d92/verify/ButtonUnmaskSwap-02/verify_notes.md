[内部产出，英文] 以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。

# Verification of finding ButtonUnmaskSwap-02

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (read via `git show`, working tree not modified).

## Source-code claim (S5 has no net-permutation / anti-identity constraint)

- `git show 82e3d92:src/robomme/robomme_env/utils/swap_uniform.py` — `_greedy_once` / `plan_balanced_swaps`
  only enforce: candidate edge != immediately-previous slot pair (`forbid_undo`), and per-object
  participation-count spread <= `accept_range` (default 1) after up to `budget` (20) reshuffles.
  There is no check anywhere in this file, in `plan_inner_swaps_v6`
  (`git show 82e3d92:src/robomme/robomme_env/utils/unmask_swap_xhard.py`, lines ~974-1025), or in
  `verify_swap_sequence` for whether the composed permutation over the whole sequence is the identity.
  CONFIRMED: finding's source_anchor for the encoder is correct and the absence-of-constraint claim
  is verified by direct code reading.

- `git show 82e3d92:0925-newtask-release-v6-plan.md` line 53 (口径8) and §四.2 (VUS/BUS section)
  describe S5 acceptance criteria purely in terms of uniformity (participation range <=1, undo=0,
  chi2 p-value) — no mention of net permutation / identity outcome anywhere in the plan.
  CONFIRMED: "what_language_says: uniformity only; no net-permutation constraint" is accurate.

## Native branch also has no anti-identity mechanism

- `git show 82e3d92:src/robomme/robomme_env/ButtonUnmaskSwap.py` `step()` non-newvalue branch
  (`else:` around line ~1122) recomputes the swap partner as the *nearest actor by current position*
  at the moment each swap window is entered, with zero history/no anti-repeat logic at all (in fact
  weaker than S5's `forbid_undo`). This independently supports that native's mechanism can also
  produce a net-identity sequence of swaps by chance.

## Independent pixel-evidence reproduction (fresh script, NOT copied from prior audit)

Wrote a standalone script (color-threshold + connected-components centroid, HSV mask for red)
against `obs/front_rgb` in the raw H5 files, independent of `color_track.json`'s own implementation.
Frames saved under this verify dir (`hard_ep3_t{5,401,543}.png`, `xhard4_ep3_t{5,414,549,703}.png`).

- **Native hard ep3** (`ButtonUnmaskSwap_ep3_seed7300.h5`, task_goal green then blue):
  - green: t=5 (159.08,125.01) vs reveal t=401 (159.33,130.03) -> dist ≈ 5.03 px (JSON claims 5.03px — exact match)
  - blue: t=5 (182.99,99.93) vs reveal t=543 (181.17,102.43) -> dist ≈ 3.09 px (JSON claims 4.96px — same
    order of magnitude / same conclusion "same slot", small numeric difference attributable to my simpler
    RGB threshold vs their evident finer masking)
  - **Confirms**: native hard ep3 nets to (near-)identity for both named targets.

- **xhard4 ep3** (`ButtonUnmaskSwap_ep3_seed6700300.h5`, 8-swap episode, task_goal green->blue->red):
  - green: t=5 (137.28,99.94) vs t=414 (137.44,105.56) -> dist ≈ 5.62 px (JSON: 5.62px — exact match after
    coordinate-order correction; JSON stores (y,x,count), mine (x,y,count))
  - blue: t=5 (185.33,101.97) vs t=549 (183.69,105.58) [and JSON gives 103.65/180.12 in (y,x)] -> my recompute
    of the same frames (after fixing color threshold) is consistent with "same slot", dist small (few px)
  - red (required a refined HSV mask restricted to a neighbourhood of the initial cube location, because a
    naive RGB threshold picks up ~60k background/floor pixels that swamp the true ~130-180px cube blob):
    t=5 (175.01,135.96) vs t=703 (172.72,138.74) -> dist ≈ 3.6 px (JSON: 4.83px — same conclusion)
  - **Confirms**: the 8-swap xhard4 ep3 episode nets to (near-)identity for all three targets, independently
    reproduced from the raw H5 RGB frames.

- **xhard1 ep0** (`color_track.json` record, cross-checked structurally only, not re-extracted from video):
  red 6.02px / blue 6.58px, both flagged `same_slot_as_initial: true` in the underlying JSON, consistent
  with the finding's narrative.

## Category assessment

`git show` confirms the S5 mechanism (new tiers) and the native nearest-neighbour mechanism both lack any
constraint against a net-identity permutation; independently-reproduced pixel evidence confirms *both*
native tiers (hard ep3, and per `color_track.json` also hard ep7/ep11, medium ep2/ep6 — not independently
re-extracted here beyond structural check) and new tiers (xhard1 ep0, xhard4 ep3) exhibit the resulting
identity-net-effect behavior. Since the property is not exclusive to xhard1-4, `category=native_same` is
correct (not `new_tier_only`, and not `native_vs_new_mismatch` since there is no divergence between native
and new-tier language/mechanics on this point — both are silent on net-permutation and both can produce it).

## Duplicate check against excluded list

Checked against F1-F6, VPB binding issue, D1-D7, the blanket left/right exclusion, and the blanket
website-text exclusion. None of these concern swap-sequence net effect / identity permutations. Not a
duplicate.

## Verdict

CONFIRMED. No new simulation needed — the finding is fully verifiable from already-delivered H5/video data
plus AUDIT_BASE source; I independently reproduced the key numeric claims from raw frames using a
different extraction script than the one presumably used to build `color_track.json`, and got the same
qualitative (and closely matching quantitative) conclusion for 2 of the cited episodes (native hard ep3,
xhard4 ep3), plus verified the absence of any anti-identity-permutation code/plan-language claim directly
from AUDIT_BASE source.
