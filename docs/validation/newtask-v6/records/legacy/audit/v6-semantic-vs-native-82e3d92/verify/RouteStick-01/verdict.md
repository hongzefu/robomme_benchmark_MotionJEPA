[内部产出，英文] RouteStick-01 verification note (see reasoning field for authoritative summary).

CONFIRMED. Independently reproduced from raw HDF5 (not just trusting prior audit JSON):
- native easy ep0 seed16000: t93 real subgoal -> t94-99 'NO RECORD' (matches finding exactly, total_timesteps=200)
- native hard ep3 seed16300: t243 real -> t244-249 'NO RECORD' (total_timesteps=500, demo half)
- native medium ep10 seed17000: t193 real -> t194-199 'NO RECORD' (total_timesteps=400)
- new-tier xhard1 ep0 seed9600000: t493 real -> t494-499 'NO RECORD' (total_timesteps=1000, demo half)

Source (git show 82e3d922...:src/robomme/robomme_env/RouteStick.py::_load_scene):
tasks.append blocks at the pick-up-stick stage and the "place the stick into the tube"
stage both hard-code name/subgoal_segment = "NO RECORD" (lines matched via grep, not
line-numbered here per repo rule 9). This code path is identical regardless of difficulty
or _xhard_segment_count_range() -- segment count only changes the middle swing-segment
loop, not the first/last placeholder tasks. Hence identical behavior across easy/medium/
hard/xhard1-4 is a structural property of shared code, confirming category=native_same.
