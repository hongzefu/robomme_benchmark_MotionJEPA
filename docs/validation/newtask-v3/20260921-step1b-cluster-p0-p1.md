# 步 1b（下半）留档：A40 上的 P1、P0 与 R1a（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 1b 的集群部分。未改动 `src/robomme/`。

## 一、集群侧就位情况

- NFS 副本 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl` 已从 `newtask-v2.1refractor` 切到 `newtaskRelease-v3`（`996bd8b`），工作区干净；`uv.lock`／`pyproject.toml` 散列与本机一致（`ff0ffd84…`／`d03537d6…`），官方 `d53f21a…` 对象与 `.venv`（Python 3.11.14）都在。
- 登录免密可用（ControlMaster 复用连接，未触发 Okta），落在 `gl-login3`。
- **4 个占位 job 全部 RUNNING**：61673583（gl1523）、61673584（gl1508）、61673585（gl1517）、61673586（gl1523，本轮开工时刚从 `AssocGrpCpuLimit` 调度上）。因此 P0 直接按 `jobs=4` 做，未使用先前拍板的 3 job 回退方案。

## 二、跑法

登录节点 tmux 会话 `glsmoke` 里并行发起 4 个 `srun --overlap --exact`（各 1 GPU / 4 CPU / 40 min），同一条 `BinFill/easy/episode_0`（`seed=4000`、`recovery_mode=z`）在每个 job 各跑一次 A1，job 61673583 额外跑 A2；产物按 job 隔离在 `artifacts/train-parity/gl-smoke-01/job<jobid>`，日志汇到 `slurm-holds/gl_smoke_01.log`。

单条耗时（1 worker）：A1 分别为 52.9 s／50.0 s／49.8 s／50.1 s，A2 为 37.1 s（官方源码树已复用，省掉导出）。

## 三、判定行（A40 实测）

```text
H5_PARITY pair=j83.A1|j83.A2 compared=1 sha_equal=1 field_mismatch=0
BASELINE_REPEAT=PASS compared=1 different=0
DATASET_GEN_REPORT_PARITY=PASS compared=4 fields=identity,recovery_mode,success,timestep_count outcome_mismatch=0 detail_mismatch=0

H5_PARITY pair=j83.A1|j84.A1 compared=1 sha_equal=1 field_mismatch=0
H5_PARITY pair=j83.A1|j85.A1 compared=1 sha_equal=1 field_mismatch=0
H5_PARITY pair=j83.A1|j86.A1 compared=1 sha_equal=1 field_mismatch=0
NODE_PARITY=PASS identities=1 jobs=4 mismatch=0
```

- **P1（BASELINE_REPEAT）**：官方基线自身在 A40 上可重复，A1↔A2 整文件 SHA-256 相同，伴生文件（含 MP4）散列也全同。
- **P0（NODE_PARITY）**：同一身份在 4 个 job（3 个不同节点 gl1523／gl1508／gl1517）逐位相同 ⇒ **允许按 task 分片**，不必单 job 串行。
- **R1a（DATASET_GEN_REPORT_PARITY）**：4 个 job 的 A1 结果与步 1a 冻结的历史投影逐条相同（身份、恢复模式、成功、帧数 550）。

## 四、本机与 A40 确实不逐位一致

同一身份的 HDF5：本机（RTX 6000 Ada，sm_89）SHA-256 前缀 `951bc0f5bcf8e85c97b7`，A40（sm_86）为 `d350b5207ffd1bc07077`。这与方案第四节的假设一致，**本机结果只能作调试参考，不进任何判据**；同时也说明 A40 内部（跨节点、跨 job）是稳定的。

## 五、实测的耗时与存储口径

| 项 | 实测 |
|---|---|
| 单条单 worker 耗时（BinFill/ep0，A40） | 约 50 s（首次含官方源码导出约 53 s，复用后 37 s） |
| 单次生成产物 | HDF5 270 MB + 视频 13 MB ≈ 283 MB |
| 官方源码隔离副本 | 每个运行目录 16 MB |
| 144 条 × 5 路 = 720 次生成的存储估计 | 约 200 GB 起（BinFill/ep0 为 550 帧；帧数更长的环境会更大） |
| Turbo 余量 | 31T 中已用 26T，可用 5.5T |

存储够用，但 720 次生成的量级需要在步 5d 前再确认一次；不清理旧产物。

## 六、本步之后的状态与下一步

- 已过：G1、历史冻结、G5、**P0（jobs=4）**、**P1**、**R1a 单条**。
- 下一步（步 2）：恢复原值默认路径并做 A↔B。`run` 已支持 B 路——用**同一份官方编排代码**加载本工作副本的 `src`（官方 `_worker` 只用 `repo_root` 定位 `src`），因此 A↔B 的差异只可能来自环境源码本身。工作副本相对官方 `d53f21a…` 的源码差异集中在：`BinFill.py`、`RouteStick.py`、`VideoRepick.py`、`VideoUnmaskSwap.py`、新增的 `utils/bin_collision.py`，以及 `utils/difficulty.py`（加 xhard 白名单）、`utils/object_generation.py`、`utils/route.py`（`walk_config` 校验入口）。其中已知会改变默认行为的是 `RouteStick.py::step` 的白球尾迹 `cur_step + 10`（官方为 `+ 40`）。
