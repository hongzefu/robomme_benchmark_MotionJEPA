# 实测报告：newtask-v2 三路对拍 15 格全量（运行编号 20260908T2255Z-parity15-3804e87）

## 1. 目的、对拍编号、参考与候选

证明「把 `BinFill` / `RouteStick` / `VideoUnmaskSwap` / `VideoRepick` 四个任务已在用的位置分布与
参数候选提取成显式输入」之后，原版行为逐位不变。覆盖方案第四步的五项重要对拍：

| 编号 | 内容 | 本轮结论 |
| --- | --- | --- |
| ① | 关键帧目视检查无区别 | **9 格通过、6 格待目视**：354 张关键帧全部出图且机检一致，但 BinFill 六格的 138 张只目视了 1 张，见第 5 节 |
| ② | 变量跳变、物体位置及产生／消失过程不变 | 15 格通过 |
| ③ | HDF5 生成产物内容与原版一致 | 15 格通过 |
| ④ | 随机抽样调用及随机流状态一致 | 15 格通过 |
| ⑤ | 同一 worker 连续生成时配置互不污染 | 两路（不传配置／显式原值配置）均通过 |

参考与候选（4.0 口径）：

| 路 | 含义 | 源码 | 入口 | 配置 |
| --- | --- | --- | --- | --- |
| `A1` / `A2` | 固定原版，同一用例两次独立运行 | `artifacts/native-baseline`（detached worktree，`94449db0a068a6b454b55a13ebd48f0394d89cc8`） | `scripts/data-generation-newSeed/generate_dataset_newseed.py` | 无 |
| `B` | 新版不传配置 | 当前工作树 | `scripts/generate_dataset_newseed.py` | 不传 |
| `C` | 新版显式传入冻结原值配置 | 当前工作树 | 同上 | `scripts/configs/newtask-v2/native_sampling.json` |

`A1↔A2` 是原版重复性与观察器校准；`A1↔B`、`A1↔C`、`B↔C` 是三路对拍。四路共用同一 `.venv`。

与上一轮的关系：本轮是 newtask-v2 上的**首轮**实测，没有上一轮可比；参考基准是固定原版 A 路本身。

## 2. 源码、配置、输入、依赖与设备指纹

| 项目 | 值 |
| --- | --- |
| 候选源码提交 | `11b54b3`（`10.1`）；本报告随 `10.2` 提交，未提交差异见该提交的 `git status` |
| 固定原版提交 | `94449db0a068a6b454b55a13ebd48f0394d89cc8` |
| 依赖锁 | `uv.lock` SHA-256 前 16 位 `983de83f7b22c98b`（基线与当前一致） |
| 运行环境 | Python 3.11.14，torch 2.9.1+cu128，PhysX CPU 仿真 |
| 设备 | NVIDIA RTX 6000 Ada Generation，`--gpus 0` |
| 采样配置 | `scripts/configs/newtask-v2/native_sampling.json`（schema 2），七份来源 SHA-256 在生成时逐项核对 |
| 用例表 | [../cases.json](../cases.json)，15 格，seed 由原公式 `offset(0) + env_code*1000 + episode*100 + attempt` 算出 |

防漂移检查（生成之外的独立证据）：

```bash
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config
uv run --no-sync python scripts/generate_dataset_newseed.py \
  --extract-config scripts/configs/newtask-v2/native_sampling.json --check-config \
  --source-ref 94449db0a068a6b454b55a13ebd48f0394d89cc8
```

第二条用旧式提取器从**未改动的基线源码**还原 61 项操作元，与快照逐项一致 —— 即接入过程
没有改动任何原版取值。

## 3. 完整命令、工作目录、会话名、耗时与输出

工作目录一律 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`（A 路子进程的 cwd 是
`artifacts/native-baseline`，由驱动设置）。

```bash
# 15 格 × 四路（A1/A2/B/C）实测，tmux 会话 parity15
uv run --no-sync python -m tests._shared.parity_runner \
  --run-id 20260908T2255Z-parity15-3804e87

# ⑤ 连续 worker（甲→乙→甲），两路各一次
PYTHONPATH=tests/_shared/parity_sitecustomize \
PARITY_OBSERVER_DIR=tests/_shared \
PARITY_EVIDENCE_DIR=artifacts/parity-evidence/20260908T2255Z-parity15-3804e87 \
PARITY_LABEL=S-default \
uv run --no-sync python -m tests._shared.parity_worker_isolation \
  --run-id 20260908T2255Z-parity15-3804e87
# 另一路把 PARITY_LABEL 换成 S-config 并加 --with-config

# 打包逐格结论与轻量证据
uv run --no-sync python -m tests._shared.native_sampling_parity pack \
  --run-root artifacts/parity/20260908T2255Z-parity15-3804e87 \
  --evidence-root artifacts/parity-evidence/20260908T2255Z-parity15-3804e87 \
  --cases docs/validation/newtask-v2/cases.json \
  --output artifacts/parity-pack/20260908T2255Z-parity15-3804e87

# ⑤ 比较
uv run --no-sync python -m tests._shared.native_sampling_parity isolation \
  --run-root artifacts/parity/20260908T2255Z-parity15-3804e87 \
  --evidence-root artifacts/parity-evidence/20260908T2255Z-parity15-3804e87 \
  --output artifacts/parity-pack/20260908T2255Z-parity15-3804e87

# ① 关键帧全量出图（--limit 0 表示全部关键帧都出图）
uv run --no-sync python -m tests._shared.parity_keyframes \
  --run-root artifacts/parity/20260908T2255Z-parity15-3804e87 \
  --cases docs/validation/newtask-v2/cases.json \
  --result artifacts/parity-pack/20260908T2255Z-parity15-3804e87/result.json \
  --output artifacts/keyframes/20260908T2255Z-parity15-3804e87 \
  --index artifacts/parity-pack/20260908T2255Z-parity15-3804e87/keyframe_index.json \
  --limit 0
```

| 阶段 | tmux 会话 | 耗时 | 退出码 |
| --- | --- | --- | --- |
| 15 格 × 四路首轮 | `parity15` | 2229.3 s | 1（`BinFill-medium-dynamicTrue` 原用例四路一致失败） |
| RouteStick 三格重跑（观察器修正后） | `parityfix` / `parityfix2` | 1079.5 s | 0 |
| 替补 episode 扫描 + 替补格四路 | `parityfix` / 后台 | 44.6 s + 181.4 s | 0 |
| ⑤ 连续 worker 两路 | 后台 | 约 170 s | 0 |
| 打包 + ⑤ 比较 + 替补格 A1 重跑 | `packrun` / `fix3` | — | 0 |
| ① 关键帧全量出图 | `keyframes3` | — | 0 |

输出目录：生成产物 `artifacts/parity/<run>/`（B/C）与
`artifacts/native-baseline/artifacts/parity/<run>/`（A1/A2），共约 20 GB；
原始证据 `artifacts/parity-evidence/<run>/`（21 MB，gzip）；
关键帧图版 `artifacts/keyframes/<run>/`（354 张，74 MB）。以上都不入 Git。

## 4. 实际 seed、难度、分支、回退登记与执行顺序

固定参数：`--episodes 1 --workers 1 --gpus 0 --layout train --max-attempts 1
--max-tasks-per-child 8`，attempt 全部为 0，四路独立进程串行执行。
`--difficulty` 是三位 easy/medium/hard 循环配额，`100`/`010`/`001` 分别强制全 easy/medium/hard。

| 格 | episode | seed | 分支 | `rrt_fallback_count` (A1/A2) | 状态 |
| --- | --- | --- | --- | --- | --- |
| BinFill-easy-dynamicTrue | 0 | 4000 | dynamic=True | 0 / 0 | 通过 |
| BinFill-medium-dynamicTrue | 2 | 4200 | dynamic=True（替补） | 0 / 0 | 通过 |
| BinFill-hard-dynamicTrue | 0 | 4000 | dynamic=True | 0 / 0 | 通过 |
| BinFill-easy-dynamicFalse | 1 | 4100 | dynamic=False | 0 / 0 | 通过 |
| BinFill-medium-dynamicFalse | 1 | 4100 | dynamic=False | 0 / 0 | 通过 |
| BinFill-hard-dynamicFalse | 1 | 4100 | dynamic=False | 0 / 0 | 通过 |
| RouteStick-easy | 0 | 16000 | backtrack=False | 0 / 0 | 通过 |
| RouteStick-medium | 0 | 16000 | backtrack=False | 0 / 0 | 通过 |
| RouteStick-hard | 0 | 16000 | backtrack=True | 0 / 0 | 通过 |
| VideoUnmaskSwap-easy | 0 | 5000 | bin=3 | 0 / 0 | 通过 |
| VideoUnmaskSwap-medium | 0 | 5000 | bin=4（第 4 个容器无藏块） | 0 / 0 | 通过 |
| VideoUnmaskSwap-hard | 0 | 5000 | bin=4 | 0 / 0 | 通过 |
| VideoRepick-easy | 0 | 9000 | 三方块 | 0 / 0 | 通过 |
| VideoRepick-medium | 0 | 9000 | 三方块 | 0 / 0 | 通过 |
| VideoRepick-hard | 0 | 9000 | 五轮循环共 15 块 | 0 / 0 | 通过 |

**15 格的 A1 与 A2 都是 `rrt_fallback_count = 0`**，即全部落在「原版逐位可复现」的适用范围内，
不需要动用 4.0 的容差退出路径。

**受阻并已补足的用例（保留记录，不删除）：** `BinFill-medium-dynamicTrue` 原定 episode 0
（seed 4000）在**原版 A 路首次尝试即失败**（`DatasetGenerationError: 环境报告失败`），
A1/A2/B/C 四路一致失败 —— 这是用例可解性问题，不是代码差异。按方案 4.6 另选同格其他
episode 补足：替补扫描在 `--scan-episodes 0-9` 内跳过 `dynamic` 分支不符的 ep1，
第一个可用的是 ep2（seed 4200，`dynamic=True`，44.6 s 成功）。受阻记录保留在
`artifacts/parity/<run>/BinFill-medium-dynamicTrue-blocked-ep0/` 与
`artifacts/parity-evidence/<run>/*/BinFill_seed4000`（difficulty=medium），
用例表里以 `blocked_original` 字段登记。

## 5. ①—⑤ 逐用例结果与实测规模

### ②③④：15 格四对比较全部一致

逐格四对（`A1-A2`、`A1-B`、`A1-C`、`B-C`）的 HDF5 全字段比较与四段证据比较**全部通过**，
详见 [result.json](result.json)。实测规模（以 A1 为准）：

| 格 | HDF5 对象数 | ④ 随机调用 | ②.1 边界 | ②.2/②.3 事件 | ②.2 逐步状态 |
| --- | --- | --- | --- | --- | --- |
| BinFill-easy-dynamicTrue | 13758 | 44 | 4 | 6624 | 1100 |
| BinFill-medium-dynamicTrue | 22083 | 71 | 4 | 14168 | 1766 |
| BinFill-hard-dynamicTrue | 23583 | 91 | 4 | 17014 | 1886 |
| BinFill-easy-dynamicFalse | 9158 | 41 | 4 | 748 | 732 |
| BinFill-medium-dynamicFalse | 13733 | 83 | 4 | 1122 | 1098 |
| BinFill-hard-dynamicFalse | 18558 | 67 | 4 | 1516 | 1484 |
| RouteStick-easy | 5008 | 11 | 4 | 3410 | 1028 |
| RouteStick-medium | 10008 | 15 | 4 | 6874 | 1428 |
| RouteStick-hard | 15008 | 19 | 4 | 6242 | 1828 |
| VideoUnmaskSwap-easy | 8158 | 19 | 4 | 5524 | 652 |
| VideoUnmaskSwap-medium | 8658 | 22 | 4 | 6576 | 692 |
| VideoUnmaskSwap-hard | 12883 | 22 | 4 | 10666 | 1030 |
| VideoRepick-easy | 18908 | 20 | 4 | 1837 | 1584 |
| VideoRepick-medium | 20258 | 20 | 4 | 2051 | 1692 |
| VideoRepick-hard | 18833 | 131 | 4 | 1615 | 1578 |

- ③ 的比较遍历实际落盘树，比较 group/dataset/attribute 全集、dtype、shape、字符串编码与
  逐元素内容；浮点按位模式、**不设容差**。原版 RecordWrapper 不写任何 HDF5 attribute，
  比较时仍遍历以确认新版也为空。差异数全部为 0。
- ②.1 的 4 个边界正是方案第二节描述的构造期链路：`after_load_scene` →
  构造期内部 reset 的 `after_initialize_episode` → `after_init` → 外层
  `record_env.reset()` 的第二次 `after_initialize_episode`。**两次 `_initialize_episode`
  分别记录**，与方案「BinFill/VideoRepick 的 task_list 以第二次为准」的描述一致。
- ④ 覆盖三类随机源：任务级 `torch.Generator`（局部与实例）、全局 numpy 流
  （VideoRepick 的 `np.random.seed`，作为事件单独登记）、全局 torch 默认流。
  `VideoRepick-hard` 的 131 次随机调用对应原五轮循环（每轮 `randperm(3)` + 三块方块的
  拒绝采样），与「15 块」的口径一致。拒绝采样的**全部尝试**都被记录，不只记成功样本。
- **盲区声明：** mplib/OMPL 规划器内部随机在 C++ 侧，Python 层不可捕获、不可播种；
  本轮 15 格 30 次原版运行的 `rrt_fallback_count` 全为 0，即没有一格落进这个盲区。

### ⑤：连续 worker 隔离，两路均通过

见 [worker_isolation.json](worker_isolation.json)。同一 worker 进程（`S-default` pid 279135、
`S-config` pid 280088）连续执行三条 job：
`BinFill ep0 easy → VideoRepick ep0 easy → BinFill ep0 easy`（乙含 VideoRepick，
覆盖其 `__init__` 里的进程级 `np.random.seed`）。

- 三局全部成功，`same_worker = true`（三条 job 落在同一个池进程）。
- 逐局与对应独立运行（不传配置对 `B`、显式配置对 `C`）比较：**HDF5 差异 0**，
  四段证据全部一致，含**第三条「再次用例甲」**——即 VideoRepick 的全局播种没有污染其后的 BinFill。
- 类级状态：四个任务类的类级 `configs`（含三份难度字典）内容散列在整轮生成前后不变；
  父进程持有的配置散列不变。
- 本项**不**验证「改一个副本其他不变」：每次 attempt 都新建环境、`EpisodeJob` 经 pickle
  逐条送入 worker，那个断言在多进程链路下恒真、没有鉴别力。

### ①：关键帧集合与目视

见 [keyframe_index.json](keyframe_index.json)。①.0 的前置成立：15 格 ③ 全部通过，因此 15 格都做目视。

关键帧集合按 ①.1 取：首帧、末帧、`is_subgoal_boundary`、`is_video_demo` 与 `is_completed`
变化、`simple_subgoal`/`grounded_subgoal` 变化，三路取并集，每个边界另加前一帧与后一帧，
越界邻帧单独登记在 `out_of_range_neighbours`。**没有假设原版存在 `is_keyframe` 字段。**
初态用观察器捕获的 `reset` 返回观测，不额外渲染，并已标注它在 HDF5 中没有对应帧。

- 关键帧总数 **354**（15 格并集），全部出图，`not_rendered` 为空。
- 图版为原分辨率无损 PNG 拼接：两行（正面 256×256×3 / 腕部 256×256×3）× 五列
  （A1、B、C 原图 + `diff A1-B`、`diff A1-C`）。原图逐像素放入、不缩放不重采样；
  差分图为了肉眼可见做了 ×8 放大，其统计量按原值记录。
- 机检：**354 张图版的差分 `max_abs` 全为 0、非零像素总数为 0**；
  逐帧内容 SHA-256 三路一致的帧数为 **708 / 708**（354 帧 × 正面与腕部两个相机）。

- **目视完成情况：217 / 354 张。** `RouteStick` 三格、`VideoUnmaskSwap` 三格、`VideoRepick` 三格
  共 9 格的全部关键帧已逐张目视，结论为无可见区别，① 记**通过**；`BinFill` 六格共 138 张
  只目视了 1 张（负责该组的目视 agent 因会话额度中断且未给出可用结论，随后用户要求停止目视），
  这六格的 ① 记**待目视**、不记通过。

目视记录、检查人、逐格结论与观察描述见 [visual_inspection.md](visual_inspection.md)，
结论绑定 [keyframe_index.json](keyframe_index.json) 里的图版与逐帧散列；图片变化后旧记录不能沿用。

## 6. 首个分歧、失败、受阻与未覆盖项

- **没有任何一格出现真实分歧**：15 格四对比较的 HDF5 与证据均无首个分歧。
- 过程中出现过三次**观察器假差异**，均已定位到根因并修正后重跑，不是产物差异
  （HDF5 在这三次里始终一致）：
  1. 随机源身份用 `id(generator)`，内存地址跨进程不同 → 改为「本局首次出现序号」。
  2. 对象 `repr` 含内存地址 → 统一抹成 `0xADDR`。
  3. RouteStick 的高亮盘 actor 名字里直接嵌了 `id(obj)`（`statechange.py:248,466`），
     抹掉数字后还会同名相撞 → 这类 actor 的身份本就不可跨进程观测，
     改为把同一归一名下的若干个按内容排序成多重集合比较。RouteStick 三格因此重跑了两次。
- **受阻并已补足** 1 项：`BinFill-medium-dynamicTrue` 原 episode 0，详见第 4 节。
- **未覆盖项：**
  - **① 的 BinFill 六格目视**：138 张关键帧只看了 1 张，其余 137 张仅有机检结论
    （逐帧 SHA-256 三路相同、差分为 0），未逐张目视。这六格的 ② ③ ④ ⑤ 已通过，
    ① 记「待目视」，两者分别登记、不互相替代。
  - 触发 RRT* 回退的局：本轮 30 次原版运行一次都没触发，因此 4.0 的容差退出路径未被启用，
    也未被验证。
  - attempt 重试分支：三路对拍固定 `attempt=0`，重试分支由单独的定向检查覆盖，本轮未做。
  - `--env all` 加 `--sampling-config` 下其余 12 任务各一局 smoke：本轮未做。
  - 合并（`--merge-only`）产物的结构与内容比较（③.4）：本轮只比较了逐 episode 原始文件。
  - 清理后复验（第五步）：尚未执行。

## 7. 证据索引、体积与重跑命令

| 文件 | 内容 |
| --- | --- |
| [result.json](result.json) | 逐格四路的运行摘要、HDF5 指纹、证据段计数与四对比较结论 |
| [manifest.json](manifest.json) | 去重后的证据文件清单、引用映射与总字节 |
| [worker_isolation.json](worker_isolation.json) | ⑤ 的逐槽位比较结果 |
| [keyframe_index.json](keyframe_index.json) | ① 的关键帧集合、入选原因、逐帧 SHA-256 与差分统计 |
| [visual_inspection.md](visual_inspection.md) | ① 的目视记录，绑定图版散列 |
| `evidence/` | 去重后的轻量证据（30 份文件、120 处引用、约 511 KB） |

Git 中的证据总体积约 1.3 MB；完整 HDF5、视频、原始逐步证据与全部 PNG 图版留在
`artifacts/`，不入 Git（与 `AGENTS.md` 禁止提交图片、视频、HDF5 的规则一致）。

**能力边界：** 轻量证据能判断内容是否相同、并把首个分歧定位到字段／记录或（大段时）
定位到一个 64 条的块、（HDF5）定位到具体哪一帧；但**不能还原画面、也不能计算像素差幅度**。
需要展开时按上面的冻结命令重跑原版，或从 `artifacts/` 按散列取回 PNG。
轻量包**不是**完整 HDF5 备份。

重跑与离线比较：

```bash
# 从头复现（冻结用例 + 固定源码，在新目录完整跑 A/B/C 并比较）
uv run --no-sync python -m pytest tests/dataset/test_native_sampling_parity.py -q \
  --parity-mode fresh --parity-output artifacts/parity-pack/<新运行编号>

# 当前代码回归（拿本目录作为固定原版参考，只重新跑当前 B/C）
uv run --no-sync python -m pytest tests/dataset/test_native_sampling_parity.py -q \
  --parity-mode regression \
  --parity-reference docs/validation/newtask-v2/20260908T2255Z-parity15-3804e87 \
  --parity-output artifacts/parity-pack/<新运行编号>

# 纯离线比较（不加载仿真、不占 GPU），须在仓库根目录执行
uv run --no-sync python -m tests._shared.native_sampling_parity compare \
  --reference <参考运行目录> --candidate <候选运行目录> --output <新目录>
```
