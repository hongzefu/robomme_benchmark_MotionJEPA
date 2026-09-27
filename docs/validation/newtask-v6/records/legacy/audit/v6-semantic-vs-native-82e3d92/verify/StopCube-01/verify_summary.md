[内部产出，英文] Internal working notes; the consuming main agent must still speak Chinese to the user.

# StopCube-01 verification

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1

## Reproduced independently

1. `git show 82e3d922...:src/robomme/robomme_env/StopCube.py`:
   - `NATIVE_SAMPLING["parameters"]["motion_segments"] = 5` (descriptive-only doc block).
   - `_initialize_episode`: `self.motion_segments = max(5, int(stop_time)) if xhard else 5`.
   - `step()`: `segments = range(self.motion_segments)` for xhard, `range(5)` for native tiers.
   - Comment in source itself acknowledges: "原三档在 step 里写死 5 趟...xhard 的 stop_time 可达 15，必须按实际停止序号展开".

2. `git show 82e3d922...:scripts/configs/newtask-v6/sampling_config.json` → `tasks.StopCube.native.parameters.motion_segments == 5`, no `xhard4` override key present anywhere in the `native` block. Confirms the value is never corrected for xhard4.

3. `artifacts/newtask-v6/v6-01/xhard4/rollout/run1/_rounds/round_00/specs.json`:
   - StopCube/0: motion_segments=6, stop_time=6
   - StopCube/3: motion_segments=14, stop_time=14
   - StopCube/6: motion_segments=15, stop_time=15
   All three exceed the config-documented value of 5.

4. H5 `StopCube_ep6_seed6200600.h5` (episode_6), independently opened with h5py:
   - `setup/task_goal` = "press the button to stop the cube just as it reaches the target for the fifteenth time" (language ordinal matches stop_time=15; language layer unaffected as claimed).
   - 902 timesteps (`timestep_0..timestep_901`), matching mp4 frame_count=902 (verified myself via cv2, independent of the prior audit's own count).
   - `timestep_868/info`: `is_completed=True`, `grounded_subgoal="press the button to stop the cube on the target at <90 137>"` — confirms frame 868 is indeed the actual episode-terminating stop event, matching the finding's claim of stop on the "15th approach at frame 868".
   - `timestep_811/info`: `is_completed=False`, cube visually near target region in the saved frame — consistent with an earlier (14th) approach before the final stop.

## Conclusion

The finding's core claim — that xhard4 runs `max(5, stop_time)` segments while the delivered/native config still documents `motion_segments=5`, and delivered specs record higher values (6/14/15) — is verified directly from AUDIT_BASE source, the config snapshot, delivered specs.json, and independently-read HDF5/mp4 data. Not a duplicate of any excluded issue (F1-F6, D1-D7, left/right, website-text). Category `new_tier_only` is correct: this discrepancy only exists for xhard4; easy/medium/hard always use exactly 5 segments matching the config value.
