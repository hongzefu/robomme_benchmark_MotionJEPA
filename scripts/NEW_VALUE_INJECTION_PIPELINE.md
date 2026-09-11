# 新值注入：候选分布 → 真实 HDF5 → 对拍 → 出图

> **这篇讲什么**：外部生成的固定规格是怎么铺出来的、怎么变成真实仿真轨迹、怎么证明它没被并发改坏、图是怎么画的。
> **运行编号**：规格与跑前分布以 `20260911-contract-v2-05`（契约 v2，2026-09-11 重冻结，本轮只做规格、静态检查与跑前图）为准；330 条实跑、对拍与跑后图仍是 `20260910-new-values-04`（契约 v1 = 原值口径）的结果，两轮规格不同，不互相引用。分支 `newtask-v2`。
> **取值域与分配的约定**见 [NEW_VALUE_CONTRACT_CHANGELOG.md](NEW_VALUE_CONTRACT_CHANGELOG.md)（契约 JSON v1／v2 的变化与用户决策）。链路代码在 [injection/](injection/)，不依赖 `tests/`。
> 完整验收口径见根目录 [NEW_VALUE_INJECTION_TEST_PLAN.md](../NEW_VALUE_INJECTION_TEST_PLAN.md)（实测在第 5.9.3 节），
> 轻量包见 [docs/validation/newtask-v2/20260910-new-values-04/](../docs/validation/newtask-v2/20260910-new-values-04/README.md)。
> 跑前分布的 2D 细图另见 [injection-before-2d/NEW_VALUE_DISTRIBUTION_BEFORE.md](injection-before-2d/NEW_VALUE_DISTRIBUTION_BEFORE.md)。

## 〇、结果速览

**23 项判定：04 运行 19 PASS、1 FAIL、2 NOT_RUN——方案尚未整体通过；05 重冻结新增 `CONTRACT_DERIVED`，规格类 7 项全 PASS（见第一节末尾）。**

| 分组 | 判定 |
|---|---|
| 规格 | `CONTRACT_DERIVED`（05 新增） `SPEC_SCOPE` `SPEC_REPRODUCIBLE` `COVERAGE_QUOTA` `STATIC_GEOMETRY` `COLLISION_GEOMETRY` `COLLISION_SWEEP` `COLLISION_REPRODUCE` `PLOT_EVIDENCE` |
| 注入生效 | `DEFAULT_PARITY` `SMOKE` `INJECTION_BINDING` |
| 可执行 | `FEASIBILITY` `RESULT_COVERAGE` `VIDEO_INDEX` `VIDEO_DECODE` `COLLISION_RUNTIME` `DELIVERY` |
| 并行一致 | `SERIAL_REFERENCE` `PARALLEL_CONTENT` ✅ ／ **`PARALLEL_OVERLAP` FAIL** ／ `PARALLEL_SCALE` NOT_RUN |

实跑 330 条（11 组 × episode 0～29）：**通过 322（97.6%）**、规划失败 5、未运行 3。

| 组 | 通过 | 其他 |
|---|---:|---|
| `BinFill` easy／medium／hard | 29／28／28 | 规划失败 1／2／2 |
| `RouteStick` easy／medium／hard | 30／30／30 | — |
| `VideoUnmaskSwap` easy／medium／hard | 30／30／30 | — |
| `VideoRepick` easy／medium | 28／29 | 未运行 2／1 |

⚠ 两类失败性质不同：5 条规划失败全在 `BinFill`、签名统一是 `DatasetGenerationError: 环境报告失败`，与原值基线同类（计划第 5.9.2 节里 `BinFill hard/ep3` 五轮同样失败），是任务自身成功率；3 条「未运行」是**人为中断**——它们在往 `RecordWrapper` 的 `fail_safe_limit = 2000` 步爬（`VideoRepick/easy/ep0` 已跑 112 分钟、RSS 14.9 GB），按用户决定 `kill -9`，本该得到的是「超时」。

## 一、候选分布怎么产生

**一句话**：外部 CPU 进程**以约定 JSON `scripts/configs/newtask-v2/injection_contract_v*.json` 为派生依据**——取值域与分配办法从契约读，几何常量仍从 `native_sampling.json` 读——按固定 seed 把每个字段铺满 100 条，视频任务再过一遍真实碰撞盒筛查，通过了才冻结成 JSON。全程不启动仿真。

```
injection_contract_v2.json ──▶ 每个字段的取值域（domain）、分配办法（allocation）、事件表两列文案
native_sampling.json       ──▶ 几何（锚点、按钮/孔板盒尺寸、避让间距、region_half_size）与节点表
        │
derive_rng(20260909, 任务, 难度, 字段)   每个字段一条独立随机流
        │
        ├── 独立离散量 ──▶ quota_series   候选列表 = contract.values(字段)，k 类各 floor/ceil(100/k)，再摊到 10 批
        ├── 连续量    ──▶ stratify       端点 = contract.bounds(分量)，10 粗箱 × 10 细层 → 10 批，每批每箱取 1 条
        └── 耦合量    ──▶ balanced_choice / rng_ep，规则 = contract.rule(字段)，只在合法候选内挑用得最少的
        │
        ▼  组装候选
  视频任务：check_bin_layout（初态）+ check_swap_sweep（每段交换）
        │  不通过 ──▶ 同粗箱内重采样，最多 256 个候选 ──▶ 耗尽则报缺口停止冻结
        ▼  通过
  冻结 specs/<任务>/<难度>.json，每条记 spec_sha256
```

代码：[scripts/injection/contract.py](injection/contract.py)（`load_contract`／`derive_all`／`RECIPES`）、[scripts/injection/contract_build.py](injection/contract_build.py)（`build-v1`／`build-v2`／`check`）、[scripts/injection/sampling.py](injection/sampling.py)（`derive_rng`／`quota_series`／`stratify`／`balanced_choice`）、[scripts/injection/specs.py](injection/specs.py)（四任务的 `build_group(task, difficulty, sampling, contract, seed)`）。

四处值得单说：

1. **随机流与进程无关**。`derive_rng` 把 `seed|任务|难度|字段` 做 SHA-256 取前 8 字节当子 seed，不用 Python 的 `hash()`（它受 `PYTHONHASHSEED` 影响）。所以 `plan` 跑两遍、甚至倒序调度，1100 条逐条散列全同——这就是 `SPEC_REPRODUCIBLE=PASS compared=1100 differences=0`。

2. **几何拒绝后在「粗箱」内重采样，不是细格**。计划第 4.3 节写的是「同分层内重采样」，最初按细分层格（宽 0.001 米）实现，结果 `VideoRepick/medium/ep79` 耗尽 256 个候选——因为**整组旋转不改变对象之间的相对距离**，格子太小时根本出不去。改成粗箱（宽 0.01 米，10 倍自由度）后最多只用 33 个候选。粗箱正是 `COVERAGE_QUOTA` 验的单位，判据不变。

3. **碰撞筛查用真实盒体，不是外接圆**。容器是 **6 个**盒体（`build_bin` 的注释说「底板加四壁」，源码还建了中央方块），方块 1 个；判据 `g > ε=1e-6 米` 才算分开，接触与穿入都排除。交换路径不抽帧，用区间二分证明整段分离，证明不出来记 `uncertified` 一律拒绝。见 [src/robomme/robomme_env/utils/bin_collision.py](../src/robomme/robomme_env/utils/bin_collision.py)。

4. **取值域有唯一来源，且被回算钉住**。契约里由难度字典或几何算出的域（`spawn_total` 的 6～8、方块 x 的 [-0.28, 0.08]、容器偏移上限 0.0425）都带 `derivation`（recipe 名 + 依赖键），`check` 的 `CONTRACT_DERIVED` 每次拿 `native_sampling.json` 回算；不一致必须落在 `overrides` 白名单里（v2 就登记了 BinFill medium/hard 的 `spawn_total` 两条，`target_count` 的规则切换另记在 `target_count_rule_override`），未登记的漂移与陈旧的登记都判 FAIL。v1 契约驱动的生成器对 04 的 1100 条规格 `spec_sha256` 逐条相同，事件表 125 行零漂移——这是「契约只是把散落的约定抽出来、没有改变 v1 口径」的硬证据。

**05 实测**（契约 v2，2026-09-11 重冻结）：`plan` 179.1 秒 / `check` 357.1 秒；`CONTRACT_DERIVED=PASS fields=155 mismatches=6 overrides=2 version=v2 problems=0`、`SPEC_SCOPE=PASS specs=1100`、`COVERAGE_QUOTA=PASS quota_gaps=0`、`STATIC_GEOMETRY=PASS checked=1100 rejected=0`、`COLLISION_SWEEP=PASS specs=500 rejected=0 min_g_m=0.00042638`、`SPEC_REPRODUCIBLE=PASS compared=1100 differences=0`。BinFill 三组几何拒绝 637／1046／1834（04 为 637／1701／3324；medium／hard 少两块方块落位更容易），其余 8 组与 04 逐位相同、拒绝数不变。

**04 实测**（契约 v1 = 原值口径：`plan` 180.6 秒 / `check` 354.1 秒）：

| 组 | 几何拒绝 | 碰撞拒绝 | 最多用掉候选 |
|---|---:|---:|---:|
| `BinFill` easy／medium／hard | 637／1701／3324 | — | — |
| `RouteStick` 三组 | 0 | 0 | 1 |
| `VideoUnmaskSwap` easy／medium／hard | 0 | 4／7／9 | 3 |
| `VideoRepick` easy／medium | 89／132 | 2／7 | 11／33 |

全部 `uncertified` 与 `numerical_boundary` 拒绝数为 **0**；500 条视频规格的最危险对象对最小间隙 `min_g_m=0.00042638` 米（0.43 毫米），远在 ε 之上。

## 二、真实 HDF5 怎么生成

**一句话**：规格在父进程校验完才进 worker，四个任务在**原创建点**消费它，产物由原录像器与原 HDF5 写出，生成入口只在 `close()` 之后做只读核验。

```
specs/<任务>/<难度>.json
   │ 父进程 load_episode_specs / validate_episode_spec    建池之前就拒绝错误输入
   ▼
EpisodeJob.episode_spec（每 job 一份 deepcopy）
   │ _worker → gym.make(任务, episode_spec=...)
   ▼
任务模块的原创建点消费：
   BinFill        build_button(randomize=False) / 板位姿 / 各色生成数 / spawn_random_cube(fixed_xy, fixed_yaw)
   RouteStick     theta / 障碍柱 RGB / 路线 nodes / 逐段 directions
   VideoUnmaskSwap build_bin(position, z_rotation_deg) / 色序 / 藏物排序 / 交换发起者
   VideoRepick    同上 + 目标方块 + num_repeats
   ▼
step 里每段交换：核验最近邻搭档 → 从实际起态做连续碰撞检查 → 原 swap_flat_two_lane
   ▼
原 RecordWrapper 写 HDF5 与 mp4 ──▶ close() 之后生成入口核验视频四态
```

代码：[generate_dataset_newseed.py](generate_dataset_newseed.py) 的 `--episode-specs`、`load_episode_specs`、`_worker`、`_video_summary`；四个任务模块的 `__init__`／`_load_scene`／`_initialize_episode`／`step`。

四处关键设计：

1. **不传 `--episode-specs` 时链路逐字不变**。每个消费点都写成 `if spec is None: 原路径 else: 用规格`，`gym.make` 也不多传这个 kwarg。这正是 `DEFAULT_PARITY` 能成立的前提。

2. **方块走原创建路径**。`spawn_random_cube` 加了 `fixed_xy`／`fixed_yaw`：传入时跳过拒绝采样直接建，但**创建代码与原路径共用同一个 `_finalize_cube`**，所以注入版与原版建出的 actor 除位姿外完全一致。容器同理——直接调 `spawn_random_bin` 末尾用的那个 `build_bin`。

3. **清单混跑**。一次调用把 11 组 job 混进同一套进程池，按 episode 轮转入队，每组落 `<输出根>/<任务>/<难度>/`。**必须分目录**：seed 只由任务与 episode 决定，所以 `BinFill` 三个难度的 ep0 的 HDF5 文件名完全相同。

4. **录像器冻结**。`RobommeRecordWrapper` 不改、不覆盖、不打补丁（[AGENTS.md](../AGENTS.md) 强制规则第 11 条）。视频就是它现有逻辑的产出，生成入口只按 `<任务>_ep<k>_seed<s>` 前缀找文件、`ffprobe -count_frames` 数帧、算 SHA-256，四态 `complete`／`frame_mismatch`／`missing`／`no_close`。**视频判定失败不改变任务结果**，也不删已落盘的 HDF5。

**实测**：330 条墙钟约 1 小时 53 分（GPU 0 单卡 12 worker）。

```
FEASIBILITY=PASS   unique=330 executed=330 unclassified=0 succeeded=322 attempt=0
VIDEO_INDEX=PASS   rows=330 complete=327 frame_mismatch=0 missing=0 no_close=3 untraceable=0
VIDEO_DECODE=PASS  success_rows=322 decoded_eq_timesteps=322 failed_videos=5 mismatches=0
COLLISION_RUNTIME=PASS unique=150 checked=147 missing_checks=0 rejected=0
INJECTION_BINDING=PASS unique=330 bound=327 mismatches=0
```

注入确实生效的直接证据（`VideoUnmaskSwap/hard/ep0` 直连验证）：交换次数 3、抓取次数 2 与规格一致；四个容器的实际 xy 与规格逐值相同，最大差 **5.18e-09**（float32 存储精度）；`initial` 复核记到 **2 次**——正是「构造期内部 reset 与外层 `record_env.reset()` 各一次」；三段交换的**预写搭档 = 执行时实际最近邻 = 独立复算结果**，全部一致。

## 三、对拍怎么做的

四类对拍，各自回答一个不同的问题。比较器统一用 [scripts/injection/h5_compare.py](injection/h5_compare.py)::`compare_h5`——它显式遍历全部 group、dataset 及各层 attribute，检查类型、形状与内容，不是只挑动作字段。

| 对拍 | 比的是什么 | 回答什么 | 实测 |
|---|---|---|---|
| `DEFAULT_PARITY` | 改动前后**关闭注入**、同 seed 同配置 | 我的改动有没有动坏原路径 | `PASS compared=8 differences=0` |
| `SERIAL_REFERENCE` | 同一规格单 worker 跑**两遍** | 这条样本的结果是不是确定的 | `PASS unique=16 comparable=16 both_failed=0 differences=0` |
| `PARALLEL_CONTENT` | 实跑 **12 worker 并行** 对 `S0a` **单 worker 串行** | 并发有没有改变结果 | `PASS unique=16 differences=0` |
| `COLLISION_REPRODUCE` | 当前实现**重算** 9 例固定案例的 51 步轨迹 | 碰撞判据能不能复现历史结论 | `PASS cases=9 accepted=6 rejected=3 max_pose_diff_m=6.32e-09` |

三点做法上的讲究：

1. **关闭态对拍要真的切回基线代码**。做法是 `git checkout 446455b -- src/robomme scripts/generate_dataset_newseed.py scripts/configs/newtask-v2/native_sampling.json` 跑一遍，再 `git checkout HEAD --` 恢复，并逐文件核对工作区与切换前一致。只对比「传不传 kwarg」不算数——那证明不了源码改动本身无副作用。

2. **必须先有串行参考，再谈并行一致**。只比「12 worker 档 vs 16 worker 档」，两者一致只能说明**并行之间**一致，不能排除并行整体相对串行有偏差。两遍串行都失败的条记 `both_failed` 并从可比数扣除——重复失败不构成「成功参考」。

3. **固定案例重算不写死参数**。交换对从首末两步的位置差推断（交换双方是唯一位置变化的两个），插值口径由数据判定：用 step 5/10/20/40 分别按「带 smoothstep」与「不带」预测，带的差 1.4e-09、不带的差 1.7e-02。⚠ 逐步对照保存的 `sat_gap_m` 必须用 `check_bin_layout(exhaustive=True)`——默认的包围球粗筛不改判定，但返回的最小值只是「精算过的那些对」里的最小。

**`PARALLEL_OVERLAP` 没通过，原因查清但不放宽**：

```
PARALLEL_OVERLAP=FAIL mode=P0x12 workers_per_gpu=12 peak_distinct_pids=11 samples=322
```

各阶段中位耗时 `make` 8.1 秒、`reset` 0.3 秒、`solve` 120.5 秒、`close` 3.6 秒，`make+close` 约占单条 **9%**，`12 × (1−0.09) ≈ 10.9 ≈ 11`，与实测峰值吻合；含 make/close 的完整窗口峰值同样是 11，说明父进程处理结果、写 jsonl、再提交下一个 job 之间还有一个 slot 在换手。并发度的时间分布是 11 个占 20.0%、10 个占 28.1%、9 个占 26.1%、8 个占 13.7%（合计 87.9%），**是真并发而不是「只有排队／导入重叠」的伪并发**。但判据字面要求「峰值 ≥ 总 worker 数」，在 make/close 非零时数学上达不到。按用户决定如实记 FAIL，判据口径的问题原样留下。

## 四、图怎么出的

出图代码 [scripts/injection/plots.py](injection/plots.py)，**跑前跑后版式相同**，跑后多一层结果着色。共 66 张（11 组 × 3 类 × 2 套）。

| 图 | 函数 | 画什么 | 跑后多什么 |
|---|---|---|---|
| 图 1 布局总览 | `plot_overview` | 10×10 小图，每条 episode 一个俯视布局：对象位置、颜色、编号、目标标记、交换连线 | 小图边框与标题按七类结果着色；`ep30~99` 标「范围外」保留细边框，不进分母 |
| 图 2 空间覆盖 | `plot_coverage` | 全部对象的 XY 散点 + 两个连续量的 10×10 占用格 + 每个连续量的粗箱计数（红虚线 = 目标 10 条） | 散点按结果着色，失败用 ✕ |
| 图 3 对象与动作分布 | `plot_distribution` | 每个字段一条横向条形；独立类别标计数差、耦合类别标未覆盖类数 | 同一条形按通过／失败分色堆叠 |

三个实现细节：

1. **中文字体要显式注册**。`.ttc` 是字体集合，matplotlib 默认不扫描，必须 `font_manager.fontManager.addfont()`。注册进来的 face 名可能是 `Noto Sans CJK JP`，但 CJK 字体汉字字形共用，简体照常渲染。不做这步标签全是豆腐块。

2. **合法类别要补零**。图 3 的条形按**约定表**的完整合法类别画，不是按「实际出现过的值」。否则 100 条全是同一个值时只画出一根条，看起来还很均匀——这正是 `COVERAGE_QUOTA` 那条 ⚠ 说的陷阱。

3. **图不作验收依据**。`PLOT_EVIDENCE` 只保证「每组跑前跑后各一套、图与计数表引用同一份规格散列」（记在 `plot_manifest_<phase>.json`），验收看的是 `check_result.json` 与 `feasibility_result.json` 里的计数。

**实测**：`PLOT_EVIDENCE=PASS groups=11 before=11 after=11 thumbnails=1100 font=Noto Sans CJK JP`。产物在 `artifacts/injection/20260910-new-values-04/plots/{before,after}/<任务>/<难度>/`。

跑前分布还有一套更细的 2D 图（只画实跑范围前 30 条，视角与回放视频 `base_camera` 对齐：画面右 = +y、画面上 = −x；每组三种：初始位置、随机事件、单个 episode，共 77 张，放在 `injection-before-2d/figures/`，不入库需本地出图）与按 11 组分难度、各分「初始化」「事件」两张的「事件 / 取值域 / 分配 / 结果分布」表，见 [injection-before-2d/NEW_VALUE_DISTRIBUTION_BEFORE.md](injection-before-2d/NEW_VALUE_DISTRIBUTION_BEFORE.md)。

## 五、复现命令

```bash
command -v uv
INJECTION_RUN_ID=20260911-contract-v2-05
# 须在仓库根目录执行（scripts 是命名空间包，scripts/injection 是其中的包）

# 〇、契约：v1 由原值派生，v2 = v1 + BinFill 对齐 heldout；check 离线回算
uv run --no-sync python -m scripts.injection.contract_build build-v1 --out scripts/configs/newtask-v2/injection_contract_v1.json
uv run --no-sync python -m scripts.injection.contract_build build-v2 --base scripts/configs/newtask-v2/injection_contract_v1.json --out scripts/configs/newtask-v2/injection_contract_v2.json
uv run --no-sync python -m scripts.injection.contract_build check --contract scripts/configs/newtask-v2/injection_contract_v2.json

# 一、候选分布：冻结 11 组 × 100 条（编号不可复用，目录已存在直接拒绝；--contract 必填，check 按清单自动取同一份契约）
uv run --no-sync python -m scripts.injection.campaign plan  --run-id "$INJECTION_RUN_ID" --contract scripts/configs/newtask-v2/injection_contract_v2.json
uv run --no-sync python -m scripts.injection.campaign check --run-id "$INJECTION_RUN_ID"

# 二、真实 HDF5：11 组各 episode 0～29 共 330 条
uv run --no-sync python -m scripts.injection.campaign run \
  --run-id "$INJECTION_RUN_ID" --phase feasibility --tier 12

# 三、对拍
uv run --no-sync python -m scripts.injection.campaign run \
  --run-id "$INJECTION_RUN_ID" --phase calibration --skip-ladder        # SERIAL_REFERENCE
uv run --no-sync python -m scripts.injection.campaign compare \
  --left  artifacts/injection/$INJECTION_RUN_ID/calibration/S0a \
  --right artifacts/injection/$INJECTION_RUN_ID/feasibility/P0x12 \
  --label PARALLEL_CONTENT --subset-only                                # PARALLEL_CONTENT
uv run --no-sync python -m scripts.injection.campaign collision-reproduce \
  --output-dir artifacts/collision-replay/<新编号> --mode trajectory     # COLLISION_REPRODUCE

# 四、出图与轻量包
uv run --no-sync python -m scripts.injection.campaign plot   --run-id "$INJECTION_RUN_ID" --phase before
uv run --no-sync python -m scripts.injection.campaign plot   --run-id "$INJECTION_RUN_ID" --phase after
uv run --no-sync python -m scripts.injection.campaign report --run-id "$INJECTION_RUN_ID"
```

⚠ 超过五分钟的阶段按 [AGENTS.md](../AGENTS.md) 强制规则第 4 条用 detached tmux 起。
⚠ `summarize --run-id <编号>` 可以**不重跑仿真**、用当前代码重新统计既有的 `episode_results.jsonl`——长任务的统计代码在父进程启动那一刻就定型了，跑到一半修好的 bug 对它无效，这是必需的退路。

## 六、没通过与没做的

| 项 | 状态 | 原因 |
|---|---|---|
| `PARALLEL_OVERLAP` | **FAIL** | 峰值 11 < worker 数 12；成因见第三节，是真并发但判据口径与调度现实不符，按用户决定不放宽 |
| `PARALLEL_SCALE` | NOT_RUN | 机器被另一用户占 639% CPU、GPU 1 占 33.7 GB，单条从 98.6 秒慢到 316 秒，吞吐测量失真，用户决定跳过档位校准 |
| `COLLISION_RERENDER` | NOT_RUN | 从保存轨迹重渲染需要 SAPIEN 渲染，本轮未做 |

还有三点边界要说清：

- 实跑只覆盖每组前 30 条共 330 条，其余 770 条只有规格、静态检查与图，**没有实跑结论**；跑前的静态与连续几何通过不代表抓取、运行时最近邻或实际物理轨迹可执行。
- 并行证据只覆盖 **GPU 0 单卡多 worker**。GPU 1 被他人占用，双卡对拍本轮没有取得新值证据，不能外推到双卡。
- 图表生成不等于逐图目视完成，视频文件存在不等于已人工观看。四容器三例是**此前**已获用户目视确认的，那个状态不外推到本轮的 330 条。
