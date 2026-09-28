# 拆包阶段 3：`src/robomme` 回退到官方 `1fadc0ec`（P2，2026-09-28）

计划：`0927-robomme-hard-layered-plan.md` 第二部分 §1.4；授权：用户 2026-09-28「阶段 3 回退 src/robomme 时的逐文件批准 全部同意」（U-21）。

## 一、清单核对（与 U-21 的 39 项逐项比对）

`git diff --name-status 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 HEAD -- src/robomme`（HEAD = 12.207）：30 M + 9 A = 39，与预期集合逐项相同（`M_equal=True A_equal=True total=39`），无多出或缺少的文件。

- M（30）：16 个环境类 `robomme_env/{BinFill,ButtonUnmask,ButtonUnmaskSwap,InsertPeg,MoveCube,PatternLock,PickHighlight,PickXtimes,RouteStick,StopCube,SwingXtimes,VideoPlaceButton,VideoPlaceOrder,VideoRepick,VideoUnmask,VideoUnmaskSwap}.py`；8 个 utils `{difficulty,object_generation,route,segmentation_utils,subgoal_language,task_goal,subgoal_planner_func,vqa_options}.py`；`env_record_wrapper/RecordWrapper.py`（冻结文件，`fail_safe_limit` 5000 → 官方 2000；`robomme_hard` 副本保留 5000）；`env_record_wrapper/episode_config_resolver.py`（去掉 `from_v4_specs` 并列路径）；四份 train 元数据 `record_dataset_{ButtonUnmask,ButtonUnmaskSwap,VideoUnmask,VideoUnmaskSwap}_metadata.json`（400 条 → 官方 100 条；400 条已在阶段 1 `cp` 进 `robomme_hard/env_metadata/train`）。
- A（9，`git rm`）：`utils/{bin_collision,episode_spec,sampling_config,swap_uniform,unmask_distractor_sampler,unmask_distractors,unmask_swap_xhard,xhard,xhard_home_site}.py`。

执行：逐个 `git checkout 1fadc0ec50316b60ddcfd8e82ac62ef2b70c18f9 -- <文件>`（固定 sha，不整树 checkout），再 `git rm` 9 个新增文件；`git status --short -- src/robomme` = 30 M + 9 D，与清单对上后提交。

## 二、判定行（真实官方态，不再设 PYTHONPATH）

```text
UPSTREAM_BYTES=PASS src_commit=1fadc0ec files=102 diff=0 shims=18
VENDOR_SAME=PASS files=4 orchestration_commit=d53f21a7
SHIMS=PASS shims=18
ABS_IMPORT=PASS files=44 retargeted=27 kept=3 unresolved=0
BORROWED_DEPS=PASS shims=18 copied=33 changed_hits=0
UPSTREAM_NET=PASS net=ok tree=3006988f        （git fetch 官方远端复核）
UPSTREAM_GUARD=PASS                           （--require-upstream）
REGISTRY_OWNER=PASS envs=16 owner=robomme_hard（三种导入顺序）
NAMESPACE_OWNER=PASS envs=16 stray=0          （三种导入顺序）
WRAPPER_CHAIN=PASS action_spaces=4 chain_equal=4 hard_modules_ok=4
STATE_MACHINE=PASS cases=4
PACKAGED_XHARD1..4=PASS；SOURCE_POOL=PASS raw=1717 dedup=89 merged=1628 delivery=1100 nondelivery=528
SPECS_IDENTITY=PASS files=6 legacy_equal=6；DELIVERY_SET=PASS equal=1100 cells=55；H5_BINDING=PASS compared=1100 mismatch=0 missing=0
S4_SUBSET=PASS s4=165 seed_match=165 spec_exact=154 spec_within_tol=11 max_abs=1.2e-07 injected_diff=0
FREEZE_EQUIV=PASS tiers=4 rows=550 selected_equal=165
HARD_RESET_REPLAY=PASS resets=1 replay=1 injected_mismatch=0 recorded_drift=0 max_abs=0 goal_mismatch=0 errors=0 shape=limit1
FREEZE_ONLY_JSONL=PASS files_written=1        （identity=f1e4c0ee1f82，与回退前逐位相同）
ROLLBACK_WRITE=PASS identity_unchanged=1 delivered=1
NATIVE_SMOKE=PASS side=O … success=1 ；NATIVE_SMOKE=PASS side=H … success=1   （两侧 h5 sha 同为 605a26cb…，与回退前相同）
HARD_EVAL_SMOKE=PASS task=BinFill episode=0 tier=xhard1 seed=8400000 episodes=80 max_steps=1500 injected_mismatch=0
TESTS_COLLECT：1296 tests collected，0 error
```

核心短测 `4 failed, 1177 passed, 4 skipped`（182.4 s）。4 个失败在官方 `1fadc0ec` 自己的 worktree（`artifacts/hard-split/official-1fadc0ec`）里用同一解释器跑 `tests/lightweight/test_TaskGoal.py tests/lightweight/test_step_error_handling.py` 同样失败（`4 failed, 27 passed`），是上游测试自身的失败，与拆包无关。

## 三、预算计数

本阶段 reset 3（单局 reset 1 + FREEZE_ONLY 2），rollout 4（ROLLBACK 1 + NATIVE 2 + EVAL 1）。累计：rollout 8／638（本机冒烟额度 8 用满，与计划 §3.1 相同），reset 6 + 8 = 14／715。
