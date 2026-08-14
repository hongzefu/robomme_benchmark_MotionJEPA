# data-generation：机械臂 mask 标定与生产

把 `front_rgb` 里的机械臂标出来，产出 **Wan VAE latent 对齐的 32×32 格级 mask**。
两个子文件夹职责不重叠：

| 子文件夹 | 职责 |
|---|---|
| `gt-data/` | 生成带 **GT segmentation** 的数据，并在其上拟合**像素表**（颜色表） |
| `arm-mask/` | 用像素表产 mask（两种数据源共用一条路径），并在有 GT 时给实测结果 |

推理链固定为三步，全链路**零浮点阈值**：

```
像素表查表 → 四条形态学规则 → K=13 网格化（32×32，一格 = 一个 latent 位置）
```

---

## 一、两个模式

| 模式 | 做什么 | 有 GT？ | 产出 |
|---|---|---|---|
| **① 现有 dataset 直接产 mask** | 读官方 h5 里已有的 `front_rgb`，直接跑推理链 | 否 | sidecar |
| **② 同 seed 重新生成 + 实测** | 用官方同 seed 重新渲染带 GT 的数据，在其上产 mask 并用 GT 当尺子量化 | 是 | sidecar + 实测 JSON |

**两个模式都不包含任何 replay。** 模式①只读 h5 里现成的像素，不重放、不起仿真；
模式②是纯 planner 重新规划生成，不读官方动作。

**mask 单独生产**：两个模式共用同一个 `make_mask.py`，走完全相同的代码路径且**全程不看
GT**；模式②的 GT 量化是之后独立的一步（`evaluate.py` 读 sidecar），既不混进生成器、也不
混进 mask 生产。

数据范围：官方 `Yinpei/robomme_data_h5` 本地备份 `/data/hongzefu/robomme_data_h5`，
**train split 每任务前 10 个 episode（ep0-9）**。

---

## 二、用户关键决策（逐条生效，改动前先确认）

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

## 三、刚性红线（第一判据，只约束像素口径）

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

## 四、用法（在仓库根）

```bash
# 模式①：官方 h5 直接产 mask（16 任务 × ep0-9）
uv run --no-sync python scripts/data-generation/arm-mask/make_mask.py \
  --source /data/hongzefu/robomme_data_h5 --tasks all --episodes 0-9 --workers 16

# 模式②：一条命令跑完 生成 → 产 mask → 实测 → 删数据
uv run --locked python scripts/data-generation/arm-mask/run_generated.py \
  --episodes 10 --workers 16 --gpus 0,1
#   加 --keep-dataset 保留数据集（约 60 GB）供换参重跑
#   加 --skip-generate 对已存在的数据集只跑后两步

# 单步跑（run_generated.py 内部就是串这三条）
uv run --locked python scripts/data-generation/gt-data/generate_dataset.py \
  --output-dir artifacts/generated/<名字> --env all --episodes 10 --split train \
  --workers 16 --gpus 0,1
uv run --no-sync python scripts/data-generation/arm-mask/make_mask.py \
  --source artifacts/generated/<名字> --episodes 0-9 --out-dir <sidecar 目录> --no-baseline
uv run --no-sync python scripts/data-generation/arm-mask/evaluate.py \
  --sidecar-dir <sidecar 目录> --source artifacts/generated/<名字> --episodes 0-9

# 重新拟合像素表（一般不用跑：需先生成 val split 数据集，单进程约 19 分钟）
uv run --no-sync python scripts/data-generation/gt-data/fit_color_model.py \
  --h5 'artifacts/generated/<val 数据集>/record_dataset_*.h5' --episodes 0-9 \
  --out scripts/data-generation/gt-data/outputs/color_model.npz

# 单元测试
uv run --no-sync python -m pytest tests/lightweight/test_arm_mask.py \
  tests/lightweight/test_grid_mask.py tests/lightweight/test_make_mask.py \
  tests/lightweight/test_seg_id_table.py tests/lightweight/test_record_wrapper.py -q
```

---

## 五、文件结构

```text
gt-data/                     职责①：产 GT + 拟合像素表
  generate_dataset.py        生成入口（--split/--episodes；失败 episode 跳过并记录）
  record_wrapper.py          薄子类：落盘 GT segmentation + seg_id 表。⚠ 不 override step()
  seg_id_table.py            场景对象 → segmentation id 枚举表（GT 三类映射的唯一依据）
  contract.py                任务清单、各 split episode 条数、metadata 严格读取
  color_model.py             像素表定义 / 拟合 / 推理（唯一碰 GT 的模块）
  fit_color_model.py         拟合入口
  outputs/color_model.npz    ★ 像素表，唯一入 git 的产物
arm-mask/                    职责②：产 mask + 实测
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

---

## 六、实测结果（2026-08-14，16 任务 × ep0-9 = 160 episode / 80,853 帧）

数字全部来自模式②——它是唯一有 GT 当尺子的口径。模式①（官方 h5）没有 GT，只有金丝雀
与结构量。机读原件在 `arm-mask/outputs/json/`。

### 6.1 像素口径（刚性红线在此）

| 指标 | 实测 |
|---|---:|
| **误标物体像素（刚性红线）** | **0** |
| 误标背景像素 | **0** |
| **标定精确率** | **1.000000** |
| 机械臂召回 | 0.816906 |
| 未见颜色率 | 0.1626% |
| 存在物体误标的帧占比 | 0 |

闸门输出：逐 episode 共 160 项误标物体像素全部为 0。实测耗时 11.5 秒（16 进程）——
`evaluate.py` 读 sidecar 而非重跑推理链，故比历史上「两处各跑一遍链路」快近一个数量级。

### 6.2 网格口径 K=13（⚠ 刚性红线在此不适用）

| 指标 | 实测 |
|---|---:|
| GT 臂像素覆盖率 | 0.883361 |
| GT 物体像素被涂比例 | 0.006211 |
| 网格精确率 | 0.916749 |
| **纯误涂格（格内 GT 臂像素为 0）** | **0** |
| 网格臂格占比（/ 全部格） | 6.417% |

**纯误涂格恒为 0** 是像素刚性红线在网格口径留下的结构性遗产：任何被选中的格子都至少含
1 个真臂像素。

**低估补偿换算表**（名义占比是链路看到的，GT 臂真实占比才是真相）：K=13 名义 20.3%，
格内 **GT 臂真实平均占比 50.6%**；K=32 名义 50%，实际 69.1%。想选「格内真实臂占比 ≥ X」
直接查 JSON 里的 `低估补偿换算表`，**不要拿整体召回做反推**——反推假设漏标在格间均匀，
实际薄边缘格漏得多、臂身中央格几乎不漏。

### 6.3 模式①（官方 h5）

80,853 帧，未见颜色率 0.1626%，像素判臂率 5.44%，空像素 mask 帧 0、空网格帧 0，
**金丝雀 PASS（零命中项）**，耗时 68 秒。sidecar 44 MB。

### 6.4 ⚠ 同 seed 重放的实际保真度

用户决策里预估的两项代价，本轮实测**都没有兑现**：

| 预估代价 | 本轮实测 |
|---|---|
| 可能无法 100% 完成全部 episode | **160/160 成功，0 失败** |
| 可能无法获得完全一致的 RGB 观察 | 抽 6 个任务 8 个 episode（2734 帧）与官方逐像素对比，**8/8 帧数相同且逐位完全一致，最大绝对差 0** |

佐证：模式①与模式②在 **16/16 个任务**上的帧数、未见色像素、臂像素、网格格数四项**逐位
相等**——两份数据在本链路看来完全同一。成因是 screw 规划本身确定性，只有 RRTStar 兜底
才引入随机，本轮未触发。

⚠ **这是实测观察，不构成保证。** 采样非全量；多 worker 抢卡时兜底一旦触发就会分叉；
本链路也没有任何机制去校验它（对拍器已随「不回放 joint angle」一并删除）。第二节的风险
声明照旧成立，不因这次结果放松。

---

## 七、已知代价（诚实清单）

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
