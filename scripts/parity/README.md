# scripts/parity/：与官方比

拆包后（[0927 计划](../../docs/plans/0927-robomme-hard-layered-plan.md)）本目录只做「与官方比」。新值档的生产链路在 [`../injection-dev/`](../injection-dev/)，新值环境源码在 [`src/robomme_hard/`](../../src/robomme_hard/README.md)。

| 文件 | 干什么 |
|---|---|
| `official/` | 官方生成编排 `d53f21a7:scripts/data-generation/` 四文件逐字节 vendor（`generate_dataset.py` 依赖另三个）；`SOURCE.json` 记 url／commit／tree／逐文件 sha256。不得修改（红线 R2） |
| `upstream_guard.py` | G1 守卫：`build` 生成 `src/robomme_hard/UPSTREAM.json`；`check` 输出 `UPSTREAM_BYTES`（`src/robomme` 与官方 `1fadc0ec` 逐字节）、`VENDOR_SAME`、`SHIMS`、`ABS_IMPORT`、`BORROWED_DEPS`（借用 shim 目标在官方源码上的传递闭包不含任何被复制的模块），`--require-upstream`、`--net`；`manifest-md` 出复制／借用／子类／新增逐文件表。纯 CPU、秒级 |
| `train_split_runner.py` | 隔离运行器：用 vendor 的官方编排调官方 `_worker`（A 路：`--src-root` 指官方源码树；P 侧：指 tag `pre-hard-split` 的 worktree）或镜像 worker（`--force-mirror`／`--sampling-config`／`--episode-specs`）。`--official-root` 默认 `official/`，此时 `--src-root` 必填；`--metadata-root` 显式把官方 train 元数据根（原默认 `configs/newtask-v3/official_train` 已于 12.214 删除，须显式传入或从提交 `6e70c0bf` 取回；核 `records_sha256`）传给官方 `read_train_metadata`；逐局追加 `results.partial.jsonl` 并 fsync，`--resume` 续跑 |
| `train_split_worker.py` | 镜像 worker：官方 `_worker` 的最小镜像，只多传 `sampling_config`／`native_episode_spec`；环境包由 `ROBOMME_ENV_PACKAGE`（`robomme`／`robomme_hard`）决定，结果记 `env_module`／`wrapper_modules` |
| `train_split_config.py` | 从环境源码提取 `sampling_config`（`extract --pkg robomme_hard --release newtask-v6`；缺省落点 `artifacts/hard-split/`） |
| `train_split_parity.py`、`train_split_comparison.py`、`train_split_audit.py`、`comparator_fixtures.py` | S0 原始 train 五路逐位对拍设施（`compare_h5_pair` 等），见 git 历史里 V3 的说明 |
| `hard_parity.py` | 三侧对拍入口（O 官方 / P 修改前 / H 修改后）：`generate`（A40 断言、每局 sha 后搬到 NFS 暂存并写 `SHIPPED`）、`publish`（上传 bucket `HongzeFu/robomme-hard-parity` 并逐对象读回核 sha → `BUCKET_SYNC`）、`compare`（判定层 + 容差层 + 参考层 → `PARITY_*`；`--calibrate` 只许 O:P，按 U-22 规则写 `configs/hard-parity-tolerances.json`）、`import-s4`（P 侧 xhard = S4 交付存档）、`binding`（`ENV_PACKAGE_BINDING`） |
| `hard_pull.py` | sled-vail 上逐局拉取：NFS 暂存 → `/data` → 核 sha → 删 NFS 副本（只拉带 `SHIPPED` 的局） |
| `hard_regression.py` | `s4-subset`（S4 165 局是 1100 局交付集的子集，回注点逐位、记录点 ≤ 1e-5）、`reset-replay`（55 次回注 reset 经 builder 评估链）、`eval-smoke`（合作者入口冒烟） |
| `results/` | 历史日志（被 ignore，按计划不删） |

## 对拍判定（行为一致，用户 U-1）

- **每侧自检**：身份唯一、h5 `setup` 的 seed／difficulty 与身份一致、`timestep_*` 连续、数据集可读。
- **判定层（全等才 PASS）**：身份集合、`setup`（seed、difficulty、task_goal、多选项、相机内参）、结构（数据集名／dtype／shape 集合，不比帧数）、任务成功相等且双侧各自成功（`both_success`，同失败不算相等）、包归属（`ENV_PACKAGE_BINDING`）。
- **容差层（U-19）**：共同前缀（两侧按时间步对齐的公共长度）上的 `action_max`（`joint_action` 最大绝对差，rad）、`state_max`（`joint_state`／`gripper_state`）、`image_mad`（前视与腕视 RGB 逐像素平均绝对差的每身份均值，取最大）、`frames_max`（帧数差）。阈值只从 `configs/hard-parity-tolerances.json` 读（R21），由 `compare --pair O:P --calibrate` 按「O:P 最大值 × 1.5，下界 0.005/0.005/1.0/5，合理性上界 0.05/0.05/10/200」写入。
- **参考层（INFO）**：`sha_equal`、帧数相等数、首个分叉时间步分布。

判定不做字节级：mplib RRT 的墙钟预算让 16 worker 并发下同身份轨迹分叉（见 `docs/validation/newtask-v3/20260921-worker-nondeterminism.md`）。

## 历史

2026-09-22 起本目录由 `scripts/test-vs-original/` 改名而来。拆包前的「vs 原版发布集容差校验」全文（`tolerance.json` 三档、16x3 身份与实测结果）以及 V4/V5 的 `v4_specs`／`v4_rollout`／`v5_generation` 说明已移出，原文见 `git show 7a6cee35:scripts/parity/README.md`。
