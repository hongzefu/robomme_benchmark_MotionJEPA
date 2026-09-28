# 拆包阶段 0：锚点、vendor、导入扫描、tag 与 bucket（2026-09-28）

计划：[`0927-robomme-hard-layered-plan.md`](../../../../0927-robomme-hard-layered-plan.md) 第二部分 §1.1。开工时 HEAD `4e3e979076ecc1fe61c2d1a58fd4b977e9abafff`（12.204.15），工作区干净。

## 用户原话

- 「/data/hongzefu/robomme_benchmark_MotionJEPANewTask/0927-robomme-hard-layered-plan.md 开工 有问题现在可以立刻问」
- 「记住现在的时间 1小时后就不要中断了跑完为止」——记录时刻 2026-09-28 00:28:58 EDT；01:29 EDT 之后不再请示，按计划 §3.4 停止类只停受影响部分。
- 预算追认（AskUserQuestion）：「批 638/715（推荐）」——生成侧 rollout ≤ 本机 8 + A40 600 + 基础设施重跑 30 = 638；reset ≤ 纯 reset 77 + 每次 rollout 各一次 638 = 715（U-14 原写 635/712，差 3 片 × 1 局 `SHARD_SMOKE`）。

## 官方两锚点

```text
git rev-parse 1fadc0ec…^{tree} → 3006988fed0a708e7dcba906fb663f2475dc8d34
git rev-parse d53f21a7…^{tree} → 1d4c13697f0c5fbd7a8b05e01c196c984a07406c
git diff --quiet 1fadc0ec d53f21a7 -- src/robomme → 退出码 0
```

两个 tree 与计划所记一致。官方 `1fadc0ec` 的只读 worktree 建在 `artifacts/hard-split/official-1fadc0ec`，供「官方态」闸门的 `PYTHONPATH` 使用。

## vendor 与 UPSTREAM.json

四文件由 `git show d53f21a7:scripts/data-generation/<f>` 写入 `scripts/parity/official/scripts/data-generation/`，逐个与隔离树 `artifacts/train-parity/local-smoke-01/official-src/` 同名文件 `cmp` 相同；`SOURCE.json` 记 url／commit／tree／逐文件 sha256。

```text
$ uv run --no-sync python scripts/parity/upstream_guard.py build
UPSTREAM_MANIFEST=WRITTEN files=102 shims=18 vendor=4 manifest_sha256=9406a4ecd0aa
$ uv run --no-sync python scripts/parity/upstream_guard.py check
UPSTREAM_BYTES=PENDING src_commit=1fadc0ec files=102 diff=39 changed=30 extra=9 missing=0
VENDOR_SAME=PASS files=4 orchestration_commit=d53f21a7
SHIMS=FAIL …（18 个 shim 尚未建立，阶段 1 落地）
```

`diff=39` 即阶段 3 要回退的 30 个修改 + 9 个新增，与 U-21 的 39 项数量一致（逐项核对放在阶段 3）。

## 导入扫描（AST，官方 1fadc0ec 源码，相对 + 绝对 + 星号导入，传递闭包）

脚本逻辑已并入 `scripts/parity/upstream_guard.py::check_borrowed_deps`；原始结果 [`records/stage0-import-scan.json`](records/stage0-import-scan.json)。结论与计划第一部分 §3.1 完全一致：闭包干净的 13 个 utils + 4 个 wrapper + `logging_utils` 共 18 项借用；`subgoal_evaluate_func`、`task4recovery`、`DemonstrationWrapper`、`OraclePlannerDemonstrationWrapper` 闭包脏，复制。

| 官方模块 | 分类 | 闭包内改过的模块数 |
|---|---|---|
| `robomme` | 闭包干净 | 0 |
| `robomme.env_record_wrapper` | 闭包脏（复制） | 26 |
| `robomme.env_record_wrapper.DemonstrationWrapper` | 闭包脏（复制） | 23 |
| `robomme.env_record_wrapper.EndeffectorDemonstrationWrapper` | 闭包干净 | 0 |
| `robomme.env_record_wrapper.FailAwareWrapper` | 闭包干净 | 0 |
| `robomme.env_record_wrapper.MultiStepDemonstrationWrapper` | 闭包干净 | 0 |
| `robomme.env_record_wrapper.OraclePlannerDemonstrationWrapper` | 闭包脏（复制） | 22 |
| `robomme.env_record_wrapper.RecordWrapper` | 改过（复制） | 24 |
| `robomme.env_record_wrapper.episode_config_resolver` | 改过（复制） | 23 |
| `robomme.env_record_wrapper.episode_dataset_resolver` | 闭包干净 | 0 |
| `robomme.logging_utils` | 闭包干净 | 0 |
| `robomme.robomme_env` | 闭包脏（复制） | 22 |
| `robomme.robomme_env.BinFill` | 改过（复制） | 22 |
| `robomme.robomme_env.ButtonUnmask` | 改过（复制） | 22 |
| `robomme.robomme_env.ButtonUnmaskSwap` | 改过（复制） | 22 |
| `robomme.robomme_env.InsertPeg` | 改过（复制） | 22 |
| `robomme.robomme_env.MoveCube` | 改过（复制） | 22 |
| `robomme.robomme_env.PatternLock` | 改过（复制） | 22 |
| `robomme.robomme_env.PickHighlight` | 改过（复制） | 22 |
| `robomme.robomme_env.PickXtimes` | 改过（复制） | 22 |
| `robomme.robomme_env.RouteStick` | 改过（复制） | 22 |
| `robomme.robomme_env.StopCube` | 改过（复制） | 22 |
| `robomme.robomme_env.SwingXtimes` | 改过（复制） | 22 |
| `robomme.robomme_env.VideoPlaceButton` | 改过（复制） | 22 |
| `robomme.robomme_env.VideoPlaceOrder` | 改过（复制） | 22 |
| `robomme.robomme_env.VideoRepick` | 改过（复制） | 22 |
| `robomme.robomme_env.VideoUnmask` | 改过（复制） | 22 |
| `robomme.robomme_env.VideoUnmaskSwap` | 改过（复制） | 22 |
| `robomme.robomme_env.utils` | 闭包脏（复制） | 22 |
| `robomme.robomme_env.utils.SceneGenerationError` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.adjacent` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.choice_action_mapping` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.constant` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.difficulty` | 改过（复制） | 0 |
| `robomme.robomme_env.utils.generate_sample_action` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.object_generation` | 改过（复制） | 0 |
| `robomme.robomme_env.utils.obschange` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.oracle_action_matcher` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.planner_denseStep` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.planner_fail_safe` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.reset_panda` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.route` | 改过（复制） | 0 |
| `robomme.robomme_env.utils.rpy_util` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.save_reset_video` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.segmentation_utils` | 改过（复制） | 0 |
| `robomme.robomme_env.utils.statechange` | 闭包干净 | 0 |
| `robomme.robomme_env.utils.subgoal_evaluate_func` | 闭包脏（复制） | 22 |
| `robomme.robomme_env.utils.subgoal_language` | 改过（复制） | 0 |
| `robomme.robomme_env.utils.subgoal_planner_func` | 改过（复制） | 22 |
| `robomme.robomme_env.utils.task4recovery` | 闭包脏（复制） | 22 |
| `robomme.robomme_env.utils.task_goal` | 改过（复制） | 0 |
| `robomme.robomme_env.utils.vqa_options` | 改过（复制） | 22 |

## tag 与 bucket

```text
$ git tag pre-hard-split 7c7118fa5e9a0872c9cca90e4ac119ddc10892fc && git push origin pre-hard-split
 * [new tag]           pre-hard-split -> pre-hard-split
$ git ls-remote --tags origin pre-hard-split
7c7118fa5e9a0872c9cca90e4ac119ddc10892fc	refs/tags/pre-hard-split
$ git diff --stat 7c7118fa ca32e9b -- src/   → 空（P 侧 tag 与生产代码基线 src 零 diff）
$ uvx --from huggingface_hub==1.8.0 --with click hf buckets create HongzeFu/robomme-hard-parity --private
Bucket created: https://huggingface.co/buckets/HongzeFu/robomme-hard-parity
$ uvx --from huggingface_hub==1.8.0 --with click hf buckets list HongzeFu | head -3
ID                                  PRIVATE         SIZE TOTAL_FILES CREATED_AT
HongzeFu/robomme-hard-parity        ✔                  0             2026-09-28
```

`huggingface_hub==1.8.0` 的 uvx 临时环境缺 `click`，补 `--with click`（一次性工具环境，不进项目依赖）。

## 开工时集群与本机快照

```text
$ squeue -u hongzefu -o '%i %j %T %L %N %m %C %b'
62126062 hs-hold-20260927-3 RUNNING 1-20:04:37 gl1506 192G 16 gres/gpu:1
62126061 hs-hold-20260927-2 RUNNING 1-19:26:49 gl1504 192G 16 gres/gpu:1
62126060 hs-hold-20260927-1 RUNNING 1-17:37:00 gl1517 192G 16 gres/gpu:1
62018665 v6gen-hold-3-20260926 RUNNING 18:27:06 gl1510 192G 16 gres/gpu:1
$ df -h /data → 14T 13T 833G 94%；NFS turbo 剩 5.2T
```

本机既有 tmux 会话 `claude-newtask`、`corlvis-site`、`smvla-site-8060` 不属本方案，一律不动。
