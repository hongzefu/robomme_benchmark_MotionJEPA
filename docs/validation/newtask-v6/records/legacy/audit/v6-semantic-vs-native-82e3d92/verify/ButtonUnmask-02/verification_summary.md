# ButtonUnmask-02 verification (AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

## Source (git show, read-only)
- src/robomme/robomme_env/ButtonUnmask.py::_load_scene: confirmed `for i in range(bin_layout["count"][self.difficulty])`,
  on RuntimeError from spawn_random_bin: if xhard -> raise SceneGenerationError (records layout.bin_count.placed);
  else -> plain `break` (no error, no placed-count record). Native tiers get zero visibility into truncation.
- config_hard={'bin':15,'pick':2}, config_medium={'bin':5}, config_easy={'bin':3} (class attrs) -- matches finding.
- scripts/configs/newtask-v6/sampling_config.json: tasks.ButtonUnmask.decision.bin_layout_policy.count =
  {hard:15, easy:3, medium:5, xhard1..4:8}; tasks.ButtonUnmask.native.positions.bins.min_gap_factor = 2. Matches finding exactly.
- VideoUnmask.py::_load_scene has the IDENTICAL loop/break/raise pattern (same file structure, same variable names) --
  this is the same code-level bug class as excluded D1, just instantiated in a sibling env file.
- 0925-newtask-release-v6-plan.md 三/四: BU row (line 69) only tables distractor-count/pick per tier (0/8/10/12/14 distractor,
  pick 2/2/3/3/3) and says "同上" (inner ring fixed at 8, not graded). No line anywhere mentions native hard/medium's
  inner container count being silently truncated. Confirms finding's "plan says nothing about ... native truncation".

## Independently reproduced frames (own extraction, not reusing prior audit's PNGs)
Extracted front_rgb at timestep_33 directly from listed H5 files with a fresh script (extract_frame.py), then
nearest-neighbor upscaled 256->768 for counting (see *_big.png in this dir). Visually counted only bin-shaped
(box+lid) objects, excluding the single small round grey disc that appears identically at the ring center in every
frame (this is likely the button seen from top-down, not a bin -- shape mismatch is on-screen).

| file | tier | mp4 filename tier label | boxes counted |
|---|---|---|---|
| native_hard_ep3_t33_big.png  | hard (confirmed via mp4 filename `..._hard_...`) | hard | 6 |
| native_hard_ep7_t33_big.png  | hard | hard | 6 |
| native_hard_ep11_t33_big.png | hard | hard | 6 |
| native_medium_ep2_t33_big.png | medium | medium | 5 |
| native_medium_ep6_t33_big.png | medium | medium | 5 |
| native_medium_ep10_t33_big.png| medium | medium | 4 |
| native_easy_ep0_t33_big.png  | easy | easy | 3 (== configured easy count, no truncation) |
| newtier_xhard4_ep0_t33_big.png | xhard4 | (new-tier-index.json) | large ring, visibly >> hard's 6, consistent with 8 inner + 14 distractor = 22 |

Tier labels were cross-checked against the actual mp4 filenames in
artifacts/newtask-v6/v1/base/B/ButtonUnmask_episode_{0,1,2,3,4,6,7,10,11}/videos/*.mp4, which embed the difficulty
word (`_easy_`, `_medium_`, `_hard_`) -- not assumed from episode index alone.

All independently-reproduced counts (6/6/6, 5/5/4, 3) exactly match the finding's claimed counts.

## Verdict
CONFIRMED. Source anchors, config values, and visual container counts all independently reproduce. The
native/new-tier mismatch (silent truncation + no failure signal vs. fail-loud exact-count enforcement) is real and
undocumented in the plan. Not run: any new simulation (none needed; all evidence came from already-delivered H5s).

## Duplicate-of-excluded assessment
Excluded D1 is scoped explicitly to VideoUnmask ("VideoUnmask hard '15 containers' text"). This finding is about
ButtonUnmask, a different env/source file, with additional data D1 does not cover (medium-tier truncation:
ep2/ep6=5 vs ep10=4, i.e. the shortfall is itself non-deterministic even at the same configured difficulty).
Root cause is the same code pattern duplicated across BU/VU. Judgment: NOT a strict duplicate (different env,
extra data point about medium-tier variability), but same bug class as D1 -- flagged for the consumer to decide
whether to merge into D1 or keep separate.
