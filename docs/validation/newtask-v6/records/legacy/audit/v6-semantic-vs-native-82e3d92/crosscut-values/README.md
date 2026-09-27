# 横切：配置档位值 vs 交付数据实测值（crosscut-values）

- 审计锚点 `AUDIT_BASE=82e3d922b78d48ec1e825b168cccc0e1b8c690c1`；开审与收尾两次 `git rev-parse HEAD` 均为该值，`git status --porcelain` 均为空。源码只经 `git show <AUDIT_BASE>:<path>` 读取（`sampling_config.json`、`plan.md` 为其快照副本）。
- 纯只读：未运行仓库内脚本、未导入任何仿真包；只用 h5py / numpy / cv2 读已有 HDF5。辅助脚本全部在本目录。
- 范围：新档 55 格 × 3 局 = 165 条（`../new-tier-index.json`）＋ 原三档 16 任务 × 3 档 × 3 局 = 144 条（`artifacts/newtask-v6/v1/base/B/`），共 103 格 309 条。机器可读结果：[`measured.json`](measured.json)（每格每局的配置值、实测值、`checks` 判定）。

## 测量方法

| 量 | 方法 | 脚本 / 原始输出 |
|---|---|---|
| 子目标链、演示/执行步数、完成步 | 逐步读 `info/is_subgoal_boundary`、`simple_subgoal`、`is_video_demo` | `scan.py` → `scan_raw.json`、`summary_seq.txt`、`seq_rest.txt` |
| 物体计数（方块按颜色、容器分内/外环） | `front_depth`+内外参反投影到世界系（桌面 z≈0.001 m，方块顶 0.035–0.042 m，容器顶 0.073–0.075 m），高度带连通域＋HSV 分色；同色相邻方块用顶面世界面积（单块约 20–24 cm²）拆分 | `geom.py`、`counts.py`、`cubearea.py` |
| 交换次数（VUS/BUS/VR） | 高度带掩码逐帧异或像素数得活动曲线，按低谷分窗，窗长/单次交换步长（速度1≈48帧，速度1.5≈32帧）取整求和 | `swaps.py` → `swaps_raw.json` |
| StopCube 经过靶心次数 | 连通域跟踪方块 xy，靶心在方块远离时重估（剔除方块像素），统计进入 3 cm 半径的次数 | `track.py`、`stopcube_visits.py` |
| MoveCube 圆环 | 方块顶面质心、靶盘质心到 (−0.06,0) 的距离 | `track.py` |
| VPB/VPO 每次搬运的方块身份 | 放置子目标起始帧腕部相机夹爪间区域多数色 | `vp_identity.py` → `vp_identity.json` |
| PatternLock 路径 | 由方向子目标重建格点路径：节点数、重访、跨度 | 内联于汇总 |

自动分割有三处过分割/漏计，已逐帧目视改正并在 `measured.json` 标 `bins_visual`/`cubes_t0_visual`：ButtonUnmask xhard3 ep3（20 个容器）、ButtonUnmaskSwap xhard4 ep0（14）、VideoUnmaskSwap xhard4 ep3（14）、PickHighlight xhard3 ep6（9 块）。StopCube hard ep7 跟踪失败，未测。

## 结论速览：新档 55 格

所有新档格的梯度维度实测值均落在配置区间内且与语言目标一致：

| 任务 | 梯度维度 | 实测（xhard1 / xhard2 / xhard3 / xhard4，各 3 局） | 配置 |
|---|---|---|---|
| BinFill | 投入块数 / 总块 / 颜色数 | 6,6,6 / 7,7,7 / 8,8,8 / 9,9,9；总块 12；2–3 色；目标各色数 ≤ t0 可见各色数 | 6/7/8/9；12；[2,3] |
| PickXtimes | 次数 / 干扰块 | 6,7,6 / 9,9,9 / 11,11,11 / 14,15,13；干扰 1/2/3/3（黄；黄青；黄青品） | [6,7]/[8,9]/[10,12]/[13,15]；1/2/3/3 |
| SwingXtimes | 轮数 / 干扰块 | 4,4,5 / 6,7,6 / 8,8,8 / 11,10,11；干扰 1/2/3/3 | [4,5]/[6,7]/[8,9]/[10,11] |
| PickHighlight | pick / 总块 | 4/7、5/8、6/9、7/10 | 同 |
| VideoUnmask | pick / 外环干扰容器 / 外环方块 / 内环 | 2/8/4/8、3/10/5/8、3/13/6/8、3/15/7–8/8 | 同 |
| ButtonUnmask | 同上 | 2/8/4/8、3/10/5/8、3/12/6/8、3/14/7/8 | 同 |
| VideoUnmaskSwap | swap / pick / 外环 | 4,4,4 / 7,7,7 / 9,8,8 / 11,11,12；pick 2/3/3/3；外环 4/6/8/10；单次交换约 48 帧（xhard1）、约 31 帧（其余） | [4,5]/[6,7]/[8,9]/[10,12]；50/33 步 |
| ButtonUnmaskSwap | 同上 | 4,4,4 / 5,5,5 / 6,6,7 / 8,8,8；外环 4/6/8/10 | 4/5/[6,7]/[8,9] |
| VideoRepick | 块数 / swap / repick | 4/4,3,4/2、5/6,6,6/3、6/7,8,7/4、7/12,12,10/5,6,5；同色 | 同 |
| PatternLock | 节点数 | 11,10,12 / 14,14,16 / 17,17,17 / 21,21,23；无重访、跨度 ≤5×5，演示=执行 | [9,12]/[13,16]/[17,20]/[21,25] |
| RouteStick | 段数 | 10,9,10 / 13,11,13 / 16,14,15 / 18,18,18；执行段 = 50·L | [8,10]/[11,13]/[14,16]/[17,21] |
| VideoPlaceButton | 放台次数 | 3/4/5/6；xhard3 一块 3 次一块 2 次，xhard4 各 3 次；全部放回原位 | 3/4/5/6 |
| VideoPlaceOrder | 总放台（分块） | 5（2+3）/6（3+3）/7（3+4）/8（4+4）；目标序数 ≤ 该色放台次数（七档 21/21 局） | 同 |
| MoveCube xhard4 | 圆环 | 方块/靶心半径 0.120–0.174 / 0.139–0.169 m，方块-靶 0.154–0.285 m | [0.12,0.20]；[0.10,0.30] |
| StopCube xhard4 | 第 N 次 | 经过次数 6、14、15 与目标序数一致，间隔 60 帧 | stop_time∈[6,15]，interval 60 |
| InsertPeg xhard4 | 无梯度 | 演示与执行抓取端/插入侧一致 | — |

原三档 48 格：与计划「三、四档定稿表」hard 列一致（BinFill 4,4,3；PickX 4,5,5；Swing 3；PH 3/6；VUS swap 3,2,2；BUS 2,3,2；PL 5,6,5；RS 5,5,4；VPB 2 放台；VPO 4,3,4）；唯一不符为 ButtonUnmask 原档容器数（见 V5）。

## 发现（排除清单外）

| 编号 | 类别 | 内容 | 证据 |
|---|---|---|---|
| V1 | new_tier_only / 中 | **VPB xhard4 两块档的「right/immediately before the button」时间邻接不成立。** ep0：绿 111 帧放台 → 蓝 328、492 连放两次 → 590 按钮；目标说绿块是「按钮前紧接着」放的。ep6：蓝 121 → 绿 332、492 → 581 按钮，同样。原三档与单块新档中目标块的按钮前放台都紧邻按钮。答案台（绿/蓝唯一一次按钮前放台）本身唯一。 | `vp_identity.json`；`frames/VideoPlaceButton-xhard4-ep0-*`（t150 夹绿、t360/t540 夹蓝）；锚点 `utils/task_goal.py::get_language_goal` 的 VPB 分支、配置 `VideoPlaceButton.decision.xhard4.extra_place_before=1` |
| V2 | new_tier_only / 低 | **VPB 第三条替代表述「where it was previously placed after/before the button」在多次放台时不唯一。** xhard1 ep0/ep6、xhard2 ep0/3/6：目标块按钮后放台 2 次；主表述与第 4 条（first placed after）仍唯一。原三档按钮前后各 1 次，无歧义。xhard3 ep3/ep6 属已排除项，仅标 seen。 | `measured.json` `goal_color_after`；配置 `extra_place_after=1`（xhard1/2） |
| V3 | new_tier_only / 低 | **SwingXtimes xhard4 子目标序数退化成数字「11th」。** ep0、ep6 出现「for the 11th time」，其余均为英文序词，目标句为「eleven times」。原三档最多 3 轮不触发。 | `SwingXtimes.py::_load_scene` 中 `ordinals` 只到 tenth，超出走 `f"{i+1}th"`；共用 `utils/subgoal_language.py` 已有到 fifteenth |
| V4 | new_tier_only / 低 | **计划四.7 超 1300 步清单与实测不符。** 实测执行段完成步：PickXtimes xhard2 ep0 = 1350（计划未列 xhard2）；PickHighlight xhard4 最多 1257（计划称会超）。BinFill xhard3/4、PickX xhard3/4 与计划一致。冻结的 `scripts/evaluation.py` `max_steps=1300`。 | `measured.json` `exec_steps_to_completion` |
| V5 | native_vs_new_mismatch / 低 | **ButtonUnmask 原档容器请求数被静默截断。** 配置 `bin_layout_policy.count` medium 5、hard 15；实测 medium ep10 为 4，hard 三局均为 6。源码 `ButtonUnmask.py` 放不下即 `break`，新档同一处则抛 `SceneGenerationError`，新档 8 内环实测 8。与 D1（VideoUnmask hard）同根，BU 为另一环境。 | `frames/grid-ButtonUnmask-t40.png`、`frames/ButtonUnmask-medium-ep10-front_rgb-t40.png` |

## 已见的排除项

D1（VideoUnmask hard 实测 6 个容器，配置 15）、VPB xhard3 ep3/ep6 的 last-before 绑定（按钮前目标块放台 2 次）、D2（Swing 左右）、F1（PickHighlight 两条目标）、F2（VideoRepick 措辞）、F5（BinFill 悬空删除）。

## 附注（原档专属、非本轮范围）

- BinFill 原档约一半为 `native_dynamic`：t0 可见方块少于目标（如 easy ep0 可见 1 红，目标 2 红），新档一律静态杂乱布局 12 块。计划口径 6 已写明新档沿用 xhard 机制。
- SwingXtimes medium ep2（N=1）目标说「put it down on the left-side target」，子目标写「put the green cube on the table」；目视方块确实放在该靶上，只是子目标用词更泛。

## 未覆盖

- 未逐局核对交换对象的局内均衡（S5/O4）、外环窗口与内环窗口逐一同步；外环窗口计数仅作参考。
- 未测原档 BinFill 的 spawn_cubes（动态生成）、原档 VideoRepick/VPB/VPO 的方块总数以外的布局参数、InsertPeg 杆数与 yaw。
- 颜色身份依赖 HSV 阈值；PickHighlight/VideoRepick 新档任意色只计数不命名。
