# 新值注入：候选与实跑

当前链路只有两个生产阶段：`scripts.injection.candidates` 冻结、筛查候选并出图；`scripts.injection.rollout` 从冻结候选生成 HDF5、核验 test 环境并生成数轴及报告。所有命令在仓库根目录执行，Python 由 `uv` 启动。旧流程的历史计划、校准入口及图表工具不再作为现行使用说明。

## 唯一环境输入与 Git 留档

`artifacts/injection/<run-id>/candidates/candidates.jsonl` 是环境启动的唯一数据入口，必须进入 Git。首行为 header，内嵌完整 `sampling_config`、`runtime`、交付配置快照和来源指纹；后续行携带完整旧 `spec`、身份散列、筛查证据及派生角色。统一读取器 `scripts/injection/candidates/io.py::load_candidates` 核对封套版本、完整键集合、内外身份、旧规格散列和采样快照源码指纹。冻结后不再读取外部配置来覆盖快照；显式提供配置时只允许断言相等。

三个消费者的契约如下：

| 消费者 | 选择范围 | 环境参数来源 |
|---|---|---|
| `generate_dataset_newseed.py`，由 `rollout/run.py::execute_scope` 派发 | train 与本次清单的交集 | 行内 spec、header 配置与固定 runtime；单次尝试 |
| `rollout/reset_check.py` | test，按配额或显式最小范围选择 | 同一候选快照；只 make、reset、close |
| 策略侧未来入口 | test 且 role 为 primary | 同一读取契约；本仓库不实现策略侧代码 |

这里的 train/test 是自定义候选划分，均使用 `SeedLayout("train")`，不是官方 test seed 集。reset 通过仅证明能建环境，不能当成能完成任务或能出 HDF5。

配置 `scripts/configs/newtask-v2/injection_contract_v3.json`、`native_sampling.json`、`delivery_400.json` 用于生成候选。v1/v2 仅作为 `tests/fixtures/injection_legacy/` 中的历史测试夹具。生产代码不依赖 tests。

## 运行及恢复

先核验 uv。使用全新运行编号生成正式候选：

```bash
command -v uv
uv run --no-sync python -m scripts.injection.candidates --run-id <新运行编号> \
  --contract scripts/configs/newtask-v2/injection_contract_v3.json \
  --delivery-config scripts/configs/newtask-v2/delivery_400.json
```

候选默认出图与生成 `candidates/DISTRIBUTION.md`。已有候选禁止覆盖；失败重试用新编号。正式大规模仿真前必须先通过单组、单条、单 worker 冒烟。预计超过五分钟的运行必须在 detached tmux 中启动，以 `pipefail`、`PYTHONUNBUFFERED=1`、`tee` 保存完整日志和退出码。

最小独立验证可按以下顺序运行，总预算 280 秒；任何一步失败即停止：

```bash
command -v uv
timeout 280s bash <<'SMOKE'
set -euo pipefail
SMOKE_RUN=refactor-example-smoke
uv run --no-sync python -m scripts.injection.candidates --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --blocks 2
uv run --no-sync python -m scripts.injection.rollout --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --episodes 1 --reset-limit 1 \
  --tier 1 --gpus 0 --label smoke
uv run --no-sync python -m scripts.injection.rollout.reset_check --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --limit 1 --tier 1 --gpus 0 --label smoke
SMOKE
```

示例中的编号须替换为未使用的合法名称。两块共 200 条候选是为了包含从 ep115 起的 test；实际只生成一个 HDF5、核验一个 test 环境。影子候选、结果、图表均在 `rollout/logs/smoke/smoke/`，不回写正式候选。重复调用必须复用终态，输出 `RESET_IDEMPOTENT=PASS rerun=0 duplicates=0`。

正式执行入口为 `uv run --no-sync python -m scripts.injection.rollout --run-id <编号> --tier <每卡worker数> --gpus 0,1`。`--episodes`/`--episode-range` 只取 train 交集，越过冻结候选上界直接拒绝。`--candidates` 从另一运行导入时只读源文件，复制并重置管理状态；来源身份与散列留档。`--no-figures` 仅供诊断，不代表完整交付验收。

每个运行只有一个写入者。`rollout/results.jsonl` 是执行状态依据，主键为 kind 加候选身份；候选角色从它派生。先原子写结果，再回写候选，两个文件不构成整体原子事务。续跑先重放 `logs/attempts/` 中完整终态，再恢复角色，最后只派发缺失键；半行不算终态，同键冲突直接拒绝。成功和失败都复用，不能换 seed 补样本。

普通 reset 达到每组 50 条通过即按原整批收齐规则停止，余下 test 为 unused。`--only-unused` 仅用于既有运行十的 838 条专项补查，冻结完整范围且不改变原 primary。已归档并清理媒体的临时对拍运行拒绝恢复执行。迁移状态非 complete 时，普通读取及执行入口拒绝启动。

## 结果与图表

正式角色按 episode 升序选择，失败顺延，多余成功为 spare；失败和备用路径均保留。报告实际读取成功 HDF5 的大小和 SHA-256 后才通过。`purpose=smoke/parity` 的局部结果与正式交付配额分别判断，局部通过不能当成完整交付。

| 位置 | 内容 |
|---|---|
| `candidates/candidates.jsonl` | 唯一候选输入，Git 跟踪 |
| `candidates/DISTRIBUTION.md`、`candidates/figures/` | 14 组跑前分布及事件表，正式规模 98 张图 |
| `rollout/results.jsonl`、`rollout/ROLLOUT.md` | 唯一结果、角色、配额、失败及视频状态 |
| `rollout/WINDOWS.md`、`rollout/figures/` | 完整数轴与汇总，正式规模 15 张图 |
| 两阶段的 `logs/` | 原始终态、范围、恢复日志、筛查证据及验收 JSON，Git 跟踪 |

窗口长度 33 帧、步长 16 帧，demo 与执行段分别取窗。沿用单段超过 400 帧或有效总长超过组中位两倍的慢条剔除规则，保留完整剔除记录；只从图表统计剔除，不删除 HDF5 或改变交付角色。`rollout/single_binfill.py` 是可选单条图工具，不进入主流程。

HDF5、MP4 和各类图片递归忽略，包含 logs 内嵌套 smoke；只放行正式 `rollout/figures/windows_overview.png` 总览图。候选、结果和轻量日志须逐个明确路径暂存，禁止全量 git add。

## 已有运行十与验证边界

运行十 `20260912-contract-v3-10` 原候选 3400 条：train 1842、test 1558。全量结果为 train 正式 1600、备用 196、失败 46；test 正式 700、备用 858，无失败和 unused。补查未换 seed、未补样本。旧文件按冻结 `rollout/logs/migration/path_map.json` 移动，原始小文件保存在两阶段的 `logs/legacy/`，所有旧媒体保留；活动消费者只读新候选及唯一结果。

验收分开报告：L1 完整规格及采样诊断相等；L2 比较 113 张 PNG 字节、事件表及全部 1796 条数轴记录（保留 1795、剔除 1）；L3 独立重跑 210 条，205 成功 HDF5 散列相同、5 失败类型相同；L4 原 720 个 reset 键结果、停止位置、角色相同。视频诊断有 221 对通过、2 条超时无可比视频，整体保留 NOT_RUN，不冒充全视频对拍通过。完整证据见[实施留档](../docs/validation/newtask-v2/20260917-injection-refactor/README.md)。

`scripts/hf_release.py` 本轮冻结，再次发布须先改为读取 `results.jsonl` 的 role；不能直接沿用已迁移前的交付清单路径。`scripts/injection/delivery.py` 仅为冻结发布脚本保留纯格式化函数 `render_verdict_line`，不是旧交付入口。

短测试命令为 `uv run --no-sync python -m pytest tests/lightweight/ -q`，预算五分钟。旧校准数学判据通过测试专用固定 Git 基线保留，当前采样、筛查、范围、唯一结果、角色、reset、数轴与报告均测试新接口；测试中的历史基线不属于生产依赖。
