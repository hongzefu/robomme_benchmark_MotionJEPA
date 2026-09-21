# 步 4 报告：`episode_spec` 的只读导出与原值回注（2026-09-21）

对应 [NEWTASK_RELEASE_V3_PLAN.md](../../../NEWTASK_RELEASE_V3_PLAN.md) 第五节步 4，闸门 G4（`SPEC_BINDING`）与 P4（`INJECTION_PARITY` 的 B↔C↔D 与 A1↔D）。本报告即用户要求的「`src/robomme` 改完出 md 报告」。

## 一、机制：一个记录器同时承担导出与回注

新增 [src/robomme/robomme_env/utils/episode_spec.py](../../../src/robomme/robomme_env/utils/episode_spec.py) 的 `SpecRecorder`：

| 模式 | 触发 | 行为 |
|---|---|---|
| 导出（C 路） | `native_episode_spec=None` | 在**原调用点**只读记下每个取值点，不多抽不少抽、不改任何取值 |
| 回注（D 路） | 传入冻结规格 | 同一调用点**照常执行原抽样**（随机流不漂移，红线 R8），但建场景用的值来自冻结规格 |

**最关键的一条**：回注模式下 `value()` 返回的是**冻结值**，哪怕原抽样恰好抽出同样的数也一样。方案点名拒绝「重抽出相同值却绕过规格」的实现，这里从结构上堵死——用于建场景的对象就是规格里的那一个。原抽样结果只作兼容核验，差异记进 `spec_replay.json`。

配套：`leaf_paths()`／`consumed_paths()` 用于算「规格里存了值却没被消费」的 `unused`；版本与身份守卫（`spec_kind=native-parity/1`、task 必须对得上、缺取值点直接报错）。

**旧的 `episode_spec` 注入通道（「传了规格就跳过抽样」那条分支）原样保留、不复用为 D 路**（红线 R9）——新通道只挂在原随机分支上，由新的 `native_episode_spec` 开关驱动。

## 二、公共工具的记录器钩子

`utils/object_generation.py` 的 `build_button` / `spawn_random_cube` / `spawn_random_target` / `spawn_random_bin` 各加 `recorder` + `spec_path` 两个可选参数，钩子挂在**「拒绝采样通过、即将创建」**的那一点：失败尝试照常发生，只冻结被接受的那一组值。不传钩子时行为逐字不变，A／B 路与既有调用方不受影响。

## 三、三类必须小心的地方

1. **无效抽样照样发生，并记进 `sampling_trace`**：InsertPeg 的 `random_peg_idx`（抽完被 0 覆盖）、ButtonUnmask 构造器的 `randint(1,6)`、StopCube 的 `randint(27,33)`、MoveCube 的 `dir_sample`（抽了没用）。它们不进 D 路的场景输入，但必须照常发生。
2. **延迟到事件时点才知道的量按事件序号冻结**：VideoRepick 的交换搭档在交换发生时才选，规格路径带 `event_index`，不在 reset 时按初始坐标猜（方案 8.2）。
3. **每次初始化各记一份**：BinFill 的两次颜色排列、各环境的恢复动作索引、InsertPeg 每次初始化的孔位与三根杆位姿、VideoPlaceOrder 的访问序列与答案，一律按 `initializations.<序号>` 分开存。

## 四、G4 反例：改坏规格，产物必须跟着变

把 C 路导出的规格里 `layout.board.offsets` 三个分量各改一点后重跑 D（本机，调试用）：

```text
H5_PARITY pair=good.D|bad.D compared=1 sha_equal=0 field_mismatch=6352
差异分布：obs/front_rgb 550、obs/front_depth 550、obs/wrist_* 各 534、action/* 各 447
帧数 550 → 558
spec_replay.json 精确记下 layout.board.offsets 的「抽样值 vs 冻结值」分歧
```

改一个值就改变了整条轨迹与全部观测，证明规格确实驱动场景，而不是「重抽出相同值」。

## 五、A40 实测（首批四环境）

```text
BinFill / PickXtimes / StopCube / SwingXtimes：
  H5_PARITY pair=<env>.A1|<env>.B  sha_equal=1 field_mismatch=0
  H5_PARITY pair=<env>.B|<env>.C   sha_equal=1 field_mismatch=0
  H5_PARITY pair=<env>.C|<env>.D   sha_equal=1 field_mismatch=0
  H5_PARITY pair=<env>.A1|<env>.D  sha_equal=1 field_mismatch=0
  SPEC_BINDING=PASS missing=0 unused=0 mismatch=0
```

其中 **A1↔D 是端到端**：官方原链路产物与「显式原值配置 + 回注冻结规格」的产物逐字节相同。

BinFill 导出的规格含 16 个取值点，两次初始化的颜色排列分开保存（`[1,2,0]` 与 `[2,0,1]`），D 路全部消费、`unused` 为空。

## 六、十六环境完整验收（A40，运行目录 `gl-bcd-02`）

每个环境取 `episode 0`，跑 A1／B／C／D 四路并做四对比较；下表每行代表四对全部
`sha_equal=1 field_mismatch=0`、伴生文件（含 MP4）散列相同、无仅单侧存在的身份。

| 环境 | A1↔B | B↔C | C↔D | A1↔D | SPEC_BINDING |
|---|---|---|---|---|---|
| PickXtimes | ✓ | ✓ | ✓ | ✓ | PASS |
| StopCube | ✓ | ✓ | ✓ | ✓ | PASS |
| SwingXtimes | ✓ | ✓ | ✓ | ✓ | PASS |
| BinFill | ✓ | ✓ | ✓ | ✓ | PASS |
| VideoUnmaskSwap | ✓ | ✓ | ✓ | ✓ | PASS |
| VideoUnmask | ✓ | ✓ | ✓ | ✓ | PASS |
| ButtonUnmaskSwap | ✓ | ✓ | ✓ | ✓ | PASS |
| ButtonUnmask | ✓ | ✓ | ✓ | ✓ | PASS |
| VideoRepick | ✓ | ✓ | ✓ | ✓ | PASS |
| VideoPlaceButton | ✓ | ✓ | ✓ | ✓ | PASS |
| VideoPlaceOrder | ✓ | ✓ | ✓ | ✓ | PASS |
| PickHighlight | ✓ | ✓ | ✓ | ✓ | PASS |
| InsertPeg | ✓ | ✓ | ✓ | ✓ | PASS |
| MoveCube | ✓ | ✓ | ✓ | ✓ | PASS |
| RouteStick | ✓ | ✓ | ✓ | ✓ | PASS |
| PatternLock | ✓ | ✓ | ✓ | ✓ | 首轮 FAIL（记账缺陷），修复后补跑 |

合计 60 对 HDF5 比较、**零字段差异**。其中 A1↔D 是端到端：官方原链路产物与「显式原值配置 + 回注冻结规格」的产物逐字节相同。

## 七、两个被闸门抓出来的真实缺陷

这两个都**不是**被 HDF5 对拍抓到的（那一层一直是零差异），而是被 G4 的 `SPEC_BINDING` 抓到的，说明闸门确实比对拍更严：

1. **初始化序号作用域错**（`12.13`）：计数器只在 `_initialize_episode` 里创建，而 PickXtimes／SwingXtimes／VideoUnmask／ButtonUnmask／VideoPlaceOrder 的若干取值点其实位于 `_load_scene`，先用后建 → `AttributeError`，B／C 路直接失败。修法是十六环境统一在建记录器时初始化计数器，并把 `_load_scene` 里的取值点改为不带序号的场景级路径；另加静态核对禁止在 `_initialize_episode` 之外使用该序号。
2. **只读记录没计入消费**（`12.14`）：`record()` 记的派生量（`seed_anchor`、`rejected_attempts`、`path_attempts`）没有写进 trace，被 `unused` 统计误判成「规格里存了值却没被消费」。本机 `BinFill/ep4` 与集群 PatternLock 各命中一次。修法是 `record()` 同样计入 trace，但 `provenance.value_points` 仍只数真正的取值点。

## 八、覆盖边界

- 每环境只跑 `episode 0` 一条；48 格子集、三种恢复模式与连续 worker 污染在步 5b／5c。
- `spec_replay.json` 的 `mismatch=0` 表示原抽样与冻结值一致，即随机流没漂移；它不能替代 `unused=0`（规格被真正消费）这一条。
