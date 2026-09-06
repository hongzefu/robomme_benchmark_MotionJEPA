# PickXtimes-test 逐 episode 动作参数

共 50 条。数据来源：本轮按 test metadata 死 seed 实跑生成。

口径：动作次数与颜色组成直接读 `setup/task_goal`（BinFill 是要放几个什么颜色的 cube，PickXtimes 是同一动作重复几次）；每次动作在数据里是 pick 与 place 两段，末尾再加一段 press button，所以核心段数 = 2 × 动作次数 + 1（本报告的每条都验过这条恒等式）。时长单位是 timestep（1 timestep = 1 个 env step = 0.05 s）。关键点坐标取该段内 z 最低的 `action/waypoint_action`（段首帧常残留上一段的值，不可用）——pick 段即 cube 位置、press 段即按钮位置、put 段即 bin 上方的松手点，SAPIEN 世界坐标、单位米（机器人 base 在 `(-0.615, 0, 0)`）；该帧没有关键点时记 —。

与 PatternLock / RouteStick 不同，这两个任务**没有视频演示段**，所以不存在「演示段 / 执行段」之分，下表每一行就是真正执行的一段。每行的子目标必是三类之一：`pick up …`（找到并抓起指定 cube）、`put / place …`（送到 bin 或 target）、`press …`（按按钮）；每次动作产生一对 pick + place，末尾另有一段 press。

#### episode 0 — seed `510000`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 693 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 112 ts | (-0.121, +0.178, +0.020) |
| 2 | place the green cube onto the target | 94 ts | (-0.241, +0.120, +0.005) |
| 3 | pick up the green cube for the second time | 86 ts | (-0.240, +0.123, +0.020) |
| 4 | place the green cube onto the target | 74 ts | (-0.241, +0.120, +0.005) |
| 5 | pick up the green cube for the third time | 159 ts | (-0.238, +0.121, +0.020) |
| 6 | place the green cube onto the target | 82 ts | (-0.241, +0.120, +0.005) |
| 7 | press the button to stop | 50 ts | (-0.156, -0.015, +0.007) |

#### episode 1 — seed `510100`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 346 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 164 ts | (+0.032, +0.050, +0.020) |
| 2 | place the green cube onto the target | 86 ts | (-0.053, +0.050, +0.005) |
| 3 | press the button to stop | 54 ts | (-0.203, +0.111, +0.007) |

#### episode 2 — seed `510200`，难度 medium，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 353 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 163 ts | (-0.019, +0.137, +0.020) |
| 2 | place the blue cube onto the target | 87 ts | (-0.162, +0.158, +0.005) |
| 3 | press the button to stop | 68 ts | (-0.175, -0.017, +0.007) |

#### episode 3 — seed `510300`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 928 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 122 ts | (-0.160, +0.179, +0.020) |
| 2 | place the blue cube onto the target | 102 ts | (-0.247, -0.105, +0.005) |
| 3 | pick up the blue cube for the second time | 86 ts | (-0.244, -0.107, +0.020) |
| 4 | place the blue cube onto the target | 79 ts | (-0.247, -0.105, +0.005) |
| 5 | pick up the blue cube for the third time | 85 ts | (-0.245, -0.109, +0.020) |
| 6 | place the blue cube onto the target | 81 ts | (-0.247, -0.105, +0.005) |
| 7 | pick up the blue cube for the fourth time | 197 ts | (-0.248, -0.108, +0.020) |
| 8 | place the blue cube onto the target | 85 ts | (-0.247, -0.105, +0.005) |
| 9 | press the button to stop | 49 ts | (-0.223, +0.058, +0.007) |

#### episode 4 — seed `510400`，难度 easy，动作 2 次

目标：pick up the blue cube and place it on the target, repeating this action two times, then press the button to stop

整条 540 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 200 ts | (+0.058, +0.004, +0.020) |
| 2 | place the blue cube onto the target | 101 ts | (-0.139, -0.092, +0.005) |
| 3 | pick up the blue cube for the second time | 75 ts | (-0.135, -0.095, +0.020) |
| 4 | place the blue cube onto the target | 69 ts | (-0.139, -0.092, +0.005) |
| 5 | press the button to stop | 58 ts | (-0.159, +0.189, +0.007) |

#### episode 5 — seed `510500`，难度 easy，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 511 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 191 ts | (-0.093, +0.140, +0.020) |
| 2 | place the red cube onto the target | 82 ts | (+0.034, +0.151, +0.005) |
| 3 | pick up the red cube for the second time | 75 ts | (+0.042, +0.151, +0.020) |
| 4 | place the red cube onto the target | 55 ts | (+0.034, +0.151, +0.005) |
| 5 | press the button to stop | 71 ts | (-0.206, -0.029, +0.007) |

#### episode 6 — seed `510600`，难度 medium，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 308 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 104 ts | (+0.058, +0.131, +0.020) |
| 2 | place the green cube onto the target | 110 ts | (-0.227, -0.076, +0.005) |
| 3 | press the button to stop | 55 ts | (-0.200, +0.093, +0.007) |

#### episode 7 — seed `510700`，难度 hard，动作 5 次

目标：pick up the green cube and place it on the target, repeating this action five times, then press the button to stop

整条 796 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 105 ts | (+0.003, +0.175, +0.020) |
| 2 | place the green cube onto the target | 87 ts | (-0.006, +0.057, +0.005) |
| 3 | pick up the green cube for the second time | 71 ts | (+0.001, +0.059, +0.020) |
| 4 | place the green cube onto the target | 56 ts | (-0.006, +0.057, +0.005) |
| 5 | pick up the green cube for the third time | 71 ts | (+0.003, +0.059, +0.020) |
| 6 | place the green cube onto the target | 58 ts | (-0.006, +0.057, +0.005) |
| 7 | pick up the green cube for the fourth time | 71 ts | (+0.001, +0.059, +0.020) |
| 8 | place the green cube onto the target | 57 ts | (-0.006, +0.057, +0.005) |
| 9 | pick up the green cube for the fifth time | 70 ts | (+0.001, +0.059, +0.020) |
| 10 | place the green cube onto the target | 56 ts | (-0.006, +0.057, +0.005) |
| 11 | press the button to stop | 59 ts | (-0.178, -0.036, +0.007) |

#### episode 8 — seed `510800`，难度 easy，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 418 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 107 ts | (+0.027, +0.074, +0.020) |
| 2 | place the green cube onto the target | 85 ts | (-0.048, -0.114, +0.005) |
| 3 | pick up the green cube for the second time | 71 ts | (-0.039, -0.116, +0.020) |
| 4 | place the green cube onto the target | 66 ts | (-0.048, -0.114, +0.005) |
| 5 | press the button to stop | 53 ts | (-0.165, +0.016, +0.007) |

#### episode 9 — seed `510900`，难度 easy，动作 2 次

目标：pick up the blue cube and place it on the target, repeating this action two times, then press the button to stop

整条 448 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 132 ts | (-0.190, +0.133, +0.020) |
| 2 | place the blue cube onto the target | 90 ts | (+0.015, +0.048, +0.005) |
| 3 | pick up the blue cube for the second time | 69 ts | (+0.019, +0.048, +0.020) |
| 4 | place the blue cube onto the target | 54 ts | (+0.015, +0.048, +0.005) |
| 5 | press the button to stop | 65 ts | (-0.174, -0.054, +0.007) |

#### episode 10 — seed `511000`，难度 medium，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 298 timestep（其中收尾段 45）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 110 ts | (-0.088, +0.175, +0.020) |
| 2 | place the green cube onto the target | 78 ts | (+0.004, +0.142, +0.005) |
| 3 | press the button to stop | 65 ts | (-0.247, -0.180, +0.007) |

#### episode 11 — seed `511100`，难度 hard，动作 5 次

目标：pick up the red cube and place it on the target, repeating this action five times, then press the button to stop

整条 875 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 124 ts | (-0.219, +0.139, +0.020) |
| 2 | place the red cube onto the target | 103 ts | (-0.036, -0.143, +0.005) |
| 3 | pick up the red cube for the second time | 69 ts | (-0.032, -0.141, +0.020) |
| 4 | place the red cube onto the target | 65 ts | (-0.036, -0.143, +0.005) |
| 5 | pick up the red cube for the third time | 69 ts | (-0.032, -0.143, +0.020) |
| 6 | place the red cube onto the target | 65 ts | (-0.036, -0.143, +0.005) |
| 7 | pick up the red cube for the fourth time | 70 ts | (-0.030, -0.142, +0.020) |
| 8 | place the red cube onto the target | 64 ts | (-0.036, -0.143, +0.005) |
| 9 | pick up the red cube for the fifth time | 69 ts | (-0.031, -0.140, +0.020) |
| 10 | place the red cube onto the target | 65 ts | (-0.036, -0.143, +0.005) |
| 11 | press the button to stop | 72 ts | (-0.240, -0.081, +0.007) |

#### episode 12 — seed `511200`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 605 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 141 ts | (-0.261, +0.093, +0.020) |
| 2 | place the green cube onto the target | 95 ts | (-0.037, -0.007, +0.005) |
| 3 | pick up the green cube for the second time | 70 ts | (-0.030, -0.009, +0.020) |
| 4 | place the green cube onto the target | 62 ts | (-0.037, -0.007, +0.005) |
| 5 | pick up the green cube for the third time | 70 ts | (-0.030, -0.009, +0.020) |
| 6 | place the green cube onto the target | 62 ts | (-0.037, -0.007, +0.005) |
| 7 | press the button to stop | 64 ts | (-0.216, -0.116, +0.007) |

#### episode 13 — seed `511300`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 289 timestep（其中收尾段 43）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 103 ts | (+0.042, +0.072, +0.020) |
| 2 | place the green cube onto the target | 83 ts | (-0.084, +0.137, +0.005) |
| 3 | press the button to stop | 60 ts | (-0.246, +0.000, +0.007) |

#### episode 14 — seed `511400`，难度 medium，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 341 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 136 ts | (-0.276, -0.017, +0.020) |
| 2 | place the blue cube onto the target | 100 ts | (-0.118, +0.110, +0.005) |
| 3 | press the button to stop | 67 ts | (-0.171, -0.152, +0.007) |

#### episode 15 — seed `511501`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 709 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 122 ts | (-0.217, -0.149, +0.020) |
| 2 | place the blue cube onto the target | 81 ts | (-0.090, -0.015, +0.005) |
| 3 | pick up the blue cube for the second time | 77 ts | (-0.085, -0.015, +0.020) |
| 4 | place the blue cube onto the target | 60 ts | (-0.090, -0.015, +0.005) |
| 5 | pick up the blue cube for the third time | 78 ts | (-0.085, -0.017, +0.020) |
| 6 | place the blue cube onto the target | 60 ts | (-0.090, -0.015, +0.005) |
| 7 | pick up the blue cube for the fourth time | 76 ts | (-0.085, -0.018, +0.020) |
| 8 | place the blue cube onto the target | 59 ts | (-0.090, -0.015, +0.005) |
| 9 | press the button to stop | 54 ts | (-0.223, +0.083, +0.007) |

#### episode 16 — seed `511600`，难度 easy，动作 1 次

目标：pick up the red cube and place it on the target, then press the button to stop

整条 283 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 105 ts | (-0.015, +0.144, +0.020) |
| 2 | place the red cube onto the target | 86 ts | (-0.042, -0.078, +0.005) |
| 3 | press the button to stop | 56 ts | (-0.182, -0.101, +0.007) |

#### episode 17 — seed `511700`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 598 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 135 ts | (-0.201, -0.054, +0.020) |
| 2 | place the green cube onto the target | 96 ts | (+0.046, +0.088, +0.005) |
| 3 | pick up the green cube for the second time | 74 ts | (+0.051, +0.090, +0.020) |
| 4 | place the green cube onto the target | 53 ts | (+0.046, +0.088, +0.005) |
| 5 | pick up the green cube for the third time | 75 ts | (+0.052, +0.090, +0.020) |
| 6 | place the green cube onto the target | 54 ts | (+0.046, +0.088, +0.005) |
| 7 | press the button to stop | 69 ts | (-0.239, +0.131, +0.007) |

#### episode 18 — seed `511800`，难度 medium，动作 2 次

目标：pick up the blue cube and place it on the target, repeating this action two times, then press the button to stop

整条 424 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 104 ts | (-0.008, -0.152, +0.020) |
| 2 | place the blue cube onto the target | 82 ts | (+0.057, +0.141, +0.005) |
| 3 | pick up the blue cube for the second time | 77 ts | (+0.064, +0.142, +0.020) |
| 4 | place the blue cube onto the target | 54 ts | (+0.057, +0.141, +0.005) |
| 5 | press the button to stop | 70 ts | (-0.203, -0.095, +0.007) |

#### episode 19 — seed `511900`，难度 hard，动作 5 次

目标：pick up the red cube and place it on the target, repeating this action five times, then press the button to stop

整条 836 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 121 ts | (-0.133, +0.141, +0.020) |
| 2 | place the red cube onto the target | 87 ts | (+0.049, -0.131, +0.005) |
| 3 | pick up the red cube for the second time | 75 ts | (+0.053, -0.130, +0.020) |
| 4 | place the red cube onto the target | 52 ts | (+0.049, -0.131, +0.005) |
| 5 | pick up the red cube for the third time | 76 ts | (+0.056, -0.130, +0.020) |
| 6 | place the red cube onto the target | 53 ts | (+0.049, -0.131, +0.005) |
| 7 | pick up the red cube for the fourth time | 76 ts | (+0.055, -0.130, +0.020) |
| 8 | place the red cube onto the target | 53 ts | (+0.049, -0.131, +0.005) |
| 9 | pick up the red cube for the fifth time | 76 ts | (+0.055, -0.130, +0.020) |
| 10 | place the red cube onto the target | 53 ts | (+0.049, -0.131, +0.005) |
| 11 | press the button to stop | 75 ts | (-0.236, -0.104, +0.007) |

#### episode 20 — seed `512000`，难度 easy，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 461 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 134 ts | (-0.193, -0.103, +0.020) |
| 2 | place the red cube onto the target | 92 ts | (+0.035, +0.074, +0.005) |
| 3 | pick up the red cube for the second time | 72 ts | (+0.040, +0.076, +0.020) |
| 4 | place the red cube onto the target | 53 ts | (+0.035, +0.074, +0.005) |
| 5 | press the button to stop | 69 ts | (-0.244, +0.146, +0.007) |

#### episode 21 — seed `512100`，难度 easy，动作 1 次

目标：pick up the red cube and place it on the target, then press the button to stop

整条 297 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 115 ts | (-0.070, -0.053, +0.020) |
| 2 | place the red cube onto the target | 78 ts | (+0.023, +0.061, +0.005) |
| 3 | press the button to stop | 64 ts | (-0.183, +0.023, +0.007) |

#### episode 22 — seed `512200`，难度 medium，动作 3 次

目标：pick up the blue cube and place it on the target, repeating this action three times, then press the button to stop

整条 578 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 105 ts | (+0.038, +0.140, +0.020) |
| 2 | place the blue cube onto the target | 100 ts | (-0.158, -0.144, +0.005) |
| 3 | pick up the blue cube for the second time | 75 ts | (-0.153, -0.144, +0.020) |
| 4 | place the blue cube onto the target | 65 ts | (-0.158, -0.144, +0.005) |
| 5 | pick up the blue cube for the third time | 75 ts | (-0.152, -0.144, +0.020) |
| 6 | place the blue cube onto the target | 64 ts | (-0.158, -0.144, +0.005) |
| 7 | press the button to stop | 54 ts | (-0.176, +0.084, +0.007) |

#### episode 23 — seed `512300`，难度 hard，动作 5 次

目标：pick up the red cube and place it on the target, repeating this action five times, then press the button to stop

整条 906 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 101 ts | (-0.023, -0.168, +0.020) |
| 2 | place the red cube onto the target | 108 ts | (-0.181, +0.018, +0.005) |
| 3 | pick up the red cube for the second time | 81 ts | (-0.177, +0.015, +0.020) |
| 4 | place the red cube onto the target | 77 ts | (-0.181, +0.018, +0.005) |
| 5 | pick up the red cube for the third time | 79 ts | (-0.176, +0.016, +0.020) |
| 6 | place the red cube onto the target | 75 ts | (-0.181, +0.018, +0.005) |
| 7 | pick up the red cube for the fourth time | 78 ts | (-0.177, +0.016, +0.020) |
| 8 | place the red cube onto the target | 72 ts | (-0.181, +0.018, +0.005) |
| 9 | pick up the red cube for the fifth time | 78 ts | (-0.172, +0.020, +0.020) |
| 10 | place the red cube onto the target | 67 ts | (-0.181, +0.018, +0.005) |
| 11 | press the button to stop | 55 ts | (-0.175, +0.170, +0.007) |

#### episode 24 — seed `512400`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 619 timestep（其中收尾段 33）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 126 ts | (-0.158, -0.000, +0.020) |
| 2 | place the green cube onto the target | 92 ts | (-0.206, +0.133, +0.005) |
| 3 | pick up the green cube for the second time | 84 ts | (-0.203, +0.134, +0.020) |
| 4 | place the green cube onto the target | 71 ts | (-0.206, +0.133, +0.005) |
| 5 | pick up the green cube for the third time | 78 ts | (-0.204, +0.135, +0.020) |
| 6 | place the green cube onto the target | 68 ts | (-0.206, +0.133, +0.005) |
| 7 | press the button to stop | 67 ts | (-0.174, -0.183, +0.007) |

#### episode 25 — seed `512500`，难度 easy，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 431 timestep（其中收尾段 32）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 130 ts | (-0.214, -0.068, +0.020) |
| 2 | place the green cube onto the target | 88 ts | (+0.001, +0.108, +0.005) |
| 3 | pick up the green cube for the second time | 70 ts | (+0.006, +0.108, +0.020) |
| 4 | place the green cube onto the target | 55 ts | (+0.001, +0.108, +0.005) |
| 5 | press the button to stop | 56 ts | (-0.163, +0.157, +0.007) |

#### episode 26 — seed `512600`，难度 medium，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 541 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 104 ts | (+0.045, +0.094, +0.020) |
| 2 | place the green cube onto the target | 75 ts | (+0.049, -0.055, +0.005) |
| 3 | pick up the green cube for the second time | 75 ts | (+0.055, -0.057, +0.020) |
| 4 | place the green cube onto the target | 53 ts | (+0.049, -0.055, +0.005) |
| 5 | pick up the green cube for the third time | 75 ts | (+0.055, -0.054, +0.020) |
| 6 | place the green cube onto the target | 53 ts | (+0.049, -0.055, +0.005) |
| 7 | press the button to stop | 68 ts | (-0.228, -0.135, +0.007) |

#### episode 27 — seed `512700`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 686 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 102 ts | (+0.015, +0.096, +0.020) |
| 2 | place the blue cube onto the target | 80 ts | (-0.035, -0.001, +0.005) |
| 3 | pick up the blue cube for the second time | 71 ts | (-0.028, -0.005, +0.020) |
| 4 | place the blue cube onto the target | 65 ts | (-0.035, -0.001, +0.005) |
| 5 | pick up the blue cube for the third time | 70 ts | (-0.028, -0.004, +0.020) |
| 6 | place the blue cube onto the target | 65 ts | (-0.035, -0.001, +0.005) |
| 7 | pick up the blue cube for the fourth time | 71 ts | (-0.028, -0.003, +0.020) |
| 8 | place the blue cube onto the target | 65 ts | (-0.035, -0.001, +0.005) |
| 9 | press the button to stop | 58 ts | (-0.207, -0.028, +0.007) |

#### episode 28 — seed `512800`，难度 easy，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 463 timestep（其中收尾段 46）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 132 ts | (-0.235, -0.180, +0.020) |
| 2 | place the red cube onto the target | 83 ts | (-0.066, -0.130, +0.005) |
| 3 | pick up the red cube for the second time | 76 ts | (-0.061, -0.129, +0.020) |
| 4 | place the red cube onto the target | 57 ts | (-0.066, -0.130, +0.005) |
| 5 | press the button to stop | 69 ts | (-0.215, -0.067, +0.007) |

#### episode 29 — seed `512900`，难度 easy，动作 1 次

目标：pick up the red cube and place it on the target, then press the button to stop

整条 304 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 108 ts | (-0.039, +0.121, +0.020) |
| 2 | place the red cube onto the target | 88 ts | (-0.016, -0.081, +0.005) |
| 3 | press the button to stop | 68 ts | (-0.243, +0.049, +0.007) |

#### episode 30 — seed `513000`，难度 medium，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 315 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 115 ts | (-0.050, -0.033, +0.020) |
| 2 | place the blue cube onto the target | 86 ts | (-0.149, +0.006, +0.005) |
| 3 | press the button to stop | 75 ts | (-0.246, -0.187, +0.007) |

#### episode 31 — seed `513100`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 701 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 125 ts | (-0.196, +0.086, +0.020) |
| 2 | place the blue cube onto the target | 84 ts | (-0.059, +0.049, +0.005) |
| 3 | pick up the blue cube for the second time | 70 ts | (-0.053, +0.051, +0.020) |
| 4 | place the blue cube onto the target | 61 ts | (-0.059, +0.049, +0.005) |
| 5 | pick up the blue cube for the third time | 71 ts | (-0.052, +0.051, +0.020) |
| 6 | place the blue cube onto the target | 60 ts | (-0.059, +0.049, +0.005) |
| 7 | pick up the blue cube for the fourth time | 72 ts | (-0.051, +0.052, +0.020) |
| 8 | place the blue cube onto the target | 61 ts | (-0.059, +0.049, +0.005) |
| 9 | press the button to stop | 59 ts | (-0.234, -0.067, +0.007) |

#### episode 32 — seed `513200`，难度 easy，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 547 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 104 ts | (-0.017, +0.138, +0.020) |
| 2 | place the red cube onto the target | 78 ts | (-0.082, +0.063, +0.005) |
| 3 | pick up the red cube for the second time | 79 ts | (-0.076, +0.063, +0.020) |
| 4 | place the red cube onto the target | 59 ts | (-0.082, +0.063, +0.005) |
| 5 | pick up the red cube for the third time | 78 ts | (-0.078, +0.065, +0.020) |
| 6 | place the red cube onto the target | 59 ts | (-0.082, +0.063, +0.005) |
| 7 | press the button to stop | 56 ts | (-0.196, -0.095, +0.007) |

#### episode 33 — seed `513300`，难度 easy，动作 1 次

目标：pick up the red cube and place it on the target, then press the button to stop

整条 293 timestep（其中收尾段 44）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 103 ts | (+0.007, +0.040, +0.020) |
| 2 | place the red cube onto the target | 74 ts | (+0.044, -0.150, +0.005) |
| 3 | press the button to stop | 72 ts | (-0.244, -0.003, +0.007) |

#### episode 34 — seed `513400`，难度 medium，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 298 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 111 ts | (+0.064, +0.089, +0.020) |
| 2 | place the blue cube onto the target | 86 ts | (-0.070, +0.154, +0.005) |
| 3 | press the button to stop | 63 ts | (-0.234, -0.038, +0.007) |

#### episode 35 — seed `513500`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 753 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 131 ts | (-0.215, +0.158, +0.020) |
| 2 | place the blue cube onto the target | 90 ts | (-0.190, +0.003, +0.005) |
| 3 | pick up the blue cube for the second time | 77 ts | (-0.189, +0.002, +0.020) |
| 4 | place the blue cube onto the target | 67 ts | (-0.190, +0.003, +0.005) |
| 5 | pick up the blue cube for the third time | 78 ts | (-0.186, +0.003, +0.020) |
| 6 | place the blue cube onto the target | 65 ts | (-0.190, +0.003, +0.005) |
| 7 | pick up the blue cube for the fourth time | 81 ts | (-0.186, +0.004, +0.020) |
| 8 | place the blue cube onto the target | 68 ts | (-0.190, +0.003, +0.005) |
| 9 | press the button to stop | 61 ts | (-0.171, -0.199, +0.007) |

#### episode 36 — seed `513600`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 326 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 133 ts | (-0.254, +0.064, +0.020) |
| 2 | place the green cube onto the target | 97 ts | (+0.039, +0.068, +0.005) |
| 3 | press the button to stop | 62 ts | (-0.170, -0.035, +0.007) |

#### episode 37 — seed `513700`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 600 timestep（其中收尾段 45）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 134 ts | (-0.242, +0.155, +0.020) |
| 2 | place the green cube onto the target | 89 ts | (-0.036, +0.075, +0.005) |
| 3 | pick up the green cube for the second time | 70 ts | (-0.029, +0.074, +0.020) |
| 4 | place the green cube onto the target | 60 ts | (-0.036, +0.075, +0.005) |
| 5 | pick up the green cube for the third time | 70 ts | (-0.029, +0.075, +0.020) |
| 6 | place the green cube onto the target | 59 ts | (-0.036, +0.075, +0.005) |
| 7 | press the button to stop | 73 ts | (-0.243, -0.067, +0.007) |

#### episode 38 — seed `513800`，难度 medium，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 619 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 105 ts | (+0.071, -0.064, +0.020) |
| 2 | place the red cube onto the target | 109 ts | (-0.208, +0.046, +0.005) |
| 3 | pick up the red cube for the second time | 80 ts | (-0.205, +0.046, +0.020) |
| 4 | place the red cube onto the target | 70 ts | (-0.208, +0.046, +0.005) |
| 5 | pick up the red cube for the third time | 80 ts | (-0.204, +0.051, +0.020) |
| 6 | place the red cube onto the target | 70 ts | (-0.208, +0.046, +0.005) |
| 7 | press the button to stop | 65 ts | (-0.211, -0.137, +0.007) |

#### episode 39 — seed `513900`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 744 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 122 ts | (-0.145, -0.120, +0.020) |
| 2 | place the blue cube onto the target | 88 ts | (-0.127, +0.001, +0.005) |
| 3 | pick up the blue cube for the second time | 75 ts | (-0.122, +0.002, +0.020) |
| 4 | place the blue cube onto the target | 68 ts | (-0.127, +0.001, +0.005) |
| 5 | pick up the blue cube for the third time | 75 ts | (-0.123, +0.001, +0.020) |
| 6 | place the blue cube onto the target | 65 ts | (-0.127, +0.001, +0.005) |
| 7 | pick up the blue cube for the fourth time | 75 ts | (-0.123, +0.003, +0.020) |
| 8 | place the blue cube onto the target | 65 ts | (-0.127, +0.001, +0.005) |
| 9 | press the button to stop | 70 ts | (-0.208, +0.172, +0.007) |

#### episode 40 — seed `514000`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 535 timestep（其中收尾段 33）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 115 ts | (-0.108, -0.021, +0.020) |
| 2 | place the green cube onto the target | 75 ts | (-0.058, +0.048, +0.005) |
| 3 | pick up the green cube for the second time | 71 ts | (-0.052, +0.047, +0.020) |
| 4 | place the green cube onto the target | 60 ts | (-0.058, +0.048, +0.005) |
| 5 | pick up the green cube for the third time | 71 ts | (-0.052, +0.047, +0.020) |
| 6 | place the green cube onto the target | 60 ts | (-0.058, +0.048, +0.005) |
| 7 | press the button to stop | 50 ts | (-0.185, +0.154, +0.007) |

#### episode 41 — seed `514100`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 305 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 110 ts | (-0.048, +0.008, +0.020) |
| 2 | place the green cube onto the target | 92 ts | (-0.127, -0.148, +0.005) |
| 3 | press the button to stop | 64 ts | (-0.219, +0.015, +0.007) |

#### episode 42 — seed `514200`，难度 medium，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 413 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 104 ts | (+0.037, -0.130, +0.020) |
| 2 | place the red cube onto the target | 78 ts | (+0.046, +0.122, +0.005) |
| 3 | pick up the red cube for the second time | 76 ts | (+0.053, +0.125, +0.020) |
| 4 | place the red cube onto the target | 54 ts | (+0.046, +0.122, +0.005) |
| 5 | press the button to stop | 63 ts | (-0.152, -0.006, +0.007) |

#### episode 43 — seed `514300`，难度 hard，动作 5 次

目标：pick up the blue cube and place it on the target, repeating this action five times, then press the button to stop

整条 829 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 144 ts | (-0.266, +0.163, +0.020) |
| 2 | place the blue cube onto the target | 89 ts | (+0.013, -0.038, +0.005) |
| 3 | pick up the blue cube for the second time | 68 ts | (+0.018, -0.039, +0.020) |
| 4 | place the blue cube onto the target | 55 ts | (+0.013, -0.038, +0.005) |
| 5 | pick up the blue cube for the third time | 69 ts | (+0.019, -0.039, +0.020) |
| 6 | place the blue cube onto the target | 54 ts | (+0.013, -0.038, +0.005) |
| 7 | pick up the blue cube for the fourth time | 68 ts | (+0.020, -0.040, +0.020) |
| 8 | place the blue cube onto the target | 54 ts | (+0.013, -0.038, +0.005) |
| 9 | pick up the blue cube for the fifth time | 69 ts | (+0.020, -0.040, +0.020) |
| 10 | place the blue cube onto the target | 55 ts | (+0.013, -0.038, +0.005) |
| 11 | press the button to stop | 65 ts | (-0.150, +0.019, +0.007) |

#### episode 44 — seed `514400`，难度 easy，动作 2 次

目标：pick up the blue cube and place it on the target, repeating this action two times, then press the button to stop

整条 447 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 109 ts | (-0.041, +0.157, +0.020) |
| 2 | place the blue cube onto the target | 103 ts | (-0.188, -0.051, +0.005) |
| 3 | pick up the blue cube for the second time | 79 ts | (-0.184, -0.053, +0.020) |
| 4 | place the blue cube onto the target | 76 ts | (-0.188, -0.051, +0.005) |
| 5 | press the button to stop | 44 ts | (-0.161, +0.145, +0.007) |

#### episode 45 — seed `514500`，难度 easy，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 300 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 102 ts | (+0.016, -0.096, +0.020) |
| 2 | place the blue cube onto the target | 100 ts | (-0.119, -0.109, +0.005) |
| 3 | press the button to stop | 57 ts | (-0.179, +0.077, +0.007) |

#### episode 46 — seed `514600`，难度 medium，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 549 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 110 ts | (-0.033, +0.100, +0.020) |
| 2 | place the red cube onto the target | 82 ts | (-0.058, -0.073, +0.005) |
| 3 | pick up the red cube for the second time | 70 ts | (-0.054, -0.075, +0.020) |
| 4 | place the red cube onto the target | 61 ts | (-0.058, -0.073, +0.005) |
| 5 | pick up the red cube for the third time | 71 ts | (-0.051, -0.072, +0.020) |
| 6 | place the red cube onto the target | 62 ts | (-0.058, -0.073, +0.005) |
| 7 | press the button to stop | 54 ts | (-0.186, +0.067, +0.007) |

#### episode 47 — seed `514700`，难度 hard，动作 5 次

目标：pick up the blue cube and place it on the target, repeating this action five times, then press the button to stop

整条 867 timestep（其中收尾段 47）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 141 ts | (-0.271, +0.076, +0.020) |
| 2 | place the blue cube onto the target | 96 ts | (+0.028, -0.102, +0.005) |
| 3 | pick up the blue cube for the second time | 72 ts | (+0.034, -0.104, +0.020) |
| 4 | place the blue cube onto the target | 54 ts | (+0.028, -0.102, +0.005) |
| 5 | pick up the blue cube for the third time | 74 ts | (+0.034, -0.103, +0.020) |
| 6 | place the blue cube onto the target | 54 ts | (+0.028, -0.102, +0.005) |
| 7 | pick up the blue cube for the fourth time | 74 ts | (+0.035, -0.103, +0.020) |
| 8 | place the blue cube onto the target | 55 ts | (+0.028, -0.102, +0.005) |
| 9 | pick up the blue cube for the fifth time | 74 ts | (+0.035, -0.103, +0.020) |
| 10 | place the blue cube onto the target | 55 ts | (+0.028, -0.102, +0.005) |
| 11 | press the button to stop | 71 ts | (-0.239, -0.028, +0.007) |

#### episode 48 — seed `514800`，难度 easy，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 605 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 126 ts | (-0.193, +0.169, +0.020) |
| 2 | place the red cube onto the target | 95 ts | (-0.009, +0.113, +0.005) |
| 3 | pick up the red cube for the second time | 72 ts | (+0.002, +0.109, +0.020) |
| 4 | place the red cube onto the target | 67 ts | (-0.009, +0.113, +0.005) |
| 5 | pick up the red cube for the third time | 70 ts | (-0.003, +0.109, +0.020) |
| 6 | place the red cube onto the target | 64 ts | (-0.009, +0.113, +0.005) |
| 7 | press the button to stop | 73 ts | (-0.229, -0.036, +0.007) |

#### episode 49 — seed `514900`，难度 easy，动作 1 次

目标：pick up the red cube and place it on the target, then press the button to stop

整条 299 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 118 ts | (-0.073, -0.146, +0.020) |
| 2 | place the red cube onto the target | 91 ts | (-0.030, +0.113, +0.005) |
| 3 | press the button to stop | 56 ts | (-0.195, -0.175, +0.007) |
