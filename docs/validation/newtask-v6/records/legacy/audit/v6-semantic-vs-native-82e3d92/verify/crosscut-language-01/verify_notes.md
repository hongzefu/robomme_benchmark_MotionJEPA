[Internal, English] Verification of finding crosscut-language-01 (SwingXtimes xhard4 11th ordinal digit vs "eleven" word in goal).

AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1 (confirmed via `git rev-parse HEAD`, porcelain clean).

1. Source anchor confirmed via `git show <BASE>:src/robomme/robomme_env/SwingXtimes.py`:
   - line ~584: `ordinals = ["first", ..., "tenth"]` (10 entries)
   - line ~586: `ordinal = ordinals[i] if i < len(ordinals) else f"{i+1}th"` — for round index i=10 (the 11th round, 0-indexed), falls through to digit format "11th".
   - Used at lines ~589/590/604/605 in subgoal `name`/`subgoal_segment` f-strings.

2. Goal-text generator confirmed via `git show <BASE>:src/robomme/robomme_env/utils/task_goal.py`:
   - `num2words` dict (lines 1-22) covers 1..20 as words, including 11 -> "eleven".
   - SwingXtimes branch (lines ~110-117) uses `word = num2words.get(repeats, str(repeats))` and embeds it as "...repeating this back-and-forth motion {word} times...". For repeats=11 -> "eleven times".
   - So goal text always uses full word ordinals up to 20 reps, but per-round subgoal ordinal list only covers up to 10 -> digit fallback exactly at round 11. Confirmed code-level inconsistency between two independently-written ordinal tables (0-9 word list vs 1-20 word dict).

3. Plan check: `git show <BASE>:0925-newtask-release-v6-plan.md` section 三 (line ~66) confirms SwingXtimes xhard4 num_repeats=[10,11], distractor=3. No mention anywhere in the plan of subgoal ordinal wording, i.e. this digit/word mismatch is an unplanned side effect of extending num_repeats beyond native's max of 3, not a documented design choice.

4. Data evidence reproduced independently (not copied from the audit's checks.json) via h5py on
   artifacts/newtask-v6/v6-01-infra-recovery-01/rollout/run1/episodes/SwingXtimes_episode_0/hdf5_files/SwingXtimes_ep0_seed6300000.h5:
   - setup/difficulty = b'xhard4'
   - setup/task_goal = [b'...repeating this back-and-forth motion eleven times, finally press the button to stop', b'...repeating this right-to-left swing motion eleven times, then put down the cube and press the button to stop']
   - Full grounded_subgoal boundary scan (all 1261 timesteps) shows monotonic ordinal progression 'first'..'tenth' at boundary timesteps 114..955 (rounds 1-10), then at timestep_1000 and timestep_1044 (rounds 11, right/left) grounded_subgoal reads "...for the 11th time" (digit form) instead of "eleventh". This exactly matches the finding's cited evidence_paths (same file, same timestep ids 1000/1044).
   - Episode has exactly 11 right+11 left swing rounds (22 boundary subgoals) + put-down + button-press, matching num_repeats=11 spec and the goal's "eleven times" claim — i.e. the counted behavior is fully consistent with the language; only the ordinal surface form (digit vs word) is inconsistent at round 11.

5. Native-tier comparison: native (easy/medium/hard) num_repeats <= 3 (hard=3 per plan/native spec), so index i never reaches 10 in the ordinals list; the digit-fallback branch `f"{i+1}th"` is structurally unreachable in native tiers. This bug is exclusively reachable in xhard4 (the only tier with num_repeats > 10). Category new_tier_only is correct.

VERDICT: CONFIRMED. High confidence, reproduced independently from AUDIT_BASE source and from a fresh read of the delivered HDF5 file (not reused from the prior audit's checks.json, though the result matches it exactly).

No duplicate of any excluded issue (F1-F6, D1-D7, left/right wording, website-text) — this is a subgoal-text digit/word ordinal formatting bug, not a left/right or website issue.

Category: new_tier_only (confirmed correct as classified). No simulation needed — fully verified from static source + already-delivered episode data.
