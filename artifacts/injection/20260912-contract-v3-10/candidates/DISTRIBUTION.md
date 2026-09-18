# 候选分布

运行：`20260912-contract-v3-10`，共 3400 条候选。

## 取值域、分配与结果

统计表覆盖每组全部候选；连续量按每 100 条独立 block 分层，位置重试和整体布局重试的计数单位不同。
候选能通过静态筛查不等于可完成任务，实跑结果见下一阶段的结果表。

<!-- AUTO:EVENT_TABLES BEGIN -->
### BinFill / easy（300 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `dynamic`（方块分批出现还是开局全在） | True / False | 配额 50/50 | True:150 False:150 |
| `colors_present`（场上有哪些颜色） | 红蓝绿里取 1 种 | 配额 | red:102 blue:99 green:99 |
| `spawn_total`（生成几块） | 4～6 | 配额 | 4:102 5:99 6:99 |
| `initialize_color_order`（颜色创建顺序） | 蓝红绿 6 种排列 | 配额 | blue-red-green:51 blue-green-red:51 red-blue-green:51 red-green-blue:51 green-blue-red:48 green-red-blue:48 |
| `spawn_count[颜色]`（每色生成几块） | 每色至少 max(目标,1)，余量随机摊 | `rng_ep` 逐条随机（耦合） | blue=6:35 red=4:35 red=5:35 green=4:34 blue=4:33 green=5:33 green=6:32 red=6:32 blue=5:31（共 300 个颜色项） |
| 方块生成顺序 | (颜色, 序号) 的随机排列 | `rng_ep.permutation` | 生成序首块的颜色 red:102 blue:99 green:99 |
| `button_xy`（按钮中心） | x∈[-0.25,-0.15] y∈[-0.2,0.2] | 分层 | x 10 箱各 30，实测 [-0.2499, -0.1505]；y 10 箱各 30，实测 [-0.2000, 0.1981] |
| `board.xy`、`board.yaw_deg`（孔板） | x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°] | 分层 | x 10 箱各 30，实测 [-0.0498, 0.1499]；y 10 箱各 30，实测 [-0.1995, 0.1999]；yaw 10 箱各 30，实测 [-19.97, 19.96] |
| `cubes[i].xy`、`yaw_rad`（每块方块） | x∈[-0.28,0.08] y∈[-0.23,0.23]，yaw 0～2π | 第 0 块首次尝试分层；其余块粗箱轮转；被拒整域重抽 | 采样输入 cube_x 10 箱各 30、cube_y 10 箱各 30、cube_yaw 10 箱各 30；实际位置 x 箱计数 167,109,126,133,143,163,180,157,155,164，实测 [-0.2800, 0.0798]；y 箱计数 206,149,153,131,133,127,123,133,149,193，实测 [-0.2300, 0.2298]；yaw 实测 [0.00, 6.28]（共 1497 块） |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `put_in_color` 目标色种数 | 1 | 配额 | 1:300 |
| `target_pool`（要投入的颜色子集） | 场上颜色的子集 | 合法候选内平衡 | red:102 blue:99 green:99；未覆盖 无 |
| `put_in_total`（投入几块） | 1～3 | 配额 | 1:102 2:99 3:99 |
| `target_count[颜色]`（每色投几块） | 单色直接给总数；多目标色每色先各 1，余量逐个随机分（heldout 规则，不允许 0） | `rng_ep` 逐条随机（耦合） | green=2:43 blue=1:42 red=1:39 red=3:38 green=3:35 blue=2:31 blue=3:26 red=2:25 green=1:21（共 300 个颜色项） |
| `actions`（抓哪块） | 按颜色创建顺序遍历，每色取生成列表最前 `target_count` 块 | 推出 | 推出：被抓方块的色内序号 0:105 1:125 2:126 3:133 4:77 5:31（共 597 个动作） |

### BinFill / medium（300 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `dynamic`（方块分批出现还是开局全在） | True / False | 配额 50/50 | True:150 False:150 |
| `colors_present`（场上有哪些颜色） | 红蓝绿里取 2 种 | 配额 | red+blue:102 red+green:99 blue+green:99 |
| `spawn_total`（生成几块） | 6～8 | 配额 | 6:102 7:99 8:99 |
| `initialize_color_order`（颜色创建顺序） | 蓝红绿 6 种排列 | 配额 | blue-red-green:51 blue-green-red:51 red-blue-green:51 red-green-blue:51 green-blue-red:48 green-red-blue:48 |
| `spawn_count[颜色]`（每色生成几块） | 每色至少 max(目标,1)，余量随机摊 | `rng_ep` 逐条随机（耦合） | green=3:61 blue=3:57 red=3:55 blue=4:50 green=4:50 red=4:43 red=2:40 red=5:40 blue=2:37 green=2:36 green=5:35 blue=5:33 …另 8 类略（共 600 个颜色项） |
| 方块生成顺序 | (颜色, 序号) 的随机排列 | `rng_ep.permutation` | 生成序首块的颜色 red:97 blue:110 green:93 |
| `button_xy`（按钮中心） | x∈[-0.25,-0.15] y∈[-0.2,0.2] | 分层 | x 10 箱各 30，实测 [-0.2499, -0.1505]；y 10 箱各 30，实测 [-0.1986, 0.1984] |
| `board.xy`、`board.yaw_deg`（孔板） | x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°] | 分层 | x 10 箱各 30，实测 [-0.0500, 0.1485]；y 10 箱各 30，实测 [-0.1970, 0.1992]；yaw 10 箱各 30，实测 [-19.87, 19.93] |
| `cubes[i].xy`、`yaw_rad`（每块方块） | x∈[-0.28,0.08] y∈[-0.23,0.23]，yaw 0～2π | 第 0 块首次尝试分层；其余块粗箱轮转；被拒整域重抽 | 采样输入 cube_x 10 箱各 30、cube_y 10 箱各 30、cube_yaw 10 箱各 30；实际位置 x 箱计数 257,148,198,171,217,215,244,220,203,224，实测 [-0.2800, 0.0799]；y 箱计数 312,190,199,178,191,165,166,184,227,285，实测 [-0.2299, 0.2297]；yaw 实测 [0.00, 6.28]（共 2097 块） |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `put_in_color` 目标色种数 | 1/2 | 配额 | 1:150 2:150 |
| `target_pool`（要投入的颜色子集） | 场上颜色的子集 | 合法候选内平衡 | red+blue:53 blue+green:52 green:51 red:50 blue:49 red+green:45；未覆盖 无 |
| `put_in_total`（投入几块） | 2～4 | 配额 | 2:102 3:99 4:99 |
| `target_count[颜色]`（每色投几块） | 单色直接给总数；多目标色每色先各 1，余量逐个随机分（heldout 规则，不允许 0） | `rng_ep` 逐条随机（耦合） | red=1:64 green=1:61 blue=1:58 blue=2:57 red=0:53 green=0:50 blue=0:47 green=2:44 red=2:39 red=3:30 blue=3:22 green=3:22 …另 3 类略（共 600 个颜色项） |
| `actions`（抓哪块） | 按颜色创建顺序遍历，每色取生成列表最前 `target_count` 块 | 推出 | 推出：被抓方块的色内序号 0:255 1:233 2:198 3:129 4:68 5:13 6:1（共 897 个动作） |

### BinFill / hard（300 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `dynamic`（方块分批出现还是开局全在） | True / False | 配额 50/50 | True:150 False:150 |
| `colors_present`（场上有哪些颜色） | 红蓝绿里取 3 种 | 配额 | red+blue+green:300 |
| `spawn_total`（生成几块） | 8～10 | 配额 | 8:102 9:99 10:99 |
| `initialize_color_order`（颜色创建顺序） | 蓝红绿 6 种排列 | 配额 | blue-red-green:51 blue-green-red:51 red-blue-green:51 red-green-blue:51 green-blue-red:48 green-red-blue:48 |
| `spawn_count[颜色]`（每色生成几块） | 每色至少 max(目标,1)，余量随机摊 | `rng_ep` 逐条随机（耦合） | blue=3:104 red=3:101 green=3:98 green=2:81 blue=2:76 red=4:73 red=2:69 blue=4:59 green=4:58 green=1:34 red=5:29 blue=1:28 …另 7 类略（共 900 个颜色项） |
| 方块生成顺序 | (颜色, 序号) 的随机排列 | `rng_ep.permutation` | 生成序首块的颜色 red:93 blue:98 green:109 |
| `button_xy`（按钮中心） | x∈[-0.25,-0.15] y∈[-0.2,0.2] | 分层 | x 10 箱各 30，实测 [-0.2500, -0.1504]；y 10 箱各 30，实测 [-0.1974, 0.1992] |
| `board.xy`、`board.yaw_deg`（孔板） | x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°] | 分层 | x 10 箱各 30，实测 [-0.0496, 0.1492]；y 10 箱各 30，实测 [-0.1988, 0.1996]；yaw 10 箱各 30，实测 [-19.90, 19.95] |
| `cubes[i].xy`、`yaw_rad`（每块方块） | x∈[-0.28,0.08] y∈[-0.23,0.23]，yaw 0～2π | 第 0 块首次尝试分层；其余块粗箱轮转；被拒整域重抽 | 采样输入 cube_x 10 箱各 30、cube_y 10 箱各 30、cube_yaw 10 箱各 30；实际位置 x 箱计数 309,231,212,229,265,299,306,276,259,311，实测 [-0.2799, 0.0800]；y 箱计数 397,233,259,218,233,222,248,248,271,368，实测 [-0.2299, 0.2298]；yaw 实测 [0.00, 6.28]（共 2697 块） |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `put_in_color` 目标色种数 | 2/3 | 配额 | 2:150 3:150 |
| `target_pool`（要投入的颜色子集） | 场上颜色的子集 | 合法候选内平衡 | red+blue+green:150 red+blue:51 blue+green:50 red+green:49；未覆盖 无 |
| `put_in_total`（投入几块） | 3～5 | 配额 | 3:102 4:99 5:99 |
| `target_count[颜色]`（每色投几块） | 单色直接给总数；多目标色每色先各 1，余量逐个随机分（heldout 规则，不允许 0） | `rng_ep` 逐条随机（耦合） | red=1:137 green=1:135 blue=1:129 blue=2:93 green=2:88 red=2:80 green=0:51 red=0:50 blue=0:49 red=3:30 blue=3:24 green=3:24 …另 3 类略（共 900 个颜色项） |
| `actions`（抓哪块） | 按颜色创建顺序遍历，每色取生成列表最前 `target_count` 块 | 推出 | 推出：被抓方块的色内序号 0:418 1:368 2:258 3:114 4:30 5:9（共 1197 个动作） |

### RouteStick / easy（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `rotation_deg`（整排绕世界原点转） | [-30°, 30°] | 分层 | 10 箱各 20，实测 [-29.93, 29.93] |
| `obstacle_rgb[4]`（4 根障碍柱颜色） | 每根一个随机 RGB，各通道 [0,1) | `rng_ep` 随机（只影响观感） | 通道值 箱计数 244,250,212,246,243,235,229,252,249,240，实测 [0.000, 0.999]（共 2400 个通道值） |
| 9 个格点位置 | 由 `rotation_deg` 唯一确定 | 推出 | 推出：1800 个格点 x 实测 [-0.2264, 0.0531]，y 实测 [-0.2973, 0.2973] |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `L`（走几段） | 2～3 | 配额 | 2:100 3:100 |
| 起点 `nodes[0]` | 0/2/4/6/8 | 配额各 20 | 0:40 2:40 4:40 6:40 8:40 |
| 每段去哪（有向边） | 线性邻接 ±1；不许回退：剔除上一步，端点被迫掉头 | 合法候选内平衡 | 0→2:85 8→6:80 2→4:62 6→4:62 2→0:56 6→8:56 4→6:50 4→2:49（共 500 段）；未覆盖 无 |
| 每段绕行方向 `directions` | clockwise / counterclockwise | 合法候选内平衡 | clockwise:250 counterclockwise:250（共 500 段） |

### RouteStick / medium（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `rotation_deg`（整排绕世界原点转） | [-30°, 30°] | 分层 | 10 箱各 20，实测 [-29.68, 29.81] |
| `obstacle_rgb[4]`（4 根障碍柱颜色） | 每根一个随机 RGB，各通道 [0,1) | `rng_ep` 随机（只影响观感） | 通道值 箱计数 248,217,236,228,255,231,264,249,224,248，实测 [0.001, 1.000]（共 2400 个通道值） |
| 9 个格点位置 | 由 `rotation_deg` 唯一确定 | 推出 | 推出：1800 个格点 x 实测 [-0.2259, 0.0524]，y 实测 [-0.2973, 0.2973] |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `L`（走几段） | 4～5 | 配额 | 4:100 5:100 |
| 起点 `nodes[0]` | 0/2/4/6/8 | 配额各 20 | 0:40 2:40 4:40 6:40 8:40 |
| 每段去哪（有向边） | 线性邻接 ±1；不许回退：剔除上一步，端点被迫掉头 | 合法候选内平衡 | 0→2:120 8→6:120 2→4:113 2→0:111 4→2:110 4→6:110 6→4:108 6→8:108（共 900 段）；未覆盖 无 |
| 每段绕行方向 `directions` | clockwise / counterclockwise | 合法候选内平衡 | clockwise:450 counterclockwise:450（共 900 段） |

### RouteStick / hard（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `rotation_deg`（整排绕世界原点转） | [-30°, 30°] | 分层 | 10 箱各 20，实测 [-29.93, 29.74] |
| `obstacle_rgb[4]`（4 根障碍柱颜色） | 每根一个随机 RGB，各通道 [0,1) | `rng_ep` 随机（只影响观感） | 通道值 箱计数 244,246,207,243,246,230,240,260,241,243，实测 [0.002, 0.999]（共 2400 个通道值） |
| 9 个格点位置 | 由 `rotation_deg` 唯一确定 | 推出 | 推出：1800 个格点 x 实测 [-0.2264, 0.0531]，y 实测 [-0.2973, 0.2973] |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `L`（走几段） | 4～7 | 配额 | 4:50 5:50 6:50 7:50 |
| 起点 `nodes[0]` | 0/2/4/6/8 | 配额各 20 | 0:40 2:40 4:40 6:40 8:40 |
| 每段去哪（有向边） | 线性邻接 ±1；允许回退 | 合法候选内平衡 | 0→2:150 8→6:150 6→4:141 6→8:141 2→0:130 4→6:130 2→4:129 4→2:129（共 1100 段）；未覆盖 无 |
| 每段绕行方向 `directions` | clockwise / counterclockwise | 合法候选内平衡 | clockwise:550 counterclockwise:550（共 1100 段） |

### RouteStick / xhard（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `rotation_deg`（整排绕世界原点转） | [-30°, 30°] | 分层 | 10 箱各 20，实测 [-29.71, 29.50] |
| `obstacle_rgb[4]`（4 根障碍柱颜色） | 每根一个随机 RGB，各通道 [0,1) | `rng_ep` 随机（只影响观感） | 通道值 箱计数 225,252,230,256,237,272,239,233,236,220，实测 [0.000, 0.999]（共 2400 个通道值） |
| 9 个格点位置 | 由 `rotation_deg` 唯一确定 | 推出 | 推出：1800 个格点 x 实测 [-0.2256, 0.0519]，y 实测 [-0.2973, 0.2973] |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `L`（走几段） | 8～10 | 配额 | 8:68 9:66 10:66 |
| 起点 `nodes[0]` | 0/2/4/6/8 | 配额各 20 | 0:40 2:40 4:40 6:40 8:40 |
| 每段去哪（有向边） | 线性邻接 ±1；允许回退 | 合法候选内平衡 | 8→6:243 6→4:228 6→8:227 0→2:223 4→2:221 2→0:219 4→6:219 2→4:218（共 1798 段）；未覆盖 无 |
| 每段绕行方向 `directions` | clockwise / counterclockwise | 合法候选内平衡 | clockwise:899 counterclockwise:899（共 1798 段） |

### VideoUnmaskSwap / easy（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `layout_type`（锚点布局） | 三角／直线 | 配额 | region3_tri:100 region3_line:100 |
| `selected`（藏物容器排序） | 前三个容器的 6 种排列 | 配额 | 0-1-2:34 0-2-1:34 1-0-2:34 1-2-0:34 2-0-1:32 2-1-0:32 |
| `color_order`（藏物颜色顺序） | 红绿蓝 6 种排列 | 配额 | red-green-blue:34 red-blue-green:34 green-red-blue:34 green-blue-red:34 blue-red-green:32 blue-green-red:32 |
| `theta_rad`（整组绕原点转） | [0, 180] 弧度（原单位就是弧度，不是度） | 分层；被拒同粗箱重抽 | 10 箱各 20，实测 [0.79, 179.21] |
| `bins[i].xy`、`yaw_deg`（每个容器） | 锚点旋转后各偏移 ≤ 0.0425，yaw 0～90° | 分层；被拒同粗箱重抽 | bin_0：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0425, 0.0425]，yaw 实测 [0.58, 89.57]；bin_1：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0424, 0.0424]，yaw 实测 [0.16, 89.87]；bin_2：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0425, 0.0418]，yaw 实测 [0.05, 89.79] |
| `hidden`（颜色→容器） | 由 `selected` + `color_order` 算出 | 推出 | 推出：red→bin_0:73 blue→bin_2:71 green→bin_1:70 green→bin_2:67 blue→bin_1:65 red→bin_1:65 blue→bin_0:64 green→bin_0:63 red→bin_2:62（共 600 项）；未覆盖 无 |
| `empty`（空容器） | 不在 `selected` 里的容器 | 推出 | 推出：无:200 |
| `collision.candidates_used`（冻结用了第几个候选） | 1～256 | 几何／碰撞被拒后重抽的落地结果 | 1:190 2:7 3:1 4:1 5:1 |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `n_swaps`（交换几次） | 1～2 | 配额 | 1:100 2:100 |
| `n_picks`（视频后抓几个） | 1～2 | 配额 | 1:100 2:100 |
| 前两个发起者 `swap_initiators[:2]` | 3 取 2 的 6 种有序对（原代码把藏物序号当生成序号用，照抄） | 配额 | bin_0-bin_1:34 bin_0-bin_2:34 bin_1-bin_0:34 bin_1-bin_2:34 bin_2-bin_0:32 bin_2-bin_1:32 |
| 第三个发起者 `swap_initiators[2]` | 其余生成序号 | 合法候选内平衡 | bin_2:68 bin_0:66 bin_1:66；未覆盖 无 |
| `pick_order`（视频后抓取顺序） | `selected` 的前 `n_picks` 个 | 推出 | 推出：bin_2:36 bin_0:33 bin_1:31 bin_1→bin_0:20 bin_0→bin_2:19 bin_1→bin_2:17 bin_0→bin_1:16 bin_2→bin_1:16 bin_2→bin_0:12 |
| `swap_pairs[k].partner`（交换搭档） | 交换开始时的水平最近邻，等距取序号小者 | 推出（执行时核验，不符即失败） | 推出：bin_0→bin_2:72 bin_1→bin_2:65 bin_2→bin_0:56 bin_2→bin_1:44 bin_0→bin_1:33 bin_1→bin_0:30（共 300 次交换）；未覆盖 无 |

### VideoUnmaskSwap / medium（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `layout_type`（锚点布局） | 四点（固定） | 常量 | region4:200 |
| `selected`（藏物容器排序） | 前三个容器的 6 种排列 | 配额 | 0-1-2:34 0-2-1:34 1-0-2:34 1-2-0:34 2-0-1:32 2-1-0:32 |
| `color_order`（藏物颜色顺序） | 红绿蓝 6 种排列 | 配额 | red-green-blue:34 red-blue-green:34 green-red-blue:34 green-blue-red:34 blue-red-green:32 blue-green-red:32 |
| `theta_rad`（整组绕原点转） | [0, 180] 弧度（原单位就是弧度，不是度） | 分层；被拒同粗箱重抽 | 10 箱各 20，实测 [0.91, 179.79] |
| `bins[i].xy`、`yaw_deg`（每个容器） | 锚点旋转后各偏移 ≤ 0.0425，yaw 0～90° | 分层；被拒同粗箱重抽 | bin_0：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0424, 0.0423]，yaw 实测 [0.80, 89.22]；bin_1：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0422, 0.0420]，yaw 实测 [0.33, 89.75]；bin_2：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0425, 0.0424]，yaw 实测 [0.24, 89.65]；bin_3：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0421, 0.0424]，yaw 实测 [0.84, 89.50] |
| `hidden`（颜色→容器） | 由 `selected` + `color_order` 算出 | 推出 | 推出：blue→bin_2:78 red→bin_0:74 green→bin_0:73 blue→bin_1:69 green→bin_1:69 red→bin_2:64 red→bin_1:62 green→bin_2:58 blue→bin_0:53（共 600 项）；未覆盖 无 |
| `empty`（空容器） | 不在 `selected` 里的容器 | 推出 | 推出：bin_3:200 |
| `collision.candidates_used`（冻结用了第几个候选） | 1～256 | 几何／碰撞被拒后重抽的落地结果 | 1:191 2:7 3:2 |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `n_swaps`（交换几次） | 1～2 | 配额 | 1:100 2:100 |
| `n_picks`（视频后抓几个） | 1 | 配额 | 1:200 |
| 前两个发起者 `swap_initiators[:2]` | 3 取 2 的 6 种有序对（原代码把藏物序号当生成序号用，照抄） | 配额 | bin_0-bin_1:34 bin_0-bin_2:34 bin_1-bin_0:34 bin_1-bin_2:34 bin_2-bin_0:32 bin_2-bin_1:32 |
| 第三个发起者 `swap_initiators[2]` | 其余生成序号 | 合法候选内平衡 | bin_0:51 bin_1:50 bin_3:50 bin_2:49；未覆盖 无 |
| `pick_order`（视频后抓取顺序） | `selected` 的前 `n_picks` 个 | 推出 | 推出：bin_0:68 bin_1:68 bin_2:64 |
| `swap_pairs[k].partner`（交换搭档） | 交换开始时的水平最近邻，等距取序号小者 | 推出（执行时核验，不符即失败） | 推出：bin_0→bin_3:84 bin_2→bin_1:84 bin_1→bin_2:83 bin_1→bin_0:14 bin_0→bin_1:12 bin_2→bin_3:10 bin_1→bin_3:5 bin_2→bin_0:5 bin_0→bin_2:3（共 300 次交换）；未覆盖 bin_3→bin_0、bin_3→bin_1、bin_3→bin_2 |

### VideoUnmaskSwap / hard（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `layout_type`（锚点布局） | 四点（固定） | 常量 | region4:200 |
| `selected`（藏物容器排序） | 前三个容器的 6 种排列 | 配额 | 0-1-2:34 0-2-1:34 1-0-2:34 1-2-0:34 2-0-1:32 2-1-0:32 |
| `color_order`（藏物颜色顺序） | 红绿蓝 6 种排列 | 配额 | red-green-blue:34 red-blue-green:34 green-red-blue:34 green-blue-red:34 blue-red-green:32 blue-green-red:32 |
| `theta_rad`（整组绕原点转） | [0, 180] 弧度（原单位就是弧度，不是度） | 分层；被拒同粗箱重抽 | 10 箱各 20，实测 [0.47, 178.68] |
| `bins[i].xy`、`yaw_deg`（每个容器） | 锚点旋转后各偏移 ≤ 0.0425，yaw 0～90° | 分层；被拒同粗箱重抽 | bin_0：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0424, 0.0422]，yaw 实测 [0.17, 89.81]；bin_1：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0424, 0.0422]，yaw 实测 [0.08, 89.67]；bin_2：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0423, 0.0421]，yaw 实测 [0.62, 89.73]；bin_3：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0422, 0.0425]，yaw 实测 [0.04, 89.71] |
| `hidden`（颜色→容器） | 由 `selected` + `color_order` 算出 | 推出 | 推出：green→bin_0:76 blue→bin_2:73 red→bin_1:70 red→bin_2:68 blue→bin_1:65 green→bin_1:65 blue→bin_0:62 red→bin_0:62 green→bin_2:59（共 600 项）；未覆盖 无 |
| `empty`（空容器） | 不在 `selected` 里的容器 | 推出 | 推出：bin_3:200 |
| `collision.candidates_used`（冻结用了第几个候选） | 1～256 | 几何／碰撞被拒后重抽的落地结果 | 1:190 2:8 3:2 |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `n_swaps`（交换几次） | 2～3 | 配额 | 2:100 3:100 |
| `n_picks`（视频后抓几个） | 2 | 配额 | 2:200 |
| 前两个发起者 `swap_initiators[:2]` | 3 取 2 的 6 种有序对（原代码把藏物序号当生成序号用，照抄） | 配额 | bin_0-bin_1:34 bin_0-bin_2:34 bin_1-bin_0:34 bin_1-bin_2:34 bin_2-bin_0:32 bin_2-bin_1:32 |
| 第三个发起者 `swap_initiators[2]` | 其余生成序号 | 合法候选内平衡 | bin_0:50 bin_1:50 bin_2:50 bin_3:50；未覆盖 无 |
| `pick_order`（视频后抓取顺序） | `selected` 的前 `n_picks` 个 | 推出 | 推出：bin_0→bin_1:34 bin_0→bin_2:34 bin_1→bin_0:34 bin_1→bin_2:34 bin_2→bin_0:32 bin_2→bin_1:32 |
| `swap_pairs[k].partner`（交换搭档） | 交换开始时的水平最近邻，等距取序号小者 | 推出（执行时核验，不符即失败） | 推出：bin_2→bin_1:134 bin_0→bin_3:121 bin_1→bin_2:121 bin_1→bin_0:26 bin_0→bin_1:24 bin_3→bin_0:22 bin_2→bin_3:17 bin_0→bin_2:16 bin_2→bin_0:9 bin_1→bin_3:7 bin_3→bin_2:2 bin_3→bin_1:1（共 500 次交换）；未覆盖 无 |

### VideoUnmaskSwap / xhard（200 条）

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `layout_type`（锚点布局） | 四点（固定） | 常量 | region4:200 |
| `selected`（藏物容器排序） | 前三个容器的 6 种排列 | 配额 | 0-1-2:34 0-2-1:34 1-0-2:34 1-2-0:34 2-0-1:32 2-1-0:32 |
| `color_order`（藏物颜色顺序） | 红绿蓝 6 种排列 | 配额 | red-green-blue:34 red-blue-green:34 green-red-blue:34 green-blue-red:34 blue-red-green:32 blue-green-red:32 |
| `theta_rad`（整组绕原点转） | [0, 180] 弧度（原单位就是弧度，不是度） | 分层；被拒同粗箱重抽 | 10 箱各 20，实测 [0.62, 179.85] |
| `bins[i].xy`、`yaw_deg`（每个容器） | 锚点旋转后各偏移 ≤ 0.0425，yaw 0～90° | 分层；被拒同粗箱重抽 | bin_0：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0420, 0.0423]，yaw 实测 [0.49, 89.57]；bin_1：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0420, 0.0424]，yaw 实测 [0.14, 89.99]；bin_2：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0424, 0.0424]，yaw 实测 [0.14, 89.93]；bin_3：dx/dy/yaw 各 10 箱各 20，偏移实测 [-0.0422, 0.0423]，yaw 实测 [0.45, 89.88] |
| `hidden`（颜色→容器） | 由 `selected` + `color_order` 算出 | 推出 | 推出：green→bin_1:75 red→bin_0:72 blue→bin_2:69 red→bin_2:68 blue→bin_0:66 blue→bin_1:65 green→bin_2:63 green→bin_0:62 red→bin_1:60（共 600 项）；未覆盖 无 |
| `empty`（空容器） | 不在 `selected` 里的容器 | 推出 | 推出：bin_3:200 |
| `collision.candidates_used`（冻结用了第几个候选） | 1～256 | 几何／碰撞被拒后重抽的落地结果 | 1:185 2:12 3:2 4:1 |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `n_swaps`（交换几次） | 4～5 | 配额 | 4:100 5:100 |
| `n_picks`（视频后抓几个） | 2 | 配额 | 2:200 |
| 前两个发起者 `swap_initiators[:2]` | 3 取 2 的 6 种有序对（原代码把藏物序号当生成序号用，照抄） | 配额 | bin_0-bin_1:34 bin_0-bin_2:34 bin_1-bin_0:34 bin_1-bin_2:34 bin_2-bin_0:32 bin_2-bin_1:32 |
| 第三个发起者 `swap_initiators[2]` | 其余生成序号 | 合法候选内平衡 | bin_3:51 bin_1:50 bin_2:50 bin_0:49；未覆盖 无 |
| `pick_order`（视频后抓取顺序） | `selected` 的前 `n_picks` 个 | 推出 | 推出：bin_0→bin_1:34 bin_0→bin_2:34 bin_1→bin_0:34 bin_1→bin_2:34 bin_2→bin_0:32 bin_2→bin_1:32 |
| `swap_pairs[k].partner`（交换搭档） | 交换开始时的水平最近邻，等距取序号小者；第 k 次发起者 = swap_initiators[k mod 3]（4～5 次时循环沿用 3 个发起者） | 推出（执行时核验，不符即失败） | 推出：bin_1→bin_2:230 bin_2→bin_1:221 bin_0→bin_3:199 bin_0→bin_1:49 bin_1→bin_0:44 bin_3→bin_0:43 bin_2→bin_0:33 bin_0→bin_2:32 bin_2→bin_3:27 bin_1→bin_3:14 bin_3→bin_2:6 bin_3→bin_1:2（共 900 次交换）；未覆盖 无 |

### VideoRepick / easy（300 条）

> 注：VideoRepick 的三块方块在规格里 `object_id` 是 `bin_0/1/2`（沿用源码命名），下表照此写。

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `layout_type`（锚点布局） | 三角／直线 | 配额 | region3_tri:150 region3_line:150 |
| `color`（三块统一颜色） | 红／蓝／绿 | 配额 | red:102 blue:99 green:99 |
| `theta_rad`、`button_xy` | [0, 180] 弧度；x∈[-0.25,-0.15] y∈[-0.05,0.05] | 分层（θ 被拒同粗箱重抽，按钮不参与重抽） | θ 10 箱各 30，实测 [0.52, 179.76]；按钮 x 10 箱各 30，实测 [-0.2498, -0.1506]；按钮 y 10 箱各 30，实测 [-0.0497, 0.0496] |
| `cubes[i].xy`、`yaw_rad`（每块方块） | 锚点旋转后各偏移 ≤ 0.0500，yaw 0～2π | 分层；方块间距 < 0.02、压按钮或碰撞被拒后同粗箱重抽 | bin_0：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0499, 0.0498]，yaw 实测 [0.02, 6.28]；bin_1：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0496, 0.0500]，yaw 实测 [0.01, 6.28]；bin_2：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0497, 0.0499]，yaw 实测 [0.00, 6.25] |
| `collision.candidates_used`（冻结用了第几个候选） | 1～256 | 几何／碰撞被拒后重抽的落地结果 | 1:174 2:64 3:27 4:10 5:7 6:7 7:3 8:3 9:1 10:1 11:1 15:1 …另 1 类略 |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `n_swaps`（交换几次） | 1～2 | 配额 | 1:150 2:150 |
| `num_repeats`（重复抓放次数） | 1～3 | 配额 | 1:102 2:99 3:99 |
| `target`（目标方块） | 三块之一 | 配额 | bin_0:102 bin_1:99 bin_2:99 |
| 后续发起者顺序 `tail` | 另外两块的 2 种排列 | 配额 | bin_0-bin_1:49 bin_0-bin_2:49 bin_1-bin_0:50 bin_1-bin_2:52 bin_2-bin_0:50 bin_2-bin_1:50 |
| `swap_pairs[k].partner`（交换搭档） | 交换开始时的水平最近邻，等距取序号小者 | 推出（执行时核验，不符即失败） | 推出：bin_0→bin_2:108 bin_1→bin_2:99 bin_2→bin_0:77 bin_2→bin_1:63 bin_1→bin_0:57 bin_0→bin_1:46（共 450 次交换）；未覆盖 无 |

### VideoRepick / medium（300 条）

> 注：VideoRepick 的三块方块在规格里 `object_id` 是 `bin_0/1/2`（沿用源码命名），下表照此写。

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `layout_type`（锚点布局） | 三角／直线 | 配额 | region3_tri:150 region3_line:150 |
| `color`（三块统一颜色） | 红／蓝／绿 | 配额 | red:102 blue:99 green:99 |
| `theta_rad`、`button_xy` | [0, 180] 弧度；x∈[-0.25,-0.15] y∈[-0.05,0.05] | 分层（θ 被拒同粗箱重抽，按钮不参与重抽） | θ 10 箱各 30，实测 [0.06, 178.87]；按钮 x 10 箱各 30，实测 [-0.2499, -0.1505]；按钮 y 10 箱各 30，实测 [-0.0496, 0.0497] |
| `cubes[i].xy`、`yaw_rad`（每块方块） | 锚点旋转后各偏移 ≤ 0.0500，yaw 0～2π | 分层；方块间距 < 0.02、压按钮或碰撞被拒后同粗箱重抽 | bin_0：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0494, 0.0498]，yaw 实测 [0.01, 6.26]；bin_1：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0499, 0.0500]，yaw 实测 [0.01, 6.26]；bin_2：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0496, 0.0500]，yaw 实测 [0.02, 6.28] |
| `collision.candidates_used`（冻结用了第几个候选） | 1～256 | 几何／碰撞被拒后重抽的落地结果 | 1:167 2:73 3:23 4:13 5:5 6:7 7:3 8:3 9:2 10:1 11:1 33:1 …另 1 类略 |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `n_swaps`（交换几次） | 2～3 | 配额 | 2:150 3:150 |
| `num_repeats`（重复抓放次数） | 1～3 | 配额 | 1:102 2:99 3:99 |
| `target`（目标方块） | 三块之一 | 配额 | bin_0:102 bin_1:99 bin_2:99 |
| 后续发起者顺序 `tail` | 另外两块的 2 种排列 | 配额 | bin_0-bin_1:52 bin_0-bin_2:57 bin_1-bin_0:47 bin_1-bin_2:41 bin_2-bin_0:42 bin_2-bin_1:61 |
| `swap_pairs[k].partner`（交换搭档） | 交换开始时的水平最近邻，等距取序号小者 | 推出（执行时核验，不符即失败） | 推出：bin_1→bin_2:151 bin_0→bin_2:149 bin_2→bin_0:136 bin_2→bin_1:119 bin_0→bin_1:103 bin_1→bin_0:92（共 750 次交换）；未覆盖 无 |

### VideoRepick / xhard（300 条）

> 注：VideoRepick 的三块方块在规格里 `object_id` 是 `bin_0/1/2`（沿用源码命名），下表照此写。

#### 初始化（场景开局是什么样：物体种类、数量、位姿、藏物关系）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `layout_type`（锚点布局） | 三角／直线 | 配额 | region3_tri:150 region3_line:150 |
| `color`（三块统一颜色） | 红／蓝／绿 | 配额 | red:102 blue:99 green:99 |
| `theta_rad`、`button_xy` | [0, 180] 弧度；x∈[-0.25,-0.15] y∈[-0.05,0.05] | 分层（θ 被拒同粗箱重抽，按钮不参与重抽） | θ 10 箱各 30，实测 [0.04, 178.84]；按钮 x 10 箱各 30，实测 [-0.2499, -0.1504]；按钮 y 10 箱各 30，实测 [-0.0497, 0.0499] |
| `cubes[i].xy`、`yaw_rad`（每块方块） | 锚点旋转后各偏移 ≤ 0.0500，yaw 0～2π | 分层；方块间距 < 0.02、压按钮或碰撞被拒后同粗箱重抽 | bin_0：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0496, 0.0497]，yaw 实测 [0.00, 6.28]；bin_1：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0498, 0.0499]，yaw 实测 [0.01, 6.28]；bin_2：dx/dy/yaw 各 10 箱各 30，偏移实测 [-0.0499, 0.0496]，yaw 实测 [0.03, 6.28] |
| `collision.candidates_used`（冻结用了第几个候选） | 1～256 | 几何／碰撞被拒后重抽的落地结果 | 1:182 2:52 3:26 4:17 5:7 6:2 7:4 8:1 9:1 10:2 11:1 14:1 …另 4 类略 |

#### 事件（任务要做什么：投入／抓取／路线／交换的选择）

| 事件 | 取值域 | 分配 | 结果分布 |
|---|---|---|---|
| `n_swaps`（交换几次） | 4～5 | 配额 | 4:150 5:150 |
| `num_repeats`（重复抓放次数） | 1～3 | 配额 | 1:102 2:99 3:99 |
| `target`（目标方块） | 三块之一 | 配额 | bin_0:102 bin_1:99 bin_2:99 |
| 后续发起者顺序 `tail` | 另外两块的 2 种排列 | 配额 | bin_0-bin_1:49 bin_0-bin_2:55 bin_1-bin_0:50 bin_1-bin_2:46 bin_2-bin_0:44 bin_2-bin_1:56 |
| `swap_pairs[k].partner`（交换搭档） | 交换开始时的水平最近邻，等距取序号小者；第 k 次发起者 = swap_initiators[k mod 3]（4～5 次时循环沿用 3 个发起者） | 推出（执行时核验，不符即失败） | 推出：bin_1→bin_2:263 bin_0→bin_2:253 bin_2→bin_0:247 bin_0→bin_1:201 bin_2→bin_1:201 bin_1→bin_0:185（共 1350 次交换）；未覆盖 无 |
<!-- AUTO:EVENT_TABLES END -->

## 三类图的读法

视角与 base_camera 对齐：画面右是世界 +y，上是世界 −x；绘图坐标为 (y, −x)，是纯旋转，不改变朝向或顺逆时针。
每组图只画前 30 条候选，统计表覆盖全部候选；不能用叠图的视觉密度替代配额统计。

- 图 1：全部初始位置与按物体种类拆分的面板；矩形是真实尺寸和朝向，圆是按钮底座，虚线表示合法区域。
- 图 2：BinFill 的全部方块带颜色、被抓物体以黑边和 1/2/3 标顺序；RouteStick 按起点分面并区分绕行方向；视频任务按交换序号画发起者与搭档。
- 图 3：每页 6 条、共 5 页，逐条画布局、编号和动作，并列出随机事件与位姿数值。

| 组 | 初始位置 | 随机事件 | 逐条图 |
|---|---|---|---|
| BinFill/easy | [图 1](figures/BinFill/easy/1_positions.png) | [图 2](figures/BinFill/easy/2_events.png) | [1](figures/BinFill/easy/3_episodes_p1.png) [2](figures/BinFill/easy/3_episodes_p2.png) [3](figures/BinFill/easy/3_episodes_p3.png) [4](figures/BinFill/easy/3_episodes_p4.png) [5](figures/BinFill/easy/3_episodes_p5.png) |
| BinFill/medium | [图 1](figures/BinFill/medium/1_positions.png) | [图 2](figures/BinFill/medium/2_events.png) | [1](figures/BinFill/medium/3_episodes_p1.png) [2](figures/BinFill/medium/3_episodes_p2.png) [3](figures/BinFill/medium/3_episodes_p3.png) [4](figures/BinFill/medium/3_episodes_p4.png) [5](figures/BinFill/medium/3_episodes_p5.png) |
| BinFill/hard | [图 1](figures/BinFill/hard/1_positions.png) | [图 2](figures/BinFill/hard/2_events.png) | [1](figures/BinFill/hard/3_episodes_p1.png) [2](figures/BinFill/hard/3_episodes_p2.png) [3](figures/BinFill/hard/3_episodes_p3.png) [4](figures/BinFill/hard/3_episodes_p4.png) [5](figures/BinFill/hard/3_episodes_p5.png) |
| RouteStick/easy | [图 1](figures/RouteStick/easy/1_positions.png) | [图 2](figures/RouteStick/easy/2_events.png) | [1](figures/RouteStick/easy/3_episodes_p1.png) [2](figures/RouteStick/easy/3_episodes_p2.png) [3](figures/RouteStick/easy/3_episodes_p3.png) [4](figures/RouteStick/easy/3_episodes_p4.png) [5](figures/RouteStick/easy/3_episodes_p5.png) |
| RouteStick/medium | [图 1](figures/RouteStick/medium/1_positions.png) | [图 2](figures/RouteStick/medium/2_events.png) | [1](figures/RouteStick/medium/3_episodes_p1.png) [2](figures/RouteStick/medium/3_episodes_p2.png) [3](figures/RouteStick/medium/3_episodes_p3.png) [4](figures/RouteStick/medium/3_episodes_p4.png) [5](figures/RouteStick/medium/3_episodes_p5.png) |
| RouteStick/hard | [图 1](figures/RouteStick/hard/1_positions.png) | [图 2](figures/RouteStick/hard/2_events.png) | [1](figures/RouteStick/hard/3_episodes_p1.png) [2](figures/RouteStick/hard/3_episodes_p2.png) [3](figures/RouteStick/hard/3_episodes_p3.png) [4](figures/RouteStick/hard/3_episodes_p4.png) [5](figures/RouteStick/hard/3_episodes_p5.png) |
| RouteStick/xhard | [图 1](figures/RouteStick/xhard/1_positions.png) | [图 2](figures/RouteStick/xhard/2_events.png) | [1](figures/RouteStick/xhard/3_episodes_p1.png) [2](figures/RouteStick/xhard/3_episodes_p2.png) [3](figures/RouteStick/xhard/3_episodes_p3.png) [4](figures/RouteStick/xhard/3_episodes_p4.png) [5](figures/RouteStick/xhard/3_episodes_p5.png) |
| VideoUnmaskSwap/easy | [图 1](figures/VideoUnmaskSwap/easy/1_positions.png) | [图 2](figures/VideoUnmaskSwap/easy/2_events.png) | [1](figures/VideoUnmaskSwap/easy/3_episodes_p1.png) [2](figures/VideoUnmaskSwap/easy/3_episodes_p2.png) [3](figures/VideoUnmaskSwap/easy/3_episodes_p3.png) [4](figures/VideoUnmaskSwap/easy/3_episodes_p4.png) [5](figures/VideoUnmaskSwap/easy/3_episodes_p5.png) |
| VideoUnmaskSwap/medium | [图 1](figures/VideoUnmaskSwap/medium/1_positions.png) | [图 2](figures/VideoUnmaskSwap/medium/2_events.png) | [1](figures/VideoUnmaskSwap/medium/3_episodes_p1.png) [2](figures/VideoUnmaskSwap/medium/3_episodes_p2.png) [3](figures/VideoUnmaskSwap/medium/3_episodes_p3.png) [4](figures/VideoUnmaskSwap/medium/3_episodes_p4.png) [5](figures/VideoUnmaskSwap/medium/3_episodes_p5.png) |
| VideoUnmaskSwap/hard | [图 1](figures/VideoUnmaskSwap/hard/1_positions.png) | [图 2](figures/VideoUnmaskSwap/hard/2_events.png) | [1](figures/VideoUnmaskSwap/hard/3_episodes_p1.png) [2](figures/VideoUnmaskSwap/hard/3_episodes_p2.png) [3](figures/VideoUnmaskSwap/hard/3_episodes_p3.png) [4](figures/VideoUnmaskSwap/hard/3_episodes_p4.png) [5](figures/VideoUnmaskSwap/hard/3_episodes_p5.png) |
| VideoUnmaskSwap/xhard | [图 1](figures/VideoUnmaskSwap/xhard/1_positions.png) | [图 2](figures/VideoUnmaskSwap/xhard/2_events.png) | [1](figures/VideoUnmaskSwap/xhard/3_episodes_p1.png) [2](figures/VideoUnmaskSwap/xhard/3_episodes_p2.png) [3](figures/VideoUnmaskSwap/xhard/3_episodes_p3.png) [4](figures/VideoUnmaskSwap/xhard/3_episodes_p4.png) [5](figures/VideoUnmaskSwap/xhard/3_episodes_p5.png) |
| VideoRepick/easy | [图 1](figures/VideoRepick/easy/1_positions.png) | [图 2](figures/VideoRepick/easy/2_events.png) | [1](figures/VideoRepick/easy/3_episodes_p1.png) [2](figures/VideoRepick/easy/3_episodes_p2.png) [3](figures/VideoRepick/easy/3_episodes_p3.png) [4](figures/VideoRepick/easy/3_episodes_p4.png) [5](figures/VideoRepick/easy/3_episodes_p5.png) |
| VideoRepick/medium | [图 1](figures/VideoRepick/medium/1_positions.png) | [图 2](figures/VideoRepick/medium/2_events.png) | [1](figures/VideoRepick/medium/3_episodes_p1.png) [2](figures/VideoRepick/medium/3_episodes_p2.png) [3](figures/VideoRepick/medium/3_episodes_p3.png) [4](figures/VideoRepick/medium/3_episodes_p4.png) [5](figures/VideoRepick/medium/3_episodes_p5.png) |
| VideoRepick/xhard | [图 1](figures/VideoRepick/xhard/1_positions.png) | [图 2](figures/VideoRepick/xhard/2_events.png) | [1](figures/VideoRepick/xhard/3_episodes_p1.png) [2](figures/VideoRepick/xhard/3_episodes_p2.png) [3](figures/VideoRepick/xhard/3_episodes_p3.png) [4](figures/VideoRepick/xhard/3_episodes_p4.png) [5](figures/VideoRepick/xhard/3_episodes_p5.png) |
