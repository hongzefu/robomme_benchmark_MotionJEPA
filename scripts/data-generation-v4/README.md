# 数据生成 v4：用 GT 三类像素分布 + 形态学规则标定机械臂

本目录回答的问题与 [v3-claude](../data-generation-v3-claude/README.md) /
[v3.1-claude](../data-generation-v3.1-claude/README.md) 是同一个——**把 RoboMME
`front_rgb` 里的机械臂标出来、涂成纯红 (255,0,0)**——但**口径整个换掉**：

| 方面 | v3 / v3.1 | **v4（本目录）** |
|---|---|---|
| 允许用仿真真值吗 | 完全不许，AST 防火墙钉死 | **允许，但只允许一处**：用 GT segmentation 得到背景 / 物体 / 机械臂三类的像素分布 |
| 判据 | 背景差分 + 无彩先验 + 触边连通 + 一堆经验阈值 | **颜色表最大后验 + 四条形态学规则**，无人工阈值 |
| 宗旨 | v3「多删可接受、漏删不可接受」；v3.1「物体零误删 + 保黑指尖」 | **绝不误标其他物体；允许少量机械臂没被标进去** |
| 验证 | 人眼逐张目视 | **对 GT segmentation 逐像素算指标**，拟合集 / 留出集分开 |

## 口径（用户逐条拍板）

1. **三类的定义**，直接读 h5 `setup` 里现成的 seg_id 枚举表：
   - **机械臂** = `flow_excluded` 中 `reason == "robot_link"` 的 link（15 个，含腕相机支架与两根手指）
   - **背景** = `flow_excluded` 中 `reason == "background_prop"`（`table-workspace`、`ground`）+ seg_id 0
   - **物体** = `flow_objects` 里的 actor / link（`fixed_cube`、`peg_head`、`goal_site` 这些）

   `flow_objects` 里还有一项 `kind == "tcp"`（`panda_hand_tcp`）——夹爪的工具中心点，
   一个不参与渲染的虚拟坐标点，语义上属于机器人，因此归**机械臂**。

   ⚠ **setup 表没覆盖的 seg id 归物体**（用户拍板）：`flow_objects` / `flow_excluded`
   是 `reset()` 那一刻对 `segmentation_id_map` 的快照，**episode 运行中动态创建的对象
   不在里面**。实测 5 个任务会出现这种 id，逐帧目视核对过，全是任务的目标 / 路径标记物：
   InsertPeg 箱顶的插孔标记（29–32）、PickHighlight 的绿色高亮块（27–32）、
   SwingXtimes 的靶心圆盘（27–30）、PatternLock 的图案连线节点（id 涨到 572）、
   RouteStick 的路线曲线（涨到 710）。机器人各 link 与桌面地面都是 `reset()` 之前
   就建好、已被完整枚举的，所以运行中新出现的 id 必定是任务相关的可见物体——归物体
   既符合语义，也让它们吃到下游的物体硬否决保护。这条兜底不是静默的：这部分像素在
   `metrics.json` 里由 `uncovered_gt_pixels` / `false_uncovered_pixels` 单独计数。

2. **GT 只在拟合分布时出现**。逐帧推理完全不看 GT；验证环节的 GT 是尺子，不参与产出。

3. **尽量不引入阈值**。全部可调项只有三个整数（开运算 1 次、时间窗 3 帧、最终腐蚀
   1 次），没有任何一个是在连续量上切一刀。

4. **规则尽可能简单**，四条，见下。

5. **宗旨**：不能误标定其他物体；允许少量机械臂没被标进去。

## 方法

### 一、三类像素分布 = 一张精确颜色表（`color_model.py`）

统计**每种 24 位 RGB 颜色在三类里各出现多少次**，推理时逐像素查表取 `argmax`。

`argmax` 就是最大后验：`P(类 | 颜色) ∝ count(颜色, 类)`，类先验已经隐含在计数里，
不需要再乘任何系数——**这一步一个超参都没有**。

之所以敢用「精确颜色」而不是直方图 bin 或高斯：ManiSkill 渲染的确定性极强
（v3 实测 86% 的像素跨 291 帧逐位重复），颜色本身就是天然离散量，按 bin 归并反而要
引入「bin 数」这种拍脑袋的量。没见过的颜色返回 `UNKNOWN`，下游一律按「不是机械臂」
处理——宗旨要求往保守方向倒。

### 二、四条形态学规则（`arm_mask_v4.py`）

输入只有上一步的三类标签图，按顺序执行：

1. **开运算**（先腐蚀后膨胀，3×3）——去掉抗锯齿边缘与阴影上的零星臂色噪点。
   先腐蚀保证候选区只会变小或持平，不会往物体那边长。
2. **只保留从上方进入的连通域**——机械臂根部固定在画面顶部、整条臂从上方伸进来；
   桌面上的任务物体不触顶。这是「不误标物体」最主要的结构性保障，比任何颜色阈值都硬。
3. **时间平滑**——3 帧滑动多数表决，抹掉只闪一两帧的误判；真臂连续存在不受影响。
   严格**按 `info/is_video_demo` 相位分段**做，两个相位之间场景会重摆，跨段投票等于
   把两个不同场景的帧混在一起。
4. **保守收缩**——先把标签图判为「物体」的像素整体扣掉（**硬否决**，哪怕它与臂连成
   一片，即接触帧），再整体腐蚀一次。

四条规则方向刻意统一：**每一条都只会让标定区域变小或持平**，正对应「绝不误标物体、
允许漏标机械臂」的宗旨。

### 三、生成侧：把 GT segmentation 落进 h5

现成产物（`v21-16env` / `v21mask-16env`）里**没有** segmentation：父类
`RecordWrapper` 在 `step()` 里已经把 `front_camera_segmentation` 放进 buffer
（`obs_mode="rgb+depth+segmentation"`），但写盘那行 `create_dataset` 是注释状态。
v2.1 的 `front_rgb_masked` 只是它的二值化派生物（机器人 vs 非机器人），分不出
「物体」与「背景」，也因黑指尖豁免而缺掉一部分机器人像素。

所以 `record_wrapper_v4.py` 在 v2.1 薄子类之上再叠一层，在 `close()` 里把 buffer 里
现成的那张图原样多写一个 dataset。**只增不改**：既有字段的数值、dtype、shape、group
层级、timestep 数量与写入时序全不动，随机数消费顺序也完全不变（热路径一个字没改，
实测写盘开销 0.11 秒 / episode）。

`generate_dataset.py` 相对 v2.1 只有四处差别：换 wrapper、新增 `--segmentation`
（默认开）、`--masked-rgb` 默认改关（v4 用不上，省约 23% 体积）、`--gpus` 放开多卡
（v4 产物不与任何既有产物逐位对拍，episode 之间本就互不耦合）。校验、报告、flow、
遮蔽图四件套一律 import v2.1 的现成实现，不拷贝不重写。

## 结构

| 文件 | 作用 |
|---|---|
| `record_wrapper_v4.py` | 薄子类，只新增 `obs/front_camera_segmentation` 落盘 |
| `generate_dataset.py` | 生成入口（拷自 v2.1，四处改动如上） |
| `color_model.py` | 三类映射 + 颜色表拟合 / 推理（**唯一碰 GT 的模块**） |
| `arm_mask_v4.py` | 四条形态学规则 + 涂红 |
| `fit_color_model.py` | 拟合入口 |
| `render_outputs.py` | 推理 + 对 GT 验证 + 出图入口 |
| `../../tests/lightweight/test_arm_mask_v4.py` | 三类映射、颜色表、四条规则的逻辑测试（14 个，0.13 秒） |

## 用法

```bash
# 1. 生成带 GT segmentation 的数据集（16 任务 × 20 episode，双卡，约 1.5 小时 / 约 95 GB）
#    ⚠ 正式生成前须与用户确认新的 --output-dir 名字
uv run --locked scripts/data-generation-v4/generate_dataset.py \
  --output-dir artifacts/generated/v4seg-16env-20ep --env all --episodes 20 \
  --workers 16 --gpus 0,1 --reference-root /data/hongzefu/robomme_data_h5 \
  --no-reference-validation

# 2. 在拟合集（每任务前 10 个 episode）上拟合三类颜色表
uv run --no-sync python scripts/data-generation-v4/fit_color_model.py \
  --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \
  --episodes 0-9 --out scripts/data-generation-v4/outputs/color_model.npz

# 3. 在留出集（每任务后 10 个 episode）上推理 + 对 GT 验证 + 出图
uv run --no-sync python scripts/data-generation-v4/render_outputs.py \
  --h5 'artifacts/generated/v4seg-16env-20ep/record_dataset_*.h5' \
  --model scripts/data-generation-v4/outputs/color_model.npz \
  --episodes 10-19 --out scripts/data-generation-v4/outputs/holdout

# 4. 单元测试
uv run --no-sync python -m pytest tests/lightweight/test_arm_mask_v4.py -q
```

产物（`outputs/holdout/`）：

- `<Task>_episode_<k>_preview.png`：均匀抽 8 帧的三联网格——原图 | 红遮罩 | 误差图。
  误差图配色：**白 = 标对的机械臂、红 = 误标到物体（核心红线，必须为零）、
  黄 = 误标到背景、蓝 = 漏标的机械臂**（漏标按口径可接受，故给冷色以便与红一眼区分）。
- `metrics.json`：逐 episode / 逐任务 / 全局的像素级统计，**全帧口径**（不是抽样帧）。

## 实测结论（2026-08-11）

数据集 `artifacts/generated/v4seg-16env-20ep`：16 任务 × 20 episode = 320 episode /
158125 帧 / 119 GB，双卡 16 worker 约 1.5 小时，320/320 全部成功。
拟合集 = 每任务 episode 0–9，留出集 = 每任务 episode 10–19，**两者零重叠**。

### 三类分布（拟合集，160 episode / 约 7.9 万帧 / 52 亿像素）

- **唯一颜色只有 16397 种**，整张表 85 KB；各类颜色数：背景 12214 / 物体 2561 / 机械臂 1748；
- **跨类共享的颜色只有 126 种**（占 0.77%），但它们覆盖 1.66% 的像素——这 1.66% 就是
  「外观上不可分」的全部战场，也是唯一的误标风险来源；
- 拟合耗时 19 分钟（单进程，全帧不抽稀）。

### 留出集（160 episode / **77272 帧全帧口径**，非抽样）

| 指标 | 默认（开共享色否决） | 对照（`--no-shared-veto`，纯 argmax） |
|---|---:|---:|
| **误标物体像素** | **0** | 241765 |
| 误标背景像素 | **0** | 0 |
| **标定精确率** | **1.000** | 0.99922 |
| 机械臂召回 | 0.8184 | 0.9090 |
| 存在物体误标的帧占比 | **0** | 9.63% |
| 未见颜色占比 | 0.196% | 0.196% |

默认口径下 `pred_pixels == true_arm_pixels == 278742663`——**每一个被标红的像素都是
真机械臂，16 个任务无一例外**。逐任务召回从 0.684（StopCube）到 0.852（MoveCube）。

代价是明确的：共享色否决换掉 9.1 个百分点的召回。漏标的形态很集中，preview 图上
一眼可见——**几乎全在夹爪头部**，那正是与白色任务物体同色、被否决规则保护掉的部分。
按「绝不误标其他物体、允许少量机械臂没被标进去」的宗旨，这个交换是划算的；需要另一端
的取舍时加 `--no-shared-veto` 即可。

`uncovered_gt_pixels` = 2278922（动态目标 / 路径标记物），其中被误标 **0**。

验证全程 37 秒（16 进程并行）。

### 过程中修掉的一个真 bug

第一版把第 4 条写成「扣掉判为物体的像素」，留出集上 InsertPeg 仍残留 292 个误标像素。
逐像素追下去发现它们的颜色**在拟合表里压根没出现过**（品红系 (135,38,114) 等）——
本该判 `UNKNOWN` 不标，是**时间平滑的多数表决把它们补进来的**：本帧不在候选里、
前后帧在，投票就填上了。这违反了「每条规则只让标定区域变小或持平」的设计原则。
收紧成「只保留本帧判定的机械臂」之后，误标从 351 px 归零。
`tests/lightweight/test_arm_mask_v4.py::test_时间平滑只能删不能加` 钉死这条。

### 已知代价（诚实清单）

1. **夹爪头部大面积漏标**：白色夹爪与白色任务物体在 24 位 RGB 上同色，共享色否决
   一视同仁地放过它们。这是宗旨的直接代价，不是 bug。
2. **StopCube 召回最低（0.684）**：该任务左上角的黑色装置与臂的暗部同色，且臂在
   画面内的时间本来就少。
3. **未见颜色 0.196% 不标**：留出集出现拟合集没见过的颜色时一律按「不是机械臂」处理。
4. **触顶规则漏掉非从上方入画的臂**：v3 记录过 RouteStick 首帧夹爪从右缘探入的情形，
   本口径按用户拍板只认上边界，这类帧漏标。属可接受漏标。
5. **验证只覆盖每任务 10 个留出 episode**，不是全部 100 个 episode。
