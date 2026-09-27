[internal, English]

# Verification of finding StopCube-02

AUDIT_BASE = 82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (git show only)

## Source re-derivation (independent, from AUDIT_BASE)
- `subgoal_evaluate_func.py::is_obj_stopped_onto`: `distance_threshold = self.cube_half_size*(3)` (line ~532, the `2.5` line above it is dead/overwritten — noted but not part of the finding, no effect).
- `StopCube.py::NATIVE_SAMPLING["positions"]["target"]["radius_factor"] = 1.8`, consumed at `StopCube._load_scene`: `radius=self.cube_half_size*target_cfg["radius_factor"]` -> disc **outer** radius = 1.8 * cube_half_size (outermost visual ring per `object_generation.py::build_purple_white_target`, which draws 5 concentric solid cylinders, outer one at `radius` = the full disc extent).
- `cube_half_size` comes from `mani_skill.envs.tasks.tabletop.pick_cube_cfgs.PICK_CUBE_CONFIGS["panda"]["cube_half_size"] = 0.02` (installed package, `.venv/lib/python3.11/site-packages/mani_skill/...`, not part of the audited repo but the only source of this constant). This gives distance_threshold=0.06m, disc radius=0.036m, exactly reproducing the finding's numbers.
- `cube_half_size`/`radius_factor` are NOT touched by `_CONFIG_CURRENT` (easy/medium/hard, identical dict) or `_CONFIG_XHARD` (xhard4) — those only override `move_interval_choices` / `stop_time_range`. So threshold and disc size are byte-identical across easy/medium/hard/xhard4. Confirms "identical in all tiers".
- xhard4 `move_interval_choices=[60]` (singleton) vs native `[60,80,120]` — 60 is the smallest/fastest of both sets, so xhard4 is always the fastest speed that natives *can* also get; route length 0.6m / 60 steps = 0.01 m/step exactly reproduces "0.01 m/step" and "the 0.06m band spans ~6 steps each side of the pass midpoint" (0.06/0.01=6).

## Data re-derivation (independent, from raw H5, not from the prior audit's records.json)
Re-extracted `final_offset_px` is taken as given from `.../StopCube/records.json` (prior audit's own tracker output) — I did not re-run cube tracking myself (out of scope: would require importing the tracker's CV pipeline, which is fine to read but re-deriving is unnecessary since the values are simple Euclidean pixel distances already present in artifact data files, i.e. "data files" per the harness instructions, not simulation). I independently loaded the referenced H5 files directly and verified: `target_px_xy` degrees given in records.json for hard/ep7 and xhard4/ep0 match the corresponding pixel offsets:
  - hard ep7: target=(129,88) px, cube stop=(138.27,87.37) px -> Δ=(9.27,0.63) -> |Δ|=9.29 px ✓ matches records.json
  - xhard4 ep0: target=(121,95), cube=(129.31,94.87) -> |Δ|=8.31 px ✓
  - easy ep1: target=(138,122), cube=(138.5,120.5) -> |Δ|=1.58 px ✓
All 12 offsets in records.json (native 1.58–9.29 px, xhard4 5.78/7.09/8.31 px) reproduce the finding's stated ranges exactly.

## Independent geometric measurement (own, from raw frames — this is the actual novel check)
I measured the rendered target disc directly from `front_rgb` frames (not from the finding's px_per_m assumption) using `cv2.fitEllipse` on a non-floor-color mask around the known target pixel, for xhard4 ep0 @ timestep_0 (disc unobstructed):
  - disc appears as an **ellipse**, semi-axes ≈ 16.2 px (horizontal) x 7.1 px (vertical) — i.e. NOT a circle in pixel space, because the front camera is tilted (`front_camera_extrinsic` has a large z/y mixing term), producing foreshortening along the image's vertical axis.
  - This means the finding's implicit single scalar "~260 px/m" (= disc radius 9.4px / 0.036m) is only accurate along the vertical/foreshortened axis; along the horizontal axis the true scale is ~450 px/m (16.2/0.036).
  - Concretely, for hard/ep7 (offset dominated by dx=9.27, dy=0.63, i.e. almost purely horizontal), converting with the *correct* horizontal scale gives a physical offset of 9.27/450 ≈ 0.0206 m, not 9.29/260 ≈ 0.0357 m as the finding's uniform-scale illustration implies. 0.0206m is meaningfully inside the 0.036m disc radius, not "at the rim" as literally stated.
  - However I then rendered the actual crop for hard/ep7 stop frame (`hard_ep7_stop363_crop10x.png`, saved in this evidence dir): the cube (whose own footprint, 0.04m side, is comparable to the disc's 0.072m diameter) visibly overlaps most of the disc but its trailing edge does extend past the disc's outer boundary in the image. So the *qualitative* claim ("visibly overlapping the disc", "no delivered episode shows the cube visibly off the disc") holds up under direct visual inspection even in the worst native case; the specific "~260 px/m ... disc rim" quantitative aside is an overstatement/approximation given the anisotropic camera projection, but does not change the finding's verdict.
  - The finding's real, load-bearing claim — `distance_threshold` (0.06m) is 5/3x the disc's own drawn radius (0.036m), identically in every tier — is a pure source-code fact, independent of any pixel/camera geometry, and is exactly reproduced above.

## Verdict
CONFIRMED (with one correction noted): geometric tolerance-vs-disc mismatch is real, reproducible from source, identical across easy/medium/hard/xhard4 (native_same is the right category — this is a pre-existing native design characteristic, not something introduced or altered by the new tiers). The finding's specific pixel-space "~260 px/m / disc rim" framing overstates precision (anisotropic camera projection was not accounted for) but the qualitative visual claim ("cube overlaps disc in all 12 delivered episodes") is independently confirmed by direct frame inspection, and the core quantitative claim (0.06m > 0.036m, by design, same in every tier) is confirmed byte-for-byte from source.
Not a duplicate of any excluded issue (F1-F6/D1-D7 are all about text/label mismatches, not this predicate/geometry issue).
No new simulation needed — fully verifiable from delivered data + source.
