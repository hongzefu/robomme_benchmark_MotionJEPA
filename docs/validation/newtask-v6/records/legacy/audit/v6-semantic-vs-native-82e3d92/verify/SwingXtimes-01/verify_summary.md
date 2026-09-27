[内部产出，英文]
以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。

# Verification of finding SwingXtimes-01

Verdict: CONFIRMED (independently reproduced from AUDIT_BASE source + data, not by trusting the finding's own text).

## Source-side reproduction (AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1)
- `src/robomme/robomme_env/SwingXtimes.py::SwingXtimes._load_scene`: local `ordinals = [first..tenth]` (10 entries), loop `for i in range(self.num_repeats): ordinal = ordinals[i] if i < len(ordinals) else f"{i+1}th"`. Confirmed via `git show <sha>:path`.
- `config_xhard4 = {'number_min': 10, 'number_max': 11, ...}` and `scripts/configs/newtask-v6/sampling_config.json` `.tasks.SwingXtimes.decision.number_range.xhard4 = [10, 11]` both confirmed at AUDIT_BASE. Native tiers cap at hard=3/easy=[1,3]/medium=[1,2]; xhard1-3 cap at 9 ([4,5]/[6,7]/[8,9]). Only xhard4 can reach num_repeats=11 (i index 10), which is the only value that overflows the 10-entry list.
- `src/robomme/robomme_env/utils/task_goal.py` has a *second*, independent ordinal dict `num2words_2` that already includes `11: "eleventh"` (goes to 20), proving the project already has a word-based ordinal table elsewhere; `SwingXtimes._load_scene` simply doesn't use it and keeps its own truncated local list. Also confirmed the top-level goal sentence for SwingXtimes uses the *cardinal* dict `num2words` (has 11→"eleven") via `get_language_goal()/env=="SwingXtimes"`, so the delivered goal text does say "... repeating this back-and-forth motion eleven times ..." while round-11 subgoals say "11th" — an internal inconsistency confirmed at the source level.

## Data-side reproduction (independent re-derivation, not copied from the finding)
Read HDF5 directly with h5py (script run under project venv, read-only, `uv run --no-sync`):
- `xhard4/.../SwingXtimes_episode_0/hdf5_files/SwingXtimes_ep0_seed6300000.h5`: `info/simple_subgoal` and `info/grounded_subgoal` text extracted across all 1261 timesteps. Rounds 1-10 (timesteps 114-955) read "... for the first time" through "... for the tenth time" (all word ordinals). Round 11 (timesteps 1000 and 1044) reads "move to the top of the right-side target for the 11th time" and "... left-side target for the 11th time" — numeric fallback, exactly as claimed.
- `xhard4/.../SwingXtimes_episode_6/hdf5_files/SwingXtimes_ep6_seed6300600.h5`: same pattern, round 11 at timesteps 895/934 reads "11th".
- Extracted video frames 1005/1030/1049 from ep0's xhard4 mp4 (saved under `frames/`) — overlay text visible reads "11th", cube visibly at/near the correct target, confirming the behavior (grounding) is correct and only the ordinal word format is inconsistent.
- Full extracted text log with per-timestep-family listing at `subgoal_texts.json` in this evidence dir.

## Category check
- `new_tier_only` is correct: native tiers (easy/medium/hard) cap num_repeats at 3, and xhard1-3 cap at 9 — none of them can ever produce round index ≥10 (0-indexed i=10), so the truncated `ordinals` list is only ever exhausted by xhard4. This is not a native-vs-new mismatch of a shared code path behaving differently by config value; it is new-tier-only exposed behavior. `native_same` does not apply (native tiers never exercise this branch); `native_vs_new_mismatch` doesn't fit either since there's no native reference frame for round 11 to compare against — the bug is purely a data-range vs. hardcoded-list-length mismatch introduced by config_xhard4's own number_range.

## Duplicate check against excluded list
Not a duplicate of F1-F6, D1-D7, or the blanket left/right or website-text exclusions. Excluded list is entirely about label/phrase semantics for other envs, or left/right framing, or website-only text — none of which touches SwingXtimes ordinal-word formatting for round ≥11. Not a duplicate.

## needs_new_simulation
No new simulation needed — the claim is fully verifiable from already-delivered data (xhard4 ep0 and ep6, both already containing num_repeats=11 rounds) and from AUDIT_BASE source. No simulation_request required.
