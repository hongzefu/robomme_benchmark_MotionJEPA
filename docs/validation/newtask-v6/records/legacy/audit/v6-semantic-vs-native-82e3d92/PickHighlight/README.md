# PickHighlight — semantic-vs-visual / native-vs-new-tier audit (AUDIT_BASE 82e3d922b78d48ec1e825b168cccc0e1b8c690c1)

Pure read-only audit. Source read only via `git show 82e3d92:<path>`. No simulation; h5py/numpy/cv2/json only.
Helper scripts in this dir: `h5_keys.py`, `proj_test.py`, `extract.py`, `grounded_scan.py`, `annotate.py`, `dump_frames.py`.

## Sources read
- `src/robomme/robomme_env/PickHighlight.py` (NATIVE_SAMPLING, XHARD_DECISION/NEWVALUE_DECISION, `_load_scene`, `evaluate`, `step`)
- `utils/task_goal.py::get_language_goal` (PickHighlight branch), `utils/subgoal_language.py` (_ORDINALS to 20),
  `utils/subgoal_evaluate_func.py::sequential_task_check`, `utils/statechange.py::highlight_obj` (disk_radius 0.05, white, z-0.01)
- `env_record_wrapper/RecordWrapper.py` (offline/online `process_segmentation`, NO_OBJECT video)
- `scripts/configs/newtask-v6/sampling_config.json` tasks.PickHighlight
- Plans: `0925-newtask-release-v6-plan.md` 二/三/四.7; `0922-newtask-release-v4-plan.md` 2.12 (C3, D4/H2, J3, J4); `0926-v6-audit-fix-plan.md` (F1, D3, judgment envelope)

## Per-tier table
| tier | spawn | pick(highlight) | colors | subgoal pick text | button failure_func | highlight window |
|---|---|---|---|---|---|---|
| easy | 3 | 1 | red/blue/green per cube | `pick up the highlighted cube, which is {color}` | evaluated tensor (never fires; D4) | steps 10–100, simultaneous, white disk r=0.05 |
| medium | 4 | 2 | same | `pick up the {ordinal} highlighted cube, which is {color}` | same | same |
| hard | 6 | 3 | same | same | same | same |
| xhard1 | 7 | 4 | HSV any (S≥0.5,V≥0.4) | `pick up the {ordinal} highlighted cube` (J4 omit) | lambda (effective, D4 fix only in xhard) | same |
| xhard2 | 8 | 5 | same | same | same | same |
| xhard3 | 9 | 6 | same | same | same | same |
| xhard4 | 10 | 7 | same | same | same | same |
Language goals: identical two sentences in all 21 episodes (F1 excluded). Choices a/b/c identical in all 21. Success: every target picked ≥1 (rising edge); pick failure: any non-target picked (all tiers).
Plan table 三 matches config exactly (pick/total 4/7,5/8,6/9,7/10).

## Coverage
- New tier: all 12 delivered HDF5 (xhard1..4 × ep0/3/6), specs from `artifacts/newtask-v6/v6-01/<tier>/specs.jsonl` (cube xy, colors, highlight_ids).
- Native: all 9 base HDF5 (easy ep0/1/4, medium ep2/6/10, hard ep3/7/11); cubes detected by colour segmentation at t=5 and back-projected with front camera K/extrinsic (2 phantom "red" detections per episode with 0 white ring — ignore).
- Checks per episode (`records.json`): subgoal sequence and boundaries; count of pick subgoals == highlight_count; choice_action point vs projected target (all ≤1.7 px); gripper-close grasp positions vs initial cube xy (all picks within ≤0.011 m of the correct target, in highlight_ids order); white-ring fraction around each target over frames 10–100 (new: 0.58–0.94); non-target nearest-target center distance (new min 0.0846 m > 0.05+0.028 footprint overlap bound ⇒ no non-target sits on a white disk); white connected components at t=30; grounded_subgoal coordinate presence per frame (`grounded_scan.json`).
- Annotated frames: `frames/*_t30_annot.png` (green=target, red=non-target), `frames/compare_merge_t30.png`, occlusion frames `frames/xh*_nocoord_*.png`.

## Findings
1. **PH-G1 (new_tier_only, low)** — offline `grounded_subgoal` has no `at <r,c>` for an entire pick segment in 3/12 new-tier episodes (native 0/9): xhard2 ep6 t480–585 (3rd pick, cube1), xhard3 ep3 t701–820 (5th, cube8), xhard4 ep0 t785–908 (5th, cube0). Cause: `RecordWrapper` fills the offline coordinate once at the subgoal switch; at that frame the arm (returning from the previous place) occludes the target (see `frames/xh*_nocoord_*.png`); the `success_NO_OBJECT_*.mp4` companions exist exactly for these 3 episodes. Because xhard also drops the `, which is {color}` suffix (J4), these segments' grounded text `pick up the {ordinal} highlighted cube` carries no visual referent at all, while the same-step `choice_action.point` is correct (e.g. xhard2 ep6 point [88,122] = cube1 projected (122.3,88.4)). Mechanism is shared with native; the frequency difference comes from clutter/more picks. Not described in the plans.
2. **PH-O1 (native_same, low)** — ordinal words "first/second/…" in pick subgoals refer to the hidden `randperm` order (`objects.highlight_ids`); all targets are highlighted simultaneously (window 10–100) so nothing in the video establishes an order. Native with colour suffix is ambiguous whenever two targets share a colour (hard ep3/7/11 blue,blue; medium ep2 green,green: 4/6 multi-target native eps); xhard (colour omitted by plan J4) is ambiguous in 12/12. Only grounded coordinates / choice point disambiguate.

## Checked, no finding
- Highlight count and identity: every target has a visible white disk; no non-target overlaps a disk; grasp order = highlight_ids order; picks = highlight_count (4/5/6/7).
- Disk merging (C3) present in new tiers (e.g. xhard4 ep0: 3 white components for 7 targets) and native (medium ep10, hard ep7); plan V4 C3 user-decided "先不动"; each target cube still visibly sits on white and no non-target does ⇒ not reported.
- D4 button failure lambda only in xhard, HSV colours, colour-suffix omission, no fail-recover in new tiers: plan-declared (V4 2.12/H2/J3/J4; recovery_rule in specs header).
- Episode lengths 705–1257 frames (< 1301). Ordinal table covers "seventh".

## Excluded, seen
F1 (terminal button phrase + "highlighteted"), D3 (auto highlight at steps 10–100, not button-triggered).
