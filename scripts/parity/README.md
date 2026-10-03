# scripts/parity/：与官方比

拆包后（[0927 计划](../../docs/plans/0927-robomme-hard-layered-plan.md)）本目录只做「与官方比」。新值档的生产链路在 [`../injection-dev/`](../injection-dev/)，新值环境源码在 [`src/robomme_hard/`](../../src/robomme_hard/README.md)。

| 文件 | 干什么 |
|---|---|
| `official/` | 官方生成编排 `d53f21a7:scripts/data-generation/` 四文件逐字节 vendor（`generate_dataset.py` 依赖另三个）；`SOURCE.json` 记 url／commit／tree／逐文件 sha256。不得修改（红线 R2） |
| `upstream_guard.py` | G1 守卫：`build` 生成 `src/robomme_hard/UPSTREAM.json`；`check` 输出 `UPSTREAM_BYTES`（`src/robomme` 与官方 `1fadc0ec` 逐字节）、`VENDOR_SAME`、`SHIMS`、`ABS_IMPORT`、`BORROWED_DEPS`（借用 shim 目标在官方源码上的传递闭包不含任何被复制的模块），`--require-upstream`、`--net`；`manifest-md` 出复制／借用／子类／新增逐文件表。纯 CPU、秒级 |
| `train_split_runner.py` | 隔离运行器：用 vendor 的官方编排调官方 `_worker`（A 路：`--src-root` 指官方源码树；P 侧：指 tag `pre-hard-split` 的 worktree）或镜像 worker（`--force-mirror`／`--sampling-config`／`--episode-specs`）。`--official-root` 默认 `official/`，此时 `--src-root` 必填；`--metadata-root` 显式把官方 train 元数据根（原默认 `configs/newtask-v3/official_train` 已于 12.214 删除，须显式传入或从提交 `6e70c0bf` 取回；核 `records_sha256`）传给官方 `read_train_metadata`；逐局追加 `results.partial.jsonl` 并 fsync，`--resume` 续跑 |
| `train_split_worker.py` | 镜像 worker：官方 `_worker` 的最小镜像，只多传 `sampling_config`／`native_episode_spec`；环境包由 `ROBOMME_ENV_PACKAGE`（`robomme`／`robomme_hard`）决定，结果记 `env_module`／`wrapper_modules` |
| `train_split_config.py` | 从环境源码提取 `sampling_config`（`extract --pkg robomme_hard --release newtask-v7`，v7 起为默认；缺省落点 `artifacts/hard-split/`） |
| `train_split_parity.py`、`train_split_comparison.py`、`train_split_audit.py`、`comparator_fixtures.py` | S0 原始 train 五路逐位对拍设施（`compare_h5_pair` 等），见 git 历史里 V3 的说明 |
| `hard_parity.py` | 四侧对拍入口（O 官方 / P 修改前 / H 修改后 / H2 第二次生成；档 `native`／`xhard`／`xhard0`／`v8`；v8 起 `v7` 键改 `v8`，`compare` 先核对分母）：`generate`（A40 断言、每局 sha 后搬到 NFS 暂存并写 `SHIPPED`）、`publish`（上传 bucket `HongzeFu/robomme-hard-parity` 并逐对象读回核 sha → `BUCKET_SYNC`）、`compare`（判定层 + 容差层 + 参考层 → `PARITY_*`；`--p-anchor` 按登记的锚点取 P 侧并先核验；两侧都失败单列 `both_fail`；`--calibrate` 只许 O:P，按 U-22 规则写 `configs/hard-parity-tolerances.json`）、`anchor register／check`（锚点登记表 `docs/validation/parity-anchors.json` → `PARITY_ANCHOR`）、`export-xhard0-manifest`（从官方 test 元数据导出 xhard0 192 局清单）、`import-delivery`（v8 gen1 交付清单转对拍清单）、`binding`（`ENV_PACKAGE_BINDING`）。v7 起删去 `import-s4` |
| `hard_pull.py` | sled-vail 上逐局拉取：NFS 暂存 → `/data` → 核 sha → 删 NFS 副本（只拉带 `SHIPPED` 的局） |
| `hard_regression.py` | `delivery-set`／`tier-values`（v8 交付形态、seed 按档隔离、布局独立与档位取值 → `V8_DELIVERY_SET`／`V8_SEED_DISJOINT`／`V8_LAYOUT_INDEPENDENT`／`V8_TIER_VALUES`）、`reset-replay`（换包后读包内 v8 规格，43 格各 1 次回注 reset 经 builder 评估链 → `V8_RESET_REPLAY`；换包后 builder 对 /3 根一律拒绝，v7 规格的回放请检出标签 `parity-anchor-v7`）、`layout-shared`／`prefix-geometry`（只适用 v7：四档共用布局与前缀几何静态闸门，v8 不跑）、`eval-smoke`（合作者入口冒烟，按档断言导出／回注模式）、`xhard0-reset-parity`（xhard0 O:H 的 reset 层对拍，逐局另起子进程取演示前状态，`name_only` 单列）、`xhard0-eval-parity`（两路线 xhard0 评估结果按 seed 对齐，只报告）、`step-headroom`（v8：交付 h5 非演示步 ≤ 1600、超限过滤数、xhard0 ≤ 1300 → `V8_STEP_CAP`；v7 交付清单或 `--v7` 沿用 90% + B4 判据 → `V7_STEP_HEADROOM`）。v7 起删去 `s4-subset` |
| `gate_set.py` | 生成噪声基线的固定检查集：V9 每个交付格取 candidate 最小 3 局（43 格 × 3 = 129，冻结 `scripts/configs/gate-set-v9-129.json`）、xhard0 小样本 16 × 3 = 48（冻结 `gate-set-xhard0-48.json`）；`check`／`check-xhard0` 输出 `GATE_SET`／`GATE_SET_XHARD0`，`export` 导出 generate／env-digest／legacy 身份清单。`hard_parity.py generate --identities` 自 12.363 起也接受 xhard0 子集（只筛作业，运行器仍拿完整 192 行清单） |
| `noise_run.py`、`noise_run_gl.sh` | GL 单遍运行包装：`preflight`（输出根必须不存在或为空 → `RUN_FRESH=FAIL`；flock + fsync 追加式预算账本按 kind 与总量核上限；权重与 tokenizer 全量 sha256 对资产锁；环境指纹与来源报告）、`finish`、`eval-shard`（从 v8 执行清单分片筛身份子集）、`ship`（核对 `SHIPPED` 逐局搬运）；壳脚本最后一行 `EXIT_CODE=` |
| `noise_gate.py` | 噪声基线比较器与闸门：`gen-compare`（h5 全数据集逐帧比较，互斥五类 byte_equal／diverge／gen_fail／structural／unknown；多态字段白名单 `POLYMORPHIC_KEYS`）、`eval-extract`（v8 按账本被接受尝试／legacy 旧路线严格规则）、`run-fresh`、`baseline-*`、`freeze`／`verify`（Clopper–Pearson + 二项分位算线，输入 sha256 绑定）、`check-gen`／`check-eval`／`check-reset`、`selftest`（`GATE_SELFTEST`）。2026-10-03 起基线与回归只测生成噪声，见 `docs/1003-noise-baseline.md` |
| `results/` | 历史日志（被 ignore，按计划不删） |

## 对拍判定（行为一致，用户 U-1）

- **每侧自检**：身份唯一、h5 `setup` 的 seed／difficulty 与身份一致、`timestep_*` 连续、数据集可读。
- **判定层（全等才 PASS）**：身份集合、`setup`（seed、difficulty、task_goal、多选项、相机内参）、结构（数据集名／dtype／shape 集合，不比帧数）、任务成功相等且双侧各自成功（`both_success`，同失败不算相等）、包归属（`ENV_PACKAGE_BINDING`）。
- **容差层（U-19）**：共同前缀（两侧按时间步对齐的公共长度）上的 `action_max`（`joint_action` 最大绝对差，rad）、`state_max`（`joint_state`／`gripper_state`）、`image_mad`（前视与腕视 RGB 逐像素平均绝对差的每身份均值，取最大）、`frames_max`（帧数差）。阈值只从 `configs/hard-parity-tolerances.json` 读（R21），由 `compare --pair O:P --calibrate` 按「O:P 最大值 × 1.5，下界 0.005/0.005/1.0/5，合理性上界 0.05/0.05/10/200」写入。
- **参考层（INFO）**：`sha_equal`、帧数相等数、首个分叉时间步分布。

判定不做字节级：mplib RRT 的墙钟预算让 16 worker 并发下同身份轨迹分叉（见 `docs/validation/newtask-v3/20260921-worker-nondeterminism.md`）。

## 历史

2026-09-22 起本目录由 `scripts/test-vs-original/` 改名而来。拆包前的「vs 原版发布集容差校验」全文（`tolerance.json` 三档、16x3 身份与实测结果）以及 V4/V5 的 `v4_specs`／`v4_rollout`／`v5_generation` 说明已移出，原文见 `git show 7a6cee35:scripts/parity/README.md`。
