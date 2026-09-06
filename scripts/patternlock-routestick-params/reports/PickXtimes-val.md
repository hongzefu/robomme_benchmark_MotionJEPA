# PickXtimes-val 逐 episode 动作参数

共 50 条。数据来源：原版 h5 `/data/hongzefu/data-0306/record_dataset_PickXtimes.h5`。

口径：动作次数与颜色组成直接读 `setup/task_goal`（BinFill 是要放几个什么颜色的 cube，PickXtimes 是同一动作重复几次）；每次动作在数据里是 pick 与 place 两段，末尾再加一段 press button，所以核心段数 = 2 × 动作次数 + 1（本报告的每条都验过这条恒等式）。时长单位是 timestep（1 timestep = 1 个 env step = 0.05 s）。关键点坐标取该段内 z 最低的 `action/waypoint_action`（段首帧常残留上一段的值，不可用）——pick 段即 cube 位置、press 段即按钮位置、put 段即 bin 上方的松手点，SAPIEN 世界坐标、单位米（机器人 base 在 `(-0.615, 0, 0)`）；该帧没有关键点时记 —。

与 PatternLock / RouteStick 不同，这两个任务**没有视频演示段**，所以不存在「演示段 / 执行段」之分，下表每一行就是真正执行的一段。每行的子目标必是三类之一：`pick up …`（找到并抓起指定 cube）、`put / place …`（送到 bin 或 target）、`press …`（按按钮）；每次动作产生一对 pick + place，末尾另有一段 press。

#### episode 0 — seed `1010000`，难度 easy，动作 3 次

目标：pick up the blue cube and place it on the target, repeating this action three times, then press the button to stop

整条 661 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 131 ts | (-0.256, +0.046, +0.020) |
| 2 | place the blue cube onto the target | 86 ts | (-0.170, +0.098, +0.005) |
| 3 | pick up the blue cube for the second time | 82 ts | (-0.167, +0.101, +0.020) |
| 4 | place the blue cube onto the target | 64 ts | (-0.170, +0.098, +0.005) |
| 5 | pick up the blue cube for the third time | 142 ts | (-0.168, +0.103, +0.020) |
| 6 | place the blue cube onto the target | 70 ts | (-0.170, +0.098, +0.005) |
| 7 | press the button to stop | 48 ts | (-0.184, -0.180, +0.007) |

#### episode 1 — seed `1010100`，难度 easy，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 374 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 179 ts | (-0.129, +0.092, +0.020) |
| 2 | place the blue cube onto the target | 85 ts | (+0.057, +0.055, +0.005) |
| 3 | press the button to stop | 75 ts | (-0.205, -0.160, +0.007) |

#### episode 2 — seed `1010200`，难度 medium，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 648 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 102 ts | (-0.007, -0.178, +0.020) |
| 2 | place the green cube onto the target | 97 ts | (-0.199, -0.139, +0.005) |
| 3 | pick up the green cube for the second time | 77 ts | (-0.192, -0.138, +0.020) |
| 4 | place the green cube onto the target | 67 ts | (-0.199, -0.139, +0.005) |
| 5 | pick up the green cube for the third time | 145 ts | (-0.195, -0.141, +0.020) |
| 6 | place the green cube onto the target | 69 ts | (-0.199, -0.139, +0.005) |
| 7 | press the button to stop | 51 ts | (-0.191, +0.086, +0.007) |

#### episode 3 — seed `1010300`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 760 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 108 ts | (-0.047, +0.170, +0.020) |
| 2 | place the blue cube onto the target | 83 ts | (+0.018, -0.143, +0.005) |
| 3 | pick up the blue cube for the second time | 72 ts | (+0.023, -0.144, +0.020) |
| 4 | place the blue cube onto the target | 53 ts | (+0.018, -0.143, +0.005) |
| 5 | pick up the blue cube for the third time | 73 ts | (+0.025, -0.143, +0.020) |
| 6 | place the blue cube onto the target | 53 ts | (+0.018, -0.143, +0.005) |
| 7 | pick up the blue cube for the fourth time | 162 ts | (+0.024, -0.142, +0.020) |
| 8 | place the blue cube onto the target | 54 ts | (+0.018, -0.143, +0.005) |
| 9 | press the button to stop | 65 ts | (-0.170, -0.065, +0.007) |

#### episode 4 — seed `1010400`，难度 easy，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 501 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 103 ts | (-0.021, +0.120, +0.020) |
| 2 | place the green cube onto the target | 81 ts | (-0.096, -0.039, +0.005) |
| 3 | pick up the green cube for the second time | 167 ts | (-0.091, -0.038, +0.020) |
| 4 | place the green cube onto the target | 58 ts | (-0.096, -0.039, +0.005) |
| 5 | press the button to stop | 50 ts | (-0.223, -0.184, +0.007) |

#### episode 5 — seed `1010501`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 376 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 189 ts | (-0.020, +0.160, +0.020) |
| 2 | place the green cube onto the target | 80 ts | (+0.038, -0.045, +0.005) |
| 3 | press the button to stop | 69 ts | (-0.195, +0.028, +0.007) |

#### episode 6 — seed `1010600`，难度 medium，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 604 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 124 ts | (-0.160, +0.013, +0.020) |
| 2 | place the green cube onto the target | 84 ts | (-0.171, -0.129, +0.005) |
| 3 | pick up the green cube for the second time | 78 ts | (-0.167, -0.132, +0.020) |
| 4 | place the green cube onto the target | 73 ts | (-0.171, -0.129, +0.005) |
| 5 | pick up the green cube for the third time | 76 ts | (-0.168, -0.131, +0.020) |
| 6 | place the green cube onto the target | 67 ts | (-0.171, -0.129, +0.005) |
| 7 | press the button to stop | 66 ts | (-0.212, +0.133, +0.007) |

#### episode 7 — seed `1010700`，难度 hard，动作 4 次

目标：pick up the green cube and place it on the target, repeating this action four times, then press the button to stop

整条 715 timestep（其中收尾段 44）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 107 ts | (+0.057, -0.177, +0.020) |
| 2 | place the green cube onto the target | 88 ts | (-0.062, -0.077, +0.005) |
| 3 | pick up the green cube for the second time | 80 ts | (-0.057, -0.078, +0.020) |
| 4 | place the green cube onto the target | 59 ts | (-0.062, -0.077, +0.005) |
| 5 | pick up the green cube for the third time | 80 ts | (-0.057, -0.082, +0.020) |
| 6 | place the green cube onto the target | 59 ts | (-0.062, -0.077, +0.005) |
| 7 | pick up the green cube for the fourth time | 81 ts | (-0.058, -0.082, +0.020) |
| 8 | place the green cube onto the target | 59 ts | (-0.062, -0.077, +0.005) |
| 9 | press the button to stop | 58 ts | (-0.229, +0.178, +0.007) |

#### episode 8 — seed `1010800`，难度 easy，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 546 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 117 ts | (-0.136, -0.180, +0.020) |
| 2 | place the red cube onto the target | 81 ts | (+0.013, -0.106, +0.005) |
| 3 | pick up the red cube for the second time | 70 ts | (+0.018, -0.107, +0.020) |
| 4 | place the red cube onto the target | 53 ts | (+0.013, -0.106, +0.005) |
| 5 | pick up the red cube for the third time | 71 ts | (+0.020, -0.106, +0.020) |
| 6 | place the red cube onto the target | 55 ts | (+0.013, -0.106, +0.005) |
| 7 | press the button to stop | 62 ts | (-0.184, +0.128, +0.007) |

#### episode 9 — seed `1010900`，难度 easy，动作 2 次

目标：pick up the blue cube and place it on the target, repeating this action two times, then press the button to stop

整条 456 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 142 ts | (-0.266, -0.074, +0.020) |
| 2 | place the blue cube onto the target | 92 ts | (+0.022, -0.010, +0.005) |
| 3 | pick up the blue cube for the second time | 71 ts | (+0.027, -0.010, +0.020) |
| 4 | place the blue cube onto the target | 53 ts | (+0.022, -0.010, +0.005) |
| 5 | press the button to stop | 61 ts | (-0.159, -0.019, +0.007) |

#### episode 10 — seed `1011000`，难度 medium，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 409 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 107 ts | (+0.076, -0.086, +0.020) |
| 2 | place the green cube onto the target | 77 ts | (+0.001, +0.077, +0.005) |
| 3 | pick up the green cube for the second time | 70 ts | (+0.007, +0.076, +0.020) |
| 4 | place the green cube onto the target | 55 ts | (+0.001, +0.077, +0.005) |
| 5 | press the button to stop | 63 ts | (-0.159, -0.144, +0.007) |

#### episode 11 — seed `1011100`，难度 hard，动作 4 次

目标：pick up the red cube and place it on the target, repeating this action four times, then press the button to stop

整条 700 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 128 ts | (-0.210, +0.085, +0.020) |
| 2 | place the red cube onto the target | 88 ts | (-0.000, -0.006, +0.005) |
| 3 | pick up the red cube for the second time | 70 ts | (+0.007, -0.005, +0.020) |
| 4 | place the red cube onto the target | 56 ts | (-0.000, -0.006, +0.005) |
| 5 | pick up the red cube for the third time | 71 ts | (+0.008, -0.006, +0.020) |
| 6 | place the red cube onto the target | 57 ts | (-0.000, -0.006, +0.005) |
| 7 | pick up the red cube for the fourth time | 71 ts | (+0.008, -0.005, +0.020) |
| 8 | place the red cube onto the target | 57 ts | (-0.000, -0.006, +0.005) |
| 9 | press the button to stop | 63 ts | (-0.233, +0.187, +0.007) |

#### episode 12 — seed `1011200`，难度 easy，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 442 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 123 ts | (-0.188, -0.017, +0.020) |
| 2 | place the green cube onto the target | 88 ts | (-0.065, +0.129, +0.005) |
| 3 | pick up the green cube for the second time | 69 ts | (-0.061, +0.127, +0.020) |
| 4 | place the green cube onto the target | 60 ts | (-0.065, +0.129, +0.005) |
| 5 | press the button to stop | 65 ts | (-0.222, +0.148, +0.007) |

#### episode 13 — seed `1011300`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 282 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 104 ts | (-0.019, -0.005, +0.020) |
| 2 | place the green cube onto the target | 74 ts | (+0.031, +0.154, +0.005) |
| 3 | press the button to stop | 67 ts | (-0.235, +0.176, +0.007) |

#### episode 14 — seed `1011400`，难度 medium，动作 2 次

目标：pick up the blue cube and place it on the target, repeating this action two times, then press the button to stop

整条 444 timestep（其中收尾段 43）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 119 ts | (-0.175, +0.158, +0.020) |
| 2 | place the blue cube onto the target | 90 ts | (-0.118, +0.068, +0.005) |
| 3 | pick up the blue cube for the second time | 73 ts | (-0.114, +0.071, +0.020) |
| 4 | place the blue cube onto the target | 70 ts | (-0.118, +0.068, +0.005) |
| 5 | press the button to stop | 49 ts | (-0.214, -0.087, +0.007) |

#### episode 15 — seed `1011500`，难度 hard，动作 5 次

目标：pick up the green cube and place it on the target, repeating this action five times, then press the button to stop

整条 848 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 105 ts | (-0.015, -0.035, +0.020) |
| 2 | place the green cube onto the target | 93 ts | (-0.136, -0.042, +0.005) |
| 3 | pick up the green cube for the second time | 75 ts | (-0.131, -0.043, +0.020) |
| 4 | place the green cube onto the target | 67 ts | (-0.136, -0.042, +0.005) |
| 5 | pick up the green cube for the third time | 74 ts | (-0.133, -0.045, +0.020) |
| 6 | place the green cube onto the target | 66 ts | (-0.136, -0.042, +0.005) |
| 7 | pick up the green cube for the fourth time | 75 ts | (-0.130, -0.043, +0.020) |
| 8 | place the green cube onto the target | 65 ts | (-0.136, -0.042, +0.005) |
| 9 | pick up the green cube for the fifth time | 75 ts | (-0.132, -0.045, +0.020) |
| 10 | place the green cube onto the target | 65 ts | (-0.136, -0.042, +0.005) |
| 11 | press the button to stop | 49 ts | (-0.231, +0.135, +0.007) |

#### episode 16 — seed `1011600`，难度 easy，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 620 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 105 ts | (-0.018, +0.092, +0.020) |
| 2 | place the red cube onto the target | 107 ts | (-0.182, +0.075, +0.005) |
| 3 | pick up the red cube for the second time | 79 ts | (-0.177, +0.075, +0.020) |
| 4 | place the red cube onto the target | 73 ts | (-0.182, +0.075, +0.005) |
| 5 | pick up the red cube for the third time | 77 ts | (-0.179, +0.074, +0.020) |
| 6 | place the red cube onto the target | 70 ts | (-0.182, +0.075, +0.005) |
| 7 | press the button to stop | 70 ts | (-0.198, -0.196, +0.007) |

#### episode 17 — seed `1011700`，难度 easy，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 415 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 109 ts | (-0.040, -0.169, +0.020) |
| 2 | place the green cube onto the target | 84 ts | (-0.032, +0.011, +0.005) |
| 3 | pick up the green cube for the second time | 70 ts | (-0.026, +0.010, +0.020) |
| 4 | place the green cube onto the target | 64 ts | (-0.032, +0.011, +0.005) |
| 5 | press the button to stop | 54 ts | (-0.185, +0.132, +0.007) |

#### episode 18 — seed `1011800`，难度 medium，动作 2 次

目标：pick up the blue cube and place it on the target, repeating this action two times, then press the button to stop

整条 432 timestep（其中收尾段 43）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 119 ts | (-0.071, +0.111, +0.020) |
| 2 | place the blue cube onto the target | 78 ts | (-0.094, -0.028, +0.005) |
| 3 | pick up the blue cube for the second time | 76 ts | (-0.091, -0.032, +0.020) |
| 4 | place the blue cube onto the target | 58 ts | (-0.094, -0.028, +0.005) |
| 5 | press the button to stop | 58 ts | (-0.248, -0.069, +0.007) |

#### episode 19 — seed `1011900`，难度 hard，动作 4 次

目标：pick up the green cube and place it on the target, repeating this action four times, then press the button to stop

整条 733 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 108 ts | (-0.037, -0.118, +0.020) |
| 2 | place the green cube onto the target | 93 ts | (-0.162, +0.038, +0.005) |
| 3 | pick up the green cube for the second time | 86 ts | (-0.159, +0.040, +0.020) |
| 4 | place the green cube onto the target | 65 ts | (-0.162, +0.038, +0.005) |
| 5 | pick up the green cube for the third time | 90 ts | (-0.157, +0.042, +0.020) |
| 6 | place the green cube onto the target | 64 ts | (-0.162, +0.038, +0.005) |
| 7 | pick up the green cube for the fourth time | 85 ts | (-0.160, +0.037, +0.020) |
| 8 | place the green cube onto the target | 65 ts | (-0.162, +0.038, +0.005) |
| 9 | press the button to stop | 42 ts | (-0.180, +0.191, +0.007) |

#### episode 20 — seed `1012000`，难度 easy，动作 3 次

目标：pick up the blue cube and place it on the target, repeating this action three times, then press the button to stop

整条 641 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 123 ts | (-0.163, +0.102, +0.020) |
| 2 | place the blue cube onto the target | 93 ts | (-0.255, +0.015, +0.005) |
| 3 | pick up the blue cube for the second time | 89 ts | (-0.252, +0.014, +0.020) |
| 4 | place the blue cube onto the target | 73 ts | (-0.255, +0.015, +0.005) |
| 5 | pick up the blue cube for the third time | 87 ts | (-0.252, +0.015, +0.020) |
| 6 | place the blue cube onto the target | 76 ts | (-0.255, +0.015, +0.005) |
| 7 | press the button to stop | 61 ts | (-0.169, -0.135, +0.007) |

#### episode 21 — seed `1012100`，难度 easy，动作 3 次

目标：pick up the blue cube and place it on the target, repeating this action three times, then press the button to stop

整条 559 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 104 ts | (-0.005, -0.073, +0.020) |
| 2 | place the blue cube onto the target | 86 ts | (-0.034, +0.131, +0.005) |
| 3 | pick up the blue cube for the second time | 70 ts | (-0.029, +0.133, +0.020) |
| 4 | place the blue cube onto the target | 66 ts | (-0.034, +0.131, +0.005) |
| 5 | pick up the blue cube for the third time | 69 ts | (-0.029, +0.128, +0.020) |
| 6 | place the blue cube onto the target | 66 ts | (-0.034, +0.131, +0.005) |
| 7 | press the button to stop | 59 ts | (-0.153, -0.018, +0.007) |

#### episode 22 — seed `1012200`，难度 medium，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 573 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 107 ts | (+0.069, +0.114, +0.020) |
| 2 | place the green cube onto the target | 88 ts | (-0.038, +0.111, +0.005) |
| 3 | pick up the green cube for the second time | 71 ts | (-0.029, +0.115, +0.020) |
| 4 | place the green cube onto the target | 66 ts | (-0.038, +0.111, +0.005) |
| 5 | pick up the green cube for the third time | 71 ts | (-0.029, +0.114, +0.020) |
| 6 | place the green cube onto the target | 66 ts | (-0.038, +0.111, +0.005) |
| 7 | press the button to stop | 67 ts | (-0.167, -0.057, +0.007) |

#### episode 23 — seed `1012300`，难度 hard，动作 5 次

目标：pick up the blue cube and place it on the target, repeating this action five times, then press the button to stop

整条 795 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 108 ts | (+0.050, -0.035, +0.020) |
| 2 | place the blue cube onto the target | 84 ts | (-0.005, +0.123, +0.005) |
| 3 | pick up the blue cube for the second time | 72 ts | (+0.001, +0.126, +0.020) |
| 4 | place the blue cube onto the target | 55 ts | (-0.005, +0.123, +0.005) |
| 5 | pick up the blue cube for the third time | 70 ts | (+0.002, +0.127, +0.020) |
| 6 | place the blue cube onto the target | 55 ts | (-0.005, +0.123, +0.005) |
| 7 | pick up the blue cube for the fourth time | 71 ts | (+0.003, +0.129, +0.020) |
| 8 | place the blue cube onto the target | 56 ts | (-0.005, +0.123, +0.005) |
| 9 | pick up the blue cube for the fifth time | 70 ts | (+0.002, +0.128, +0.020) |
| 10 | place the blue cube onto the target | 56 ts | (-0.005, +0.123, +0.005) |
| 11 | press the button to stop | 63 ts | (-0.206, -0.142, +0.007) |

#### episode 24 — seed `1012400`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 317 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 112 ts | (-0.104, -0.004, +0.020) |
| 2 | place the green cube onto the target | 101 ts | (-0.252, +0.103, +0.005) |
| 3 | press the button to stop | 70 ts | (-0.158, -0.171, +0.007) |

#### episode 25 — seed `1012500`，难度 easy，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 552 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 103 ts | (-0.028, +0.110, +0.020) |
| 2 | place the red cube onto the target | 81 ts | (-0.014, -0.003, +0.005) |
| 3 | pick up the red cube for the second time | 71 ts | (-0.006, -0.004, +0.020) |
| 4 | place the red cube onto the target | 67 ts | (-0.014, -0.003, +0.005) |
| 5 | pick up the red cube for the third time | 70 ts | (-0.009, -0.001, +0.020) |
| 6 | place the red cube onto the target | 67 ts | (-0.014, -0.003, +0.005) |
| 7 | press the button to stop | 58 ts | (-0.190, -0.058, +0.007) |

#### episode 26 — seed `1012600`，难度 medium，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 527 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 112 ts | (+0.067, +0.130, +0.020) |
| 2 | place the red cube onto the target | 76 ts | (-0.002, +0.049, +0.005) |
| 3 | pick up the red cube for the second time | 69 ts | (+0.002, +0.046, +0.020) |
| 4 | place the red cube onto the target | 55 ts | (-0.002, +0.049, +0.005) |
| 5 | pick up the red cube for the third time | 71 ts | (+0.005, +0.046, +0.020) |
| 6 | place the red cube onto the target | 55 ts | (-0.002, +0.049, +0.005) |
| 7 | press the button to stop | 55 ts | (-0.167, +0.131, +0.007) |

#### episode 27 — seed `1012700`，难度 hard，动作 5 次

目标：pick up the blue cube and place it on the target, repeating this action five times, then press the button to stop

整条 1006 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 101 ts | (+0.024, -0.016, +0.020) |
| 2 | place the blue cube onto the target | 111 ts | (-0.248, +0.131, +0.005) |
| 3 | pick up the blue cube for the second time | 90 ts | (-0.245, +0.132, +0.020) |
| 4 | place the blue cube onto the target | 74 ts | (-0.248, +0.131, +0.005) |
| 5 | pick up the blue cube for the third time | 89 ts | (-0.245, +0.134, +0.020) |
| 6 | place the blue cube onto the target | 78 ts | (-0.248, +0.131, +0.005) |
| 7 | pick up the blue cube for the fourth time | 92 ts | (-0.245, +0.135, +0.020) |
| 8 | place the blue cube onto the target | 86 ts | (-0.248, +0.131, +0.005) |
| 9 | pick up the blue cube for the fifth time | 96 ts | (-0.245, +0.134, +0.020) |
| 10 | place the blue cube onto the target | 89 ts | (-0.248, +0.131, +0.005) |
| 11 | press the button to stop | 62 ts | (-0.190, -0.162, +0.007) |

#### episode 28 — seed `1012800`，难度 easy，动作 3 次

目标：pick up the red cube and place it on the target, repeating this action three times, then press the button to stop

整条 549 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 104 ts | (+0.059, +0.059, +0.020) |
| 2 | place the red cube onto the target | 86 ts | (-0.045, +0.019, +0.005) |
| 3 | pick up the red cube for the second time | 70 ts | (-0.038, +0.019, +0.020) |
| 4 | place the red cube onto the target | 62 ts | (-0.045, +0.019, +0.005) |
| 5 | pick up the red cube for the third time | 71 ts | (-0.037, +0.020, +0.020) |
| 6 | place the red cube onto the target | 63 ts | (-0.045, +0.019, +0.005) |
| 7 | press the button to stop | 56 ts | (-0.174, -0.147, +0.007) |

#### episode 29 — seed `1012900`，难度 easy，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 410 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 102 ts | (+0.012, +0.118, +0.020) |
| 2 | place the green cube onto the target | 78 ts | (+0.041, -0.125, +0.005) |
| 3 | pick up the green cube for the second time | 75 ts | (+0.047, -0.129, +0.020) |
| 4 | place the green cube onto the target | 55 ts | (+0.041, -0.125, +0.005) |
| 5 | press the button to stop | 65 ts | (-0.182, -0.036, +0.007) |

#### episode 30 — seed `1013000`，难度 medium，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 306 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 103 ts | (+0.030, +0.057, +0.020) |
| 2 | place the blue cube onto the target | 96 ts | (-0.191, +0.145, +0.005) |
| 3 | press the button to stop | 66 ts | (-0.175, +0.003, +0.007) |

#### episode 31 — seed `1013100`，难度 hard，动作 5 次

目标：pick up the red cube and place it on the target, repeating this action five times, then press the button to stop

整条 841 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 122 ts | (-0.066, +0.118, +0.020) |
| 2 | place the red cube onto the target | 89 ts | (-0.059, -0.140, +0.005) |
| 3 | pick up the red cube for the second time | 69 ts | (-0.056, -0.143, +0.020) |
| 4 | place the red cube onto the target | 63 ts | (-0.059, -0.140, +0.005) |
| 5 | pick up the red cube for the third time | 70 ts | (-0.052, -0.143, +0.020) |
| 6 | place the red cube onto the target | 64 ts | (-0.059, -0.140, +0.005) |
| 7 | pick up the red cube for the fourth time | 70 ts | (-0.052, -0.142, +0.020) |
| 8 | place the red cube onto the target | 64 ts | (-0.059, -0.140, +0.005) |
| 9 | pick up the red cube for the fifth time | 70 ts | (-0.052, -0.142, +0.020) |
| 10 | place the red cube onto the target | 64 ts | (-0.059, -0.140, +0.005) |
| 11 | press the button to stop | 60 ts | (-0.205, +0.072, +0.007) |

#### episode 32 — seed `1013200`，难度 easy，动作 1 次

目标：pick up the blue cube and place it on the target, then press the button to stop

整条 270 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 103 ts | (-0.018, +0.052, +0.020) |
| 2 | place the blue cube onto the target | 88 ts | (-0.156, +0.099, +0.005) |
| 3 | press the button to stop | 43 ts | (-0.165, -0.071, +0.007) |

#### episode 33 — seed `1013300`，难度 easy，动作 1 次

目标：pick up the red cube and place it on the target, then press the button to stop

整条 339 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 128 ts | (-0.248, +0.177, +0.020) |
| 2 | place the red cube onto the target | 101 ts | (-0.029, -0.093, +0.005) |
| 3 | press the button to stop | 68 ts | (-0.243, -0.001, +0.007) |

#### episode 34 — seed `1013400`，难度 medium，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 483 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 139 ts | (-0.252, -0.164, +0.020) |
| 2 | place the green cube onto the target | 100 ts | (-0.014, +0.061, +0.005) |
| 3 | pick up the green cube for the second time | 70 ts | (-0.008, +0.063, +0.020) |
| 4 | place the green cube onto the target | 65 ts | (-0.014, +0.061, +0.005) |
| 5 | press the button to stop | 67 ts | (-0.215, -0.023, +0.007) |

#### episode 35 — seed `1013500`，难度 hard，动作 5 次

目标：pick up the blue cube and place it on the target, repeating this action five times, then press the button to stop

整条 797 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 110 ts | (-0.037, -0.090, +0.020) |
| 2 | place the blue cube onto the target | 85 ts | (-0.014, +0.141, +0.005) |
| 3 | pick up the blue cube for the second time | 70 ts | (-0.008, +0.144, +0.020) |
| 4 | place the blue cube onto the target | 55 ts | (-0.014, +0.141, +0.005) |
| 5 | pick up the blue cube for the third time | 70 ts | (-0.008, +0.143, +0.020) |
| 6 | place the blue cube onto the target | 55 ts | (-0.014, +0.141, +0.005) |
| 7 | pick up the blue cube for the fourth time | 70 ts | (-0.008, +0.144, +0.020) |
| 8 | place the blue cube onto the target | 55 ts | (-0.014, +0.141, +0.005) |
| 9 | pick up the blue cube for the fifth time | 71 ts | (-0.006, +0.145, +0.020) |
| 10 | place the blue cube onto the target | 56 ts | (-0.014, +0.141, +0.005) |
| 11 | press the button to stop | 64 ts | (-0.205, -0.040, +0.007) |

#### episode 36 — seed `1013600`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 530 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 104 ts | (+0.039, +0.131, +0.020) |
| 2 | place the green cube onto the target | 78 ts | (+0.032, -0.052, +0.005) |
| 3 | pick up the green cube for the second time | 72 ts | (+0.037, -0.052, +0.020) |
| 4 | place the green cube onto the target | 54 ts | (+0.032, -0.052, +0.005) |
| 5 | pick up the green cube for the third time | 71 ts | (+0.036, -0.051, +0.020) |
| 6 | place the green cube onto the target | 53 ts | (+0.032, -0.052, +0.005) |
| 7 | press the button to stop | 63 ts | (-0.177, -0.113, +0.007) |

#### episode 37 — seed `1013700`，难度 easy，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 419 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 105 ts | (+0.071, +0.066, +0.020) |
| 2 | place the red cube onto the target | 89 ts | (-0.084, +0.115, +0.005) |
| 3 | pick up the red cube for the second time | 80 ts | (-0.077, +0.117, +0.020) |
| 4 | place the red cube onto the target | 59 ts | (-0.084, +0.115, +0.005) |
| 5 | press the button to stop | 48 ts | (-0.153, -0.028, +0.007) |

#### episode 38 — seed `1013800`，难度 medium，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 425 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 105 ts | (-0.020, +0.094, +0.020) |
| 2 | place the red cube onto the target | 75 ts | (+0.051, +0.150, +0.005) |
| 3 | pick up the red cube for the second time | 75 ts | (+0.058, +0.148, +0.020) |
| 4 | place the red cube onto the target | 53 ts | (+0.051, +0.150, +0.005) |
| 5 | press the button to stop | 76 ts | (-0.224, -0.083, +0.007) |

#### episode 39 — seed `1013900`，难度 hard，动作 5 次

目标：pick up the red cube and place it on the target, repeating this action five times, then press the button to stop

整条 793 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 106 ts | (-0.026, +0.140, +0.020) |
| 2 | place the red cube onto the target | 75 ts | (+0.019, +0.029, +0.005) |
| 3 | pick up the red cube for the second time | 70 ts | (+0.025, +0.026, +0.020) |
| 4 | place the red cube onto the target | 55 ts | (+0.019, +0.029, +0.005) |
| 5 | pick up the red cube for the third time | 72 ts | (+0.027, +0.025, +0.020) |
| 6 | place the red cube onto the target | 55 ts | (+0.019, +0.029, +0.005) |
| 7 | pick up the red cube for the fourth time | 70 ts | (+0.026, +0.026, +0.020) |
| 8 | place the red cube onto the target | 55 ts | (+0.019, +0.029, +0.005) |
| 9 | pick up the red cube for the fifth time | 73 ts | (+0.028, +0.025, +0.020) |
| 10 | place the red cube onto the target | 56 ts | (+0.019, +0.029, +0.005) |
| 11 | press the button to stop | 67 ts | (-0.172, -0.137, +0.007) |

#### episode 40 — seed `1014000`，难度 easy，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 427 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 106 ts | (+0.019, -0.069, +0.020) |
| 2 | place the red cube onto the target | 83 ts | (-0.087, +0.041, +0.005) |
| 3 | pick up the red cube for the second time | 78 ts | (-0.084, +0.045, +0.020) |
| 4 | place the red cube onto the target | 60 ts | (-0.087, +0.041, +0.005) |
| 5 | press the button to stop | 58 ts | (-0.194, -0.101, +0.007) |

#### episode 41 — seed `1014100`，难度 easy，动作 3 次

目标：pick up the green cube and place it on the target, repeating this action three times, then press the button to stop

整条 613 timestep（其中收尾段 44）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 113 ts | (-0.083, -0.102, +0.020) |
| 2 | place the green cube onto the target | 95 ts | (-0.126, +0.114, +0.005) |
| 3 | pick up the green cube for the second time | 75 ts | (-0.120, +0.117, +0.020) |
| 4 | place the green cube onto the target | 71 ts | (-0.126, +0.114, +0.005) |
| 5 | pick up the green cube for the third time | 74 ts | (-0.121, +0.114, +0.020) |
| 6 | place the green cube onto the target | 71 ts | (-0.126, +0.114, +0.005) |
| 7 | press the button to stop | 70 ts | (-0.240, -0.146, +0.007) |

#### episode 42 — seed `1014200`，难度 medium，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 460 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 132 ts | (-0.260, -0.169, +0.020) |
| 2 | place the green cube onto the target | 98 ts | (-0.016, +0.016, +0.005) |
| 3 | pick up the green cube for the second time | 70 ts | (-0.010, +0.015, +0.020) |
| 4 | place the green cube onto the target | 67 ts | (-0.016, +0.016, +0.005) |
| 5 | press the button to stop | 59 ts | (-0.175, +0.128, +0.007) |

#### episode 43 — seed `1014300`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 677 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 108 ts | (+0.071, -0.068, +0.020) |
| 2 | place the blue cube onto the target | 68 ts | (+0.057, +0.054, +0.005) |
| 3 | pick up the blue cube for the second time | 74 ts | (+0.060, +0.056, +0.020) |
| 4 | place the blue cube onto the target | 54 ts | (+0.057, +0.054, +0.005) |
| 5 | pick up the blue cube for the third time | 77 ts | (+0.063, +0.058, +0.020) |
| 6 | place the blue cube onto the target | 54 ts | (+0.057, +0.054, +0.005) |
| 7 | pick up the blue cube for the fourth time | 76 ts | (+0.062, +0.058, +0.020) |
| 8 | place the blue cube onto the target | 54 ts | (+0.057, +0.054, +0.005) |
| 9 | press the button to stop | 74 ts | (-0.234, +0.047, +0.007) |

#### episode 44 — seed `1014400`，难度 easy，动作 2 次

目标：pick up the red cube and place it on the target, repeating this action two times, then press the button to stop

整条 435 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the red cube for the first time | 119 ts | (-0.177, -0.120, +0.020) |
| 2 | place the red cube onto the target | 89 ts | (+0.057, +0.092, +0.005) |
| 3 | pick up the red cube for the second time | 75 ts | (+0.063, +0.093, +0.020) |
| 4 | place the red cube onto the target | 54 ts | (+0.057, +0.092, +0.005) |
| 5 | press the button to stop | 62 ts | (-0.152, +0.126, +0.007) |

#### episode 45 — seed `1014500`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 295 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 106 ts | (+0.066, +0.052, +0.020) |
| 2 | place the green cube onto the target | 74 ts | (+0.015, -0.036, +0.005) |
| 3 | press the button to stop | 73 ts | (-0.219, -0.051, +0.007) |

#### episode 46 — seed `1014600`，难度 medium，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 316 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 105 ts | (+0.008, +0.162, +0.020) |
| 2 | place the green cube onto the target | 98 ts | (-0.154, -0.109, +0.005) |
| 3 | press the button to stop | 77 ts | (-0.164, +0.173, +0.007) |

#### episode 47 — seed `1014700`，难度 hard，动作 4 次

目标：pick up the blue cube and place it on the target, repeating this action four times, then press the button to stop

整条 692 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the blue cube for the first time | 120 ts | (-0.179, +0.056, +0.020) |
| 2 | place the blue cube onto the target | 87 ts | (+0.029, +0.098, +0.005) |
| 3 | pick up the blue cube for the second time | 72 ts | (+0.036, +0.097, +0.020) |
| 4 | place the blue cube onto the target | 53 ts | (+0.029, +0.098, +0.005) |
| 5 | pick up the blue cube for the third time | 72 ts | (+0.035, +0.097, +0.020) |
| 6 | place the blue cube onto the target | 53 ts | (+0.029, +0.098, +0.005) |
| 7 | pick up the blue cube for the fourth time | 73 ts | (+0.037, +0.097, +0.020) |
| 8 | place the blue cube onto the target | 54 ts | (+0.029, +0.098, +0.005) |
| 9 | press the button to stop | 69 ts | (-0.187, -0.060, +0.007) |

#### episode 48 — seed `1014800`，难度 easy，动作 1 次

目标：pick up the green cube and place it on the target, then press the button to stop

整条 292 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 106 ts | (+0.032, -0.097, +0.020) |
| 2 | place the green cube onto the target | 86 ts | (-0.037, -0.016, +0.005) |
| 3 | press the button to stop | 64 ts | (-0.227, +0.108, +0.007) |

#### episode 49 — seed `1014900`，难度 easy，动作 2 次

目标：pick up the green cube and place it on the target, repeating this action two times, then press the button to stop

整条 430 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the green cube for the first time | 109 ts | (-0.052, -0.098, +0.020) |
| 2 | place the green cube onto the target | 83 ts | (+0.045, +0.123, +0.005) |
| 3 | pick up the green cube for the second time | 73 ts | (+0.048, +0.122, +0.020) |
| 4 | place the green cube onto the target | 55 ts | (+0.045, +0.123, +0.005) |
| 5 | press the button to stop | 71 ts | (-0.152, +0.008, +0.007) |
