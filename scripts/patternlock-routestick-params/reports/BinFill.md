# BinFill 逐 episode 动作参数

共 100 条（test 50 + val 50，每条标出来源）。数据来源：val 来自原版 h5 `/data/hongzefu/data-0306/record_dataset_BinFill.h5`；test 本机无官方 h5，由本轮按 test metadata 死 seed 实跑生成。

口径：动作次数与颜色组成直接读 `setup/task_goal`（BinFill 是要放几个什么颜色的 cube，PickXtimes 是同一动作重复几次）；每次动作在数据里是 pick 与 place 两段，末尾再加一段 press button，所以核心段数 = 2 × 动作次数 + 1（本报告的每条都验过这条恒等式）。时长单位是 timestep（1 timestep = 1 个 env step = 0.05 s）。关键点坐标取该段内 z 最低的 `action/waypoint_action`（段首帧常残留上一段的值，不可用）——pick 段即 cube 位置、press 段即按钮位置、put 段即 bin 上方的松手点，SAPIEN 世界坐标、单位米（机器人 base 在 `(-0.615, 0, 0)`）；该帧没有关键点时记 —。

与 PatternLock / RouteStick 不同，这两个任务**没有视频演示段**，所以不存在「演示段 / 执行段」之分，下表每一行就是真正执行的一段。每行的子目标必是三类之一：`pick up …`（找到并抓起指定 cube）、`put / place …`（送到 bin 或 target）、`press …`（按按钮）；每次动作产生一对 pick + place，末尾另有一段 press。

#### test-ep0 — seed `540000`，难度 easy，动作 1 次

目标：put one red cube into the bin, then press the button to stop

整条 366 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 180 ts | (-0.133, -0.158, +0.020) |
| 2 | put it into the bin | 79 ts | (+0.075, +0.074, +0.200) |
| 3 | press the button | 66 ts | (-0.216, -0.030, +0.007) |

#### test-ep1 — seed `540101`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 361 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 186 ts | (-0.160, -0.183, +0.020) |
| 2 | put it into the bin | 81 ts | (+0.073, +0.081, +0.200) |
| 3 | press the button | 56 ts | (-0.185, +0.172, +0.007) |

#### test-ep2 — seed `540201`，难度 medium，动作 4 次

目标：put four green cubes into the bin, then press the button to stop

整条 837 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 103 ts | (-0.014, +0.116, +0.020) |
| 2 | put it into the bin | 58 ts | (-0.049, -0.147, +0.200) |
| 3 | pick up the second green cube | 99 ts | (-0.111, -0.030, +0.020) |
| 4 | put it into the bin | 57 ts | (-0.049, -0.147, +0.200) |
| 5 | pick up the third green cube | 151 ts | (-0.005, -0.047, +0.020) |
| 6 | put it into the bin | 55 ts | (-0.049, -0.147, +0.200) |
| 7 | pick up the fourth green cube | 132 ts | (-0.252, +0.066, +0.020) |
| 8 | put it into the bin | 71 ts | (-0.049, -0.147, +0.200) |
| 9 | press the button | 74 ts | (-0.247, -0.183, +0.007) |

#### test-ep3 — seed `540302`，难度 hard，动作 4 次

目标：put three red cubes and one green cube into the bin, then press the button to stop

整条 969 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 134 ts | (-0.200, +0.124, +0.020) |
| 2 | put it into the bin | 94 ts | (+0.123, +0.002, +0.200) |
| 3 | pick up the second red cube | 114 ts | (-0.242, +0.201, +0.020) |
| 4 | put it into the bin | 92 ts | (+0.123, +0.002, +0.200) |
| 5 | pick up the third red cube | 93 ts | (-0.036, -0.064, +0.020) |
| 6 | put it into the bin | 76 ts | (+0.123, +0.002, +0.200) |
| 7 | pick up the first green cube | 178 ts | (-0.107, +0.016, +0.020) |
| 8 | put it into the bin | 83 ts | (+0.123, +0.002, +0.200) |
| 9 | press the button | 64 ts | (-0.238, -0.184, +0.007) |

#### test-ep4 — seed `540400`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 397 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 210 ts | (-0.170, -0.069, +0.020) |
| 2 | put it into the bin | 87 ts | (+0.142, +0.021, +0.200) |
| 3 | press the button | 61 ts | (-0.162, +0.120, +0.007) |

#### test-ep5 — seed `540500`，难度 easy，动作 2 次

目标：put two green cubes into the bin, then press the button to stop

整条 517 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 121 ts | (-0.130, -0.080, +0.020) |
| 2 | put it into the bin | 62 ts | (-0.009, +0.172, +0.200) |
| 3 | pick up the second green cube | 183 ts | (-0.052, -0.049, +0.020) |
| 4 | put it into the bin | 61 ts | (-0.009, +0.172, +0.200) |
| 5 | press the button | 55 ts | (-0.156, +0.133, +0.007) |

#### test-ep6 — seed `540600`，难度 medium，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 420 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 106 ts | (+0.010, -0.019, +0.020) |
| 2 | put it into the bin | 52 ts | (+0.007, -0.175, +0.200) |
| 3 | pick up the second blue cube | 98 ts | (+0.034, +0.149, +0.020) |
| 4 | put it into the bin | 64 ts | (+0.007, -0.175, +0.200) |
| 5 | press the button | 60 ts | (-0.200, +0.049, +0.007) |

#### test-ep7 — seed `540701`，难度 hard，动作 5 次

目标：put one blue cube and four green cubes into the bin, then press the button to stop

整条 1080 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 105 ts | (-0.028, +0.098, +0.020) |
| 2 | put it into the bin | 65 ts | (+0.090, +0.094, +0.200) |
| 3 | pick up the second green cube | 121 ts | (-0.226, -0.005, +0.020) |
| 4 | put it into the bin | 82 ts | (+0.090, +0.094, +0.200) |
| 5 | pick up the third green cube | 113 ts | (-0.143, -0.113, +0.020) |
| 6 | put it into the bin | 76 ts | (+0.090, +0.094, +0.200) |
| 7 | pick up the fourth green cube | 126 ts | (-0.229, -0.220, +0.020) |
| 8 | put it into the bin | 88 ts | (+0.090, +0.094, +0.200) |
| 9 | pick up the first blue cube | 119 ts | (-0.070, -0.113, +0.020) |
| 10 | put it into the bin | 70 ts | (+0.090, +0.094, +0.200) |
| 11 | press the button | 76 ts | (-0.169, +0.150, +0.007) |

#### test-ep8 — seed `540800`，难度 easy，动作 3 次

目标：put three green cubes into the bin, then press the button to stop

整条 699 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 119 ts | (-0.100, +0.222, +0.020) |
| 2 | put it into the bin | 79 ts | (+0.125, +0.088, +0.200) |
| 3 | pick up the second green cube | 97 ts | (-0.073, +0.040, +0.020) |
| 4 | put it into the bin | 79 ts | (+0.125, +0.088, +0.200) |
| 5 | pick up the third green cube | 133 ts | (-0.270, +0.080, +0.020) |
| 6 | put it into the bin | 93 ts | (+0.125, +0.088, +0.200) |
| 7 | press the button | 65 ts | (-0.164, -0.181, +0.007) |

#### test-ep9 — seed `540900`，难度 easy，动作 2 次

目标：put two green cubes into the bin, then press the button to stop

整条 455 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 113 ts | (-0.050, -0.022, +0.020) |
| 2 | put it into the bin | 72 ts | (+0.108, -0.125, +0.200) |
| 3 | pick up the second green cube | 93 ts | (-0.121, +0.200, +0.020) |
| 4 | put it into the bin | 78 ts | (+0.108, -0.125, +0.200) |
| 5 | press the button | 65 ts | (-0.203, -0.164, +0.007) |

#### test-ep10 — seed `541000`，难度 medium，动作 4 次

目标：put one red cube and three green cubes into the bin, then press the button to stop

整条 812 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 110 ts | (+0.070, +0.137, +0.020) |
| 2 | put it into the bin | 69 ts | (+0.137, -0.134, +0.200) |
| 3 | pick up the second green cube | 92 ts | (-0.019, -0.076, +0.020) |
| 4 | put it into the bin | 76 ts | (+0.137, -0.134, +0.200) |
| 5 | pick up the third green cube | 103 ts | (-0.103, -0.039, +0.020) |
| 6 | put it into the bin | 83 ts | (+0.137, -0.134, +0.200) |
| 7 | pick up the first red cube | 76 ts | (+0.027, +0.011, +0.020) |
| 8 | put it into the bin | 82 ts | (+0.137, -0.134, +0.200) |
| 9 | press the button | 80 ts | (-0.200, +0.042, +0.007) |

#### test-ep11 — seed `541100`，难度 hard，动作 5 次

目标：put two red cubes, one blue cube and two green cubes into the bin, then press the button to stop

整条 1020 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 145 ts | (-0.276, +0.156, +0.020) |
| 2 | put it into the bin | 73 ts | (+0.014, +0.060, +0.200) |
| 3 | pick up the first red cube | 108 ts | (-0.183, +0.229, +0.020) |
| 4 | put it into the bin | 64 ts | (+0.014, +0.060, +0.200) |
| 5 | pick up the second red cube | 80 ts | (-0.098, +0.117, +0.020) |
| 6 | put it into the bin | 60 ts | (+0.014, +0.060, +0.200) |
| 7 | pick up the first green cube | 125 ts | (-0.264, -0.199, +0.020) |
| 8 | put it into the bin | 75 ts | (+0.014, +0.060, +0.200) |
| 9 | pick up the second green cube | 118 ts | (-0.177, -0.180, +0.020) |
| 10 | put it into the bin | 71 ts | (+0.014, +0.060, +0.200) |
| 11 | press the button | 64 ts | (-0.232, -0.018, +0.007) |

#### test-ep12 — seed `541200`，难度 easy，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 433 timestep（其中收尾段 33）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 111 ts | (+0.063, -0.010, +0.020) |
| 2 | put it into the bin | 55 ts | (+0.005, +0.193, +0.200) |
| 3 | pick up the second blue cube | 101 ts | (-0.185, +0.076, +0.020) |
| 4 | put it into the bin | 75 ts | (+0.005, +0.193, +0.200) |
| 5 | press the button | 58 ts | (-0.181, -0.163, +0.007) |

#### test-ep13 — seed `541300`，难度 easy，动作 3 次

目标：put three green cubes into the bin, then press the button to stop

整条 677 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 147 ts | (-0.272, +0.194, +0.020) |
| 2 | put it into the bin | 78 ts | (-0.028, -0.133, +0.200) |
| 3 | pick up the second green cube | 108 ts | (+0.065, +0.139, +0.020) |
| 4 | put it into the bin | 68 ts | (-0.028, -0.133, +0.200) |
| 5 | pick up the third green cube | 103 ts | (-0.001, +0.080, +0.020) |
| 6 | put it into the bin | 59 ts | (-0.028, -0.133, +0.200) |
| 7 | press the button | 76 ts | (-0.176, -0.164, +0.007) |

#### test-ep14 — seed `541400`，难度 medium，动作 3 次

目标：put three red cubes into the bin, then press the button to stop

整条 636 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 115 ts | (-0.068, -0.160, +0.020) |
| 2 | put it into the bin | 66 ts | (-0.049, +0.156, +0.200) |
| 3 | pick up the second red cube | 129 ts | (-0.256, -0.189, +0.020) |
| 4 | put it into the bin | 70 ts | (-0.049, +0.156, +0.200) |
| 5 | pick up the third red cube | 111 ts | (-0.011, -0.132, +0.020) |
| 6 | put it into the bin | 60 ts | (-0.049, +0.156, +0.200) |
| 7 | press the button | 49 ts | (-0.156, +0.076, +0.007) |

#### test-ep15 — seed `541500`，难度 hard，动作 5 次

目标：put four blue cubes and one green cube into the bin, then press the button to stop

整条 978 timestep（其中收尾段 33）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 101 ts | (+0.009, +0.060, +0.020) |
| 2 | put it into the bin | 70 ts | (+0.107, -0.083, +0.200) |
| 3 | pick up the second blue cube | 85 ts | (-0.057, +0.147, +0.020) |
| 4 | put it into the bin | 73 ts | (+0.107, -0.083, +0.200) |
| 5 | pick up the third blue cube | 123 ts | (-0.258, -0.173, +0.020) |
| 6 | put it into the bin | 84 ts | (+0.107, -0.083, +0.200) |
| 7 | pick up the fourth blue cube | 92 ts | (+0.071, +0.037, +0.020) |
| 8 | put it into the bin | 67 ts | (+0.107, -0.083, +0.200) |
| 9 | pick up the first green cube | 95 ts | (-0.057, -0.105, +0.020) |
| 10 | put it into the bin | 72 ts | (+0.107, -0.083, +0.200) |
| 11 | press the button | 83 ts | (-0.166, +0.142, +0.007) |

#### test-ep16 — seed `541601`，难度 easy，动作 1 次

目标：put one red cube into the bin, then press the button to stop

整条 308 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 136 ts | (-0.275, -0.141, +0.020) |
| 2 | put it into the bin | 73 ts | (+0.007, -0.139, +0.200) |
| 3 | press the button | 57 ts | (-0.225, +0.077, +0.007) |

#### test-ep17 — seed `541700`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 249 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 103 ts | (-0.008, +0.050, +0.020) |
| 2 | put it into the bin | 59 ts | (-0.039, -0.156, +0.200) |
| 3 | press the button | 51 ts | (-0.218, +0.067, +0.007) |

#### test-ep18 — seed `541802`，难度 medium，动作 2 次

目标：put two green cubes into the bin, then press the button to stop

整条 461 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 112 ts | (-0.035, +0.083, +0.020) |
| 2 | put it into the bin | 69 ts | (+0.055, -0.076, +0.200) |
| 3 | pick up the second green cube | 111 ts | (-0.111, -0.174, +0.020) |
| 4 | put it into the bin | 70 ts | (+0.055, -0.076, +0.200) |
| 5 | press the button | 61 ts | (-0.201, -0.044, +0.007) |

#### test-ep19 — seed `541900`，难度 hard，动作 5 次

目标：put three blue cubes and two green cubes into the bin, then press the button to stop

整条 994 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 132 ts | (-0.237, -0.038, +0.020) |
| 2 | put it into the bin | 72 ts | (-0.040, +0.193, +0.200) |
| 3 | pick up the second blue cube | 119 ts | (-0.073, +0.084, +0.020) |
| 4 | put it into the bin | 58 ts | (-0.040, +0.193, +0.200) |
| 5 | pick up the third blue cube | 107 ts | (-0.236, +0.017, +0.020) |
| 6 | put it into the bin | 71 ts | (-0.040, +0.193, +0.200) |
| 7 | pick up the first green cube | 102 ts | (-0.049, -0.114, +0.020) |
| 8 | put it into the bin | 61 ts | (-0.040, +0.193, +0.200) |
| 9 | pick up the second green cube | 100 ts | (-0.135, -0.062, +0.020) |
| 10 | put it into the bin | 68 ts | (-0.040, +0.193, +0.200) |
| 11 | press the button | 67 ts | (-0.189, +0.126, +0.007) |

#### test-ep20 — seed `542001`，难度 easy，动作 3 次

目标：put three blue cubes into the bin, then press the button to stop

整条 599 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 117 ts | (-0.163, -0.220, +0.020) |
| 2 | put it into the bin | 69 ts | (+0.011, +0.059, +0.200) |
| 3 | pick up the second blue cube | 94 ts | (-0.097, -0.002, +0.020) |
| 4 | put it into the bin | 59 ts | (+0.011, +0.059, +0.200) |
| 5 | pick up the third blue cube | 93 ts | (-0.074, +0.180, +0.020) |
| 6 | put it into the bin | 54 ts | (+0.011, +0.059, +0.200) |
| 7 | press the button | 73 ts | (-0.218, +0.065, +0.007) |

#### test-ep21 — seed `542100`，难度 easy，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 417 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 112 ts | (-0.041, -0.022, +0.020) |
| 2 | put it into the bin | 58 ts | (+0.001, +0.156, +0.200) |
| 3 | pick up the second red cube | 94 ts | (+0.031, -0.024, +0.020) |
| 4 | put it into the bin | 56 ts | (+0.001, +0.156, +0.200) |
| 5 | press the button | 60 ts | (-0.202, -0.198, +0.007) |

#### test-ep22 — seed `542200`，难度 medium，动作 4 次

目标：put four blue cubes into the bin, then press the button to stop

整条 808 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 133 ts | (-0.256, +0.165, +0.020) |
| 2 | put it into the bin | 66 ts | (-0.041, +0.051, +0.200) |
| 3 | pick up the second blue cube | 103 ts | (+0.064, +0.008, +0.020) |
| 4 | put it into the bin | 58 ts | (-0.041, +0.051, +0.200) |
| 5 | pick up the third blue cube | 112 ts | (+0.050, -0.226, +0.020) |
| 6 | put it into the bin | 71 ts | (-0.041, +0.051, +0.200) |
| 7 | pick up the fourth blue cube | 108 ts | (-0.157, +0.219, +0.020) |
| 8 | put it into the bin | 61 ts | (-0.041, +0.051, +0.200) |
| 9 | press the button | 62 ts | (-0.197, -0.149, +0.007) |

#### test-ep23 — seed `542300`，难度 hard，动作 3 次

目标：put two blue cubes and one green cube into the bin, then press the button to stop

整条 632 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 139 ts | (-0.270, +0.173, +0.020) |
| 2 | put it into the bin | 77 ts | (+0.008, +0.175, +0.200) |
| 3 | pick up the second blue cube | 103 ts | (+0.043, +0.055, +0.020) |
| 4 | put it into the bin | 49 ts | (+0.008, +0.175, +0.200) |
| 5 | pick up the first green cube | 97 ts | (-0.086, -0.145, +0.020) |
| 6 | put it into the bin | 67 ts | (+0.008, +0.175, +0.200) |
| 7 | press the button | 60 ts | (-0.215, -0.001, +0.007) |

#### test-ep24 — seed `542400`，难度 easy，动作 3 次

目标：put three green cubes into the bin, then press the button to stop

整条 624 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 119 ts | (-0.175, -0.159, +0.020) |
| 2 | put it into the bin | 67 ts | (-0.048, +0.180, +0.200) |
| 3 | pick up the second green cube | 106 ts | (+0.071, +0.112, +0.020) |
| 4 | put it into the bin | 58 ts | (-0.048, +0.180, +0.200) |
| 5 | pick up the third green cube | 99 ts | (+0.028, -0.062, +0.020) |
| 6 | put it into the bin | 63 ts | (-0.048, +0.180, +0.200) |
| 7 | press the button | 74 ts | (-0.157, -0.018, +0.007) |

#### test-ep25 — seed `542500`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 309 timestep（其中收尾段 46）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 123 ts | (-0.234, +0.182, +0.020) |
| 2 | put it into the bin | 80 ts | (+0.067, -0.026, +0.200) |
| 3 | press the button | 60 ts | (-0.246, -0.163, +0.007) |

#### test-ep26 — seed `542600`，难度 medium，动作 4 次

目标：put four red cubes into the bin, then press the button to stop

整条 705 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 107 ts | (-0.078, -0.186, +0.020) |
| 2 | put it into the bin | 57 ts | (+0.007, -0.103, +0.200) |
| 3 | pick up the second red cube | 93 ts | (-0.097, -0.104, +0.020) |
| 4 | put it into the bin | 62 ts | (+0.007, -0.103, +0.200) |
| 5 | pick up the third red cube | 83 ts | (-0.026, +0.070, +0.020) |
| 6 | put it into the bin | 54 ts | (+0.007, -0.103, +0.200) |
| 7 | pick up the fourth red cube | 98 ts | (+0.046, +0.160, +0.020) |
| 8 | put it into the bin | 60 ts | (+0.007, -0.103, +0.200) |
| 9 | press the button | 54 ts | (-0.200, +0.064, +0.007) |

#### test-ep27 — seed `542700`，难度 hard，动作 3 次

目标：put one red cube and two blue cubes into the bin, then press the button to stop

整条 626 timestep（其中收尾段 44）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 104 ts | (+0.009, -0.029, +0.020) |
| 2 | put it into the bin | 65 ts | (+0.060, +0.134, +0.200) |
| 3 | pick up the second blue cube | 97 ts | (-0.130, +0.069, +0.020) |
| 4 | put it into the bin | 79 ts | (+0.060, +0.134, +0.200) |
| 5 | pick up the first red cube | 99 ts | (+0.043, -0.182, +0.020) |
| 6 | put it into the bin | 65 ts | (+0.060, +0.134, +0.200) |
| 7 | press the button | 73 ts | (-0.225, -0.106, +0.007) |

#### test-ep28 — seed `542800`，难度 easy，动作 1 次

目标：put one blue cube into the bin, then press the button to stop

整条 251 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 107 ts | (-0.016, -0.012, +0.020) |
| 2 | put it into the bin | 55 ts | (+0.015, -0.157, +0.200) |
| 3 | press the button | 54 ts | (-0.152, -0.118, +0.007) |

#### test-ep29 — seed `542900`，难度 easy，动作 3 次

目标：put three red cubes into the bin, then press the button to stop

整条 690 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 128 ts | (-0.141, -0.119, +0.020) |
| 2 | put it into the bin | 82 ts | (+0.116, -0.006, +0.200) |
| 3 | pick up the second red cube | 79 ts | (-0.006, +0.151, +0.020) |
| 4 | put it into the bin | 66 ts | (+0.116, -0.006, +0.200) |
| 5 | pick up the third red cube | 129 ts | (-0.254, -0.000, +0.020) |
| 6 | put it into the bin | 92 ts | (+0.116, -0.006, +0.200) |
| 7 | press the button | 80 ts | (-0.160, +0.169, +0.007) |

#### test-ep30 — seed `543000`，难度 medium，动作 4 次

目标：put three red cubes and one green cube into the bin, then press the button to stop

整条 782 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 126 ts | (-0.226, +0.168, +0.020) |
| 2 | put it into the bin | 68 ts | (+0.016, +0.024, +0.200) |
| 3 | pick up the second red cube | 89 ts | (-0.126, +0.074, +0.020) |
| 4 | put it into the bin | 63 ts | (+0.016, +0.024, +0.200) |
| 5 | pick up the third red cube | 99 ts | (-0.142, -0.102, +0.020) |
| 6 | put it into the bin | 63 ts | (+0.016, +0.024, +0.200) |
| 7 | pick up the first green cube | 105 ts | (+0.067, -0.207, +0.020) |
| 8 | put it into the bin | 59 ts | (+0.016, +0.024, +0.200) |
| 9 | press the button | 72 ts | (-0.213, -0.198, +0.007) |

#### test-ep31 — seed `543100`，难度 hard，动作 3 次

目标：put one red cube and two green cubes into the bin, then press the button to stop

整条 703 timestep（其中收尾段 33）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 142 ts | (-0.278, +0.183, +0.020) |
| 2 | put it into the bin | 84 ts | (+0.069, +0.048, +0.200) |
| 3 | pick up the second green cube | 102 ts | (-0.119, -0.188, +0.020) |
| 4 | put it into the bin | 75 ts | (+0.069, +0.048, +0.200) |
| 5 | pick up the first red cube | 129 ts | (-0.198, -0.173, +0.020) |
| 6 | put it into the bin | 80 ts | (+0.069, +0.048, +0.200) |
| 7 | press the button | 58 ts | (-0.169, -0.002, +0.007) |

#### test-ep32 — seed `543200`，难度 easy，动作 3 次

目标：put three green cubes into the bin, then press the button to stop

整条 626 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 131 ts | (-0.243, +0.160, +0.020) |
| 2 | put it into the bin | 85 ts | (+0.067, -0.093, +0.200) |
| 3 | pick up the second green cube | 88 ts | (+0.037, +0.034, +0.020) |
| 4 | put it into the bin | 57 ts | (+0.067, -0.093, +0.200) |
| 5 | pick up the third green cube | 88 ts | (+0.024, +0.227, +0.020) |
| 6 | put it into the bin | 63 ts | (+0.067, -0.093, +0.200) |
| 7 | press the button | 78 ts | (-0.188, -0.107, +0.007) |

#### test-ep33 — seed `543300`，难度 easy，动作 3 次

目标：put three green cubes into the bin, then press the button to stop

整条 669 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 128 ts | (-0.213, +0.053, +0.020) |
| 2 | put it into the bin | 89 ts | (+0.095, +0.147, +0.200) |
| 3 | pick up the second green cube | 91 ts | (+0.044, -0.113, +0.020) |
| 4 | put it into the bin | 63 ts | (+0.095, +0.147, +0.200) |
| 5 | pick up the third green cube | 100 ts | (-0.134, -0.009, +0.020) |
| 6 | put it into the bin | 79 ts | (+0.095, +0.147, +0.200) |
| 7 | press the button | 80 ts | (-0.237, -0.077, +0.007) |

#### test-ep34 — seed `543400`，难度 medium，动作 3 次

目标：put three blue cubes into the bin, then press the button to stop

整条 632 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 125 ts | (-0.179, +0.053, +0.020) |
| 2 | put it into the bin | 64 ts | (-0.047, +0.109, +0.200) |
| 3 | pick up the second blue cube | 115 ts | (-0.267, +0.022, +0.020) |
| 4 | put it into the bin | 75 ts | (-0.047, +0.109, +0.200) |
| 5 | pick up the third blue cube | 97 ts | (+0.002, -0.224, +0.020) |
| 6 | put it into the bin | 68 ts | (-0.047, +0.109, +0.200) |
| 7 | press the button | 48 ts | (-0.208, -0.096, +0.007) |

#### test-ep35 — seed `543501`，难度 hard，动作 4 次

目标：put one red cube, two blue cubes and one green cube into the bin, then press the button to stop

整条 893 timestep（其中收尾段 44）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 106 ts | (+0.015, -0.211, +0.020) |
| 2 | put it into the bin | 71 ts | (+0.133, -0.131, +0.200) |
| 3 | pick up the first red cube | 96 ts | (-0.108, -0.170, +0.020) |
| 4 | put it into the bin | 83 ts | (+0.133, -0.131, +0.200) |
| 5 | pick up the first blue cube | 114 ts | (-0.195, -0.192, +0.020) |
| 6 | put it into the bin | 85 ts | (+0.133, -0.131, +0.200) |
| 7 | pick up the second blue cube | 128 ts | (-0.270, +0.126, +0.020) |
| 8 | put it into the bin | 96 ts | (+0.133, -0.131, +0.200) |
| 9 | press the button | 70 ts | (-0.207, -0.043, +0.007) |

#### test-ep36 — seed `543600`，难度 easy，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 438 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 107 ts | (-0.042, +0.222, +0.020) |
| 2 | put it into the bin | 64 ts | (+0.090, +0.127, +0.200) |
| 3 | pick up the second blue cube | 99 ts | (+0.029, -0.215, +0.020) |
| 4 | put it into the bin | 74 ts | (+0.090, +0.127, +0.200) |
| 5 | press the button | 60 ts | (-0.173, +0.150, +0.007) |

#### test-ep37 — seed `543700`，难度 easy，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 449 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 129 ts | (-0.225, -0.134, +0.020) |
| 2 | put it into the bin | 68 ts | (+0.002, -0.074, +0.200) |
| 3 | pick up the second blue cube | 96 ts | (-0.063, +0.177, +0.020) |
| 4 | put it into the bin | 62 ts | (+0.002, -0.074, +0.200) |
| 5 | press the button | 54 ts | (-0.212, +0.085, +0.007) |

#### test-ep38 — seed `543800`，难度 medium，动作 3 次

目标：put three green cubes into the bin, then press the button to stop

整条 626 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 127 ts | (-0.157, +0.210, +0.020) |
| 2 | put it into the bin | 78 ts | (-0.015, -0.150, +0.200) |
| 3 | pick up the second green cube | 89 ts | (-0.155, +0.104, +0.020) |
| 4 | put it into the bin | 70 ts | (-0.015, -0.150, +0.200) |
| 5 | pick up the third green cube | 99 ts | (-0.012, +0.169, +0.020) |
| 6 | put it into the bin | 66 ts | (-0.015, -0.150, +0.200) |
| 7 | press the button | 55 ts | (-0.221, -0.065, +0.007) |

#### test-ep39 — seed `543900`，难度 hard，动作 5 次

目标：put two red cubes and three green cubes into the bin, then press the button to stop

整条 917 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 111 ts | (+0.075, +0.068, +0.020) |
| 2 | put it into the bin | 54 ts | (-0.024, +0.191, +0.200) |
| 3 | pick up the second green cube | 104 ts | (-0.089, -0.218, +0.020) |
| 4 | put it into the bin | 67 ts | (-0.024, +0.191, +0.200) |
| 5 | pick up the third green cube | 109 ts | (-0.045, +0.058, +0.020) |
| 6 | put it into the bin | 56 ts | (-0.024, +0.191, +0.200) |
| 7 | pick up the first red cube | 87 ts | (-0.035, -0.088, +0.020) |
| 8 | put it into the bin | 65 ts | (-0.024, +0.191, +0.200) |
| 9 | pick up the second red cube | 108 ts | (-0.199, +0.026, +0.020) |
| 10 | put it into the bin | 68 ts | (-0.024, +0.191, +0.200) |
| 11 | press the button | 51 ts | (-0.155, -0.095, +0.007) |

#### test-ep40 — seed `544000`，难度 easy，动作 2 次

目标：put two green cubes into the bin, then press the button to stop

整条 447 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 133 ts | (-0.267, -0.037, +0.020) |
| 2 | put it into the bin | 70 ts | (-0.047, -0.015, +0.200) |
| 3 | pick up the second green cube | 99 ts | (-0.209, -0.209, +0.020) |
| 4 | put it into the bin | 65 ts | (-0.047, -0.015, +0.200) |
| 5 | press the button | 42 ts | (-0.165, +0.117, +0.007) |

#### test-ep41 — seed `544100`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 273 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 119 ts | (-0.188, -0.143, +0.020) |
| 2 | put it into the bin | 65 ts | (-0.034, -0.194, +0.200) |
| 3 | press the button | 52 ts | (-0.160, +0.084, +0.007) |

#### test-ep42 — seed `544200`，难度 medium，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 509 timestep（其中收尾段 44）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 124 ts | (-0.166, -0.112, +0.020) |
| 2 | put it into the bin | 92 ts | (+0.120, +0.048, +0.200) |
| 3 | pick up the second red cube | 101 ts | (-0.142, -0.208, +0.020) |
| 4 | put it into the bin | 78 ts | (+0.120, +0.048, +0.200) |
| 5 | press the button | 70 ts | (-0.244, +0.059, +0.007) |

#### test-ep43 — seed `544300`，难度 hard，动作 4 次

目标：put one red cube, two blue cubes and one green cube into the bin, then press the button to stop

整条 932 timestep（其中收尾段 45）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 116 ts | (-0.123, +0.030, +0.020) |
| 2 | put it into the bin | 73 ts | (+0.074, -0.010, +0.200) |
| 3 | pick up the first green cube | 105 ts | (+0.036, +0.143, +0.020) |
| 4 | put it into the bin | 58 ts | (+0.074, -0.010, +0.200) |
| 5 | pick up the first blue cube | 101 ts | (-0.062, -0.009, +0.020) |
| 6 | put it into the bin | 68 ts | (+0.074, -0.010, +0.200) |
| 7 | pick up the second blue cube | 149 ts | (-0.244, +0.195, +0.020) |
| 8 | put it into the bin | 91 ts | (+0.074, -0.010, +0.200) |
| 9 | press the button | 126 ts | (-0.195, -0.171, +0.007) |

#### test-ep44 — seed `544400`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 275 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 114 ts | (-0.102, -0.067, +0.020) |
| 2 | put it into the bin | 58 ts | (-0.016, -0.169, +0.200) |
| 3 | press the button | 65 ts | (-0.230, +0.050, +0.007) |

#### test-ep45 — seed `544500`，难度 easy，动作 3 次

目标：put three blue cubes into the bin, then press the button to stop

整条 605 timestep（其中收尾段 47）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 111 ts | (+0.067, +0.061, +0.020) |
| 2 | put it into the bin | 59 ts | (-0.036, -0.108, +0.200) |
| 3 | pick up the second blue cube | 118 ts | (-0.079, +0.206, +0.020) |
| 4 | put it into the bin | 73 ts | (-0.036, -0.108, +0.200) |
| 5 | pick up the third blue cube | 89 ts | (-0.130, -0.229, +0.020) |
| 6 | put it into the bin | 56 ts | (-0.036, -0.108, +0.200) |
| 7 | press the button | 52 ts | (-0.220, +0.056, +0.007) |

#### test-ep46 — seed `544600`，难度 medium，动作 3 次

目标：put one blue cube and two green cubes into the bin, then press the button to stop

整条 637 timestep（其中收尾段 33）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 102 ts | (-0.033, +0.155, +0.020) |
| 2 | put it into the bin | 74 ts | (+0.100, -0.147, +0.200) |
| 3 | pick up the first green cube | 116 ts | (-0.127, +0.119, +0.020) |
| 4 | put it into the bin | 76 ts | (+0.100, -0.147, +0.200) |
| 5 | pick up the second green cube | 94 ts | (-0.099, +0.179, +0.020) |
| 6 | put it into the bin | 76 ts | (+0.100, -0.147, +0.200) |
| 7 | press the button | 66 ts | (-0.170, -0.063, +0.007) |

#### test-ep47 — seed `544700`，难度 hard，动作 5 次

目标：put five blue cubes into the bin, then press the button to stop

整条 971 timestep（其中收尾段 47）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 128 ts | (-0.239, +0.058, +0.020) |
| 2 | put it into the bin | 83 ts | (+0.097, -0.094, +0.200) |
| 3 | pick up the second blue cube | 95 ts | (-0.078, -0.185, +0.020) |
| 4 | put it into the bin | 76 ts | (+0.097, -0.094, +0.200) |
| 5 | pick up the third blue cube | 91 ts | (+0.050, +0.169, +0.020) |
| 6 | put it into the bin | 64 ts | (+0.097, -0.094, +0.200) |
| 7 | pick up the fourth blue cube | 77 ts | (-0.012, -0.096, +0.020) |
| 8 | put it into the bin | 66 ts | (+0.097, -0.094, +0.200) |
| 9 | pick up the fifth blue cube | 96 ts | (-0.101, -0.066, +0.020) |
| 10 | put it into the bin | 73 ts | (+0.097, -0.094, +0.200) |
| 11 | press the button | 75 ts | (-0.230, -0.096, +0.007) |

#### test-ep48 — seed `544800`，难度 easy，动作 1 次

目标：put one red cube into the bin, then press the button to stop

整条 308 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 110 ts | (-0.046, +0.184, +0.020) |
| 2 | put it into the bin | 86 ts | (+0.138, +0.143, +0.200) |
| 3 | press the button | 75 ts | (-0.198, -0.044, +0.007) |

#### test-ep49 — seed `544900`，难度 easy，动作 3 次

目标：put three blue cubes into the bin, then press the button to stop

整条 641 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 120 ts | (-0.117, +0.228, +0.020) |
| 2 | put it into the bin | 72 ts | (+0.093, +0.008, +0.200) |
| 3 | pick up the second blue cube | 110 ts | (-0.167, -0.064, +0.020) |
| 4 | put it into the bin | 82 ts | (+0.093, +0.008, +0.200) |
| 5 | pick up the third blue cube | 78 ts | (-0.054, +0.165, +0.020) |
| 6 | put it into the bin | 71 ts | (+0.093, +0.008, +0.200) |
| 7 | press the button | 73 ts | (-0.150, -0.173, +0.007) |

#### val-ep0 — seed `1040000`，难度 easy，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 550 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 121 ts | (-0.194, -0.182, +0.020) |
| 2 | put it into the bin | 65 ts | (+0.012, -0.082, +0.200) |
| 3 | pick up the second red cube | 183 ts | (-0.277, +0.225, +0.020) |
| 4 | put it into the bin | 79 ts | (+0.012, -0.082, +0.200) |
| 5 | press the button | 61 ts | (-0.241, +0.072, +0.007) |

#### val-ep1 — seed `1040100`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 330 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 161 ts | (-0.009, -0.067, +0.020) |
| 2 | put it into the bin | 61 ts | (-0.016, +0.152, +0.200) |
| 3 | press the button | 68 ts | (-0.186, -0.107, +0.007) |

#### val-ep2 — seed `1040200`，难度 medium，动作 3 次

目标：put one blue cube and two green cubes into the bin, then press the button to stop

整条 722 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 195 ts | (-0.221, -0.110, +0.020) |
| 2 | put it into the bin | 83 ts | (+0.093, -0.192, +0.200) |
| 3 | pick up the second green cube | 83 ts | (+0.008, -0.006, +0.020) |
| 4 | put it into the bin | 66 ts | (+0.093, -0.192, +0.200) |
| 5 | pick up the first blue cube | 90 ts | (-0.059, +0.223, +0.020) |
| 6 | put it into the bin | 79 ts | (+0.093, -0.192, +0.200) |
| 7 | press the button | 87 ts | (-0.200, +0.173, +0.007) |

#### val-ep3 — seed `1040300`，难度 hard，动作 4 次

目标：put two red cubes, one blue cube and one green cube into the bin, then press the button to stop

整条 918 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 110 ts | (+0.078, +0.046, +0.020) |
| 2 | put it into the bin | 53 ts | (+0.084, +0.175, +0.200) |
| 3 | pick up the first blue cube | 182 ts | (-0.145, +0.246, +0.020) |
| 4 | put it into the bin | 77 ts | (+0.084, +0.175, +0.200) |
| 5 | pick up the first red cube | 115 ts | (-0.158, +0.024, +0.020) |
| 6 | put it into the bin | 78 ts | (+0.084, +0.175, +0.200) |
| 7 | pick up the second red cube | 116 ts | (-0.229, +0.068, +0.020) |
| 8 | put it into the bin | 87 ts | (+0.084, +0.175, +0.200) |
| 9 | press the button | 62 ts | (-0.200, -0.126, +0.007) |

#### val-ep4 — seed `1040400`，难度 easy，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 602 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 118 ts | (-0.181, -0.177, +0.020) |
| 2 | put it into the bin | 89 ts | (+0.132, +0.059, +0.200) |
| 3 | pick up the second red cube | 204 ts | (-0.240, +0.233, +0.020) |
| 4 | put it into the bin | 87 ts | (+0.132, +0.059, +0.200) |
| 5 | press the button | 69 ts | (-0.174, +0.035, +0.007) |

#### val-ep5 — seed `1040500`，难度 easy，动作 3 次

目标：put three red cubes into the bin, then press the button to stop

整条 689 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 208 ts | (-0.161, -0.214, +0.020) |
| 2 | put it into the bin | 71 ts | (+0.067, +0.049, +0.200) |
| 3 | pick up the second red cube | 88 ts | (-0.038, -0.205, +0.020) |
| 4 | put it into the bin | 65 ts | (+0.067, +0.049, +0.200) |
| 5 | pick up the third red cube | 86 ts | (-0.035, -0.001, +0.020) |
| 6 | put it into the bin | 64 ts | (+0.067, +0.049, +0.200) |
| 7 | press the button | 65 ts | (-0.228, +0.111, +0.007) |

#### val-ep6 — seed `1040601`，难度 medium，动作 3 次

目标：put two red cubes and one blue cube into the bin, then press the button to stop

整条 647 timestep（其中收尾段 43）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 124 ts | (-0.184, -0.127, +0.020) |
| 2 | put it into the bin | 80 ts | (+0.038, -0.194, +0.200) |
| 3 | pick up the first red cube | 98 ts | (+0.062, -0.006, +0.020) |
| 4 | put it into the bin | 58 ts | (+0.038, -0.194, +0.200) |
| 5 | pick up the second red cube | 102 ts | (-0.018, -0.072, +0.020) |
| 6 | put it into the bin | 66 ts | (+0.038, -0.194, +0.200) |
| 7 | press the button | 76 ts | (-0.228, +0.132, +0.007) |

#### val-ep7 — seed `1040700`，难度 hard，动作 3 次

目标：put one red cube, one blue cube and one green cube into the bin, then press the button to stop

整条 609 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 123 ts | (-0.188, -0.217, +0.020) |
| 2 | put it into the bin | 77 ts | (+0.072, +0.139, +0.200) |
| 3 | pick up the first red cube | 88 ts | (-0.003, -0.006, +0.020) |
| 4 | put it into the bin | 68 ts | (+0.072, +0.139, +0.200) |
| 5 | pick up the first blue cube | 89 ts | (+0.056, -0.089, +0.020) |
| 6 | put it into the bin | 65 ts | (+0.072, +0.139, +0.200) |
| 7 | press the button | 59 ts | (-0.198, +0.105, +0.007) |

#### val-ep8 — seed `1040800`，难度 easy，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 425 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 108 ts | (-0.051, +0.038, +0.020) |
| 2 | put it into the bin | 57 ts | (+0.011, -0.071, +0.200) |
| 3 | pick up the second red cube | 87 ts | (-0.109, -0.085, +0.020) |
| 4 | put it into the bin | 60 ts | (+0.011, -0.071, +0.200) |
| 5 | press the button | 76 ts | (-0.168, +0.122, +0.007) |

#### val-ep9 — seed `1040901`，难度 easy，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 472 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 116 ts | (-0.060, -0.100, +0.020) |
| 2 | put it into the bin | 67 ts | (+0.085, -0.035, +0.200) |
| 3 | pick up the second blue cube | 106 ts | (-0.062, +0.020, +0.020) |
| 4 | put it into the bin | 70 ts | (+0.085, -0.035, +0.200) |
| 5 | press the button | 76 ts | (-0.209, -0.013, +0.007) |

#### val-ep10 — seed `1041000`，难度 medium，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 520 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 125 ts | (-0.228, +0.187, +0.020) |
| 2 | put it into the bin | 83 ts | (+0.058, +0.183, +0.200) |
| 3 | pick up the second blue cube | 132 ts | (-0.274, +0.115, +0.020) |
| 4 | put it into the bin | 86 ts | (+0.058, +0.183, +0.200) |
| 5 | press the button | 59 ts | (-0.202, -0.127, +0.007) |

#### val-ep11 — seed `1041100`，难度 hard，动作 5 次

目标：put three red cubes and two green cubes into the bin, then press the button to stop

整条 1097 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 118 ts | (-0.180, -0.140, +0.020) |
| 2 | put it into the bin | 93 ts | (+0.137, +0.174, +0.200) |
| 3 | pick up the second green cube | 103 ts | (+0.000, +0.220, +0.020) |
| 4 | put it into the bin | 79 ts | (+0.137, +0.174, +0.200) |
| 5 | pick up the first red cube | 114 ts | (-0.156, -0.067, +0.020) |
| 6 | put it into the bin | 99 ts | (+0.137, +0.174, +0.200) |
| 7 | pick up the second red cube | 91 ts | (+0.015, +0.134, +0.020) |
| 8 | put it into the bin | 77 ts | (+0.137, +0.174, +0.200) |
| 9 | pick up the third red cube | 110 ts | (-0.199, +0.213, +0.020) |
| 10 | put it into the bin | 97 ts | (+0.137, +0.174, +0.200) |
| 11 | press the button | 79 ts | (-0.214, +0.080, +0.007) |

#### val-ep12 — seed `1041201`，难度 easy，动作 2 次

目标：put two green cubes into the bin, then press the button to stop

整条 488 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 135 ts | (-0.245, +0.064, +0.020) |
| 2 | put it into the bin | 83 ts | (+0.085, +0.042, +0.200) |
| 3 | pick up the second green cube | 100 ts | (-0.063, +0.088, +0.020) |
| 4 | put it into the bin | 73 ts | (+0.085, +0.042, +0.200) |
| 5 | press the button | 61 ts | (-0.238, -0.183, +0.007) |

#### val-ep13 — seed `1041300`，难度 easy，动作 1 次

目标：put one red cube into the bin, then press the button to stop

整条 275 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 121 ts | (-0.128, -0.051, +0.020) |
| 2 | put it into the bin | 61 ts | (-0.010, -0.132, +0.200) |
| 3 | press the button | 56 ts | (-0.244, -0.186, +0.007) |

#### val-ep14 — seed `1041402`，难度 medium，动作 4 次

目标：put two blue cubes and two green cubes into the bin, then press the button to stop

整条 785 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 128 ts | (-0.245, -0.164, +0.020) |
| 2 | put it into the bin | 69 ts | (+0.010, +0.049, +0.200) |
| 3 | pick up the second blue cube | 121 ts | (-0.231, -0.082, +0.020) |
| 4 | put it into the bin | 76 ts | (+0.010, +0.049, +0.200) |
| 5 | pick up the first green cube | 86 ts | (-0.140, +0.228, +0.020) |
| 6 | put it into the bin | 64 ts | (+0.010, +0.049, +0.200) |
| 7 | pick up the second green cube | 94 ts | (+0.028, -0.078, +0.020) |
| 8 | put it into the bin | 53 ts | (+0.010, +0.049, +0.200) |
| 9 | press the button | 56 ts | (-0.161, +0.105, +0.007) |

#### val-ep15 — seed `1041500`，难度 hard，动作 5 次

目标：put two red cubes and three blue cubes into the bin, then press the button to stop

整条 1017 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 116 ts | (-0.144, +0.225, +0.020) |
| 2 | put it into the bin | 57 ts | (-0.035, +0.191, +0.200) |
| 3 | pick up the second blue cube | 129 ts | (-0.270, -0.176, +0.020) |
| 4 | put it into the bin | 79 ts | (-0.035, +0.191, +0.200) |
| 5 | pick up the third blue cube | 98 ts | (-0.139, -0.033, +0.020) |
| 6 | put it into the bin | 69 ts | (-0.035, +0.191, +0.200) |
| 7 | pick up the first red cube | 117 ts | (+0.034, -0.181, +0.020) |
| 8 | put it into the bin | 65 ts | (-0.035, +0.191, +0.200) |
| 9 | pick up the second red cube | 123 ts | (-0.189, -0.229, +0.020) |
| 10 | put it into the bin | 77 ts | (-0.035, +0.191, +0.200) |
| 11 | press the button | 52 ts | (-0.186, +0.072, +0.007) |

#### val-ep16 — seed `1041601`，难度 easy，动作 3 次

目标：put three red cubes into the bin, then press the button to stop

整条 619 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 133 ts | (-0.228, +0.057, +0.020) |
| 2 | put it into the bin | 70 ts | (-0.003, -0.142, +0.200) |
| 3 | pick up the second red cube | 95 ts | (+0.048, +0.111, +0.020) |
| 4 | put it into the bin | 62 ts | (-0.003, -0.142, +0.200) |
| 5 | pick up the third red cube | 97 ts | (-0.064, -0.034, +0.020) |
| 6 | put it into the bin | 55 ts | (-0.003, -0.142, +0.200) |
| 7 | press the button | 68 ts | (-0.203, -0.111, +0.007) |

#### val-ep17 — seed `1041700`，难度 easy，动作 3 次

目标：put three red cubes into the bin, then press the button to stop

整条 634 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 103 ts | (-0.013, -0.129, +0.020) |
| 2 | put it into the bin | 76 ts | (+0.133, +0.018, +0.200) |
| 3 | pick up the second red cube | 106 ts | (-0.110, +0.094, +0.020) |
| 4 | put it into the bin | 82 ts | (+0.133, +0.018, +0.200) |
| 5 | pick up the third red cube | 90 ts | (+0.030, +0.127, +0.020) |
| 6 | put it into the bin | 73 ts | (+0.133, +0.018, +0.200) |
| 7 | press the button | 67 ts | (-0.250, +0.171, +0.007) |

#### val-ep18 — seed `1041800`，难度 medium，动作 4 次

目标：put three red cubes and one blue cube into the bin, then press the button to stop

整条 826 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 127 ts | (-0.193, -0.213, +0.020) |
| 2 | put it into the bin | 81 ts | (+0.061, -0.091, +0.200) |
| 3 | pick up the second red cube | 90 ts | (+0.015, +0.059, +0.020) |
| 4 | put it into the bin | 59 ts | (+0.061, -0.091, +0.200) |
| 5 | pick up the third red cube | 113 ts | (+0.060, -0.210, +0.020) |
| 6 | put it into the bin | 53 ts | (+0.061, -0.091, +0.200) |
| 7 | pick up the first blue cube | 104 ts | (-0.197, -0.059, +0.020) |
| 8 | put it into the bin | 81 ts | (+0.061, -0.091, +0.200) |
| 9 | press the button | 79 ts | (-0.187, +0.051, +0.007) |

#### val-ep19 — seed `1041900`，难度 hard，动作 4 次

目标：put two blue cubes and two green cubes into the bin, then press the button to stop

整条 817 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 113 ts | (-0.104, +0.095, +0.020) |
| 2 | put it into the bin | 86 ts | (+0.146, +0.053, +0.200) |
| 3 | pick up the second green cube | 85 ts | (-0.018, -0.215, +0.020) |
| 4 | put it into the bin | 75 ts | (+0.146, +0.053, +0.200) |
| 5 | pick up the first blue cube | 98 ts | (-0.106, -0.117, +0.020) |
| 6 | put it into the bin | 82 ts | (+0.146, +0.053, +0.200) |
| 7 | pick up the second blue cube | 89 ts | (-0.017, -0.100, +0.020) |
| 8 | put it into the bin | 75 ts | (+0.146, +0.053, +0.200) |
| 9 | press the button | 73 ts | (-0.227, +0.126, +0.007) |

#### val-ep20 — seed `1042000`，难度 easy，动作 1 次

目标：put one blue cube into the bin, then press the button to stop

整条 265 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 116 ts | (-0.085, -0.223, +0.020) |
| 2 | put it into the bin | 65 ts | (-0.047, -0.036, +0.200) |
| 3 | press the button | 44 ts | (-0.174, -0.035, +0.007) |

#### val-ep21 — seed `1042100`，难度 easy，动作 3 次

目标：put three blue cubes into the bin, then press the button to stop

整条 620 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 125 ts | (-0.208, -0.149, +0.020) |
| 2 | put it into the bin | 74 ts | (+0.024, -0.075, +0.200) |
| 3 | pick up the second blue cube | 98 ts | (+0.064, +0.089, +0.020) |
| 4 | put it into the bin | 57 ts | (+0.024, -0.075, +0.200) |
| 5 | pick up the third blue cube | 106 ts | (+0.065, +0.196, +0.020) |
| 6 | put it into the bin | 64 ts | (+0.024, -0.075, +0.200) |
| 7 | press the button | 57 ts | (-0.190, +0.089, +0.007) |

#### val-ep22 — seed `1042200`，难度 medium，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 464 timestep（其中收尾段 44）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 137 ts | (-0.251, +0.154, +0.020) |
| 2 | put it into the bin | 68 ts | (+0.000, +0.026, +0.200) |
| 3 | pick up the second blue cube | 100 ts | (+0.050, +0.152, +0.020) |
| 4 | put it into the bin | 53 ts | (+0.000, +0.026, +0.200) |
| 5 | press the button | 62 ts | (-0.245, +0.000, +0.007) |

#### val-ep23 — seed `1042300`，难度 hard，动作 5 次

目标：put four red cubes and one blue cube into the bin, then press the button to stop

整条 922 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 128 ts | (-0.175, +0.203, +0.020) |
| 2 | put it into the bin | 64 ts | (+0.007, -0.006, +0.200) |
| 3 | pick up the second red cube | 92 ts | (-0.162, -0.166, +0.020) |
| 4 | put it into the bin | 65 ts | (+0.007, -0.006, +0.200) |
| 5 | pick up the third red cube | 86 ts | (-0.099, -0.116, +0.020) |
| 6 | put it into the bin | 57 ts | (+0.007, -0.006, +0.200) |
| 7 | pick up the fourth red cube | 105 ts | (+0.064, +0.110, +0.020) |
| 8 | put it into the bin | 54 ts | (+0.007, -0.006, +0.200) |
| 9 | pick up the first blue cube | 115 ts | (-0.277, -0.212, +0.020) |
| 10 | put it into the bin | 71 ts | (+0.007, -0.006, +0.200) |
| 11 | press the button | 50 ts | (-0.171, +0.052, +0.007) |

#### val-ep24 — seed `1042400`，难度 easy，动作 1 次

目标：put one blue cube into the bin, then press the button to stop

整条 266 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 105 ts | (+0.074, -0.017, +0.020) |
| 2 | put it into the bin | 62 ts | (-0.042, +0.189, +0.200) |
| 3 | press the button | 61 ts | (-0.192, -0.156, +0.007) |

#### val-ep25 — seed `1042500`，难度 easy，动作 1 次

目标：put one blue cube into the bin, then press the button to stop

整条 263 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 102 ts | (+0.014, -0.081, +0.020) |
| 2 | put it into the bin | 68 ts | (-0.040, +0.152, +0.200) |
| 3 | press the button | 52 ts | (-0.195, +0.099, +0.007) |

#### val-ep26 — seed `1042600`，难度 medium，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 399 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 105 ts | (-0.007, +0.080, +0.020) |
| 2 | put it into the bin | 52 ts | (+0.048, -0.020, +0.200) |
| 3 | pick up the second blue cube | 82 ts | (-0.022, -0.209, +0.020) |
| 4 | put it into the bin | 61 ts | (+0.048, -0.020, +0.200) |
| 5 | press the button | 64 ts | (-0.204, -0.163, +0.007) |

#### val-ep27 — seed `1042700`，难度 hard，动作 5 次

目标：put three blue cubes and two green cubes into the bin, then press the button to stop

整条 971 timestep（其中收尾段 53）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 119 ts | (-0.146, +0.211, +0.020) |
| 2 | put it into the bin | 74 ts | (+0.049, -0.097, +0.200) |
| 3 | pick up the second blue cube | 86 ts | (+0.014, +0.172, +0.020) |
| 4 | put it into the bin | 61 ts | (+0.049, -0.097, +0.200) |
| 5 | pick up the third blue cube | 117 ts | (-0.251, +0.191, +0.020) |
| 6 | put it into the bin | 76 ts | (+0.049, -0.097, +0.200) |
| 7 | pick up the first green cube | 80 ts | (-0.004, +0.030, +0.020) |
| 8 | put it into the bin | 60 ts | (+0.049, -0.097, +0.200) |
| 9 | pick up the second green cube | 111 ts | (+0.067, +0.185, +0.020) |
| 10 | put it into the bin | 61 ts | (+0.049, -0.097, +0.200) |
| 11 | press the button | 73 ts | (-0.249, -0.026, +0.007) |

#### val-ep28 — seed `1042800`，难度 easy，动作 2 次

目标：put two green cubes into the bin, then press the button to stop

整条 478 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 131 ts | (-0.244, +0.211, +0.020) |
| 2 | put it into the bin | 80 ts | (+0.068, +0.160, +0.200) |
| 3 | pick up the second green cube | 97 ts | (-0.074, +0.109, +0.020) |
| 4 | put it into the bin | 70 ts | (+0.068, +0.160, +0.200) |
| 5 | press the button | 63 ts | (-0.216, +0.006, +0.007) |

#### val-ep29 — seed `1042900`，难度 easy，动作 3 次

目标：put three blue cubes into the bin, then press the button to stop

整条 639 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 132 ts | (-0.276, +0.215, +0.020) |
| 2 | put it into the bin | 82 ts | (+0.072, +0.110, +0.200) |
| 3 | pick up the second blue cube | 84 ts | (-0.037, +0.204, +0.020) |
| 4 | put it into the bin | 62 ts | (+0.072, +0.110, +0.200) |
| 5 | pick up the third blue cube | 105 ts | (-0.058, -0.083, +0.020) |
| 6 | put it into the bin | 69 ts | (+0.072, +0.110, +0.200) |
| 7 | press the button | 65 ts | (-0.246, +0.025, +0.007) |

#### val-ep30 — seed `1043000`，难度 medium，动作 3 次

目标：put three red cubes into the bin, then press the button to stop

整条 641 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 114 ts | (-0.098, +0.033, +0.020) |
| 2 | put it into the bin | 72 ts | (+0.070, -0.036, +0.200) |
| 3 | pick up the second red cube | 85 ts | (-0.035, -0.130, +0.020) |
| 4 | put it into the bin | 64 ts | (+0.070, -0.036, +0.200) |
| 5 | pick up the third red cube | 125 ts | (-0.237, +0.157, +0.020) |
| 6 | put it into the bin | 83 ts | (+0.070, -0.036, +0.200) |
| 7 | press the button | 57 ts | (-0.201, -0.145, +0.007) |

#### val-ep31 — seed `1043100`，难度 hard，动作 4 次

目标：put three red cubes and one blue cube into the bin, then press the button to stop

整条 871 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 109 ts | (-0.005, +0.146, +0.020) |
| 2 | put it into the bin | 72 ts | (+0.113, -0.129, +0.200) |
| 3 | pick up the second red cube | 101 ts | (-0.092, -0.021, +0.020) |
| 4 | put it into the bin | 86 ts | (+0.113, -0.129, +0.200) |
| 5 | pick up the third red cube | 119 ts | (-0.197, +0.197, +0.020) |
| 6 | put it into the bin | 82 ts | (+0.113, -0.129, +0.200) |
| 7 | pick up the first blue cube | 101 ts | (-0.171, -0.191, +0.020) |
| 8 | put it into the bin | 89 ts | (+0.113, -0.129, +0.200) |
| 9 | press the button | 73 ts | (-0.233, -0.048, +0.007) |

#### val-ep32 — seed `1043200`，难度 easy，动作 1 次

目标：put one red cube into the bin, then press the button to stop

整条 298 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 124 ts | (-0.189, -0.227, +0.020) |
| 2 | put it into the bin | 69 ts | (+0.032, +0.011, +0.200) |
| 3 | press the button | 64 ts | (-0.230, -0.063, +0.007) |

#### val-ep33 — seed `1043300`，难度 easy，动作 3 次

目标：put three red cubes into the bin, then press the button to stop

整条 625 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 113 ts | (-0.111, -0.141, +0.020) |
| 2 | put it into the bin | 72 ts | (+0.071, -0.066, +0.200) |
| 3 | pick up the second red cube | 94 ts | (+0.028, +0.229, +0.020) |
| 4 | put it into the bin | 61 ts | (+0.071, -0.066, +0.200) |
| 5 | pick up the third red cube | 105 ts | (+0.049, -0.204, +0.020) |
| 6 | put it into the bin | 60 ts | (+0.071, -0.066, +0.200) |
| 7 | press the button | 78 ts | (-0.219, +0.157, +0.007) |

#### val-ep34 — seed `1043400`，难度 medium，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 439 timestep（其中收尾段 40）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 101 ts | (+0.017, +0.143, +0.020) |
| 2 | put it into the bin | 55 ts | (-0.006, -0.012, +0.200) |
| 3 | pick up the second red cube | 110 ts | (+0.064, -0.176, +0.020) |
| 4 | put it into the bin | 57 ts | (-0.006, -0.012, +0.200) |
| 5 | press the button | 76 ts | (-0.233, -0.053, +0.007) |

#### val-ep35 — seed `1043501`，难度 hard，动作 4 次

目标：put two red cubes and two blue cubes into the bin, then press the button to stop

整条 781 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 126 ts | (-0.211, +0.209, +0.020) |
| 2 | put it into the bin | 68 ts | (+0.011, +0.159, +0.200) |
| 3 | pick up the second blue cube | 80 ts | (-0.100, +0.167, +0.020) |
| 4 | put it into the bin | 60 ts | (+0.011, +0.159, +0.200) |
| 5 | pick up the first red cube | 116 ts | (-0.127, -0.186, +0.020) |
| 6 | put it into the bin | 71 ts | (+0.011, +0.159, +0.200) |
| 7 | pick up the second red cube | 97 ts | (+0.065, -0.059, +0.020) |
| 8 | put it into the bin | 59 ts | (+0.011, +0.159, +0.200) |
| 9 | press the button | 62 ts | (-0.239, -0.057, +0.007) |

#### val-ep36 — seed `1043600`，难度 easy，动作 1 次

目标：put one red cube into the bin, then press the button to stop

整条 307 timestep（其中收尾段 42）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 114 ts | (-0.045, +0.003, +0.020) |
| 2 | put it into the bin | 79 ts | (+0.126, -0.198, +0.200) |
| 3 | press the button | 72 ts | (-0.218, -0.108, +0.007) |

#### val-ep37 — seed `1043700`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 342 timestep（其中收尾段 38）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 137 ts | (-0.236, -0.126, +0.020) |
| 2 | put it into the bin | 93 ts | (+0.118, +0.013, +0.200) |
| 3 | press the button | 74 ts | (-0.212, +0.037, +0.007) |

#### val-ep38 — seed `1043800`，难度 medium，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 480 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 110 ts | (-0.114, +0.166, +0.020) |
| 2 | put it into the bin | 65 ts | (+0.047, +0.109, +0.200) |
| 3 | pick up the second blue cube | 115 ts | (-0.119, -0.141, +0.020) |
| 4 | put it into the bin | 71 ts | (+0.047, +0.109, +0.200) |
| 5 | press the button | 83 ts | (-0.218, +0.082, +0.007) |

#### val-ep39 — seed `1043900`，难度 hard，动作 3 次

目标：put one red cube and two blue cubes into the bin, then press the button to stop

整条 609 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 106 ts | (-0.035, -0.189, +0.020) |
| 2 | put it into the bin | 82 ts | (+0.124, +0.169, +0.200) |
| 3 | pick up the second blue cube | 98 ts | (+0.057, -0.051, +0.020) |
| 4 | put it into the bin | 68 ts | (+0.124, +0.169, +0.200) |
| 5 | pick up the first red cube | 83 ts | (-0.004, +0.069, +0.020) |
| 6 | put it into the bin | 74 ts | (+0.124, +0.169, +0.200) |
| 7 | press the button | 62 ts | (-0.154, +0.008, +0.007) |

#### val-ep40 — seed `1044000`，难度 easy，动作 2 次

目标：put two green cubes into the bin, then press the button to stop

整条 475 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 140 ts | (-0.275, +0.052, +0.020) |
| 2 | put it into the bin | 73 ts | (+0.011, +0.024, +0.200) |
| 3 | pick up the second green cube | 100 ts | (+0.015, +0.159, +0.020) |
| 4 | put it into the bin | 52 ts | (+0.011, +0.024, +0.200) |
| 5 | press the button | 73 ts | (-0.178, -0.144, +0.007) |

#### val-ep41 — seed `1044100`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 275 timestep（其中收尾段 36）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 106 ts | (-0.037, +0.174, +0.020) |
| 2 | put it into the bin | 68 ts | (+0.097, +0.155, +0.200) |
| 3 | press the button | 65 ts | (-0.176, -0.154, +0.007) |

#### val-ep42 — seed `1044200`，难度 medium，动作 4 次

目标：put four blue cubes into the bin, then press the button to stop

整条 828 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 107 ts | (-0.069, -0.218, +0.020) |
| 2 | put it into the bin | 76 ts | (+0.134, -0.044, +0.200) |
| 3 | pick up the second blue cube | 96 ts | (+0.077, +0.112, +0.020) |
| 4 | put it into the bin | 65 ts | (+0.134, -0.044, +0.200) |
| 5 | pick up the third blue cube | 127 ts | (-0.265, +0.129, +0.020) |
| 6 | put it into the bin | 92 ts | (+0.134, -0.044, +0.200) |
| 7 | pick up the fourth blue cube | 87 ts | (-0.052, +0.112, +0.020) |
| 8 | put it into the bin | 78 ts | (+0.134, -0.044, +0.200) |
| 9 | press the button | 65 ts | (-0.193, -0.087, +0.007) |

#### val-ep43 — seed `1044300`，难度 hard，动作 3 次

目标：put one red cube, one blue cube and one green cube into the bin, then press the button to stop

整条 608 timestep（其中收尾段 41）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 128 ts | (-0.239, +0.066, +0.020) |
| 2 | put it into the bin | 69 ts | (-0.036, +0.146, +0.200) |
| 3 | pick up the first red cube | 86 ts | (-0.019, +0.026, +0.020) |
| 4 | put it into the bin | 56 ts | (-0.036, +0.146, +0.200) |
| 5 | pick up the first green cube | 107 ts | (-0.096, -0.188, +0.020) |
| 6 | put it into the bin | 63 ts | (-0.036, +0.146, +0.200) |
| 7 | press the button | 58 ts | (-0.202, -0.127, +0.007) |

#### val-ep44 — seed `1044400`，难度 easy，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 459 timestep（其中收尾段 39）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 107 ts | (+0.017, -0.210, +0.020) |
| 2 | put it into the bin | 80 ts | (+0.134, -0.178, +0.200) |
| 3 | pick up the second red cube | 96 ts | (+0.079, -0.052, +0.020) |
| 4 | put it into the bin | 72 ts | (+0.134, -0.178, +0.200) |
| 5 | press the button | 65 ts | (-0.161, +0.104, +0.007) |

#### val-ep45 — seed `1044500`，难度 easy，动作 1 次

目标：put one green cube into the bin, then press the button to stop

整条 299 timestep（其中收尾段 33）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 133 ts | (-0.246, -0.087, +0.020) |
| 2 | put it into the bin | 74 ts | (+0.034, -0.091, +0.200) |
| 3 | press the button | 59 ts | (-0.164, +0.161, +0.007) |

#### val-ep46 — seed `1044600`，难度 medium，动作 3 次

目标：put three green cubes into the bin, then press the button to stop

整条 596 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 105 ts | (+0.053, -0.196, +0.020) |
| 2 | put it into the bin | 69 ts | (-0.024, +0.047, +0.200) |
| 3 | pick up the second green cube | 106 ts | (-0.272, +0.136, +0.020) |
| 4 | put it into the bin | 69 ts | (-0.024, +0.047, +0.200) |
| 5 | pick up the third green cube | 107 ts | (+0.040, -0.078, +0.020) |
| 6 | put it into the bin | 53 ts | (-0.024, +0.047, +0.200) |
| 7 | press the button | 52 ts | (-0.151, -0.062, +0.007) |

#### val-ep47 — seed `1044700`，难度 hard，动作 5 次

目标：put three red cubes, one blue cube and one green cube into the bin, then press the button to stop

整条 945 timestep（其中收尾段 34）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first green cube | 141 ts | (-0.269, +0.023, +0.020) |
| 2 | put it into the bin | 76 ts | (+0.006, +0.060, +0.200) |
| 3 | pick up the first red cube | 100 ts | (+0.058, -0.086, +0.020) |
| 4 | put it into the bin | 54 ts | (+0.006, +0.060, +0.200) |
| 5 | pick up the second red cube | 101 ts | (-0.159, +0.008, +0.020) |
| 6 | put it into the bin | 64 ts | (+0.006, +0.060, +0.200) |
| 7 | pick up the third red cube | 97 ts | (-0.212, +0.125, +0.020) |
| 8 | put it into the bin | 67 ts | (+0.006, +0.060, +0.200) |
| 9 | pick up the first blue cube | 84 ts | (-0.117, -0.030, +0.020) |
| 10 | put it into the bin | 61 ts | (+0.006, +0.060, +0.200) |
| 11 | press the button | 66 ts | (-0.167, -0.190, +0.007) |

#### val-ep48 — seed `1044800`，难度 easy，动作 2 次

目标：put two red cubes into the bin, then press the button to stop

整条 485 timestep（其中收尾段 37）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first red cube | 125 ts | (-0.137, +0.193, +0.020) |
| 2 | put it into the bin | 74 ts | (+0.054, +0.185, +0.200) |
| 3 | pick up the second red cube | 111 ts | (-0.029, -0.210, +0.020) |
| 4 | put it into the bin | 72 ts | (+0.054, +0.185, +0.200) |
| 5 | press the button | 66 ts | (-0.203, -0.046, +0.007) |

#### val-ep49 — seed `1044900`，难度 easy，动作 2 次

目标：put two blue cubes into the bin, then press the button to stop

整条 467 timestep（其中收尾段 35）。

| # | 子目标 | 时长 | 关键点 (x,y,z) |
| --- | --- | --- | --- |
| 1 | pick up the first blue cube | 117 ts | (-0.110, -0.175, +0.020) |
| 2 | put it into the bin | 69 ts | (+0.035, +0.169, +0.200) |
| 3 | pick up the second blue cube | 113 ts | (-0.076, -0.100, +0.020) |
| 4 | put it into the bin | 71 ts | (+0.035, +0.169, +0.200) |
| 5 | press the button | 62 ts | (-0.190, +0.124, +0.007) |
