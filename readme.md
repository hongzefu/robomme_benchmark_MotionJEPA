# MotionJEPA 全任务训练数据：初始准备与仓库指导

本仓库用于准备一套同时服务于 motion encoder 和 VLA 训练的数据：完整复用 RoboMME 原版 16 个任务的 easy、medium、hard 数据，再使用原版场景生成机制和新的 seed，补充以动作次数为主要区别的 XHard1、XHard2。目标是让模型学习更长的运动与记忆过程，同时尽量保持原版场景分布和数据接口。

本文是需求与准备说明。次数型新档、全任务建库和训练尚未实施；文中的方向、待定项和验收要求不代表已有可运行接口，也不构成生成或训练的开工令。

## 一、仓库位置与代码起点

| 项目 | 固定信息 |
|---|---|
| 工作机器 | `sled-aspen.eecs.umich.edu` |
| 独立工作副本 | `/data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006` |
| 工作分支 | `newtask-v3-MotionJepa1006` |
| 来源仓库 | [hongzefu/robomme_benchmark_MotionJEPA](https://github.com/hongzefu/robomme_benchmark_MotionJEPA) |
| 生成代码起点 | `dataset-gen-NewSeed` 的 `3a5951a834ea014f63724647ab0bc091eb9f109d` |
| 对应研究 | [MotionMem 论文仓库](https://github.com/hongzefu/motionjepa-paper-CoRLWorkshop) |

独立克隆和本地分支已准备好。文档提交会使工作分支的 HEAD 前进，但上表的生成代码起点保持不变。当前尚未在这个工作副本安装依赖、建立训练数据或运行新难度。

选择 NewSeed 是为了沿用原版 `gym.make → RobommeRecordWrapper → reset → task_list / planner → close` 链路。现有入口、seed 规则和官方 HDF5 合并逻辑位于 [scripts/data-generation-newSeed/](scripts/data-generation-newSeed/README.md)。它目前只提供原版三档的新 seed 生成，不是本项目的 XHard1/2 成品生成器。

原版上游介绍保留在 Git 历史的上述起点提交中；本 README 作为本训练数据分支的入口。历史计划和旧执行记录不自动成为本轮授权。

## 二、已经确定的要求

1. **训练对象是 encoder 和 VLA。** 用户最后一次更正为“检查一下我原来是怎么训练 encoder 和 VLA 的，以最新的为准”；VAE 在最新链路中是冻结的预训练输入处理器。
2. **原版全部 16 个任务完整保留。** 用户已确认：“已有原版三档数据继续复用，只新生成 XHard1/2”。不重新生成 easy、medium、hard 来替换原件，不覆盖原版 HDF5 或 metadata。
3. **新增数据采用新的 seed 和原版场景机制。** 新 seed 产生新的样本；兼容要求针对生成规则、布局分布和数据接口，不表示新样本与发布集某一局的坐标或字节相同。
4. **新难度严格围绕已有动作次数。** 保留物体数量、颜色规则、位置区域、相机、机器人初态、运动速度及任务语义，不顺带增加干扰物或改变布局。任务指令、动作计划和成功条件必须与新的次数一致。
5. **MoveCube、InsertPeg 只保留原版三档。** 用户已确认：“严格只改已有次数参数，这两项保留原版三档”。不为了凑齐新档而加入重复移动、拔出再插入等新任务规则。
6. **同一份原始轨迹服务两种训练。** 每个最终难度样本录制一次完整轨迹，再分别派生 encoder 和 VLA 的训练输入。不先录制一条原版完整轨迹再重录升级档，也不为两种训练分别生成同一条仿真数据。

XHard1 和 XHard2 是不同的最终轨迹，不能把一条短轨迹换标签当作两档。“录制一次”也不代表场景采样、冻结或回注无需 reset；这些实际调用及失败重试都必须纳入后续预算。

本项目的新档与 NewTask 发布分支中同名的 XHard1/2 不直接等价。旧新档还包含干扰物、空间区域、速度或回放策略变化，不能直接沿用其配置再声称只改次数。

## 三、原版布局与次数如何分开

建议的逻辑顺序如下，具体实现仍需另行设计：

```text
新 seed + 明确的原版母档（easy / medium / hard）
    ↓ 原版随机采样与场景生成规则
母场景：物体、颜色、位姿、相机、机器人初态、速度
    ↓ 记录母场景身份；仅调整获准的次数参数
目标档动作计划 + 对应任务指令 + 对应成功条件
    ↓ 原版规划、执行与完整记录接口
该目标档的原始 HDF5
```

仅使用相同 seed 不足以保证场景不变。例如 BinFill 的目标配额影响生成颜色数量，改次数还可能改变随机数消耗顺序。因此必须核对母场景实际内容，并把允许变化的动作目标与应保持的布局属性分开。

每个新样本应能追溯到任务、目标档、母档、新 seed、接受的 attempt、生成代码与依赖身份、母场景记录、实际次数和原始 HDF5 的路径、字节数与 SHA256。这里是后续交付要求，尚未定义新的 manifest 文件格式或 CLI。

母档统一选 hard 还是按原三档混合采样、XHard1/2 是否共享同一母布局，目前未定。同一母布局或重复 demo 的派生样本应成组划入同一个 train/val/test split，避免布局泄漏。

## 四、16 个任务的初步次数边界

下表是静态源码分析得到的设计方向，不是已批准的次数表，也没有经过新档仿真验证。

| 任务 | 次数型扩展方向 | 必须保留或确认的边界 |
|---|---|---|
| PickXtimes | 增加抓取次数 | 保留原目标、摆放区域和物体数，不增加干扰块。 |
| SwingXtimes | 增加同一目标的摆动次数 | 保留原圆盘、间距和物体布局。 |
| StopCube | 增加停止前经过目标的次数 | 原版计数为第 2～5 次经过；保持速度，核对运动段长度与成功条件。 |
| RouteStick | 增加路线段数 | 保留物理按钮、障碍和母档回退规则。 |
| PatternLock | 增加路径节点数 | 保留母档网格和不重访规则；hard 的 5×5 网格最多有 25 个不同节点。 |
| VideoRepick | 增加重抓次数 | 保留母档原布局、颜色和交换规则；不能将原 hard 的聚集布局改为散乱布局。 |
| VideoUnmaskSwap | 增加交换次数 | 保留容器、隐藏物、交换速度和抓取语义。 |
| ButtonUnmaskSwap | 增加交换次数 | 保留按钮规则、容器布局、速度和抓取语义。 |
| PickHighlight | 增加高亮目标抓取数 | 原 hard 有 6 块、抓 3 块，增加目标数受同一场景容量限制。 |
| BinFill | 增加投入量 | 受母场景每色物体库存限制；目标数量与场景生成耦合，不能只改参数后重新抽场景。 |
| VideoUnmask | 增加抓取数的空间有限 | 原 hard 抓 2 个、场景只有 3 个隐藏物；原任务列表为固定分支，改 `pick=3` 不会自动多一次动作。两档如何成立尚未解决。 |
| ButtonUnmask | 增加抓取数的空间有限 | 隐藏物容量同样限制严格次数扩展；原任务列表也是固定分支，`pick>1` 仅追加第二次，不能保证两档都可用。 |
| VideoPlaceButton | 核对原放置规则是否允许次数扩展 | 原版使用固定主放置与 pre/post 布尔分支，没有现成的任意放置次数字段；不得加入新的序数问答语义。 |
| VideoPlaceOrder | 增加访问目标数的空间有限 | 原版只有 4 个台且不重访；原 hard 已覆盖 2～4 次，上限为 4 次。允许重访会改变规则，本轮未授权。 |
| MoveCube | 不新增难度 | 复用原版 easy、medium、hard。 |
| InsertPeg | 不新增难度 | 复用原版 easy、medium、hard。 |

“覆盖全部 16 任务”不等于“全部 16 任务都增加两档”。除了已经排除的 MoveCube、InsertPeg，其余任务也必须先证明两档能够在既定次数约束下成立；不足的任务应明确保留缺口，不能自动扩大任务语义。

## 五、一份原始 HDF5，两条训练数据链路

原始真源应保留官方完整 HDF5 接口，参考 [HDF5 格式](doc/h5_data_format.md) 和 [环境接口](doc/env_format.md)。至少保留：

- `setup/task_goal`。
- 每个连续 `timestep_N` 的 `obs/front_rgb`、`obs/wrist_rgb`、`obs/joint_state`、`obs/gripper_state`。
- `action/joint_action`。
- `info/is_video_demo`、`info/is_completed`、`info/is_subgoal_boundary`。
- `info/simple_subgoal`、`grounded_subgoal`、`simple_subgoal_online`、`grounded_subgoal_online`。

记录完整连续帧、demo/exec 边界和真实完成状态。正面 RGB 按最新 motion 链路要求为 `(256,256,3)`、`uint8`。不能只保留 MP4、关键帧或精简 RGB 文件作为共同训练真源。

```text
原版只读 HDF5 + 新增次数型 HDF5
    ↓ 唯一身份、来源校验、成组数据划分
统一的原始样本集合
    ├─ encoder：正面 RGB → 分段 → 连续 33 帧 Wan latent → 预训练窗口
    └─ VLA：图像 / 状态 / 动作 / 指令 → 策略数据
             + 同源正面 RGB → 分段 33 帧窗口 → 冻结 Wan VAE
                            → latent → 冻结 encoder → motion 缓存
```

两条链路派生格式和窗口协议不同，不能直接把同一个原始 HDF5 路径当成两个训练器都已经支持的输入。新轨迹的帧数、动作与身份变化后，原版的短轨迹缓存也不能继续复用。

## 六、以最新实际训练为参考

以下基线依据 2026-10-06 核对的固定源码与已提交训练档案，不表示本分支已经复现这些训练。

| 对象 | 实际训练基线 | 本项目应沿用的接口理解 |
|---|---|---|
| motion encoder | `wan-full1600-filter2-b176x4-72ep-a`，72 epoch；训练提交 `660cee10a86d02ae03a73db95fac6f0b8dbd28a6` | 连续 33 帧正面 RGB，经冻结 Wan VAE 得到 `(9,16,32,32)` FP32 latent，再由 encoder 输出一条 768 维 motion token；预训练窗口起点 stride 为 1。 |
| 带 motion 的 VLA | `v2-1600ep-m8x8-modul-motion-b128-80k`，80,000 步，最终 checkpoint `79999`；训练提交 `2f10473161b760f16d9240d3c2959ff326cde66b` | 冻结 motion encoder；外观历史容量 512，motion 历史容量 160；motion 窗口为 33 帧、段内 stride 为 16。 |

这两条正式 motion 训练都只覆盖 `BinFill、RouteStick、VideoRepick、VideoUnmaskSwap` 四任务。旧库的组成是：BinFill 的 `1 任务 ×（easy 134 局 + medium 133 局 + hard 133 局）= 400 局`，VideoRepick 的 `1 任务 ×（easy 134 局 + medium 133 局 + 旧 xhard 133 局）= 400 局`，加 RouteStick/VideoUnmaskSwap 的 `2 任务 × 4 档（easy/medium/hard/旧 xhard）× 100 局 = 800 局`，合计 `1,600 局`。旧 `xhard` 不是本项目待设计的 XHard1/2。

encoder 的最新配方通过 `full1600_armwnull → armwnull → default` 继承并由启动入口覆盖；联合训练 encoder 与 latent decoder，使用重建损失和 SIGReg，关闭 arm weighting。直接读取 `default` 不能还原最新正式配方。策略实际使用 epoch72 的 EMA encoder；重建选模得到的 epoch70 是另一种权重身份，不能混用。

后来确实完成过原版 16 任务 VLA 训练，但该模型关闭了 motion，不能当作“16 任务 motion 训练已完成”。

固定参考材料：[encoder 训练档案](https://github.com/hongzefu/MotionJEPA/blob/d3213de673d6b71b4ff46f6a568c9b79560231a9/docs/training-doc/wan-full1600-filter2-b176x4-72ep-a/README.md)、[motion VLA 完成记录](https://github.com/hongzefu/robomme_policy_learning_MotionJEPA/blob/f4a416d906eb8469008dfabf5c7920691290c85a/docs/training-doc/v2-1600ep-m8x8-modul-motion-b128-80k/records/training_completion.json)、[原版 16 任务后续训练证据](https://github.com/hongzefu/robomme_policy_learning_MotionJEPA/blob/f4a416d906eb8469008dfabf5c7920691290c85a/docs/training-doc/eval-orig80k-modul-vs-official/launch.md)。

扩展到本项目时必须检查三项消费端限制：

1. encoder 最新源检查硬锁四任务、旧难度集合、来源 manifest 和固定计数，需要另行适配全任务集合；模型本身不等于只支持四任务。
2. encoder 最新源检查要求非空 demo 前缀，旧分段器允许没有 demo。原版 16 任务是否都满足最新检查、完成帧后的记录是否满足分段要求，尚未逐任务验证。
3. VLA 的 demo/exec 分别起算 motion 窗口，不跨段；demo 尾窗至少包含 17 个真实帧，重复本段末帧补至 33，exec 必须有完整 33 帧。每个 episode 的 demo 与 exec 合法 motion 网格累计上限超过 160 时，现有 dataloader 会在初始化阶段拒绝该数据集。次数增长后的轨迹必须重新盘点容量，不能静默截断。encoder 的低运动过滤也不能直接套到 VLA 的完整合法窗口网格。

## 七、数据组织与开始前需要定下的事项

原版三档继续按原身份只读复用。先核实实际数据路径、固定来源、原始 metadata、文件 SHA256 与字节数，再设计原版与新数据的联合清单。NewSeed 起点中四份 Unmask train metadata 已扩充，不能把该分支默认 metadata 当成官方原版全集。

新增原始数据、派生缓存、日志与报告收敛到本工作副本的 `artifacts/`；不覆盖原件，不写回原版 `src/robomme/env_metadata/`。不将大型 HDF5、视频、权重或缓存提交到 Git。是否复制已有原版数据、其落点和容量要在获取前确定，本轮没有开始下载或搬运。

开始实现和生成前，还需要定下：

- 每任务 XHard1/2 的确切次数、母档，以及容量不足任务的最终处理；只增加已有次数的约束保持有效。
- 新 seed 范围及与原版 train/val/test 的身份隔离；训练、验证和测试按母布局成组划分。
- 每个任务×难度格的局数、失败处置、接受的 attempt 与有限重试上限。数量统一写成“任务数 × 难度档 × 每格局数”，不能只给总数或假设各格齐全。
- 完整工作的 reset 与轨迹尝试预算、worker 数、预计耗时和停止条件；场景抽样、对照、冒烟、失败重试与重跑全部计入。
- 原始数据清单与两端建库适配、长轨迹容量、encoder 过滤与留出规则，以及真正的训练配置和 run_name。

现有 NewSeed 调度器失败后会递增 attempt、换 seed 重试；后续不能不记账地继承它。任务失败与基础设施失败要分别记录，不能为挑出成功回合无限重试。单 worker 的 reset 或轨迹尝试任一超过 10、多 worker 全任务合计任一超过 50，必须提前一次性获得完整预算授权；预算不是开工令。

本次只写指导文档。后续代码改动、下载、生成和训练需要用户明确“开工”；涉及受保护的 `src/robomme/` 改动或运行时覆盖，仍须按当前用户规则逐项批准。不得修改原版录像器来迁就新难度。

## 八、后续验收应证明什么

以下判定项均为后续要求，当前没有新数据可据此判定 PASS。

| 判定项 | 检查内容 | 通过后的结论边界 |
|---|---|---|
| `ORIGINAL_REUSE` | 原版身份、文件指纹和 metadata 保持不变 | 原版数据完整复用，不代表新数据数值等价。 |
| `NATIVE_LAYOUT` | 新 seed 母场景符合原版规则；目标档保留母场景物体、颜色、位姿、相机、初态和速度 | 布局生成与次数目标分开，不由相同 seed 单独证明。 |
| `COUNT_ONLY` | 实际动作次数、任务指令、规划与成功条件一致；其他语义不变 | 新档只包含事先允许的次数变化。 |
| `H5_CONTRACT` | 完整字段、dtype/shape、连续帧、demo/exec 边界、终态及源身份 | 原始数据满足接口；任务成功字段另行报告。 |
| `CONSUMER_BUILD` | 两端从同一源清单建库，核对分段、窗口、动作标签、来源映射和容量 | encoder 与 VLA 可以消费这套新集合；不是训练效果证明。 |
| `SPLIT_ISOLATION` | 同母布局和重复 demo 不跨 split，新样本不混入原版评测身份 | 数据划分没有已检查类型的身份或布局泄漏。 |

先完成覆盖核心链路的最小样本验证，再按获批预算扩大。单任务、单档、单局、单 worker 的实际 reset 与轨迹尝试也要计入总预算；不能用一次成功回放替代全部任务兼容性证明。

检查这个源码工作副本本身可使用以下只读命令，它们不启动仿真：

```bash
cd /data/hongzefu/robomme_benchmark_newtask-v3-MotionJepa1006
git status --short --branch
git log -1 --oneline
git merge-base --is-ancestor 3a5951a834ea014f63724647ab0bc091eb9f109d HEAD
```

后续 Python 运行与依赖管理统一使用 `uv`，先核对 `pyproject.toml`、`uv.lock` 和实际环境；本 README 不提供尚未实现的 XHard1/2 启动命令。
