# 生成产物 vs 官方原始发布集：容差校验（test-vs-original）

一句话：**官方发布集本身是 20 worker 生成的，逐位复现不可能；本目录给出"按硬件分三档"的容差判据，
让以后多 worker 生成的数据集能对原版做"在差距内"的校验，同时仍能抓住真正的改动（布局、seed、指令）。**

生成仍走现有 `scripts/train_split_parity.py run` 流水线（不改）；本目录只放比较与标定脚本。
全部实测一律"产物 vs 原版发布集"，不做产物之间的互比。

```text
生成（train_split_parity.py run --paths B ...）
   └─ <run>/B/<Task>_episode_<n>/hdf5_files/*.h5
merge（train_split_parity.py merge --path B ...）
   └─ <merged>/record_dataset_<Task>.h5 + record_dataset_<Task>_metadata.json   ← 官方布局
compare_vs_original.py --generated <merged> --reference /data/hongzefu/robomme_data_h5 --tier auto
   └─ episodes.jsonl（逐局四类分类 + 各层度量）+ summary.json + 判定行
calibrate.py --tier <档> --results <多份 episodes.jsonl> --write
   └─ tolerance.json（三档阈值 + calibrated_from 留档）
```

---

## 一、三个档位，各看什么

| 档位 | 机器 | 定位 |
|---|---|---|
| `a6000` 最紧档 | aspen（RTX A6000）——实测 47/48 逐位复现原版，原版发布集应产自此机 | 逐位复现；只容忍时序临界身份的个别重规划 |
| `ada` 紧档 | sled-vail（RTX 6000 Ada） | 1e-16 级舍入内复现；只容忍少量重规划 |
| `a40` 松档 | greatlakes A40（Ampere GA102） | 跨架构只保证布局与任务结构一致，轨迹允许漂移与重规划 |

（用户 2026-09-22 决定：A6000 单独成档，从 a40 的 `match` 移出。）

`--tier auto` 用 `nvidia-smi --query-gpu=name` 匹配 `tolerance.json` 里各档的 `match` 列表；判定行必须标明档位，
防止拿松档冒充通过。无 GPU 的机器上必须显式 `--tier`。

### 每局按层判定

| 层 | 比什么 | 容差 | 不过时 |
|---|---|---|---|
| 合同层 | `setup/seed`、`setup/difficulty`；末帧 `info/is_completed`；`task_goal[0]`（主指令）与 `available_multi_choices` **归一化**（小写、去标点/连字符）后精确 | 零 | **FAIL** |
| 布局层 (a) | `timestep_0/info/grounded_subgoal` 全文（segmentation 算出的目标像素中心 `<y, x>`，reset 后布局指纹） | 零 | **FAIL** |
| 布局层 (b) | `timestep_0` 的 `obs/front_depth`、`obs/front_rgb` 逐像素（reset 后整个场景的渲染 = 全物体布局） | 紧档 0；松档 `ts0_image.px_diff_ratio` / `depth_max` | **FAIL** |
| 子目标层 | `is_subgoal_boundary=True` 各帧的 `grounded_subgoal`：去坐标文本序列须相同；坐标差 ≤ `px_tol`；边界帧号偏移 ≤ `boundary_shift_max` | 分档 | REPLAN |
| 夹爪事件层 | `joint_action[7]`、`eef_action[6]`（±1）与 `is_gripper_close` 的翻转事件：次数相等、帧号偏移 ≤ `flip_shift_max` | 分档 | REPLAN |
| 手臂轨迹层 | `joint_action[:7]`、`eef_action[:6]`、`joint_state`、`eef_state` 在公共前缀上逐帧 \|Δ\|：`p99` ≤ 档位 `p99`、`max` ≤ 档位 `max` | 分档 | REPLAN |
| 帧数 | \|T_gen − T_ref\| ≤ `frame_delta_max` | 分档 | REPLAN |
| 图像层 | 四路 rgb/depth 存在且 shape/dtype 相同（首尾帧） | — | REPLAN |

分类：全字段按位相同 → **IDENTICAL**；上述容差全部满足 → **DRIFT**；合同/布局过、其余超容差 → **REPLAN**；合同或布局不过 → **FAIL**。
数据集级：`FAIL == 0` 且 `REPLAN / compared ≤ replan_max` → `VS_ORIGINAL=PASS`。
给了 `--official-root` 时同时原样跑官方合同审计（`REFERENCE_AUDIT_COMPLETE` 行，复用 `train_split_comparison.py`），合同错误仍是硬 FAIL。

### 为什么这样设计（实测依据）

- 夹爪元素 `joint_action[7]` 取 ±1，翻转帧差 1 帧就造出 2.0 的"差异"；末尾差 1 帧会让 `joint_state` max 飙到 0.7 而 p99 仅 0.03。所以夹爪按事件比、手臂以 p99 为主判据。
- `timestep_0` 的目标中心只覆盖当前目标物；负例（改 `layout.board.offsets`）目标中心不变、但 ts0 深度图差 2.1% 像素——**全场景布局要靠 ts0 图像**。
- 发布集（v0.5 分支）与现行源码的指令文本有纯标点差异（SwingXtimes `right-side`/`right side`、VideoPlaceButton 多一个逗号），VideoPlaceButton 的 `task_goal` 现行为 3 条改写、发布集 2 条。合同层因此只比主指令 `task_goal[0]` 的归一化文本，其余只记录（`text_raw_mismatch`）。
- 跨架构（A40）实测出两种"布局相同、决策不同"的局：BinFill/ep2 的 ts0 深度/rgb 与原版逐像素相同，但首个目标物是"first **red** cube <60,83>"而原版是"first **green** cube <85,76>"；VideoPlaceOrder/ep0 的主指令是"place the blue cube on the **second** target"而原版与本机产物都是"**first** target"——该指令由示范阶段的执行结果生成，示范重规划后文本随之变。这两类是**规划层**差异，不是布局错：松档（`strict_text=false`、`strict_ts0_grounded=false`）记 REPLAN；紧档（`strict_*=true`）判 FAIL。布局层的 FAIL 始终以 **ts0 图像**为准。
- 手臂通道比较允许 ±`frame_delta_max` 帧的错位（逐帧取各偏移下的最小差）：末段多/少 1 帧会让后续整段错位一帧，否则 p99 会被抬到 0.03 把"同一条规划"误判成 REPLAN。紧档 `frame_delta_max=0` 即严格逐帧。

---

## 二、容差范围（`tolerance.json`）

### `ada` 紧档（已标定，2026-09-22；样本：sled-vail 单 worker 16×3 48 局 + local-recheck 36 局，共 84 局，均对原版）

| 项 | 实测观测值 | 最终阈值 |
|---|---|---|
| 手臂 `joint_action` / `eef_action` / `joint_state` / `eef_state` 的 p99、max | 6.7e-16 / 0 / 0 / 0（纯浮点舍入） | **1e-6**（下限） |
| 帧数差 `frame_delta_max` | DRIFT 局 0 | **0** |
| 边界坐标像素差 `px_tol`、边界帧号偏移 `boundary_shift_max`、夹爪翻转偏移 `flip_shift_max` | 0 / 0 / 0 | **0** |
| ts0 图像 `px_diff_ratio` / `depth_max` | 0 / 0 | **0 / 0** |
| REPLAN 率 `replan_max` | 1/84 = 0.0119（唯一一局 `PickHighlight/ep3`，648 vs 652 帧） | **0.0357**（×2 + 1/84） |
| `strict_text` / `strict_ts0_grounded` | — | **true**（指令语义或首个目标物不同即 FAIL） |

紧档下 48 局里 **5 局连图像在内全字段按位相同**（InsertPeg 0/2/3、MoveCube 0/2），42 局只剩 1e-16 级舍入；
`PickHighlight/ep3` 是全集里对时序最敏感的身份（已见过 641/643/647/648/652 五个帧数），同架构单 worker 也会偶尔与原版不同。

### `a6000` 最紧档（已标定，2026-09-22；样本：aspen 单 worker 16×3 48 局对原版）

| 项 | 实测观测值 | 最终阈值 |
|---|---|---|
| 手臂四通道 p99、max | 0（47 局全字段按位相同，无 DRIFT 局） | **1e-6**（下限） |
| 帧数差、边界坐标 px、边界帧号偏移、夹爪翻转偏移、ts0 图像 | 0 | **0** |
| REPLAN 率 `replan_max` | 1/48 = 0.0208（`PickHighlight/ep3` 653 vs 652） | **0.0625**（×2 + 1/48） |
| `strict_text` / `strict_ts0_grounded` | — | **true** |

### `a40` 松档（已标定，2026-09-22；样本：greatlakes A40 对原版共 480 局 = 16×3 48 局单 worker + 144 局 4 worker（新跑）+ gl-5e 144 局单 worker + gl-5e-w4 144 局 4 worker；aspen 不进标定）

| 项 | 实测观测值（DRIFT 局最大，或全体最大） | 最终阈值（×2 余量） |
|---|---|---|
| 手臂 `joint_action` / `joint_state` p99、max | 0.0186 / ~0.03 | **0.04 / 0.06** |
| 手臂 `eef_action` / `eef_state` p99、max | 0.017 / ~0.02 | **0.04 / 0.04** |
| 帧数差 `frame_delta_max`（DRIFT 局） | 2 | **4** |
| 边界坐标像素差 `px_tol` | 1 | **2** |
| 边界帧号偏移 `boundary_shift_max`（DRIFT 局） | 2 | **4** |
| 夹爪翻转偏移 `flip_shift_max`（DRIFT 局） | 1 | **2** |
| ts0 图像 `px_diff_ratio` / `depth_max`（全体最大） | 2.53% / 65 | **5.06% / 130** |
| REPLAN 率 `replan_max` | 52/480 = 0.1083 | **0.2188**（×2 + 1/480） |
| `strict_text` / `strict_ts0_grounded` | — | **false**（示范/规划重规划导致的指令或首目标变化记 REPLAN） |

**松档的已知局限（必须知道）**：跨架构下 reset 前的物理沉降有微小差异，InsertPeg/1、PickHighlight/7、VideoRepick/11 的 ts0 图像与原版差 0.13%～2.5% 像素（深度 max 53～65），阈值因此放到 5%/130；而负例（`layout.board.offsets` 改 3 cm/5°）在 ts0 图像上只差 2.1%/62——**松档对这个量级的布局扰动没有检出力**。松档能保证的是 seed/difficulty 合同、reset 后目标中心、任务结构与轨迹形态一致；**布局级回归请用紧档（sled-vail，或 aspen）查**，那里 ts0 图像逐像素相同、任何扰动都会被抓到。

余量规则（`calibrate.py`，`--margin` 默认 2）：手臂阈值 = 观测 DRIFT 局该统计量最大值 × 2 向上取 1 位有效数字；
`replan_max` = 观测 REPLAN 率 × 2 + 1/compared；帧号/像素类上限 = 观测 max × 2；紧档（`strict_text=true` 的 `a6000` / `ada`）的 `ts0_image` 与帧号/像素类上限固定 0，手臂阈值下限 1e-6。

---

## 三、全部实测调用方法

### 3.1 身份

- `identities_16x3.txt`：48 局（子集 manifest 每 (task, difficulty) 第一条 = episode {0, 3, 2}；恢复模式 z=32 / xy=16），供 `run --sequence` 与 `compare --sequence`。
- `manifest_16x3.json`：同 48 局的 manifest（`merge --manifest` 用；merge 要求 manifest 里该环境的局全部存在）。

### 3.2 生成（沿用现有流水线，单卡）

sled-vail（本机，紧档）：

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
SEQ=$(cat scripts/test-vs-original/identities_16x3.txt)
OUT=artifacts/train-parity/tvo-vail-16x3; mkdir -p $OUT
tmux new-session -d -s tvo-vail "set -o pipefail; CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1 .venv/bin/python scripts/train_split_parity.py run --sequence '$SEQ' --paths B --workers 1 --gpus 0 --official-root artifacts/train-parity/local-smoke-01/official-src --output $OUT 2>&1 | tee $OUT/run.log; echo \"EXIT_CODE=\$?\" >> $OUT/run.log"
```

aspen（`ssh -i ~/.ssh/id_ed25519_umich hongzefu@sled-aspen.eecs.umich.edu`，直接用 NFS 克隆的 `.venv`）：

```bash
GL=/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl
OUT=$GL/artifacts/train-parity/aspen-tvo-16x3; mkdir -p $OUT
tmux new-session -d -s tvo-aspen "set -o pipefail; cd $GL; CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1 .venv/bin/python scripts/train_split_parity.py run --sequence '$SEQ' --paths B --workers 1 --gpus 0 --official-root $GL/artifacts/train-parity/gl-5d/shard1/official-src --output $OUT 2>&1 | tee $OUT/run.log; echo \"EXIT_CODE=\$?\" >> $OUT/run.log"
```

greatlakes（四个 spgpu 占位 job，**必须带 `--gpu_cmode=shared`**；每 job 先跑自己那 12 局单 worker，再跑自己那片 144 局 4 worker）：

```bash
# 登录节点上，K=1..4；tvo_segments.txt 是 48 局按顺序切成的四段
tmux new-session -d -s tvo-$K "srun --jobid=<占位job> --overlap --exact --ntasks=1 --cpus-per-task=4 --gpu_cmode=shared $H/tvo_one.sh $K"
# tvo_one.sh 内：
#   run --sequence "$SEG" --paths B --workers 1 --gpus 0 --official-root ... --output $GL/artifacts/train-parity/gl-tvo-16x3/shard$K
#   run --shard $K/4      --paths B --workers 4 --gpus 0 --official-root ... --output $GL/artifacts/train-parity/gl-tvo-w4/shard$K
```

### 3.3 合并成官方布局

```bash
.venv/bin/python scripts/train_split_parity.py merge --run <run或分片…可重复> --path B \
  --manifest scripts/test-vs-original/manifest_16x3.json \
  --official-root artifacts/train-parity/local-smoke-01/official-src --output <merged>
```

（144 局用默认 `subset_manifest.json`；单局负例用只含该局的 manifest。）

### 3.4 比较

```bash
.venv/bin/python scripts/test-vs-original/compare_vs_original.py \
  --generated <merged> --reference /data/hongzefu/robomme_data_h5 \
  --tier auto --official-root artifacts/train-parity/local-smoke-01/official-src \
  --label "<机器 规模 worker数>" --output scripts/test-vs-original/results/<名字> [--verbose]
```

### 3.5 标定

```bash
.venv/bin/python scripts/test-vs-original/calibrate.py --tier a40 \
  --results scripts/test-vs-original/results/gl-16x3-48-w1 scripts/test-vs-original/results/gl-w4-144 ... \
  --note "<用了哪些产物>" --write
```

---

## 四、实测结果（2026-09-22，全部"产物 vs 原版发布集"）

三条生成线同步发（sled-vail、aspen、greatlakes 四个占位 job），零失败：vail 48 局 2969 s、aspen 48 局 2493 s、
GL 48 局单 worker 四片 237～565 s、GL 144 局 4 worker 四片 273～685 s。

### 4.1 紧档（`ada`，sled-vail RTX 6000 Ada）

```text
VS_ORIGINAL=PASS tier=ada compared=48 identical=5 drift=42 replan=1 fail=0 replan_rate=0.0208 replan_max=0.0357   ← 16×3 48 局单 worker
# 手臂通道 DRIFT 局 p99 最大值：joint_action=6.66e-16 eef_action=0 joint_state=0 eef_state=0
# 布局层：ts0 grounded 相同=48/48；ts0 图像最大像素差比例=0.0000，深度 max=0；边界坐标最大像素差=0；边界帧号最大偏移=2；夹爪翻转最大偏移=2；帧数最大差=4
REFERENCE_AUDIT_COMPLETE=PASS compared=48 contract_errors=0 missing=0
VS_ORIGINAL=PASS tier=ada compared=36 identical=0 drift=36 replan=0 fail=0 replan_rate=0.0000 replan_max=0.0357   ← local-recheck 36 局单 worker（正例）
```

5 局连图像在内全字段按位相同（InsertPeg 0/2/3、MoveCube 0/2）；唯一 REPLAN 是 `PickHighlight/ep3`（648 vs 652 帧）。

### 4.2 aspen（A6000，单 worker，`a6000` 档）

```text
VS_ORIGINAL=PASS tier=a6000 compared=48 identical=47 drift=0 replan=1 fail=0 replan_rate=0.0208 replan_max=0.0625
# 布局层：ts0 grounded 相同=48/48；ts0 图像最大像素差比例=0.0000，深度 max=0；边界帧号最大偏移=1；夹爪翻转最大偏移=1；帧数最大差=1
```

**47/48 逐位复现原版**（含四路图像；14 局仅 `task_goal` 标点/改写条目不同，归一化后计 IDENTICAL），
唯一例外 `PickHighlight/ep3`（653 vs 652）。aspen 上存有 2026-03-06 的 `robomme_benchmark-v0.5` 克隆，与发布集文件日期一致——
**原版发布集几乎可以确定就产自 aspen**。按此数据 A6000 才是原版的"同机器"，比 sled-vail（5/48 逐位、其余 1e-16）还紧，
因此单独成档（用户 2026-09-22 决定）。松档标定不含 aspen 数据。

### 4.3 松档（`a40`，greatlakes A40，定稿阈值）

```text
VS_ORIGINAL=PASS tier=a40 compared=48 identical=0 drift=43 replan=5 fail=0 replan_rate=0.1042 replan_max=0.2188    ← 16×3 48 局单 worker
# 手臂通道 DRIFT 局 p99 最大值：joint_action=0.0189 eef_action=0.0227 joint_state=0.0185 eef_state=0.0226（阈值 0.04）
# 布局层：ts0 grounded 相同=47/48；ts0 图像最大像素差比例=0.0120，深度 max=10
VS_ORIGINAL=PASS tier=a40 compared=144 identical=0 drift=130 replan=14 fail=0 replan_rate=0.0972 replan_max=0.2188   ← 144 局 4 worker（新跑）
VS_ORIGINAL=PASS tier=a40 compared=144 identical=0 drift=130 replan=14 fail=0 replan_rate=0.0972 replan_max=0.2188   ← gl-5e 144 局单 worker（步 5d 的 A1 路）
VS_ORIGINAL=PASS tier=a40 compared=144 identical=0 drift=130 replan=14 fail=0 replan_rate=0.0972 replan_max=0.2188   ← gl-5e-w4 144 局 4 worker（步 5d 首轮）
# 三份 144 局：ts0 grounded 相同=141/144；ts0 图像最大像素差比例=0.0253，深度 max=65；帧数最大差=194
```

三份 A40 144 局产物（新跑 4 worker、旧单 worker、旧 4 worker）的四类计数**完全相同**（130/14/0），
说明松档判定对 worker 数与运行批次都稳定；3 局 ts0 grounded 不同（BinFill/ep2、BinFill/ep11、VideoRepick/ep11）均为规划层差异记 REPLAN。

**多 worker 与单 worker 在松档下同量级**：REPLAN 率 9.7%（4 worker，144 局）vs 10.4%（单 worker，48 局），
说明跨架构漂移是主导项、worker 争抢只是叠加少量重规划。

aspen 用松档判：`VS_ORIGINAL=PASS tier=a40 compared=48 identical=47 drift=0 replan=1 fail=0`。

负例在松档下：`# BinFill/ep0: REPLAN replan:frames:558vs550,arm:…,subgoal:px=8,boundary_shift=13,gripper:flip_shift=13`——
**不再是布局层 FAIL**（ts0 图像 2.1%/62 落在 5.06%/130 内），只因单局 REPLAN 率 100% 才使数据集 FAIL；这就是第二节写明的松档局限。

### 4.4 跨档与正负例

```text
# A40 产物用紧档判 → 必须 FAIL（档位守卫有效）
VS_ORIGINAL=FAIL tier=ada compared=144 identical=0 drift=11 replan=122 fail=11 replan_rate=0.8472 replan_max=0.0357   ← gl-5e 144 局
# 负例：BinFill/0 的 layout.board.offsets 改 (x+0.03, y−0.02, yaw+5°)，两档都 FAIL，由 ts0 图像抓到（目标中心反而相同）
# BinFill/ep0: FAIL layout:ts0_depth_over_tol,ts0_rgb_over_tol      （紧档：2.1% 像素、深度 max 62 > 0）
VS_ORIGINAL=FAIL tier=ada compared=1 identical=0 drift=0 replan=0 fail=1
```

负例在**定稿后的松档**下的判定见 4.3（松档 ts0 阈值 5%/130 大于负例的 2.1%/62，预期不再 FAIL——这就是第二节写明的松档局限）。

## 五、边界与注意

- 紧档只做了单 worker 标定（用户决定本地两台只测单 worker）；若日后在 sled-vail 用多 worker 生成，须先补标定。
- aspen 产物按 `a6000` 档判；松档（a40）标定不含 aspen 数据。
- 测试产生的 h5/mp4（本机 52 G、NFS 126 G）已在 commit、汇报、用户确认后删除；只保留 `results/` 下的 JSON/JSONL。
