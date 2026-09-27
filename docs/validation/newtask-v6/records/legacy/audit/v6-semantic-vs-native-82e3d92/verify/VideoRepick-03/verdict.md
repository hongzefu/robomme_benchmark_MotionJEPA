[内部产出，英文]
以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。

VERDICT: CONFIRMED (native_same, as originally categorized)

Independent evidence (all read via `git -C ... show 82e3d922...:<path>`, AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1):

1. Source (task_goal.py, VideoRepick branch, get_language_goal): template text is exactly
   "watch the video carefully, then repeatedly pick up and put down the same block that was
   previously picked up for {word} times, finally put it down and press the button to stop"
   for num_repeats>1 (line ~201), applying uniformly to ALL difficulties (no tier branch in
   this function).

2. Source (VideoRepick.py::_initialize_episode): task chain built by
   `for i in range(self.num_repeats): [pick-up task, put-down task]` then a single trailing
   `press the button to finish` task appended once, outside the loop. This is the SAME code
   path for every difficulty (easy/medium/hard/xhard1-4) — num_repeats value differs by tier
   sampling range, but the loop/task-construction logic itself has zero tier-specific branching.
   => structurally, exactly N pick+put-down pairs are ever generated, never N+1.

3. Data reproduction from records.json (independently re-derived by counting subgoal_segments,
   not trusting the finding's own numbers):
   - native easy ep1 (N=3): non-demo pickups=3 (343-453,510-631,689-759), non-demo putdowns=3
     (454-509,632-688,760-817), button=818-893. Exactly 3 pairs, no 4th put-down.
   - new xhard4 ep3 (N=6): non-demo pickups=6 (816-927 ... 1503-1575), non-demo putdowns=6
     (928-982 ... 1576-1629), button=1630-1680. Exactly 6 pairs, no 7th put-down.
   These two independently-recomputed counts match the finding's claim exactly and match each
   other structurally (native vs new-tier both produce N pairs, no bonus final put-down).

Conclusion: the "finally put it down" clause is language padding describing the Nth
(last) put-down of the loop, not an instruction for an (N+1)th put-down. The chain always
has exactly N put-downs matching N pick-ups. This is true identically in native (easy/medium/
hard) and new (xhard1-4) tiers by construction (same function, no tier branch) and confirmed
by direct step-range counts in both a native episode and a new-tier episode.

category_corrected: native_same is correct as filed — behavior is identical across all
tiers, driven by a single shared, non-tier-branching implementation.

Not a duplicate of excluded F2 ("previously picked up N times" phrase, about mismatch between
"previously" and the 1-pick demo video) — VideoRepick-03 is a distinct textual ambiguity
("finally put it down" implying an extra final put-down) in the same template sentence.

No new simulation needed — verified from existing recorded data + source directly.
