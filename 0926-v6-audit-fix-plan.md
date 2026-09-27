# V6 语义审查修复计划（0926；逐条待用户裁决）

> **权威性与授权边界**：本文件是对 `artifacts/audit/v6-semantic-evidence-01a0e086/审查汇总.md`（审查锚点 `0a3f989b0dfcff12a3cbb34a8112cb56864c7ee8`）所列 F1～F6、D1～D8 共 14 条发现的修复计划。**只规划不实施；每一条发现是否修都要用户单独裁决**（用户 2026-09-26 原话：「在根目录写修复计划 解释每一条查到的问题」「注意每一条查到的问题 都要问用户是否修」）。V6 计划 D7-m13「免逐项批准」在本轮被这条原话覆盖，`src/robomme/` 的每处改动仍按 AGENTS.md P2 逐个批准。修复落地后本轮**只做两件事**：重新生成「13 任务 × 新 4 档 × 3 局 ＋ 3 任务 × 1 档 × 3 局 ＝ 165 成功局」，以及更新网站；不重跑原三档 144 局真实对拍，不做清单外新增。
>
> **代码锚点**：主仓 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-v5`，当前 HEAD `0d678ef9ef7977352d90b8cd5bec24c67081b962`（工作区干净）。原 S4 启动锚点 `c8c06ab`，生产源码基线 `38488db08954ed10c0dd5450a5ccca9b6294d9dd`，`scripts/configs/newtask-v6/sampling_config.json` SHA-256 `6ab3b0c218ad77e29f765f98f2e670c7462d386db9f23257e282242094a5dab3`。审查报告里的行号只对审查锚点有效，本文一律用符号锚点。commit 体例 `12.<小版本> 中文描述`，接 `12.182`。
>
> **GL 现状（2026-09-26 复用 ControlMaster 查得，零认证）**：`61890467`（gl1526，RUNNING 1-05:56）、`61890468`（gl1517，RUNNING 1-05:42）、`62018665`（gl1510，RUNNING 3:23）三席在跑，`62018666` PENDING(Resources)；四席按 D22 保留、不 scancel。集群侧仓库 `/nfs/turbo/coe-chaijy-unreplicated/hongzefu/robomme_benchmark-newtask-gl`。
>
> **两条贯穿所有条目的前提（同样待裁决，见第四节 Q-A / Q-B）**：① 共用代码（话术、成功谓词、录像字段）一改，原三档 easy/medium/hard 的逐位冻结基线（S3 真实 144 局 SHA 全同）就不再成立；每条都标了「影响原三档？」，用户须选「按档位门控只改新四档」或「接受重新定义原三档基线」。② 165 局重生成走原 S4 管道（`scripts.parity.v5_generation pipeline`，一条命令先抽 550 候选再取 index 0/3/6），凡改了 spec 决策或轨迹的修复都必须重抽候选，纯话术修复理论上可复用候选但管道不支持只跑正式段，故默认整段重跑、新 run-id。

# 第一部分（给人看）

## 一、总览

**一句话方案**：14 条发现按「改什么层」分四类——纯文案（F1 话术、F2、D1、D4、D5）、标签/字段绑定（F3、F4、D6）、行为与成功谓词（F5、F6、D3、D7）、视角说明（D2）；用户逐条拍板后，只改被批准的条目，用轻量对拍证明未批准部分与原三档零漂移，然后以新 run-id 在既有两席重跑 S4 管道拿到 165 成功局，最后用新交付清单生成 site-v11 并全量浏览器验证。

**已定死口径**（本轮用户原话，逐字）：

| 编号 | 原话 | 落地 |
|---|---|---|
| U1 | 「在根目录写修复计划 解释每一条查到的问题」 | 本文件，第二节逐条 |
| U2 | 「修复后只做 13任务 × 新4档 × 3局＋3任务 × 1档 × 3局＝165成功局目标 和网站更新」 | 第三节两个阶段；不重跑原三档 144 局真实对拍，只做轻量对拍证明未动部分零漂移 |
| U3 | 「注意每一条查到的问题 都要问用户是否修」 | 第四节裁决表，逐条 AskUserQuestion；未获答复的条目按「不修、仅披露」处理，不默认修 |

## 一′、关键决策（2026-09-26 第二轮，用户原话逐字）

| 编号 | 原话 | 落地 |
|---|---|---|
| K1 | 「不要修任何easy medium hard的问题 我只关注xhard1234 并且报告和之前easy medium hard不一致的语义问题 这一条写入关键决策」 | 一切修复只对 xhard1～xhard4 生效（共用代码一律按档位门控）；原三档代码路径、HDF5、网站文案都不动；凡属原三档同样存在的语义问题，只在留档「与原三档不一致的语义问题」一节报告，不修 |
| K2 | 「f1同意修」 | PickHighlight 新四档末尾加按钮任务，成功后移，话术两句统一 |
| K3 | 「f2改为不动」 | VideoRepick 话术不改；该话术原三档同源（`num_repeats_range` 原三档 [1,4) 也会出 N=2/3），记入 K1 报告 |
| K4 | 「f3 我只要在视频中对齐机器人坐标系即可 对象名称可以你来改 改成和机器人坐标系对齐」「d2 不要管 所有的左右都是机器人坐标系」 | 全仓左右语义统一为机器人坐标系（机器人朝 +x，左 = +y）；BUS 的 `button_left/right` 命名按此改，物理对象与任务链顺序不变 |
| K5 | 「f4 同意修改」 | 交换后坐标缓存按位移刷新，只对新四档生效 |
| K6 | 「f5 不改」 | BinFill 悬空删除不修不披露；机制原三档同源，记入 K1 报告 |
| K7 | 「d3 自动揭示cube是预期行为 不要修」 | 不修不披露 |
| K8 | 「d4 不要管原hard」「d5 不要管」「d1（hard 展示）」 | 原 hard 文案与「静止」标签不动 |
| K9 | 「d7 xhard的生成不管vqa 但是要记录下这个问题」 | 不改 VQA；记入留档已知问题 |
| K10 | 「f6修 d6修」 | F6 完整序列占用表 + 守卫；D6 改欧氏距离（均在 xhard 分支内） |
| K11 | 「你现在有3个node可以用」 | 165 局重跑用三席：`61890467/gl1526`、`61890468/gl1517`、`62018665/gl1510`；`62018666` 仍 PENDING 不依赖 |
| K13 | 「src修改确认」随后「不要实施！」「落到计划内！！！！」 | 七项改动的详细设计只写入本计划第二部分「一」，源码零改动；实施须用户另行下令 |
| K14 | 「vpb问题也要修复 落到计划内」 | VPB 旧题（按钮前最后放置答案绑定）列为必修项，与 F6 同批实施，设计见第二部分「一」第 5 项第 2 点 |
| K12 | 「VPB 旧题…这个是什么问题？？？ 没在逐条问题内？」 | 该题不在本次审查 14 条内，是 V6 计划 D25 已知问题（xhard3 ep3/6）；解释见第二节 Q-C 小节，待用户裁决 |

## 二、逐条发现：机制、锚点、修法、影响面

每条按「是什么问题 → 源码锚点与机制 → 候选修法（推荐项在前）→ 影响原三档？→ 验收判定行」写。「影响原三档」指改动是否落在原三档也会执行的共用代码路径；落在 `is_v6_tier` 分支内的不影响。

### F1　PickHighlight 话术要求末尾再按按钮，任务链没有这一步

- **机制**：`utils/task_goal.py::get_language_goal` 的 `PickHighlight` 分支产出两句：第一句「first press the button, then pick up all cubes that have been highlighteted with white areas on the table」（另含拼写错误 highlighteted），第二句「…finally press the button again to stop」。`PickHighlight::_initialize_episode` 的 `task_list` 只有开头一个 `press the button` 任务，之后是逐块抓取与 `place the cube onto the table`，没有末尾按钮；`evaluate` 在最后一抓完成即判成功。审查实证 xhard1/ep0/seed9200000 在 693 帧完成第四抓、705 帧仍持块即结束，视频顶部字幕仍写末按钮。四新档 12/12 条 HDF5 第二句都带末按钮。
- **修法**：
  - A（推荐，纯文案）：第二句改为「first press the button, then pick up all highlighted cubes one by one」，同时修 highlighteted 拼写；两句与任务链一致。
  - B（行为）：在 `task_list` 末尾追加 `press the button` 任务（`is_button_pressed` + `solve_button`），成功判定后移；这是行为与成功谓词修改，需重验 PH 成功/失败锁存同真问题。
- **影响原三档**：`get_language_goal` 是共用函数，原三档 PH 的 HDF5 `language` 字段会随之变；不重生成原三档则磁盘文件不变，但「同一份代码复现原三档逐位相同」不再成立。可用 `self.difficulty` 门控只对新四档换话术（代价：两套话术并存）。
- **判定行**：`PH_LANGUAGE=PASS episodes=12 terminal_button_phrase=0`（新 165 局中 PH 12 条 `language` 无 "press the button again"）。

### F2　VideoRepick 把「执行 N 次」写成「演示里抓过 N 次」

- **机制**：`task_goal.py::get_language_goal` 的 `VideoRepick` 分支在 `pick_times ≥ 2` 时产出「pick up the same cube that was previously picked up {word} times」，读法是演示里抓过 N 次；`VideoRepick::_initialize_episode` 的演示段只抓一次，N 是执行段的抓放次数。审查 7 档 21 条演示均只抓一次，其中 18 条 N>1 带该话术。
- **修法**（推荐，纯文案）：两句统一改为「watch the video carefully, identify the cube that was picked up, then pick up and put down that same cube {word} times, finally press the button to stop」；`pick_times == 1` 分支同步核对。
- **影响原三档**：共用函数，同 F1；可按档位门控。
- **判定行**：`VR_LANGUAGE=PASS episodes=12 previously_times_phrase=0`。

### F3　ButtonUnmaskSwap「第一/第二按钮」的选项标签与执行对象反转

- **机制**：`ButtonUnmaskSwap` 采样配置 `button_order: ["right","left"]`；`_initialize_episode` 先按 `buttons_cfg[0]`（name `button_left`，center_xy `[-0.2,-0.1]`）建按钮存到 `self.button_left`，再建 `buttons_cfg[1]`（`button_right`，`[-0.2,0.1]`）存到 `self.button_right`。`task_list[0]` 名为「press the first button」但 `solve` 指向 `self.button_right`、`segment` 用 `cap_links["button_right"]`；`task_list[1]`「press the second button」指向 `button_left`。而 `utils/vqa_options.py::_options_button_unmask_swap` 把 label `a`「press the first button」绑到 `base.button_left`、label `b` 绑到 `button_right`——与环境任务链正好相反，`OraclePlannerDemonstrationWrapper::_execute_selected_option` 按 label 执行时会去按另一个按钮。四新档 12 条都用这套映射；两个按钮的成功谓词 `is_any_button_pressed_removelist` 接受任意先后，所以不会因此失败，但 HDF5 里记录的选择标签与像素/轨迹不一致。
- **修法**：
  - A（推荐）：`_options_button_unmask_swap` 改为按环境 `button_order` 解析——label `a` 绑 `button_list` 中 `button_order[0]` 对应对象（即当前的 `button_right`），label `b` 绑第二个；不改环境类。
  - B：反过来改环境任务链（`task_list[0].solve → button_left`），并同步 `segment`；改动面更大，且原三档 hard 的 BUS 轨迹会变。
- **影响原三档**：A 只动 VQA/oracle 选项闭包；专家演示（`solve`）路径不经过它，原三档 HDF5 轨迹不变，但 `action/choice_action` 标签字段若由该映射产生则会变，实施前用一条 hard/BUS 冒烟核实该字段来源。
- **判定行**：`BUS_CHOICE_BINDING=PASS episodes=12 label_target_mismatch=0`（逐条核对 choice label 对应的 solve 对象 == 该帧 segment 所指按钮）。

### F4　ButtonUnmaskSwap 交换后 `grounded_subgoal` 的在线坐标仍指旧位置

- **机制**：`utils/segmentation_utils.py::process_segmentation` 在子目标开始时计算目标 mask 的中心 `<center_y, center_x>` 并写入 `segmentation_points`（docstring：cached center points for current targets），`DemonstrationWrapper::_step_batch` 在子目标未切换期间沿用该缓存填充 `<>` 占位。BUS 的「先按按钮再等交换」（`_solve_press_then_wait_swaps`）让子目标在交换前就锁定，交换后目标已移到别的容器位置，但文本坐标不刷新。审查 12 条首抓中 10 条提前 53～163 帧锁定；代表 ep3 在 175 帧缓存 `<126,118>`，268 帧目标已在 `<135,179>`、动作点 `[132,182]`。
- **修法**：
  - A（推荐，最小）：把缓存刷新条件改为「子目标切换 **或** 目标 actor 的 segmentation 中心相对缓存移动超过阈值（如 8 像素）」，仍只在需要时重算。
  - B（契约）：不改数值，新增字段 `grounded_subgoal_anchor_frame`（记录缓存取自哪一帧）并在文档声明「坐标是子目标起始帧锚点」。
- **影响原三档**：`process_segmentation` 自 `8747a39` 到锚点逐字节未变、四个 Unmask 环境共用；A 会改所有档位所有环境的 `grounded_subgoal` 数值（原三档只有交换环境会实际触发），B 只加字段。都属录像字段变更，见 Q-A。
- **判定行**：`BUS_COORD_FRESH=PASS episodes=12 stale_after_swap=0`（交换结束帧之后的坐标与该帧 segmentation 中心距离 ≤ 8 像素）。

### F5　BinFill 在孔板上方约 0.2 m 悬空「删除」方块并计数

- **机制**：`utils/subgoal_planner_func.py::solve_putonto_whenhold_binspecial` 把落点 z 直接设为 `0.2` 后 `open_gripper()`；`utils/subgoal_evaluate_func.py::is_obj_dropped_onto_delete` 在 `is_obj_dropped_onto`（XY 距离 ≤ 0.05 且 `is_obj_dropped`：非演示模式下 z ≤ 0.2、未持握）与 `check_block_away_gripper`（两指开度 > 0.02 且夹爪离开）同时成立时把方块 `set_pose` 到 `(10,10,0)`。于是方块在 0.17～0.21 m（孔板顶 0.05 m）松手的下一帧即消失并计一次投入，90 次全部如此。这是显式旧机制，不是渲染漏帧。
- **修法**：
  - A（仅披露）：网站 BinFill 卡片与 README 写明「投入采用抽象收集：松手即计数并移除方块」。
  - B（行为）：`solve_putonto_whenhold_binspecial` 落点 z 降到孔板顶 + 方块半边长 + 余量（约 0.09 m），`is_obj_dropped_onto_delete` 增加 z ≤ 0.10 门槛，让方块可见地落到孔板上再移除；需验证孔板碰撞体不会把方块弹开。
- **影响原三档**：B 改共用求解与谓词，原三档 BinFill 轨迹与成功时序全变；只能门控或重定义基线。
- **判定行**（选 B 时）：`BINFILL_DROP_HEIGHT=PASS drops=90 max_delete_z=<值> threshold=0.10`。

### F6 / D8　VideoPlaceButton 额外放台缺少跨按钮时刻的占用检查

- **机制**：`VideoPlaceButton::_initialize_episode` 的 `is_v6_tier` 分支为 before/after 各抽额外放台：`side == "before"` 时 `occupied` 只取 `demo_before_targets`，`side == "after"` 时只取 `demo_after_targets`，候选台排除 `occupied` 与答案台后随机抽一个。任务链顺序是「before 放置 → 额外 before → 按钮 → after 放置（按方块顺序）→ 额外 after → 回原位」。额外 before 的台 X 只排除了 before 台，若 X 恰是某方块 j 的 after 台，而 X 上的额外方块 i 要到自己的 after 回合才搬走（i 排在 j 之后），就出现「蓝块留台 1 → 红块也放台 1 → 之后才搬蓝块」。审查在 GL 62018665 实跑 xhard4/ep5（seed 7000500）复现：850～925 帧红块降到已占台、940～960 帧松爪、之后任务 9 又提起红块，真实结果 `DatasetGenerationError`。ep7/9 只有计划反例。正式 ep0/3/6 未含这三个候选。
- **修法**（推荐）：抽额外台时按完整任务序列维护「每台当前占用」：before 侧候选同时排除 `demo_after_targets` 中「其 owner 在本额外 owner 之后才搬走」的台（最简单是全排除 after 台）；after 侧候选排除仍留在台上的额外 before 方块所占台；并在 `xhard_home_site.validate_demo_plan` 加同一条占用守卫，冲突即 `SceneGenerationError` 而不是生成冲突轨迹。**不得只改答案字段保留冲突动作序列**。
- **影响原三档**：全部在 `is_v6_tier` 分支内，原三档不受影响。改变 spec 决策 `objects.extra_place_target_ids.*` → VPB 新四档候选必须重抽。
- **判定行**：`VPB_OCCUPANCY=PASS candidates=40 conflicts=0`（离线对 40 候选 spec 回放完整放置序列，无任何一步把方块放到已占台）。
- **关联已知问题**：xhard3 ep3/6 的「按钮前最后放置」题意与程序答案台不一致（D25 只披露未修）。本轮既然重抽 VPB 候选，是否顺带把答案绑定改为「按钮前最后一次放置的台」列为 Q-C 单独裁决。

### Q-C（不在本次审查 14 条内）VideoPlaceButton「按钮前最后放置」答案绑定

- **来源**：V6 计划 D25 与最终报告 `KNOWN_ISSUES=DISCLOSED`；本次审查明确写「已知 VPB 的 last-before 同型问题…不作为新增机制重复计数」，所以没列进 F/D 编号。
- **机制**：`VideoPlaceButton::_initialize_episode` 把 before 题的答案固定为 `self.demo_before_targets[answer_index]`（即 `targets[2k]`）。新四档多出「额外放台」：若额外 before 的 owner 恰好是答案方块，演示顺序就是「答案方块放 targets[2k] → 再放额外台 X → 按按钮」，题面「place the … cube on the target where it was last placed before the button was pressed」按字面应是 X，程序答案却仍是 targets[2k]。after 题不受影响（额外 after 排在正式 after 之后，「first placed after」仍是 `targets[2k+1]`）。
- **规模**：40 候选中 6 条冲突（xhard1/2/3/4 = 0/3/2/1），已交付 12 条中 2 条（xhard3 ep3 seed 13000300：内部台 2、额外台 3；ep6 seed 13000600：内部台 0、额外台 1）；`success` 仍为 true。
- **修法**（推荐）：before 题的 `target_target` 改为「答案方块在按钮前最后一次放置的台」——若 `extra_before` owner == answer_index 则取额外台，否则不变；额外台抽取因此要先于 `target_target` 的确定（或排除答案方块作 owner，二选一，推荐前者以保留题型难度）。只在 `is_v6_tier` 分支内。

### D1　网站/计划写 VideoUnmask hard 有 15 个容器，画面只有 6 个

- **机制**：`VideoUnmask` 采样 `'bin': 15` 是请求上限，`_initialize_episode` 摆放失败即 `break` 并记 `layout.bin_count.placed`；三条展示 seed 实际放下 6。网站档位表由 `scripts/parity/v6_site_catalog.py::gradients` 解析 `0925-newtask-release-v6-plan.md` 第三节表，行 `VideoUnmask | 0（15 容器）/ 2`。
- **修法**（推荐，纯文案）：计划第三节该格改为「0（容器请求上限 15，实际按摆放结果）/ 2」，或网站卡片显示 spec 里 `layout.bin_count.placed` 实测值。
- **影响原三档**：无（不动源码）。
- **判定行**：`SITE_VU_BIN_TEXT=PASS`（页面文本含「请求上限」或实测数）。

### D2　SwingXtimes「右盘→左盘」是机器人视角，前相机画面相反

- **机制**：`task_goal.py::get_language_goal` 的 `SwingXtimes` 话术「right-side target … left-side target」按机器人左右；前相机看到的是左→右（xhard1/ep0 右盘 `<76,68>`、左盘 `<95,184>`）。
- **修法**：A（网站/README 注明「左右按机器人视角」）；B（话术加「on the robot's right/left」，共用函数，影响原三档 `language`）。
- **判定行**：`SWING_VIEW_NOTE=PASS`（网站卡片含视角说明）或 `SWING_LANGUAGE=PASS episodes=12`。

### D3　ButtonUnmask 揭示按绝对步数，按键不触发再次揭示

- **机制**：`ButtonUnmask::step` 每步按 `reveal_window`（配置 `start_step 0 / end_step 64`）调 `reveal_actors_parked` / `reveal_distractor_bins_parked`，与按钮无关；话术只说「first press the button, then pick up…」。新档按钮任务在 74～85 步结束，此后不再揭示。PickHighlight 同样按 10～100 步自动高亮。
- **修法**：A（仅披露：README/网站写明「提示按时间窗显示，按钮不触发提示」）；B（机制：改为按钮按下后开启揭示窗，属行为修改、影响原三档全部 BU 轨迹）。
- **判定行**：`BU_REVEAL_NOTE=PASS` 或（B）`BU_REVEAL_ON_PRESS=PASS episodes=12`。

### D4　PatternLock 网站写搜索预算 20000，原 hard 实际 1000

- **机制**：计划第三节 `PatternLock | 节点数（5×5，不重访，预算 20000）` 被 `gradients` 直接展示；配置里只有新四档 `path_search_max_attempts 20000`，原 hard 仍 1000。21 条路径与示范/执行吻合，不是路径错误。
- **修法**（推荐，纯文案）：改为「预算 hard 1000 / 新四档 20000」。
- **判定行**：`SITE_PL_BUDGET_TEXT=PASS`。

### D5　VPB/VPO 网站第二个「静止」子目标期间平台正在交换

- **机制**：`v6_site_catalog.py` 把无动作子目标统一标 `text = "静止"`；VPB/VPO 该段实际是机械臂等待、平台交换。
- **修法**（推荐，仅网站）：该段在 VPB/VPO 显示「机械臂等待，平台交换中」。
- **判定行**：`SITE_SWAP_WAIT_LABEL=PASS samples=30`。

### D6　InsertPeg 未选候选的 near/far 标签按 x 轴而非实际距离

- **机制**：`InsertPeg::_initialize_episode` 用 `abs(head_x - agent_x) <= abs(tail_x - agent_x)` 判 `near_link`，写入 `grasp_target_distance`；xhard4/ep5 第二布局按欧氏距离杆头 0.61363 m、杆尾 0.63401 m，标签反向。正式 ep6/2/4 未命中。
- **修法**：A（改用 TCP/基座到两端的欧氏距离）；B（文档声明 near/far 专指纵深 x 轴）。
- **影响原三档**：该判断在共用路径（实施前核实是否所有档位都走这段），改 A 会影响原三档 InsertPeg 的 `grasp_target_distance` 字段。
- **判定行**：`PEG_NEARFAR=PASS candidates=10 mismatch=0`。

### D7　四 Unmask 环境 VQA 只允许选内环容器，外环可见不可选

- **机制**：`vqa_options.py` 四个 Unmask 入口的 `available: env.spawned_bins`，外环 `distractor_bins` 不在列；像素最近邻无距离门，点外环会吸附到内环。属选择式策略评估机制缺口，不影响专家视频。
- **修法**：A（`available` 加入 `distractor_bins`，选中即按现有 `failure_func` 判失败，并加最近邻距离门，超出即「无效点」）；B（保持现状，文档写明外环不可选）。
- **影响原三档**：只动评估选项，不动 HDF5。
- **判定行**：`VQA_AVAILABLE=PASS envs=4 distractor_selectable=1 distance_gate=1`。

### 未在正式产物确认触发的成功判据缺口（审查第四节表）

`is_obj_dropped`（z ≤ 0.2）、`is_bin_pickup`（只查 z）、`is_obj_swing_onto`、MoveCube 杆推、RouteStick 方向、InsertPeg 孔轴、StopCube 容差、PH 成功/失败同真——审查明确「不能计入已发生错误」。本轮**不列为修复项**，只在 README 披露为已知判据包络；用户若要求收紧任一条，另立条目。

## 三、修复后的两个阶段

### 阶段 A：重新生成 165 成功局

- **前置**：所有获批改动 commit（`12.183+`）并 push；工作区干净；新建启动锚点文件（不覆盖 `s4-launch/launch-commit.txt`，改为 `s4-relaunch-02/launch-commit.txt`），启动器 `run-seat.sh` 的 `git diff --quiet 38488db … -- src scripts tests` 基线核对改为新的生产源码基线 commit；集群侧仓库 `robomme_benchmark-newtask-gl` 同步到同一 commit。
- **命令**（沿原 S4，只换 run-id，两席不变）：

  ```bash
  uv run --project "$PWD" --frozen --no-sync python -m scripts.parity.v5_generation pipeline \
    --release newtask-v6 --run-id /tmp/v6-s4-v6-02 --tiers "$TIERS" --tasks all \
    --candidates-per-env 10 --max-reset-attempts 60 --select 0,3,6 \
    --draw-workers 16 --draw-gpus 0 --workers 16 --rollout-gpu 0 \
    --official-root artifacts/train-parity/local-smoke-01/official-src
  ```

  `TIERS=xhard1,xhard2` 进 `61890467/gl1526`，`xhard3` 进 `61890468/gl1517`，`xhard4` 进 `62018665/gl1510`（K11 三席），各 `srun --jobid=<job> --overlap --exact --ntasks=1 --cpus-per-task=16 --gpu_cmode=shared`；本机 tmux 会话名 `v6-s4-relaunch-02-a` / `-b` / `-c`，日志 `artifacts/newtask-v6/s4-relaunch-02/logs/<job>.log`，末行 `EXIT_CODE=`。预算沿 V6 计划 5.3 节：每格最多 60 次抽签、正式只在 10 候选内递补至 3 成功。
- **验收**：`verify_s4.py` 同口径出 `final-delivery.json`：`S4_DELIVERY=PASS cells=55 successes=165 shortfall=0`；`CANDIDATE_VALUES=PASS candidates=520`；再对新 165 条跑第二节各判定行（只跑获批条目的）。
- **留档**：`docs/validation/newtask-v6/<日期>-audit-fix.md`，两段式；产物 `artifacts/newtask-v6/v6-02/`，原 `v6-01/` 与 `final-delivery.json` 原样保留。

### 阶段 B：网站更新

- 用新交付清单生成 `artifacts/newtask-v6/site-v11`：`uv run --no-sync python -m scripts.parity.v6_site_catalog --out artifacts/newtask-v6/site-v11 --delivery artifacts/newtask-v6/s4-relaunch-02/verification/final-delivery.json --poster-source artifacts/newtask-v6/site-v10`（媒体已变的卡片预览重新生成）；D1/D4/D5 文案改在 `v6_site_catalog.py` 与计划第三节；VPB `known_issue` 段按 Q-C 结果改写或保留。
- 精确重启唯一服务会话 `v6-gradient-site-8060` 切到 `--site-dir artifacts/newtask-v6/site-v11`（不动 `corlvis-site`）。
- 验收：`SITE_V11_FULL_BROWSER=PASS videos=213 failed=0 page_errors=0`（Playwright 逐视频，沿 site-v4 脚本）、`SITE_CATALOG=PASS tasks=16 cards=71 videos=213`、VPB/VPO 30 样例标签核对 `FLOW_LABELS=PASS samples=30`。

### 未批准条目的零漂移证明

对未获批的共用代码条目不做任何改动；对获批但按档位门控的条目，用 S1 同款轻量对拍证明原三档不变：`NATIVE_DEFS_UNCHANGED=PASS envs=16`、16 环境 × 原三档 reset 的 spec/位姿 sha 与 HEAD 前一版逐字相同（`RESET_PARITY_NATIVE=PASS resets=48 sha_mismatch=0`），并跑 LIGHTWEIGHT 四片（各限时 280 s）与 `tests/test_v6_tier_monotone.py`。不重跑真实 144 局。

## 四、裁决表（逐条问用户；本表随答复回填）

| 条目 | 类别 | 影响原三档 | 需重抽候选 | 用户裁决 | 备注 |
|---|---|---|---|---|---|
| F1 | 行为+话术 | 门控后否 | PH 新四档是 | **修（K2）** | 加末按钮任务 |
| F2 | 话术 | — | — | **不修（K3）** | 原三档同源，报告 |
| F3 | 命名对齐机器人坐标系 | 待核实名称是否入 HDF5 | 否 | **修（K4）** | 物理顺序不变 |
| F4 | 录像字段 | 门控后否 | 否 | **修（K5）** | |
| F5 | — | — | — | **不修不披露（K6）** | 原三档同源，报告 |
| F6/D8 | 行为（V6 分支） | 否 | VPB 是 | **修（K10）** | 完整序列占用表 + 守卫 |
| D1 | 原 hard 网站文案 | — | — | **不管（K8）** | hard 展示 seed |
| D2 | — | — | — | **不修（K4）** | 全仓机器人坐标系 |
| D3 | — | — | — | **不修（K7）** | 预期行为 |
| D4 | — | — | — | **不管（K8）** | |
| D5 | — | — | — | **不管（K8）** | |
| D6 | 字段（xhard 分支） | 否 | 否 | **修（K10）** | 改欧氏距离 |
| D7 | — | — | — | **不改，记录（K9）** | |
| Q-A | 共用代码落法 | — | — | **档位门控（K1）** | |
| Q-B | 165 局重生成方式 | — | — | **整段管道重跑，三席（K11）** | 新 run-id `v6-02` |
| Q-C | VPB 旧题答案绑定 | 否（V6 分支） | VPB 是 | **修（K14）** | 见第二节 Q-C 小节 |

# 第二部分（技术细节，供 agent 追踪）

## 〇、前置声明与红线

1. `src/robomme/` 每处改动按 P2 逐个批准，本文件第二节的修法清单不等于批准；用户在裁决表点头的条目才动，且只动该条目点名的锚点。
2. 不 `scancel` 四席任一；不重启 `corlvis-site`；不覆盖 `s4-launch/`、`v6-01/`、`final-delivery.json`、`site-v10`。
3. 改动只落主仓与集群侧同名仓库（同 commit）；`sampling_config.json` 若因 F6 守卫需要新增键，其 SHA 会变，须同步更新 `run-seat.sh` 里的 `sha256sum --check` 值，并在留档记录新旧 sha。
4. 生成期间冻结 HEAD（提交会破坏 `LAUNCH_SOURCE` 核对与 provenance）。
5. 任何判据 FAIL 只记证据链，不放宽阈值。

## 一、按文件的改动设计（用户 2026-09-26 已确认清单；**尚未实施**，实施须另行下令）

统一门控：凡共用代码一律用 `utils/difficulty.py::is_newvalue_difficulty(self.difficulty)`（xhard1～xhard4 为真，V5 旧名 `xhard` 与原三档为假）；原三档代码路径逐字不变，由闸门 G1 证明零漂移。`RecordWrapper.py` 默认冻结，本轮不碰。

### 1. F1　`robomme_env/PickHighlight.py::_initialize_episode`（xhard 分支，`xhard = is_newvalue_difficulty(self.difficulty)`）

- 现状：按钮任务 → 逐块「pick up the {idx} highlighted cube」，块间插「place the cube onto the table」，最后一块抓起即结束（`if cube_idx != num_targets-1` 才放下）。
- 改法：在 `xhard` 为真时，最后一块也追加「place the cube onto the table」（`is_obj_dropped_currentpickup` + `solve_putdown_whenhold(release_z=0.01)`），再追加末尾按钮任务：`func=is_button_pressed(self, obj=self.button)`、`name="press the button"`、`subgoal_segment="press the button at <>"`、`choice_label="press button"`、`failure_func=None`、`solve=solve_button(env, planner, obj=self.button)`、`segment=self.cap_link`。成功判定由 `sequential_task_check` 顺延到该任务完成，无需改 `evaluate`。
- 关闭态（原三档 / V5 xhard）：任务链不变。
- 判定行：`PH_TERMINAL_BUTTON=PASS episodes=12 last_task=press_the_button`；`PH_LANGUAGE=PASS episodes=12`。

### 2. F1　`robomme_env/utils/task_goal.py::get_language_goal` PickHighlight 分支

- 现状两句：「first press the button, then pick up all cubes that have been highlighteted with white areas on the table」「first press the button, then pick up all highlighted cubes, finally press the button again to stop」。
- 改法：`is_newvalue_difficulty(self.difficulty)` 为真时改为「first press the button, then pick up all highlighted cubes one by one, finally press the button to stop」与「first press the button, then pick up every cube highlighted with a white area on the table one at a time, finally press the button again to stop」（两句都与新任务链一致，并修正 highlighteted 拼写）；为假时保留原两句原文（含拼写错误，不动原三档）。
- 判定行：`PH_LANGUAGE=PASS episodes=12 phrases_match_chain=12`。

### 3. F3　`robomme_env/ButtonUnmaskSwap.py`（配置 `positions.buttons`、`button_order` 与 `_initialize_episode`）

- 原则：**只改名字，不改建构顺序、位置与随机数消费**，否则原三档按钮位姿抽样会漂。机器人朝 +x，左 = +y。
- 改法：`buttons[0]` 保持 `center_xy [-0.2,-0.1]`、`randomize_range` 不变，`name` 改为 `"button_right"`；`buttons[1]` 保持 `[-0.2, 0.1]`，`name` 改为 `"button_left"`。`_initialize_episode` 中第一个 `build_button` 之后 `self.button_right = self.button`（原为 `button_left`），第二个之后 `self.button_left = self.button`；`button_list` 顺序保持 `[buttons[0] 对象, buttons[1] 对象]`。任务链 `task_list[0]`「press the first button」的 `solve` 与 `segment` 改指 `self.button_left` / `cap_links["button_left"]`（物理上仍是 y=+0.1 那个、与现在按的是同一个按钮），`task_list[1]` 改指 `button_right`；`_solve_press_then_wait_swaps` 的实参同步改为第一按钮对象。`button_order` 改为 `["left","right"]`。`vqa_options::_options_button_unmask_swap` 不动，label a→`button_left` 自动等于第一按钮。
- 影响面核实项：`name` 字符串是否进入 spec sha 或 HDF5（`episode_spec` 目前未见记录 actor name；由 G1 的原三档 spec/位姿 sha 对拍最终裁定，若变则把改名也门控）。
- 判定行：`BUS_FIRST_BUTTON=PASS episodes=12 first_button_is_robot_left=12`；`BUS_CHOICE_BINDING=PASS label_target_mismatch=0`。

### 4. F4　`robomme_env/utils/segmentation_utils.py::process_segmentation`

- 现状：`if current_subgoal_segment != previous_subgoal_segment:` 才重算中心并填充 `<>`；否则原样返回 `existing_points` 与 `existing_subgoal_filled`。调用方在冻结的 `RecordWrapper.py`（离线与 online 各一次），签名不改。
- 改法（按 actor 打标，零全局状态、零泄漏）：BUS 在 `_initialize_episode` 且 `is_newvalue_difficulty` 为真时，给 `spawned_bins` 每个 actor 设属性 `_robomme_refresh_on_move_px = 8`（ManiSkill `Actor` 为普通 Python 对象，可设属性）。`process_segmentation` 新增分支：当子目标未切换、`existing_points` 非空、且 `current_segment`（或其列表元素）带该属性时，用当前 `segmentation_2d` 重算各目标中心；任一中心与缓存的切比雪夫距离 > 阈值即按「切换」路径整体重算并重新填充文本（`no_object_flag` 逻辑复用）。未打标的 actor 走原分支，原三档与其他环境逐字不变。
- 阈值校准：用审查样例 ep3（175 帧缓存 `<126,118>`，268 帧目标 `<135,179>`，位移 61 px）确认触发；用静止段确认不误触发。
- 判定行：`BUS_COORD_FRESH=PASS episodes=12 stale_after_swap=0 max_err_px=<值>`。

### 5. F6 + Q-C　`robomme_env/VideoPlaceButton.py::_initialize_episode`（`is_v6_tier` 分支）

- 现状顺序：先定 `target_target`（before 题 = `demo_before_targets[answer_index]`）→ 再抽额外放台，before 侧 `occupied` 只含 `demo_before_targets`，after 侧只含 `demo_after_targets`，再排除 `target_target`。台数：xhard1/2 为 3、xhard3/4 为 4（`decision.targets`），正式 before/after 占 `targets[0..2·demo_count-1]`。
- 改法：
  1. 用占用表回放整条序列：初始化 `occ = {i: None}`；正式 before：`occ[2k]=k`；逐个额外 before（owner o → X）：候选 = `{i | occ[i] is None and i ∉ after 集合 and i ≠ 临时答案台}`，抽定后 `occ[before_o 或 o 当前所在台]=None; occ[X]=o`；按钮；正式 after：断言 `occ[2k+1] is None` 否则 `SceneGenerationError`，`occ[o 当前台]=None; occ[2k+1]=k`；额外 after（owner o → Y）：候选 = `{i | occ[i] is None and i ≠ 最终答案台}`。候选为空即 `SceneGenerationError`（不静默降级）。
  2. 答案绑定（Q-C）：before 题 `target_target` = 答案方块在按钮前最后一次放下的台——若某个额外 before 的 owner == `answer_index` 则取该 X（多个取最后一个），否则取 `targets[2·answer_index]`；after 题维持 `targets[2·answer_index+1]`。`targets_not_true` 与 `_spec.record("actions.target_target_id", …)` 移到额外放台抽定之后。「临时答案台」在抽 before 侧时取 `targets[2·answer_index]`，避免额外台落到正式 before 答案台上造成歧义。
  3. 回注路径：`_spec.value("objects.extra_place_target_ids.<side>.<n>")` 键名不变；回注值不在新候选集合时沿用现有 `SceneGenerationError` 分支。
- 关闭态：原三档与 V5 `xhard` 不进此分支，不变。
- 判定行：`VPB_OCCUPANCY=PASS candidates=40 double_occupancy=0`；`VPB_LAST_BEFORE=PASS candidates=40 answer_eq_last_before=40`。

### 6. F6 守卫　`robomme_env/utils/xhard_home_site.py`

- 新增 `validate_place_sequence(steps, n_targets)`：输入 `[(cube_id, target_id), …]` 的完整放置序列（含正式与额外），回放占用表，出现「放到已被其他方块占用的台」即抛 `SceneGenerationError`；VPB 在构造 `tasks` 前调用一次。`validate_demo_plan` 保持原签名。
- 判定行：`VPB_SEQUENCE_GUARD=PASS` + 单测反例（构造冲突序列必须抛错）。

### 7. D6　`robomme_env/InsertPeg.py::_initialize_episode`（`if xhard:` 分支）

- 现状：`near_link = peg_head if abs(head_x-agent_x) <= abs(tail_x-agent_x) else peg_tail`。
- 改法：取机器人基座 `self.agent.robot.pose.p[0][:2]` 与两端 `pose.p[0][:2]` 的 XY 欧氏距离比较；日志同步打印两距离。只在 xhard 分支内。
- 判定行：`PEG_NEARFAR=PASS candidates=10 mismatch=0`。

### 8. 配置与启动器（非 `src/robomme/`）

- `scripts/configs/newtask-v6/sampling_config.json`：第 3 项若改动 `positions.buttons[*].name` 与 `button_order`，文件 SHA 改变；新 SHA 写入新启动器 `artifacts/newtask-v6/s4-relaunch-02/run-seat.sh` 的 `sha256sum --check`，旧启动器不动。
- 新启动器：复制 `s4-launch/run-seat.sh`，三席映射 `61890467→gl1526 xhard1,xhard2`、`61890468→gl1517 xhard3`、`62018665→gl1510 xhard4`，`RUN_ID=/tmp/v6-s4-v6-02`，`LAUNCH_ANCHOR` 读 `s4-relaunch-02/launch-commit.txt`，`code_baseline` 改为实施后的生产源码 commit。

## 二、对拍闸门总表

| 闸门 | 查什么 | 怎么查 | 判定行 |
|---|---|---|---|
| G1 | 未批准/门控条目对原三档零漂移 | 16 环境 × easy/medium/hard reset，spec 与位姿 sha 对比改动前 HEAD | `RESET_PARITY_NATIVE=PASS resets=48 sha_mismatch=0` |
| G2 | 定义未变 | `v6_tier_monotone` 与 S0 同款 | `NATIVE_DEFS_UNCHANGED=PASS envs=16` |
| G3 | 轻量测试 | LIGHTWEIGHT 四片各 280 s；失败集合减 S0 基线为空 | `LIGHTWEIGHT=PASS new_failures=0` |
| G4 | 每条获批修复的定向判定 | 第二节各判定行 | 逐条 |
| G5 | 165 交付 | `verify_s4.py` | `S4_DELIVERY=PASS cells=55 successes=165 shortfall=0` |
| G6 | 网站 | Playwright 全量 + 目录核对 | `SITE_V11_FULL_BROWSER=PASS videos=213 failed=0 page_errors=0` |

## 三、runbook（骨架，参数以获批清单为准）

1. 逐条 AskUserQuestion → 回填第四节裁决表 → commit `12.183 审查修复计划与裁决`。
2. 按批准实施改动 → 定向单测 + G1～G3 → commit `12.184 …` → push → 集群侧仓库 `git pull` 到同 commit → 记录 `s4-relaunch-02/launch-commit.txt`。
3. 三席各起一个 tmux 会话（`v6-s4-relaunch-02-{a,b,c}`）跑阶段 A 命令；每份日志一个 Monitor（`EXIT_CODE=|Traceback|DatasetGenerationError|SceneGenerationError|out of memory`）。
4. 回传产物 → `verify_s4.py` → G4/G5 → 留档 → commit `12.185 …`。
5. 阶段 B 生成 site-v11 → 重启 8060 → G6 → 留档 → commit `12.186 …` → push。

## 四、风险登记

- 共用话术改动会让原三档「代码复现逐位相同」失效（Q-A）；门控则两套话术并存、需在 `get_language_goal` 加档位分支并测试。
- F6 收紧候选台后 VPB 某些格可能「没有空闲的非答案 target」而 `SceneGenerationError` 增多，60 次抽签上限可能不够；出现即报告不扩预算。
- F5-B 的落板高度与孔板碰撞体未验证；先单局冒烟。
- 集群侧仓库与主仓 commit 不一致会被 `LAUNCH_SOURCE` 核对拦下，属预期。
- 6 h 外层超时沿用；两席 1-05h 已跑，48 h 上限内仍有余量，但 `62018666` 仍 PENDING，不依赖它。

## 五、盲区诚实清单

- F3 的 HDF5 `choice_action` 标签是否经 `vqa_options` 产生尚未核实；实施前一条冒烟确认。
- D6 的 near/far 判断是否只在某档分支内执行未核实。
- F4-A 的位移阈值 8 px 是估值，需在 ep3 268 帧样例上校准。
- 165 局重跑耗时按原 S4（两席、6 h 超时内完成）估计，未重新实测。

## 六、留档与 commit 纪律

沿 V6：每步 `docs/validation/newtask-v6/<日期>-<步>.md`；commit 只 add 本步文件；账本 `AGENTS.md` 「当前进度」与执行日志追加；网站报告追加 v11 节；本计划第四节裁决表随用户答复回填、不改写第二节原文。

## 七、补充审查结论（2026-09-26 第二轮 workflow，锚点 `82e3d92`，报告 `artifacts/audit/v6-semantic-vs-native-82e3d92/审查汇总.md`）

**口径**：18 个 opus 审查代理 + 每条 1 个 sonnet 反驳 + 1 个 opus 综合，共 62 个代理、37 分钟、零仿真、零源码改动；收官复核 HEAD 未变、porcelain 为空。判定行：`AUDIT_SUMMARY=DONE confirmed=42 new_tier_only=19 native_vs_new_mismatch=3 native_same=19 not_an_issue=1 unverifiable=0 refuted=0 dup_of_excluded=1`，去重后 28 个独立根因。按 K1：只对 xhard1～4 独有的问题给修法；与原三档同源的只记录。

### 7.1 表 A：新四档独有（`new_tier_only`）——推荐处置

| 编号 | 环境 | 问题一句话 | 推荐处置 | 与现有条目关系 | 待裁决 |
|---|---|---|---|---|---|
| N1 | ButtonUnmaskSwap | 按第二个按钮后机器人静止等交换 18～124 步，子目标仍标「press the second button」 | **修**：新四档在按钮任务后插入「wait until the containers stop moving」子目标（`static` 类），choice 同步；任务链变、需重跑 | 与 F4 同批 | |
| N2 | VideoPlaceButton | xhard3/4 只有 4 台、demo 2 块，额外 before 的候选恒等于 after 台集合，按钮后放台变成原地空转 | **修**：F6 的占用表方案在 4 台下会把 before 侧候选清空，须把 xhard3/4 `targets` 4→5（计划 §三 同步）或改为额外放台落到「非台的桌面点」；推荐前者 | **修正第二部分「一」第 5 项的前提** | 台数 4→5 需你拍板 |
| N3 | VideoPlaceButton | 双块档题面「right/immediately before the button」时序不成立（另一块在中间放了两次） | **修**：新四档 before 模板去掉 right/immediately，只保留「last placed before the button was pressed」 | 与 Q-C 同批 | |
| N4 | VideoPlaceButton | 单块档 ALT 第 3 模板「previously placed after the button」不唯一（额外 after 落在答案块上） | **修**：新四档该模板改为「first placed after the button was pressed」 | 同上 | |
| N5 | VideoPlaceButton/Order | 「put the cube back to its original position at <>」永远没坐标（home 标记被 `_hidden_objects` 隐藏） | **修**：新四档该子目标去掉 `at <>`，或用方块 t0 像素坐标回填；推荐去掉 | 与 F4 同文件 | |
| N6～N8（G1） | PickHighlight / VideoUnmask / ButtonUnmask | 子目标切换帧目标被机械臂遮住，整段 grounded 坐标缺失，并留下 1 帧 `success_NO_OBJECT` mp4 | **修**：并入 F4 的 `process_segmentation` 改造——目标不可见时用同帧 `choice_action.point` 回填并在后续帧重算；新四档打标生效；交付索引剔除 1 帧附属 mp4 | 扩展第二部分「一」第 4 项 | G1 归类冲突（3 条判新档独有、6 条判同源）是否统一按同源只记录 |
| N9 | PickHighlight | 新档去掉「, which is <color>」且按钮 `failure_func` 改为每步重算，V6 计划正文未写 | **只记录**：有 V4 计划依据，补写进本计划 §三 说明 | — | |
| N10 | SwingXtimes | xhard4 第 11 轮写成「11th」，其余为英文单词 | **修**：`SwingXtimes._load_scene` 改用 `subgoal_language._ordinal_word` | 新增第 8 项 | |
| N11 | VideoRepick | xhard4 ep3 实际 12 次交换只有 11 个 static 边界（间歇） | **实施时先定位**：若在 `sequential_task_check` 同步逻辑，修；定位不到则记为已知并在验收判定行加「边界数 = 交换数 + 1」 | 新增第 9 项 | |
| N12 | PickXtimes 等 | 超 1300 步的格子清单与计划不符（xhard2 ep0 1350 步） | **改计划文案**；`scripts/evaluation.py max_steps=1300` 对新档是否放宽 | — | 评估步数上限要不要按档放宽 |
| N13 | PatternLock | `config_xhard4` 注释仍写 25 节点；实际 [21,25] 且分布贴下界 | **修注释**（`src/robomme` 内，P2）；分布不改 | 新增第 10 项 | |
| N14 | MoveCube | xhard4 交付 3 局无 peg_push（0/3/6 选局恰好避开） | **待裁决**：保持 0/3/6 规则，或改为按运动方式分层选局 | — | 选局规则 |
| N15 | StopCube | `motion_segments=5` 配置项是描述值、代码不读 | **改配置注释**（`sampling_config.json` note 字段） | — | |

### 7.2 表 B：新四档与原三档不一致（`native_vs_new_mismatch`）

| 编号 | 环境 | 问题 | 推荐处置 | 待裁决 |
|---|---|---|---|---|
| M1 | VideoRepick | 提前按按钮的失败判定只在首抓后 50～500 步窗口内生效；xhard4 第 5、6 轮在窗口外 | **修（新四档）**：窗口改为随当前轮次滚动，或覆盖到最后一次放下；原三档不动 | |
| M2 | VideoPlaceOrder | 计划写「五档都放回原位」，原三档实际仍放到隐藏 goal_site | **改计划文案**：原三档 `native_random_goal_site` 如实写明，不动原三档 | |
| M3 | ButtonUnmask | 原三档容器请求数静默截断（hard 15→6），新档报错 | **只记录**（原三档自身问题，K1） | |

### 7.3 表 C：与原三档同源（`native_same`，13 组 19 条）——只记录

S1 G1 组坐标缺失（VUS/VPO/BinFill/PickXtimes/MoveCube）；S2 BUS 交换净置换可为恒等；S3 VideoRepick 延迟撤销回原槽；S4 VideoRepick 模板 1「for N times, finally put it down」读法；S5 SwingXtimes 主模板漏「放下」步；S6 BinFill 静态布局序数无对应物；S7 BinFill 抓取判据不分颜色；S8 PickHighlight 「第 k 个」顺序不可见；S9 RouteStick 末 6 帧 online 字段「NO RECORD」；S10 MoveCube 长推前相机看不到方块；S11 MoveCube 成功判据不查方式；S12 InsertPeg 演示/执行段措辞不一致；S13 StopCube 成功容差大于靶盘。全部只写进留档，不修。

### 7.4 可选实跑（全部非必需，报告第五节）

MoveCube peg_push 各 ≤10 局、VideoRepick xhard1～4 各 5～10 局、PickHighlight 原生 ≤3 局脚本策略、ButtonUnmask hard 约 5 局。均只为把单例变成发生率；不做不影响结论。用户已允许三席 `61890467/61890468/62018665`、每格 ≤10 局、不在本机。

### 7.5 对第二部分「一」的修正

- 第 4 项（F4）扩展为：位移刷新 + 遮挡回填（N6～N8），同一处改动。
- 第 5 项（F6/Q-C）前提修正：xhard3/4 台数 4→5 或改额外落点，否则占用表方案无候选（N2）。
- 新增第 8 项 N1（BUS 等待子目标）、第 9 项 N10（序数词）、第 10 项 N11（VideoRepick 边界，先定位）、第 11 项 N13（PatternLock 注释）、第 12 项 M1（VideoRepick 失败窗口）、第 13 项 N3/N4/N5（VPB/VPO 话术与回原位子目标）。
- 纯文档项：N9、N12、N15、M2 改计划或配置注释。

## 八、最终裁决与定稿改动清单（2026-09-26 第三轮，用户逐条拍板；**仍未实施**）

### 8.1 用户裁决原话与落地

| 条目 | 用户原话 | 落地 |
|---|---|---|
| N1 | 「n1 subgoal定为wait 在网页中强调这个问题」 | BUS 新四档加等待子目标；网站说明 |
| N2 | 「n2 同意改为5台 但是需要在正式开始修改文件时候 评估 5个能放下吗」 | xhard3/4 台数 4→5；实施第一步先跑 reset 验证 5 台可放，放不下回报 |
| N3 / N4 | 「n3 不改但是记录下问题 在网页中」「n4 没看懂」→ 后续「vpo vpb同意 且vpb只保留这一句 网站要详细叙述这个问题」 | VPB 新四档题面只留 `…on the target where it was last placed before the button was pressed` / `…first placed after the button was pressed` 各一句，N3/N4 随之消失；网站详细叙述题面口径、台可交换、答案按台实体 |
| N5 | 「n5 不要坐标了」 | VPB/VPO 放回原位模板删 `at <>` |
| N6～N8 | 「n6 78都不改 被遮住 导致无坐标问题 不修复」 | 不修；F4 只做位移刷新，不做遮挡回填 |
| N9 | 「n9 去掉后缀「, which is <color>」」 | 维持新档无后缀；计划补写差异来源 |
| N10 | 「n10 修复 a」 | 共享序数词表 |
| N11 | 「n11 a」 | 先定位根因再修，加判定行「边界数 = 交换数 + 1」 |
| N12 | 「n12 a」 | 改计划清单；新档评估 `max_steps` 按档放宽 |
| N13 | 「n13 a」 | 只改注释 |
| N14 | 「n14 b」 | MoveCube xhard4 按运动方式分层选局，补生成一局 peg_push |
| N15 | 「n15 a」 | 改配置说明文字 |
| VPO | 「vpo没问题」 | 只做 N5 |
| M1 | 「m1 a」 | VideoRepick 新四档失败窗口随轮次滚动 |
| M2 | 「m2 a」 | 改计划文字 |
| M3 | 未点名 | 只记录 |
| S1～S5、S7～S13 | 「不管」 | 只记录 |
| S6 | 「s6 a」 | 只记录 |

### 8.2 定稿改动清单（`src/robomme/`，按 P2 逐项列出；用户下令实施后按此执行）

| # | 文件 / 锚点 | 改什么 | 门控 | 需重抽候选 |
|---|---|---|---|---|
| 1 | `PickHighlight.py::_initialize_episode` | 末块也放下 + 追加末尾按钮任务（F1） | `is_newvalue_difficulty` | PH 是 |
| 2 | `utils/task_goal.py::get_language_goal` PickHighlight 分支 | 两句改为与新任务链一致并修拼写（F1） | 同上 | — |
| 3 | `utils/task_goal.py::get_language_goal` VideoPlaceButton 分支 | 新四档只生成一句：before 用 `last placed before`，after 用 `first placed after` | 同上 | — |
| 4 | `ButtonUnmaskSwap.py` 配置 `positions.buttons[*].name`、`button_order`、`_initialize_episode` 的 `button_left/right` 赋值与任务链 `solve`/`segment` | 命名对齐机器人坐标系（左 = +y），建构顺序与位置不变（F3） | 全档改名；若名称入 HDF5 则门控 | — |
| 5 | `ButtonUnmaskSwap.py::_initialize_episode` 任务链 | 第二按钮后插入 `wait for the containers to finish swapping` 子目标（N1），`func` 用交换时间表结束判定，choice 标签 `wait` | 同上 | BUS 是 |
| 6 | `utils/segmentation_utils.py::process_segmentation` + BUS 给 `spawned_bins` 打标 `_robomme_refresh_on_move_px=8` | 子目标未切换但目标中心位移 > 8 px 时重算（F4）；**不做遮挡回填** | 按 actor 打标 | — |
| 7 | `VideoPlaceButton.py::_initialize_episode`（V6 分支）+ `config_xhard3/4` `targets` 4→5 + `sampling_config.json` 同步 | 占用表抽额外台（F6/N2）；before 答案 = 按钮前最后一次放置（Q-C）；`_xhard_pick_place` 回原位模板删 `at <>`（N5） | V6 分支 | VPB 是 |
| 8 | `utils/xhard_home_site.py` 新增 `validate_place_sequence` | 放置序列占用守卫，冲突抛 `SceneGenerationError` | V6 调用 | — |
| 9 | `VideoPlaceOrder.py::_xhard_pick_place` | 回原位模板删 `at <>`（N5） | V6 分支 | VPO 否（文本不入 spec；若入则是） |
| 10 | `SwingXtimes.py::_load_scene` | 序数改用 `subgoal_language._ordinal_word`（N10） | 仅 N>10 触发 | — |
| 11 | `VideoRepick.py::_initialize_episode` 抓放任务 `failure_func` 的 `timewindow(max_steps=…)` | 新四档窗口随轮次滚动到最后一次放下（M1） | `is_newvalue_difficulty` | — |
| 12 | `VideoRepick.py` / `utils/subgoal_evaluate_func.py::sequential_task_check` | N11 先定位「12 次交换 11 个边界」根因再修 | 待定位 | 视修法 |
| 13 | `InsertPeg.py::_initialize_episode` `if xhard:` 分支 | near/far 改欧氏距离（D6） | xhard 分支 | — |
| 14 | `PatternLock.py::config_xhard4` 上方注释与 `XHARD_DECISION` 注释 | 25 → [21,25]（N13） | 注释 | — |

非 `src/robomme/` 改动：`scripts/configs/newtask-v6/sampling_config.json`（BUS 按钮名、VPB 台数、StopCube `motion_segments` 说明 N15）；`scripts/evaluation.py` 新档 `max_steps` 按档取值（N12）；`scripts/parity/v5_generation.py` MoveCube xhard4 选局按 `way_idx` 分层（N14）；本计划 §三/§四 文案（N9、N12、M2）；网站 `v6_site_catalog.py`（N1 等待段说明、VPB 单句题面与台交换说明、N3 历史说明、已知不修项列表）。

### 8.3 与原三档同源、只记录不修的清单（网站与留档披露）

F2、F5、D3、D7、N6～N8、S1～S13、M3。网站「已知问题」页按环境列出，注明「原三档同样存在，本轮不修」。

### 8.4 实施顺序（等用户下令）

1. VPB 5 台可放性 reset 验证（xhard3/4 各 ≥20 次 reset，只读 spec，不生成轨迹）→ 放不下先回报。
2. 按 8.2 逐项改 → 定向单测 + G1～G3（原三档 48 次 reset 零漂移）→ commit/push → 集群侧同步。
3. 三席起 S4 管道 `v6-02`（xhard1+2 / xhard3 / xhard4）→ `verify_s4.py` → 第二节各判定行 + `VPB_SEMANTIC` / `VPO_SEMANTIC` / `BUS_WAIT_SUBGOAL` / `VR_BOUNDARY` 判定行。
4. 网站 site-v11 → Playwright 全量 → 留档 → commit/push。
