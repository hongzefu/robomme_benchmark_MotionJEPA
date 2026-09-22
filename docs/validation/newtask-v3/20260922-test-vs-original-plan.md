# 计划：多 worker 生成 vs 原始发布集的容差校验（`scripts/test-vs-original/`）

## Context

官方发布集（`/data/hongzefu/robomme_data_h5`，16 task × 100 局）本身是 20 worker 生成的，逐位复现不可能；官方比较器 `compare_joint_actions` 只比 `joint_action`、零容差、帧数不等整局丢弃，所以历史轮（1600 局）和本轮（144 局）对它都判 `failed`。用户要求：给出容差方案，以后多 worker 生成后对比原始数据判"在差距内"；先跑实测标定；容差范围与全部调用方法写成 md；比较脚本全部放 `scripts/test-vs-original/`，生成仍走现有 `train_split_parity.py run`。

本轮只读探针已把噪声结构量清楚（全部数字见文末附录）：

- **同架构（sled-vail RTX 6000 Ada，与历史轮同机）+ 单 worker ≈ 精确复现原版**：36 局帧数全同、`joint_action max|Δ| ≤ 1.9e-17`。历史轮的 0.0079／10 局错位全部来自 20 worker 争抢。
- **跨架构（A40）**：整文件 108 对 0 个相同；帧数相同的局手臂通道 max≈0.014、p90≈0.01；44% 局帧数不同，其中一半只差 ±1 帧；真正重规划约 19%。
- **两个关键结构**：`joint_action[7]`／`eef_action[6]` 是夹爪 ±1 元素，翻 1 帧就造出 2.0 的"差异"，必须按事件比；末尾差 1 帧会让 max 飙到 0.7 而 p99 仅 0.03，DRIFT 主判据要用 p99。
- **布局不变量（用户点名的 segmentation 位置）**：raw segmentation 不进 HDF5，但由它算出的目标像素中心写在 `info/grounded_subgoal`（`<y, x>`）。`timestep_0` 的坐标跨硬件、连重规划局 36/36 相同 → 零容差；后续边界坐标偶差 1 px（物体被漂移轨迹推动），真重规划时抓取顺序会变。

用户已定：容差按硬件分两档（`ada` 紧 / `a40` 松，自动选档并在判定行标明）；比较 `joint_action` + 低维 obs；每局分类 IDENTICAL/DRIFT/REPLAN/FAIL 并对 REPLAN 设上限；标定用 144 条子集 × 多 worker；16×3（48 局）在 sled-vail、aspen、greatlakes A40 三台各跑一遍；aspen 只当算力不单独成档。

## 〇、最终交付的实测一览：两个档位，各看什么

**档位只有两个，按硬件分：**

| 档位 | 机器 | 定位 | 各层阈值（初值，标定后写入 `tolerance.json`） |
|---|---|---|---|
| `ada` 紧档 | sled-vail（RTX 6000 Ada，与原版同架构） | "应当精确复现原版"，只容忍多 worker 争抢带来的少量重规划 | 帧数差 0；ts0 坐标精确；后续边界坐标差 0 px、帧号偏移 0；夹爪翻转偏移 0；手臂 p99/max ≈ 1e-6（实测 1e-17 取安全下限）；REPLAN 率上限由 8 worker 实测定（历史 20 worker 为 0.6%） |
| `a40` 松档 | greatlakes A40、aspen A6000（Ampere GA102） | "跨架构只能保证布局与任务结构一致，轨迹允许漂移与重规划" | 帧数差 ≤ 2；ts0 坐标精确；后续边界坐标差 ≤ 2 px、帧号偏移 ≤ 20；夹爪翻转偏移 ≤ 2；手臂 p99 ≈ 0.02 / max ≈ 0.03（实测 0.010 / 0.014 × 2）；REPLAN 率上限由 144 局实测定（初估 ≤ 40%） |

**两档共用的零容差项（任何档不过即 FAIL）**：`setup/seed、difficulty、task_goal`、末帧 `is_completed`、`timestep_0` 的 grounded 坐标（reset 后目标中心）。

**reset 后第一帧的布局检查（用户点名，已实测）**：raw segmentation 不进 HDF5，但 `timestep_0` 的 `front_depth`／`front_rgb` 就是 reset 后整个场景的渲染，等价于全物体布局。只读实测 4 局 × 3 种配对：**11/12 与原版逐像素相同（0 像素差），含跨架构 A40 vs 原版**；唯一例外 VideoPlaceOrder/ep0 差 1.2% 像素（depth max 10）。所以布局层加一项：`timestep_0` 的 `front_depth` 与 `front_rgb` 对原版——紧档 0 像素差；松档 `px_diff_ratio ≤ …`、`depth_max ≤ …`（由 A40 产物对原版标定，初估 2% / 16）。这比只看目标中心强得多，且跨硬件仍近乎精确。

**全部实测一律"产物 vs 原版发布集"，不做产物之间的互比**（用户 2026-09-22 明令）。交付的实测共 6 组：

| # | 产物 | 对谁比 | 档位 | 看什么 |
|---|---|---|---|---|
| 1 | sled-vail 48 局（16×3）单 worker | 原版 | ada | 紧档正例：预期全 IDENTICAL；验证"同架构单 worker 零噪声"在 16 个任务、三档难度上都成立 |
| 2 | greatlakes A40 48 局单 worker | 原版 | a40 | 松档单 worker 基线：ts0 布局像素差、DRIFT 局手臂 p99/max 分布、REPLAN 率、边界/翻转帧号偏移、边界坐标像素差 |
| 3 | aspen 48 局单 worker | 原版 | a40 | 旁证：A6000 对原版是否落在松档内、REPLAN 率与 A40 是否同量级（决定 aspen 能否替集群跑松档）。不进容差表 |
| 4 | greatlakes A40 144 局 **4 worker**（四占位 job 各 36 局，每 job 4 CPU → 4 worker） | 原版 | a40 | **松档多 worker 正式标定**：多 worker 争抢引入多少 REPLAN、DRIFT 分布 → 定 `a40.replan_max` 与手臂阈值 |
| 5 | 现成 `gl-5e/merged-A1`（A40 单 worker）与 `gl-5e-w4/merged-A1`（A40 4 worker）144 局 | 原版 | a40 | 松档补充样本：与 #2/#4 取并集最大，阈值留余量更稳 |

**机器分工（用户 2026-09-22 定）**：两台本地机（sled-vail、aspen）**只测单 worker**；greatlakes **测单 + 多 worker**。紧档（`ada`）因此只有单 worker 数据，`ada.replan_max` 按单 worker 实测定（预期 0）；README 里写明"紧档未做多 worker 标定，若日后在 sled-vail 用多 worker 生成，须先补标定"。
| 6 | 正例 `local-recheck` 36 局 / 负例 `local-spec-02`（改 offsets）/ 跨档 `gl-5e` | 原版 | ada、a40 | 正例全 IDENTICAL；负例 FAIL 且由 ts0 布局层抓到；A40 产物 ada 档 FAIL、a40 档 PASS——证明判据既容噪声又抓真改动 |

每组都输出同一格式：`VS_ORIGINAL=… tier=… compared=… identical=… drift=… replan=… fail=…` + 官方合同审计 `REFERENCE_AUDIT_COMPLETE` 行；全部判定行原文与命令进 README。

## 一、新建文件（全部在 `scripts/test-vs-original/`）

| 文件 | 职责 |
|---|---|
| `compare_vs_original.py` | 核心比较器。输入：生成侧官方布局目录（`record_dataset_<Task>.h5 + _metadata.json`）、发布集目录、`tolerance.json`、可选 `--manifest`/`--sequence` 选局、`--tier {auto,ada,a40}`。输出：`<out>/episodes.jsonl`（逐局分类与各层度量）、`<out>/summary.json`、判定行。 |
| `calibrate.py` | 读一份或多份 `episodes.jsonl`，按档位统计 DRIFT 局各字段 p99/max 分位数、REPLAN 率、边界/翻转帧号漂移、像素差，套余量规则生成或更新 `tolerance.json`（保留 `calibrated_from` 留档），打印 `CALIBRATION_DONE tier=… samples=…`。 |
| `tolerance.json` | 两档阈值表（结构见第三节）。 |
| `identities_16x3.txt` | 48 局 `--sequence` 串（子集 manifest 每 (task, difficulty) 第一条：episode {0,3,2}，z=32/xy=16）。 |
| `README.md` | 容差范围表（含实测原值与余量规则）+ 全部实测调用方法（生成／merge／比较／标定／正负例／跨档）逐条可复制。 |

复用、不改：`scripts/train_split_comparison.py` 的 `load_official`（L45）、`validate_manifest_scope`（L68）、`validate_generated_subset`（L114）——每次比较先原样跑官方合同审计并打印 `REFERENCE_AUDIT_COMPLETE` 行；`scripts/train_split_parity.py` 的 `merge`（L1298）与 `_load_subset_manifest`／`select_rows`（L786，`--sequence`）。不改 `src/`、不改任何现有脚本、不新增依赖（h5py/numpy 已有）。

## 二、逐局分类算法（`compare_vs_original.py`）

对每个 (task, episode)，两侧各读 `episode_<n>`，按层次判：

1. **合同层（零容差）**：`setup/seed`、`setup/difficulty`、`setup/task_goal`；末帧 `info/is_completed`；`available_multi_choices`。任一不等 → **FAIL**。
2. **布局层**：(a) `timestep_0/info/grounded_subgoal` 全文（含 `<y, x>`）零容差，不等 → **FAIL**；(b) `timestep_0/obs/front_depth` 与 `front_rgb` 对原版逐像素比：不同像素比例 ≤ `ts0_image.px_diff_ratio`、深度差 max ≤ `ts0_image.depth_max`（紧档均为 0），超出 → **FAIL**。这一层专门抓"布局/seed 不对"，与轨迹噪声无关；实测跨架构 ts0 仍 11/12 局 0 像素差。
3. **子目标层**：取两侧 `is_subgoal_boundary=True` 的帧，按序号对齐：去掉坐标的文本序列须相同、坐标 |Δ| ≤ `px_tol`；边界帧号偏移记录 `boundary_shift`。序列长度或文本不同 → 至少 **REPLAN**。
4. **夹爪事件层**：`joint_action[:,7]`、`eef_action[:,6]`、`gripper_state`（阈值化）、`is_gripper_close` 各转成翻转事件序列：翻转次数不等 → REPLAN；帧号偏移 max 记为 `flip_shift`。
5. **手臂轨迹层（容差）**：`joint_action[:, :7]`、`eef_action[:, :6]`、`joint_state`、`eef_state` 在公共前缀 `min(T1, T2)` 上逐帧比，记每字段 `max`、`p99`、首个超阈值帧 `diverge_at`。
6. **图像层**：`front/wrist rgb/depth` 只查存在与 shape。
7. **分类**：
   - 两侧 HDF5 全字段按位相同（复用整文件 SHA-256 快速路径）→ **IDENTICAL**；
   - 否则若 `|T1−T2| ≤ frame_delta_max` 且各手臂字段 `p99 ≤ tier.p99` 且 `max ≤ tier.max` 且 `boundary_shift ≤ boundary_shift_max` 且 `flip_shift ≤ flip_shift_max` 且子目标序列一致 → **DRIFT**；
   - 否则（合同层与布局层已过）→ **REPLAN**；
   - 合同层或布局层不过 → **FAIL**。
8. **数据集级**：`FAIL == 0` 且 `replan / compared ≤ tier.replan_max` → `VS_ORIGINAL=PASS`。判定行：
   ```text
   VS_ORIGINAL=PASS tier=ada compared=144 identical=…  drift=… replan=… fail=… replan_rate=… replan_max=…
   # 手臂通道 DRIFT 局 p99：joint_action=… eef_action=… joint_state=… eef_state=…（阈值 …）
   # 布局层：ts0 grounded 全部相同；子目标边界坐标最大像素差=…；边界帧号最大偏移=…
   REFERENCE_AUDIT_COMPLETE=PASS compared=… contract_errors=0 missing=0   ← 官方合同审计原样
   EXIT_CODE=0
   ```
   `--tier auto` 用 `nvidia-smi --query-gpu=name` 匹配 `tolerance.json` 的 `match` 列表；无 GPU 时必须显式给 `--tier`。

## 三、容差表结构与标定规则

```json
{"schema": "test-vs-original-tolerance/1",
 "tiers": {
   "ada": {"match": ["RTX 6000 Ada"], "frame_delta_max": 0, "px_tol": 0,
           "boundary_shift_max": 0, "flip_shift_max": 0, "replan_max": 0.02,
           "arm": {"joint_action": {"p99": …, "max": …}, "eef_action": {…}, "joint_state": {…}, "eef_state": {…}}},
   "a40": {"match": ["A40", "A6000"], "frame_delta_max": 2, "px_tol": 2,
           "boundary_shift_max": 20, "flip_shift_max": 2, "replan_max": …, "arm": {…},
           "ts0_image": {"px_diff_ratio": 0.02, "depth_max": 16}}},
 "_note": "ada 档 ts0_image 两项均为 0；所有阈值只由『产物 vs 原版』的实测标定，不用产物互比的数字",
 "calibrated_from": [{"tier": "ada", "generated": "…", "workers": 8, "episodes": 144, "date": "…", "observed": {…}}]}
```

余量规则（写进 README，可改）：手臂阈值 = 实测 DRIFT 局该统计量的 **2 倍**并向上取 1 位有效数字；`replan_max` = 实测率 × 2 + 1/compared；帧号/像素类上限 = 实测 max × 2（紧档实测为 0 则保持 0）。`ada` 档以本机 8 worker 144 局标定；`a40` 档以现成 `gl-5e-w4/merged-A1`（4 worker）+ `gl-5e/merged-A1` + 三机 48 局标定，取并集最大值。

## 四、实测步骤（顺序执行，全部走 `train_split_parity.py run`，单卡）

| # | 机器 | 内容 | 命令要点 | 预计 |
|---|---|---|---|---|
| 1 | sled-vail | 48 局单 worker B 路（紧档正例） | `run --sequence "$(cat identities_16x3.txt)" --paths B --workers 1 --gpus 0 --sampling-config … --official-root artifacts/train-parity/local-smoke-01/official-src --output artifacts/train-parity/tvo-vail-16x3`，tmux + Monitor | ~20 min |
| 2 | greatlakes A40 | 同 48 局，四占位 job 各 12 局 | `srun --jobid=… --overlap --exact --gpu_cmode=shared`，`--sequence` 拆四段，输出 NFS `gl-tvo-16x3/shard{1..4}` | ~8 min |
| 3 | aspen | 同 48 局 | `ssh -i ~/.ssh/id_ed25519_umich hongzefu@sled-aspen.eecs.umich.edu`，tmux 在 aspen 起，直接用 NFS 克隆的 `.venv`，`CUDA_VISIBLE_DEVICES=0`，输出写 NFS `aspen-tvo-16x3` | ~30 min |
| 4 | greatlakes A40 | 144 局 B 路 **4 worker**（松档多 worker 标定） | 四占位 job `--shard k/4 --workers 4 --gpu_cmode=shared`，输出 NFS `gl-tvo-w4/shard{1..4}`，tmux + Monitor | ~30 min |
| 5 | 本机 | 四份产物各 `merge` 成官方布局 | `train_split_parity.py merge --run … --path B --output …/merged-B` | 分钟级 |
| 6 | 本机 | 逐份 `compare_vs_original.py`（先用 `--tier` 显式、阈值先取宽松初值），再 `calibrate.py` 出两档 → 写回 `tolerance.json` → 用正式阈值全部重比 | ~30 min |
| 7 | 本机 | 正负例与跨档验证（第五节）→ 写 README → commit/push → **向用户汇报并等确认** | — |
| 8 | 三台 | **用户确认后删除全部测试 h5/mp4**：本机 `artifacts/train-parity/tvo-*`、NFS `gl-tvo-*`、aspen 输出目录；只保留比较结果 JSON/JSONL（已随 commit 入库） | 分钟级 |

集群与 aspen 产物落在 NFS，本机直读，不搬数据。磁盘：本机新增约 13 GB（48 局），NFS 新增约 13 GB × 2 + 40 GB，Turbo 余 4.7 T 够用；步 8 全部回收。

**三台机器同步发（用户 2026-09-22 明确：指 gl / vail / aspen 同时启动，不是改 worker 配置）**：

- t0 同时起三条线：sled-vail 48 局单 worker、aspen 48 局单 worker、greatlakes 的测试序列。
- greatlakes 内部用现有四个占位 job，不新提 job、不改 worker 数：每个 job 先跑自己那 12 局单 worker（48 局分四段，≈8 min），跑完接着跑自己那片 144 局的 4 worker 分片（36 局，≈8 min）。单 worker 与 4 worker 不同时在同一张卡上，单 worker 基线不受争抢影响。
- 每条线各自 tmux + 各自 Monitor（一份日志一个 Monitor）。预计全部 ≤ 35 min（最慢是 aspen 48 局 ≈ 30 min）。

## 五、验证方式

- **正例**：`artifacts/train-parity/local-recheck/new/<Env>/B` merge 后 vs 发布集，`--tier ada` → 36 局全 IDENTICAL；步 1 的 48 局 → 预期全 IDENTICAL。
- **负例**：`artifacts/train-parity/local-spec-02/D`（BinFill/0 的 `layout.board.offsets` 被改）vs 发布集 → `VS_ORIGINAL=FAIL fail=1`，且 `episodes.jsonl` 里原因为 `layout:ts0_grounded_mismatch`——必须由布局层抓到，不靠轨迹层。
- **跨档**：`gl-5e/merged-A1`（A40）用 `--tier ada` → FAIL；用 `--tier a40` → PASS。`--tier auto` 在 sled-vail 判 `ada`、在 aspen/集群判 `a40`。
- **多 worker 标定自洽**：步 4 的 A40 144 局 4 worker 用标定后的 `a40` 档 → PASS；三机 48 局单 worker 各按自己档位 → PASS。
- **aspen 旁证**：aspen 48 局对原版按 a40 档判，报告 REPLAN 率与 DRIFT 分布是否与 A40 48 局对原版同量级（决定 aspen 能否代替集群跑松档）；不做产物互比，不进容差表。
- **官方口径不变**：每次比较同时打印官方合同审计 `REFERENCE_AUDIT_COMPLETE` 行，合同错误仍为硬 FAIL。
- 新脚本带 `--help`；不改旧脚本，现有 `tests/lightweight` 不受影响。

## 六、交付物与收尾

- `scripts/test-vs-original/` 五个文件 + `results/<机器-规模-worker>/{summary.json,episodes.jsonl}`（小文件）进 Git。
- **测试产生的全部 h5/mp4 在 commit、汇报、用户确认之后删除**（本机 `artifacts/train-parity/tvo-*`、NFS `gl-tvo-*`、aspen 输出）；删前逐目录列清单交用户过目，不动 5d/5e 等既有验收产物与发布集。
- README 里：两档容差表（实测原值 + 余量规则 + 最终阈值）、三机 48 局结果表、144 局 8 worker 结果表、正负例/跨档判定行原文、全部命令。
- `docs/greatlakes.md` 追加 aspen 一节（主机、密钥、A6000、NFS venv 直接可用）与 `--gpu_cmode=shared` 已有条目不变。
- 每步跑过测试后按仓库体例 commit + push。

## 附录：本轮只读探针原始数字

（其中"vail vs A40"一类产物互比只用于理解噪声结构，**不进容差标定**；正式阈值全部由"产物 vs 原版"的实测得出。）

- reset 后第一帧布局（ts0 `front_depth`/`front_rgb`，4 局）：vail vs 原版 4/4 逐像素相同；A40 vs 原版 3/4 逐像素相同，VideoPlaceOrder/ep0 差 786/65536 深度像素（1.2%，max 10）、2335/196608 rgb 像素；相机外参全同。ts0 grounded 坐标对原版 36/36 相同。

- 同架构（sled-vail 单 worker B 路 36 局 vs 发布集）：帧数 36/36 相同；`joint_action max|Δ|` 最大 1.87e-17；ts0 grounded 36/36 相同。
- 跨架构（sled-vail vs A40，同代码同配置同单 worker，36 局）：整文件 108 对 0 相同；帧数相同 20 局，手臂通道 max：joint_action 0.0141 / eef_action 0.0137 / joint_state 0.0141 / eef_state 0.0137，p90 ≈ 0.007～0.010，中位 ≈ 0.002～0.003；gripper_state max 0.0013；`is_gripper_close` 翻转次数 20/20 一致、偏移 0。帧数不同 16 局：±1 帧 9 局、4～6 帧 2 局、9～194 帧 5 局；边界帧号偏移 max 10；边界文本序列 31/36 相同（3 局仅坐标差 1 px，VideoPlaceOrder/ep0 真重规划 14 vs 12 个边界）。
- 夹爪元素：PickHighlight/ep1 手臂 7 元素 max 0.034、`joint_state |Δ|>0.1` 帧数 0，但 `joint_action[7]` 差 2.0；VideoPlaceButton/ep10 仅 t=787 一帧 > 0.1；PickHighlight/ep7 395 帧 > 0.1（真重规划）。
- 对发布集：历史轮（1600 局、20 worker、sled-vail）`max_abs_diff=0.00786`、`different=3.6%`、错位 10 局；本轮 5d（144 局、单 worker、A40）`max_abs_diff=0.0197`、`different=72.7%`、错位 39 局。
- 多 worker（同机同次）与单 worker 跨运行：144 局里只 `PickHighlight/ep3` 不稳定（已见 641/643/647/652）。
- 耗时（单 worker 单局）：sled-vail 约 25 帧/秒，48 局 ≈ 20 min、144 局 ≈ 57 min；A40 约慢 1.4 倍。
- aspen：`sled-aspen.eecs.umich.edu`，2× RTX A6000 48 GB，`Default` 模式，驱动 570.195.03（CUDA 12.8），NFS 已挂载，NFS 克隆 `.venv` 直接可用（torch 2.9.1+cu128，`cuda.is_available()=True`）。
