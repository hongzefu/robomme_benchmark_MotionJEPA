# Verification: crosscut-values-05 (ButtonUnmask native container truncation)

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1

## What was independently reproduced

1. Source anchor confirmed verbatim at AUDIT_BASE: `src/robomme/robomme_env/ButtonUnmask.py`,
   the bin-placement loop `for i in range(bin_layout["count"][self.difficulty])` wraps
   `spawn_random_bin(...)` in `try/except RuntimeError`; on failure, if `xhard` (new-tier) it
   raises `SceneGenerationError` with a "放不满" message, else it silently `break`s. Confirmed
   via `git show <AUDIT_BASE>:src/robomme/robomme_env/ButtonUnmask.py`.
2. Config confirmed: `scripts/configs/newtask-v6/sampling_config.json` ->
   `tasks.ButtonUnmask.decision.bin_layout_policy.count` = {hard:15, medium:5, easy:3,
   xhard1..4:8}.
3. Container counts independently re-measured from RAW HDF5 `obs/front_rgb` frames (t=40,
   different/additional episodes than the original audit used: ep7, ep11 hard; ep2, ep6, ep10
   medium; ep0 easy; plus re-check of ep3 hard) using an automated white/gray blob detector
   (`count_blobs.py`) that separates containers+button from the wood table by low-saturation +
   high-brightness thresholding, then subtracts the one small button blob per frame (smallest,
   ~210-235 px, present in every frame at a fixed relative height near center).

   | episode | difficulty | config count | blobs (incl. button) | containers (blobs-1) |
   |---|---|---|---|---|
   | ep0 | easy | 3 | 4 | 3 |
   | ep2 | medium | 5 | 6 | 5 |
   | ep6 | medium | 5 | 6 | 5 |
   | ep10 | medium | 5 | 5 | **4** |
   | ep3 | hard | 15 | 7 | **6** |
   | ep7 | hard | 15 | 7 | **6** |
   | ep11 | hard | 15 | 7 | **6** |

   This exactly reproduces the finding's claimed numbers (medium ep2/ep6=5, ep10=4; hard
   ep3/ep7/ep11=6) from independently extracted frames and an independently written counting
   script, not by trusting `counts_raw.json`/`measured.json`.
4. Language-goal template confirmed to never mention a container count: `src/robomme/robomme_env/
   utils/task_goal.py` ButtonUnmask branch only emits color + pick-order phrases
   ("first press the button, then pick up the container hiding the {color} cube, ..."), no
   numeric container count appears anywhere in the template.

## Category correction: plan basis exists (contradicts "native_vs_new_mismatch")

The audit categorized this as `native_vs_new_mismatch` = "new tiers differ from native
**without plan basis**". Independent reading of the referenced plan family shows this is
factually wrong: there IS explicit plan basis, at two levels:

- `0922-newtask-release-v4-plan.md` §2.2④ ("四条共用机制", a global mechanism note applying to
  every environment): documents that `spawn_random_bin`/`spawn_random_cube` silently `break`
  when `max_trials` (256) is exhausted, and states verbatim that this is a known,
  cross-environment behavior; it explicitly directs that only the **new** tiers should record
  requested-vs-actual and fail the episode on shortfall, while native tiers are left unchanged
  by design.
- §2.7② ("四个 Unmask 环境的共用事项", explicitly covering VideoUnmask AND ButtonUnmask
  together) runs an equivalent-seed simulation of the exact `spawn_random_bin` placement logic
  and states verbatim: "现在的 hard（bin=15）本来就放不满，实际只有 9~12 个，而且 break
  完全无声" ("today's hard (bin=15) was never going to fill up; only 9-12 actually land, and
  the break is completely silent") — i.e., the plan authors already knew, before the v6 release,
  that native ButtonUnmask/VideoUnmask hard undershoots its configured container count, and this
  is precisely why xhard's fail-loud behavior was added.

So the asymmetry the finding describes (native silently truncates; new tiers raise) is not an
undocumented divergence — it is the documented, intentional fix target. This is a `not_an_issue`
outcome for the *mismatch* framing; the underlying native quirk itself is real but pre-known
and explicitly out of scope for this release (native tiers deliberately kept "逐字不变").

One residual wrinkle worth flagging to the user (not part of the original finding, found
incidentally): the plan's own §2.7② simulation table predicts hard(15) should place ~10.25
(range 9-12) on average, but all three independently re-measured hard episodes (ep3/ep7/ep11)
show exactly 6 — well below even the plan's own worst-case prediction. Likewise §2.7② predicts
request=5 always places exactly 5 ("5.0/5/5"), yet ep10 (medium) delivers only 4. This suggests
the real scene (button + hidden cube + robot avoid-list already occupying the region) is more
constrained than the plan's isolated bin-only simulation assumed — a potentially separate,
narrower finding about the *plan's own prediction* being optimistic, distinct from the
native-vs-new categorization question. Not chased further here since it needs no new
simulation, only more careful reading of the isolated-simulation methodology in §2.7② vs the
full scene generator; left for the user to decide whether to spin off as its own item.

## Files in this directory
- extract_frames.py, count_blobs.py — helper scripts (read-only, HDF5 -> PNG -> blob count)
- ep{0,2,3,6,7,10,11}_*_t{5,40}.png and matching *_mask.png — independently extracted frames
  and their binary container/button masks
