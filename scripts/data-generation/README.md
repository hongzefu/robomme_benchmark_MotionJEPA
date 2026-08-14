# data-generation：机械臂 mask 标定与生产

把 `front_rgb` 里的机械臂标出来，产出 **Wan VAE latent 对齐的 32×32 格级 mask**，
供下游 MotionJEPA 消费。整条链路分两个阶段，对应两个子文件夹：

| 阶段 | 子文件夹 | 做什么 |
|---|---|---|
| **第一阶段** | `gt-data/` | 生成带 **GT segmentation** 的数据，并在其上拟合**像素表**（颜色表） |
| **第二阶段** | `arm-mask/` | 用像素表产 mask（两个模式共用一条路径），并在有 GT 时给实测结果 |

mask 的推理链固定为三步，全链路**零浮点阈值**：

```
像素表查表 → 四条形态学规则 → K=13 网格化（32×32，一格 = 一个 latent 位置）
```

数据范围：官方 `Yinpei/robomme_data_h5` 本地备份 `/data/hongzefu/robomme_data_h5`，
**train split 每任务前 10 个 episode（ep0-9）**。所有命令都在仓库根执行。

---

## 一、第一阶段：生成 GT 数据 + 拟合像素表（`gt-data/`）

### 1.1 GT 数据怎么生成

入口是 `generate_dataset.py`。它读 `src/robomme/env_metadata/<split>/` 里记录的
**官方实际使用的 seed**（含官方失败重试后递增过的值，直接取用、单次尝试、不做递增
重试），同 seed 重建 env，然后由 **planner 重新规划动作**走完整个 episode。落盘时
`record_wrapper.py`（`RecordWrapper` 的薄子类）在既有 h5 内容之外**只增不改**地多写
两样东西：

- 逐帧 GT segmentation：`timestep_<k>/obs/front_camera_segmentation`，直接取自
  ManiSkill 的 `obs`，是仿真真值，不含任何像素估计；
- seg_id 枚举表：`setup/segmentation_objects` / `setup/segmentation_excluded`
  （「场景对象 → segmentation id」清单，GT 三类映射的唯一依据，见 `seg_id_table.py`）。

两个关键设定（用户 2026-08-14 拍板，详见第五节）：**不回放 joint angle**——同 seed
只保证场景初始摆放与官方一致，轨迹会不同；**失败 episode 跳过**并记入
`generation_summary.json`，不影响其余产物落盘。

```bash
uv run --locked python scripts/data-generation/gt-data/generate_dataset.py \
  --output-dir artifacts/generated/<名字> --env all --episodes 10 --split train \
  --workers 16 --gpus 0,1
```

### 1.2 像素表怎么拟合

入口是 `fit_color_model.py`，这是整条链路**唯一**读 GT 来产出模型的地方。它在上一步
生成的带 GT 数据上，统计每种 24 位颜色在三列里的出现计数：**列 0 = 纯背景**、
**列 1 = 背景∪物体混合**（物体不单独可见，类先验对模型不可见）、**列 2 = 机械臂**。
推理时逐像素查表，只看每列「见过 / 没见过」（纯支撑三段式，计数大小不参与），
判臂条件是「混合列一次都没出现过且臂列出现过」——这使**标定集上误标物体恒为 0 是
恒等式**。完整推导与代价分析见 `color_model.py` 模块 docstring。

⚠ **标定集必须与实测集零 seed 重叠**：现行像素表在 **val split ep0-9** 上拟合，第二
阶段消费的是 **train split ep0-9**，零重叠，实测数字是干净的泛化数字。

```bash
# 需先用 1.1 的命令生成一份 --split val 的数据集；拟合本身单进程约 19 分钟
uv run --no-sync python scripts/data-generation/gt-data/fit_color_model.py \
  --h5 'artifacts/generated/<val 数据集>/record_dataset_*.h5' --episodes 0-9 \
  --out scripts/data-generation/gt-data/outputs/color_model.npz
```

产物 `outputs/color_model.npz` 是本目录**唯一入 git 的产物**，已随仓库提供——
**一般不需要重跑第一阶段**，直接进第二阶段即可。

---

## 二、第二阶段：mask 生产（`arm-mask/`）

两个模式共用同一个生产入口 `make_mask.py`，走完全相同的代码路径且**全程不看 GT**
（只读 `obs/front_rgb` 与 `info/`）；差别只在 `--source` 指向哪份数据、以及事后有没有
GT 可以量化。**两个模式都不包含任何 replay**。

| 模式 | 做什么 | 有 GT？ | 产出 |
|---|---|---|---|
| **①** | 读官方 h5 里现成的 `front_rgb`，直接跑推理链 | 否 | sidecar |
| **②** | 官方同 seed 重新生成带 GT 的数据，产 mask 后用 GT 量化 | 是 | sidecar + 实测 JSON |

### 2.1 模式①：官方 h5 直接产 mask

只读官方 h5 现成的像素，不重放、不起仿真，一条命令直接出 sidecar：

```bash
uv run --no-sync python scripts/data-generation/arm-mask/make_mask.py \
  --source /data/hongzefu/robomme_data_h5 --tasks all --episodes 0-9 --workers 16
```

官方数据没有 GT，因此模式①只有**金丝雀**（未见颜色率的倍率 + 绝对值双判据、空 mask
帧与判臂率下限的结构闸门，FAIL 以退出码 1 结束）与结构统计量，没有精确率 / 召回这类
以 GT 为尺的数字——那些数字只能来自模式②。

### 2.2 模式②：同 seed 重新生成 + 实测

一条命令跑完四步编排（`run_generated.py`）：

```
生成（gt-data/generate_dataset.py，即第一阶段 1.1 的同一入口，--split train）
  → 产 mask（make_mask.py，与模式①完全同一条路径，全程不看 GT）
  → 实测（evaluate.py，读 sidecar + GT，pixel/grid 双口径 + 刚性闸门）
  → 删数据集（用户拍板：约 60 GB，跑完即删，只留 sidecar 与实测 JSON）
```

```bash
uv run --locked python scripts/data-generation/arm-mask/run_generated.py \
  --episodes 10 --workers 16 --gpus 0,1
#   加 --keep-dataset 保留数据集（约 60 GB）供换参重跑
#   加 --skip-generate 对已存在的数据集只跑后三步
```

GT 量化是独立的一步（`evaluate.py` 读 sidecar），既不混进生成器、也不混进 mask
生产。planner 失败的 episode 会被跳过，实测样本量可能少于「任务数 × episode 数」，
实测 JSON 里如实记录。

单步拆开跑（`run_generated.py` 内部就是串这三条）：

```bash
uv run --locked python scripts/data-generation/gt-data/generate_dataset.py \
  --output-dir artifacts/generated/<名字> --env all --episodes 10 --split train \
  --workers 16 --gpus 0,1
uv run --no-sync python scripts/data-generation/arm-mask/make_mask.py \
  --source artifacts/generated/<名字> --episodes 0-9 --out-dir <sidecar 目录> --no-baseline
uv run --no-sync python scripts/data-generation/arm-mask/evaluate.py \
  --sidecar-dir <sidecar 目录> --source artifacts/generated/<名字> --episodes 0-9
```

---

## 三、实测结果（2026-08-14，16 任务 × ep0-9 = 160 episode / 80,853 帧）

数字全部来自模式②——它是唯一有 GT 当尺子的口径。模式①（官方 h5）没有 GT，只有金丝雀
与结构量。机读原件在 `arm-mask/outputs/json/`。

### 3.1 像素口径（刚性红线在此，红线定义见第四节）

逐帧把 256×256 像素 mask（sidecar 的 `arm_mask_px`）与 GT 三类标签
（`front_camera_segmentation` 按 seg_id 表映射成 臂/物体/背景）逐像素比对，全部
episode 累加后算比值：

| 指标 | 含义（怎么算） | 实测 |
|---|---|---:|
| **误标物体像素（刚性红线）** | 被判臂但 GT 真身是**物体**的像素总数，`Σ|mask ∧ GT=物体|` | **0** |
| 误标背景像素 | 被判臂但 GT 真身是**背景**的像素总数 | **0** |
| **标定精确率** | 判臂像素里 GT 真身确为臂的比例，真臂 / 全部判臂 | **1.000000** |
| 机械臂召回 | GT 臂像素里被判臂的比例，真臂 / 全部 GT 臂 | 0.816906 |
| 未见颜色率 | 颜色不在像素表里的像素 / 全部像素（帧数 × 65536）。未见 ⇒ 不判臂，方向安全 | 0.1626% |
| 存在物体误标的帧占比 | 误标物体像素 > 0 的帧数 / 总帧数 | 0 |

闸门输出：逐 episode 共 160 项误标物体像素全部为 0。实测耗时 11.5 秒（16 进程）——
`evaluate.py` 读 sidecar 而非重跑推理链，故比历史上「两处各跑一遍链路」快近一个数量级。

### 3.2 网格口径 K=13（⚠ 刚性红线在此不适用，原因见第四节）

每帧 32×32 个格子（一格 = 8×8 = 64 像素），格内像素 mask 计数 ≥ K=13 的格被选中
（「臂格」）。选中即**整格涂红**——下面所有比值的「涂红像素」都指选中格的全部
64 像素，再与 GT 三类比对：

| 指标 | 含义（怎么算） | 实测 |
|---|---|---:|
| GT 臂像素覆盖率 | 涂红区域盖住的 GT 臂像素 / 全部 GT 臂像素（网格版召回） | 0.883361 |
| GT 物体像素被涂比例 | 涂红区域盖住的 GT 物体像素 / 全部 GT 物体像素 | 0.006211 |
| 网格精确率 | 涂红像素里 GT 真身为臂的比例，涂中的 GT 臂 / （选中格数 × 64） | 0.916749 |
| **纯误涂格（格内 GT 臂像素为 0）** | 被选中但格内一个 GT 臂像素都没有的格数 | **0** |
| 网格臂格占比（/ 全部格） | 选中格数 / 全部格数（帧数 × 1024） | 6.417% |

**纯误涂格恒为 0** 是像素刚性红线在网格口径留下的结构性遗产：任何被选中的格子都至少含
1 个真臂像素。

**低估补偿换算表**（名义占比是链路看到的，GT 臂真实占比才是真相）：K=13 名义 20.3%，
格内 **GT 臂真实平均占比 50.6%**；K=32 名义 50%，实际 69.1%。想选「格内真实臂占比 ≥ X」
直接查 JSON 里的 `低估补偿换算表`，**不要拿整体召回做反推**——反推假设漏标在格间均匀，
实际薄边缘格漏得多、臂身中央格几乎不漏。

### 3.3 模式①（官方 h5）

没有 GT，只有不依赖 GT 的结构量：**像素判臂率** = 判臂像素 / 全部像素（衡量 mask
体量是否正常）；**空像素 mask 帧 / 空网格帧** = 整帧一个判臂像素 / 一个选中格都没有的
帧数（画面顶部机械臂基座恒可见，正常应为 0）。实测 80,853 帧，未见颜色率 0.1626%，
像素判臂率 5.44%，空像素 mask 帧 0、空网格帧 0，**金丝雀 PASS（零命中项，金丝雀定义
见 2.1）**，耗时 68 秒。sidecar 44 MB。

### 3.4 ⚠ 同 seed 重放的实际保真度

用户决策里预估的两项代价（见第五节），本轮实测**都没有兑现**：

| 预估代价 | 本轮实测 |
|---|---|
| 可能无法 100% 完成全部 episode | **160/160 成功，0 失败** |
| 可能无法获得完全一致的 RGB 观察 | 抽 6 个任务 8 个 episode（2734 帧）与官方逐像素对比，**8/8 帧数相同且逐位完全一致，最大绝对差 0** |

佐证：模式①与模式②在 **16/16 个任务**上的帧数、未见色像素、臂像素、网格格数四项**逐位
相等**——两份数据在本链路看来完全同一。成因是 screw 规划本身确定性，只有 RRTStar 兜底
才引入随机，本轮未触发。

⚠ **这是实测观察，不构成保证。** 采样非全量；多 worker 抢卡时兜底一旦触发就会分叉；
本链路也没有任何机制去校验它（对拍器已随「不回放 joint angle」一并删除）。第五节的风险
声明照旧成立，不因这次结果放松。

---

## 四、刚性红线（第一判据，只约束像素口径）

**不得把物体判错成 robot arm，「判错」以 GT 为准。** 精确说法：整段每一帧被标成臂的像素，
逐个查它在 `obs/front_camera_segmentation` 里的真身，真身是「物体」的像素数累加必须恒为 0
（`false_object_pixels`）。`evaluate.py` 的 `enforce_no_false_object` 逐 episode 校验，
非 0 即以非零退出码结束，**刻意不提供豁免开关**。

三点保障：口径偏保守（GT 侧认不出的 seg id 一律兜底归物体，单独计数不许静默）；判臂的
定义使**标定集上误标物体恒为 0 是恒等式**（判臂 = 混合列一次都没出现过，而混合列已把 GT
物体像素全部计入）；红线由代码闸门而非文档保证。

### ⚠ 这条红线不适用于网格口径

整格涂红必然覆盖臂边界格里的物体/背景像素，「不得误标物体」在网格口径下必然击穿、也不该
成立。网格口径下 GT 全程只当尺子做量化记录，不设闸门。**不要拿像素口径的结论去推网格
mask 的性质。**

### ⚠ 网格 mask 打破「只减不增」

四条形态学规则每条都只让区域变小或持平；网格化在 K=1 时是像素 mask 的**严格超集**——它是
整条链路第一个会让区域变大的算子。替代性质是**对阈值单调收缩**：K1 ≤ K2 ⇒
grid(K2) ⊆ grid(K1)（两条都有单测钉死）。

### ⚠ 时间维未对齐

本口径只对齐 Wan VAE 的**空间** 8× 下采样；Wan VAE 还有时间维 4× 压缩（首帧单独成组），
网格 mask 是**逐帧独立**的。接生成链路时不要把「一格 = 一个 latent 位置」外推到时间维。

---

## 五、用户关键决策（逐条生效，改动前先确认）

1. **不使用任何 joint angle 回放功能。** 动作由 planner 重新规划，代价是：
   - 可能**无法 100% 完成全部 episode**——失败的跳过并记入摘要，不影响其余产物落盘；
   - **RGB 观察与官方不完全一致**——同 seed 只保证场景初始摆放一致，轨迹会不同。
   - 因此与官方数据的契约校验、`joint_action` 逐位对拍全部删除，不存在开关。
2. **不再生成 flow，本目录不出现 flow 命名。** 历史上的逐帧稀疏物体轨迹采集已整体删除；
   原 `setup/flow_objects` / `flow_excluded` 那张表实质是「场景对象 → segmentation id」
   清单，是 GT 三类映射的唯一依据，保留并改名为 `setup/segmentation_objects` /
   `setup/segmentation_excluded`（见 `gt-data/seg_id_table.py`）。
3. **像素表沿用 val split ep0-9 拟合的 `color_model.npz`**，与两个模式消费的 train split
   **零 seed 重叠**，所以实测是干净的泛化数字。
4. **网格阈值 K = 13** 全局统一（全任务 / 全 episode / 全格子位置一体生效），唯一落点是
   `arm-mask/make_mask.py` 的 `GRID_MIN_PIXELS`；`grid_mask.GridParams.min_pixels` 刻意
   无默认值，库层不立第二个口径。
5. **模式②的数据跑完即删**（约 60 GB），只留 sidecar 与实测 JSON。

---

## 六、已知代价（诚实清单）

1. **臂与混合共享的中性灰白色一律不判臂**：臂的灰白外壳与灰白物体撞色的部分照旧漏标。
   这是本方案唯一的结构性漏标来源，代价有闭式（见 `color_model.py`）。
2. **物体误标在评估集上没有理论零保证**（标定集上才是恒等式），所以才有硬闸门——数字以
   每次实测为准，不以推理为准。
3. **未见颜色一律不标**，方向与宗旨一致（宁可漏标）。
4. **触顶规则漏掉非从上方入画的臂**（可接受漏标）。
5. **模式①的根本盲点**：官方数据没有 GT，像素刚性红线在那里**不可复验**。关闭这个盲点
   正是模式②存在的理由——同 seed 重放出带 GT 的同场景数据，让红线可验。
6. **模式②与官方轨迹不同**：不回放 joint angle，实测数字代表「同场景、planner 自己走一遍」
   的表现，不是官方那一模一样的画面上的表现。

---

## 七、文件结构与实现细节

```text
gt-data/                     第一阶段：产 GT + 拟合像素表
  generate_dataset.py        生成入口（--split/--episodes；失败 episode 跳过并记录）
  record_wrapper.py          薄子类：落盘 GT segmentation + seg_id 表。⚠ 不 override step()
  seg_id_table.py            场景对象 → segmentation id 枚举表（GT 三类映射的唯一依据）
  contract.py                任务清单、各 split episode 条数、metadata 严格读取
  color_model.py             像素表定义 / 拟合 / 推理（唯一碰 GT 的模块）
  fit_color_model.py         拟合入口
  outputs/color_model.npz    ★ 像素表，唯一入 git 的产物
arm-mask/                    第二阶段：产 mask + 实测
  make_mask.py               唯一 mask 生产入口（模式①②共用，全程不看 GT），K=13 唯一落点
  evaluate.py                模式②实测：读 sidecar + GT，pixel/grid 双口径 + 刚性闸门
  run_generated.py           模式②编排：生成 → mask → 实测 → 删数据
  arm_mask.py                四条形态学规则
  grid_mask.py               32×32 网格化纯函数
  outputs/                   sidecar 与实测 JSON（gitignore）
```

`arm-mask` 只通过 `sys.path` 只读 import `gt-data/color_model.py` 的推理侧——像素表的定义
与拟合归 `gt-data`，`arm-mask` 绝不复制第二份判别口径。

### 四条形态学规则（`arm_mask.py`，完全不看 GT）

结构元统一 3×3 八邻域。先按 `info/is_video_demo` 切相位（跨相位投票会混两个场景），每段
独立跑：①**开运算**去抗锯齿噪点；②**只保留触到画面第 0 行的连通域**（机械臂根部固定在
画面顶部、任务物体不触顶，这是「不误标物体」最主要的结构性保障）；③**3 帧滑动多数表决**
（⚠ 四条里唯一可能让区域变大的一条）；④**保守收缩**：先与本帧候选取交（白名单），再腐蚀
一次，顺序不能反。④的白名单交保证最终 mask 一定是本帧候选的子集——改动④时务必记得。

可调项只有三个整数（开运算 1、时间窗 3、末腐蚀 1），**浮点阈值数量为 0**。

### sidecar schema（`arm_grid_mask_<Task>.h5`）

每 episode 三层全存（gzip4）：

| dataset | shape / dtype | 说明 |
|---|---|---|
| `arm_grid_mask` | (T,32,32) bool | **正式产物**，K=13 |
| `arm_cell_counts` | (T,32,32) uint8 | 阈值无关，`counts >= K` 即任意档网格——**换 K 免重跑 mask** |
| `arm_mask_px` | (T,256,256) bool | 像素层留痕，任意 K / 涂红帧可由它重建 |
| `is_video_demo` / `is_completed` | (T,) bool | 下游切段与 exec 截断必需 |
| `unseen_pixels` / `arm_pixels` / `timestep_index` | (T,) int32 | 逐帧未见色数 / 像素 mask 数 / 主键 |

**刻意不存 `exec_len`**：`first_completed + 2` 的截断公式留在下游，防两仓两口径。
主键对齐：(task, `episode_<i>`, timestep 序) ↔ MotionJEPA 侧 `<Task>_ep<i>`。
写后默认回读逐位对拍（`--no-verify` 可关）。

### 单元测试

```bash
uv run --no-sync python -m pytest tests/lightweight/test_arm_mask.py \
  tests/lightweight/test_grid_mask.py tests/lightweight/test_make_mask.py \
  tests/lightweight/test_seg_id_table.py tests/lightweight/test_record_wrapper.py -q
```
