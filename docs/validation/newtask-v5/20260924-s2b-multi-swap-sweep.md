# V5 S2b：多对同时交换的联合连续判据与认证预筛（`utils/bin_collision.py` 只加不改）

日期：2026-09-24；worktree：`/data/hongzefu/robomme_v5_wt/s2b`（分支 `v5wt-s2b`，未 commit）。
依据：`NEWTASK_RELEASE_V5_PLAN.md` 2.5「关键设计点」「认证预筛（L23）」、2.15（L54 按钮底座作静止障碍）、3.5 P5 结果、第二部分「一」S2 行（`utils/bin_collision.py`）；红线 N13（共用代码只加不改）。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 |
|---|---|---|---|
| `src/robomme/robomme_env/utils/bin_collision.py` | 模块 docstring「三层接口」之后 | 追加一段说明新接口 | 文档同步 |
| 同上 | `__all__` 中 `"check_swap_sweep"` 之后 | 追加 8 个导出名 | 新公开 API |
| 同上 | `check_swap_sweep` 之后、`nearest_partner_index` 之前的新节「V5：多对同时交换……」「V5：构造静止障碍……」 | 新增常量 `PREFILTER_SAMPLES=401`、`PREFILTER_MARGIN_M=1e-3`；私有 `_swap_movers`、`_quat_to_matrix_batch`、`_local_vertices`、`_PrefilterTrack`、`_prefilter_samples`、`_prefilter_track`、`_prefilter_clearance`；公开 `check_multi_swap_sweep`、`check_swap_sweep_prefiltered`、`static_box_state`、`static_rect_state`、`static_state_from_obb2d`、`button_base_state` | 计划 S2 行、L23、L54 |
| `tests/lightweight/test_v5_multi_sweep.py`（新文件） | — | 16 条单测 | 完成判据 |

**只加不改核验**：`git diff src/robomme/robomme_env/utils/bin_collision.py` 中以 `-` 开头的删除行为 **0**，新增 406 行。`check_swap_sweep`、`_prove_pair`、`_Mover`、`_Static`、全部判据常量一字未动；原函数不调用任何预筛代码（单测 `test_原函数从不走预筛` 用 monkeypatch 把 `_prefilter_track` 换成抛错函数来证明）。没有动任何范围外文件。

## 二、关键设计点

1. **联合证明复用 `_prove_pair`**：每一对都用与 `check_swap_sweep` 逐字段相同的方式构造两个 `_Mover`（`_swap_movers`），静止物包成 `_Static`。同一窗口、同一 smoothstep 下所有对的进度相同，全体位姿是同一个 `s` 的函数，`_prove_pair` 本来就能证两个都在动的对象。
2. **检查的对象对与顺序**：①每对自身（按 `pairs` 顺序）→ ②跨对交换者两两（交换者按 `A1,B1,A2,B2,…` 排序后 `i<j` 且不同对）→ ③每个静止物依次对全部交换者。只有一对时顺序、包围球粗筛与盒对证明都与 `check_swap_sweep` 完全一致，因此 `prefilter=False` 时**逐位相同**。
3. **认证预筛（L23，默认开启）**：放在包围球粗筛之后、精确证明之前。每个对象在 `s∈[0,1]` 等距 401 点上算「竖直包围圆柱」——原点 XY 轨迹 `xy(s)`（与 `_Mover.pose_at` 同式）与半径 `rho(s)`（全部盒体顶点在当时旋转下到原点竖直轴的最大水平距离）。`G(s)=‖xy_l−xy_r‖−rho_l−rho_r` 是 `L=L_l+L_r` -Lipschitz 的（`L` 取原点平移速度上界 `‖δ‖+0.07π` 加旋转顶点速度上界 `max(radii)·2‖Δq‖/m`，与 `_Mover.speed_bound` 同式、`m` 取整段最小混合范数；静止物 0），相邻采样点之间 `G ≥ (G_i+G_{i+1})/2 − L·h/2`；整段下界 `> PREFILTER_MARGIN_M` 才跳过精确证明。
   - 与 P5 原型（`swap10lib.py`/`multi_sweep.py`）的差别：原型对所有对象用固定的容器外接圆半径 0.0424、不算旋转；正式版逐对象从真实盒体顶点算半径并把旋转纳入 Lipschitz 常数，对方块、按钮底座、任意朝向盒体、任意四元数都成立。
   - 四元数混合退化（`m ≤ DEGENERATE_NORM`）的交换者**不参与预筛**，照旧交给精确证明报 `uncertified`。
   - 预筛**只跳过、不拒绝**：拒绝一律由 `_prove_pair` 按同一对象对顺序给出，所以拒绝证据与不预筛时逐位相同。
4. **余量取 1 mm 而非 `EPS_M`**（实施方自决的细节）：理论上唯一可能的分歧是「真实间隙已被证明 > 余量，但精确证明因分离轴判定值 ≤ ε 或二分耗尽而证不出来」。这与原函数包围球粗筛是同一前提（粗筛跳过的对同样没经过精确证明）；1 mm 余量把它挤到实际几何下不会出现的区域。单测 `test_二分耗尽时预筛不会替近处的对放行` 通过人为把 `MAX_DEPTH` 压到 1 演示了这一分歧的形态：判定仍为 uncertified 拒绝，但证据从「交换双方自身」移到「贴近的旁观对象」。真实常量下 800 例大样本未出现（见第四节）。
5. **返回结构**：`(最小判定值, CollisionRejection | None)`，与 `check_swap_sweep` 相同；`raise_on_reject` 语义相同。⚠ 与原函数的粗筛同理，被跳过的对不进返回的最小 g，所以预筛开关（以及加入远处的第二对）可能改变**通过时**返回的数值，但不改变判定与拒绝证据。可选 `stats` 字典就地累加 `object_pairs / coarse_skipped / prefilter_skipped / proved_object_pairs / proved_shape_pairs`。
6. **名字唯一性**：同一 `name` 在各对与静止物中出现两次即 `ValueError`（对象同时属于两对、或既交换又静止都是调用方 bug，不能静默算成自碰撞）。空 `pairs` 也 `ValueError`。
7. **静止障碍 helper**：现有 shape spec 格式是 `ShapeSpec(local_p (3,), local_q (4,) wxyz, half (3,))`，对象是 `ObjectState(name, p (3,), q (4,) wxyz, shapes)`（`radii` 自动算）。`cube_shape_specs(h)` 是原点处单盒体、`bin_shape_specs(h)` 是 6 个盒体。新增四个 helper 都把 actor 原点放在盒体中心（包围球与预筛圆柱最紧）：
   - `static_box_state(name, center(3,), half_size(3,), *, yaw_rad=0.0)`；
   - `static_rect_state(name, center_xy, half_xy, *, yaw_rad=0.0, z_range=(z_low, z_high))`，`z_range` **故意必填**（障碍高度决定挡不挡得住，写错会静默放行）；
   - `static_state_from_obb2d(name, (c, A, h), *, z_range, tol=1e-6)`：吃仓库放置逻辑的二维 OBB 三元组（`_trimesh_box_to_obb2d` / `create_button_obb` 的返回格式，A 的列是轴），轴不单位正交即 `ValueError`；左手系轴（扣放容器的投影）接受，只取第一列定朝向；
   - `button_base_state(name, center_xy, *, scale=1.0, base_half=(0.025,0.025,0.005))`：复刻 `build_button` 的底座碰撞盒（半尺寸 × scale、轴对齐、底面贴桌），不含圆柱按帽。

## 三、新 API 用法（给 S3g VideoRepick / S3h Swap 两环境的实现者）

```python
from robomme.robomme_env.utils.bin_collision import (
    ObjectState, bin_actor_pose, bin_shape_specs, cube_actor_pose, cube_shape_specs,
    check_multi_swap_sweep, check_swap_sweep_prefiltered,
    static_box_state, static_rect_state, static_state_from_obb2d, button_base_state,
)

# Swap 两环境：内环对 (a,b) 与外环对 (o,p) 同窗口交换，其余全部静止（2.5 伪码的第一条可行性）
gap, rej = check_multi_swap_sweep(
    [(inner[a], inner[b]), (outer[o], outer[p])],
    [s for j, s in enumerate(inner) if j not in (a, b)] + [s for j, s in enumerate(outer) if j not in (o, p)],
    sweep_index=k, stage="joint",           # prefilter 默认 True（L23）
)
ok = rej is None

# Swap 两环境 reset 时的内环对内环预判（L20）：单对也要走预筛，否则 reset 慢 20～30 倍
gap, rej = check_swap_sweep_prefiltered(inner[a], inner[b], others, sweep_index=k, stage="inner_prejudge")

# VideoRepick：规划搭档时把按钮底座当静止障碍（L54）；方块用 cube_shape_specs(hs + 0.005) 的 5 mm 余量
button = button_base_state("button", button_xy, scale=button_scale)   # button_xy 用 build_button 最终的中心
gap, rej = check_swap_sweep_prefiltered(cube_i, cube_j, other_cubes + [button])

# 任意有向矩形：如放置逻辑里已有的二维 OBB 三元组
obstacle = static_state_from_obb2d("keepout", (c, A, h), z_range=(0.0, 0.05))
```

签名：

```python
check_multi_swap_sweep(pairs: Sequence[tuple[ObjectState, ObjectState]], bystanders: Sequence[ObjectState] = (), *,
                       sweep_index: int | None = None, stage: str = "sweep", raise_on_reject: bool = False,
                       prefilter: bool = True, stats: dict[str, int] | None = None) -> tuple[float, CollisionRejection | None]
check_swap_sweep_prefiltered(moving_a, moving_b, bystanders=(), *, sweep_index=None, stage="sweep",
                             raise_on_reject=False, prefilter=True, stats=None) -> tuple[float, CollisionRejection | None]
```

前提（调用方负责）：同一次调用里的所有对必须在**同一个窗口**、同一 smoothstep 下用 `lane_offset=0.07` 交换（`LANE_OFFSET` 常量；VUS/BUS/VideoRepick 实际都传 0.07）；位姿传交换开始时刻的（实际或名义）位姿。

## 四、测试与实测数字

### 4.1 新单测（`tests/lightweight/test_v5_multi_sweep.py`，16 条，本机 ≈24 s）

单对 18 例随机（含 ≥4 例接触拒绝）与 `check_swap_sweep` 逐位相同 + 预筛开判定/证据相同；已知接触样例；二分耗尽与四元数退化下预筛不替近处的对放行；原函数从不走预筛；类 Swap 场景两对联合预筛开/关证据一致；远处第二对不改变结果；两对平行交换（弦线相距 0.14）各自单查通过、联合被拒且证据为跨对的 `bin_0`↔`distractor_bin_1`；名字重复报错；预筛 Lipschitz 下界不高于 2001 点密采的真实圆柱间隙；常量；静止盒体几何与 SAT 值；二维 OBB 转换（含左手系、非正交报错）；按钮底座复刻 `build_button`；静止矩形/按钮底座作 bystander 生效；统计字典累加。全部通过。

### 4.2 离线大样本（scratch 脚本，不入库）

- **单对逐位等价**（2～5 个同类容器或方块随机撒在 0.36 m 见方，种子 20260924，600 例）：`check_multi_swap_sweep(prefilter=False)` 与 `check_swap_sweep` **600/600 逐位相同**（最小 g 与整份拒绝证据）；预筛开 **600/600 判定与证据相同**；其中接触拒绝 309、通过 291。耗时合计：原函数 81.27 s、新函数预筛关 81.17 s、预筛开 10.62 s（平均每例 135 ms → 18 ms）。
- **类 VUS/BUS 两对联合**（内环 4 容器 |x|,|y|≤0.2、最小中心距 0.065；外环 10 干扰容器 V4 环带 [0.2675,0.45]、最小中心距 0.07；奇数例加两个按钮底座 (±0.3,0)；内环对与外环对都按最近邻；种子 20260925，200 例）：预筛开/关 **200/200 判定与证据相同**；单对内环预判（其余全静止）原函数 vs `check_swap_sweep_prefiltered` 同样 200/200 相同。拒绝构成：通过 90，内环对内环接触 57，外环对外环 27，跨内外 13，外环压按钮 11，内环压按钮 2（本合成场景比真实布局拥挤得多，拒绝率不代表真实环境）。

| 检查 | 预筛关 | 预筛开 |
|---|---|---|
| 两对联合（14 容器 + 0/2 按钮） | 均值 784.7 ms，p50 842.9，p95 1399.4，最大 2073.5 | 均值 94.1 ms，**p50 21.4**，p95 415.3，最大 680.3 |
| 单对内环预判 | `check_swap_sweep` 均值 427.6 ms，p50 439.8，p95 748.7 | 均值 58.8 ms，**p50 3.7**，p95 345.2 |
| 精确证明的对象对 / 盒对 | 1661 / 54226 | 154 / 2254（预筛跳过 1507 个对象对） |

预筛开时的长尾来自**被拒的样例**（拒绝那一对必须二分到证否为止）；通过的样例基本在几十毫秒内，与 P5 原型「0.8～1.8 s → 3～55 ms」一致。

### 4.3 全量轻量测试

命令：`timeout 290s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -p no:cacheprovider`。
结果：`46 failed, 856 passed, 22 skipped, 74 deselected, 12 errors in 157.59s`；失败集合（`grep -E '^(FAILED|ERROR) ' | sed 's/ - .*//' | sort`）58 条，与 `/data/hongzefu/robomme_v5_wt/wt_baseline_failset.txt` **逐条相同**（`diff` 为空），新增 16 条全部通过。
V0 静态检查：`git diff` 中 `config_easy/config_medium/config_hard/NATIVE_SAMPLING` 命中 0 处。
本任务是纯几何函数、尚未接入任何环境，未跑演示探针。

## 五、与计划不符之处

- 计划写「采样 401 个 s 值、以 Lipschitz 界证明分离」，P5 原型用固定外接圆半径 0.0424 且不计旋转；正式版改为逐对象、计旋转的竖直圆柱（见二.3），更一般，判定不变。
- 预筛放行余量用 1 mm（原型相当于 0），见二.4。
- 无其他不符。

## 六、待用户决策

无。（余量取值、名字唯一性报错、`z_range` 必填均属实现细节，已按上文自决。）

## 七、给合并者的注意事项

- 本 S2b 只改 `bin_collision.py`（纯追加）与一个新测试文件，与其他 S2 子任务无文件重叠。
- 调用方要预筛就必须调新函数：`check_swap_sweep` 仍不预筛（P5：预筛须覆盖 reset 的三处检查——内环预判、外环联合、H1 静态候选，否则 reset 慢 20～30 倍；H1 静态候选检查不在本模块，S3h 需自行接预筛或改调本模块）。
- 通过时返回的最小 g 受预筛影响，**不要**把它写进需要跨版本逐位对拍的规格字段；判定与拒绝证据才是稳定量。
