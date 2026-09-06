# RouteStick-test 逐 episode 动作参数

共 50 条。时长来源：本轮按 test metadata 死 seed 实跑生成。

口径：坐标是 SAPIEN 世界坐标，单位米（机器人 base 在 `(-0.615, 0, 0)`），表中给的是按钮本身的位置；运动规划实际下发的终点高度统一抬到 `z=0.07`。时长单位是 timestep（1 timestep = 1 个 env step = 0.05 s）；每组 move 在数据里出现两遍，前一遍是给模型看的演示段，后一遍是真正执行段。

RouteStick 的 move 不是直线：末端要绕开挡在中间的柱子，走二次贝塞尔弧线（横向偏移 0.2 m，顺/逆时针由 `swing_directions` 决定），因此单次 move 时长稳定在 50 timestep 上下。

#### episode 0 — seed `660000`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 25.379°`；节点序列 `[4, 2, 0, 2]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.090, -0.043, +0.010) | (-0.030, -0.169, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.030, -0.169, +0.010) | (+0.030, -0.296, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (+0.030, -0.296, +0.010) | (-0.030, -0.169, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 1 — seed `660100`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 13.161°`；节点序列 `[2, 0, 2]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.065, -0.159, +0.010) | (-0.034, -0.295, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.034, -0.295, +0.010) | (-0.065, -0.159, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 2 — seed `660200`，难度 medium，move 4 次

整排绕 z 轴旋转 `theta = 20.944°`；节点序列 `[2, 0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.043, -0.166, +0.010) | (+0.007, -0.297, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (+0.007, -0.297, +0.010) | (-0.043, -0.166, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.043, -0.166, +0.010) | (-0.093, -0.036, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.093, -0.036, +0.010) | (-0.143, +0.095, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 3 — seed `660300`，难度 hard，move 4 次

整排绕 z 轴旋转 `theta = -28.151°`；节点序列 `[8, 6, 4, 2, 4]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (+0.044, +0.294, +0.010) | (-0.022, +0.171, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.022, +0.171, +0.010) | (-0.088, +0.047, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.088, +0.047, +0.010) | (-0.154, -0.076, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.154, -0.076, +0.010) | (-0.088, +0.047, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 4 — seed `660400`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 6.019°`；节点序列 `[0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.070, -0.289, +0.010) | (-0.085, -0.150, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.085, -0.150, +0.010) | (-0.099, -0.010, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.099, -0.010, +0.010) | (-0.114, +0.129, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 5 — seed `660500`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 22.956°`；节点序列 `[2, 0, 2]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.037, -0.168, +0.010) | (+0.017, -0.297, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (+0.017, -0.297, +0.010) | (-0.037, -0.168, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 6 — seed `660600`，难度 medium，move 4 次

整排绕 z 轴旋转 `theta = 2.172°`；节点序列 `[6, 8, 6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.105, +0.136, +0.010) | (-0.111, +0.276, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.111, +0.276, +0.010) | (-0.105, +0.136, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.105, +0.136, +0.010) | (-0.100, -0.004, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.100, -0.004, +0.010) | (-0.095, -0.144, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 7 — seed `660700`，难度 hard，move 5 次

整排绕 z 轴旋转 `theta = 7.316°`；节点序列 `[8, 6, 8, 6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.135, +0.265, +0.010) | (-0.117, +0.126, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.117, +0.126, +0.010) | (-0.135, +0.265, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.135, +0.265, +0.010) | (-0.117, +0.126, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.117, +0.126, +0.010) | (-0.135, +0.265, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 5 | (-0.135, +0.265, +0.010) | (-0.117, +0.126, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 8 — seed `660800`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = -3.951°`；节点序列 `[0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.119, -0.272, +0.010) | (-0.109, -0.133, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.109, -0.133, +0.010) | (-0.100, +0.007, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.100, +0.007, +0.010) | (-0.090, +0.147, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 9 — seed `660900`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 11.445°`；节点序列 `[8, 6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.154, +0.255, +0.010) | (-0.126, +0.117, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.126, +0.117, +0.010) | (-0.098, -0.020, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.098, -0.020, +0.010) | (-0.070, -0.157, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 10 — seed `661000`，难度 medium，move 4 次

整排绕 z 轴旋转 `theta = 16.374°`；节点序列 `[6, 8, 6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.135, +0.106, +0.010) | (-0.175, +0.240, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.175, +0.240, +0.010) | (-0.135, +0.106, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.135, +0.106, +0.010) | (-0.096, -0.028, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.096, -0.028, +0.010) | (-0.056, -0.163, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 11 — seed `661100`，难度 hard，move 7 次

整排绕 z 轴旋转 `theta = 27.715°`；节点序列 `[0, 2, 0, 2, 4, 6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 700 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (+0.042, -0.294, +0.010) | (-0.023, -0.170, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.023, -0.170, +0.010) | (+0.042, -0.294, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (+0.042, -0.294, +0.010) | (-0.023, -0.170, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.023, -0.170, +0.010) | (-0.089, -0.047, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (-0.089, -0.047, +0.010) | (-0.154, +0.077, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 6 | (-0.154, +0.077, +0.010) | (-0.219, +0.201, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 7 | (-0.219, +0.201, +0.010) | (-0.154, +0.077, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 12 — seed `661200`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 12.374°`；节点序列 `[4, 6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.098, -0.021, +0.010) | (-0.128, +0.115, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.128, +0.115, +0.010) | (-0.158, +0.252, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.158, +0.252, +0.010) | (-0.128, +0.115, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 13 — seed `661300`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = -19.372°`；节点序列 `[0, 2, 4]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.187, -0.231, +0.010) | (-0.141, -0.099, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.141, -0.099, +0.010) | (-0.094, +0.033, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 14 — seed `661400`，难度 medium，move 5 次

整排绕 z 轴旋转 `theta = 23.667°`；节点序列 `[8, 6, 4, 2, 0, 2]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.204, +0.216, +0.010) | (-0.148, +0.088, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.148, +0.088, +0.010) | (-0.092, -0.040, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.092, -0.040, +0.010) | (-0.035, -0.168, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.035, -0.168, +0.010) | (+0.021, -0.297, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (+0.021, -0.297, +0.010) | (-0.035, -0.168, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 15 — seed `661500`，难度 hard，move 4 次

整排绕 z 轴旋转 `theta = 13.641°`；节点序列 `[6, 8, 6, 4, 6]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.130, +0.112, +0.010) | (-0.163, +0.249, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.163, +0.249, +0.010) | (-0.130, +0.112, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.130, +0.112, +0.010) | (-0.097, -0.024, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.097, -0.024, +0.010) | (-0.130, +0.112, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 16 — seed `661600`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 9.884°`；节点序列 `[4, 2, 0]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.099, -0.017, +0.010) | (-0.074, -0.155, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.074, -0.155, +0.010) | (-0.050, -0.293, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 17 — seed `661700`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 26.364°`；节点序列 `[6, 4, 2, 0]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.152, +0.081, +0.010) | (-0.090, -0.044, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.090, -0.044, +0.010) | (-0.027, -0.170, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.027, -0.170, +0.010) | (+0.035, -0.295, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 18 — seed `661800`，难度 medium，move 4 次

整排绕 z 轴旋转 `theta = 17.126°`；节点序列 `[8, 6, 4, 2, 0]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.178, +0.238, +0.010) | (-0.137, +0.104, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.137, +0.104, +0.010) | (-0.096, -0.029, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.096, -0.029, +0.010) | (-0.054, -0.163, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.054, -0.163, +0.010) | (-0.013, -0.297, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 19 — seed `661900`，难度 hard，move 7 次

整排绕 z 轴旋转 `theta = -6.494°`；节点序列 `[4, 6, 8, 6, 4, 6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 700 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.099, +0.011, +0.010) | (-0.084, +0.150, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.084, +0.150, +0.010) | (-0.068, +0.290, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.068, +0.290, +0.010) | (-0.084, +0.150, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.084, +0.150, +0.010) | (-0.099, +0.011, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 5 | (-0.099, +0.011, +0.010) | (-0.084, +0.150, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 6 | (-0.084, +0.150, +0.010) | (-0.099, +0.011, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 7 | (-0.099, +0.011, +0.010) | (-0.115, -0.128, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 20 — seed `662000`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 8.694°`；节点序列 `[0, 2, 4]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.057, -0.292, +0.010) | (-0.078, -0.154, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.078, -0.154, +0.010) | (-0.099, -0.015, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 21 — seed `662100`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 9.142°`；节点序列 `[4, 2, 0]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.099, -0.016, +0.010) | (-0.076, -0.154, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.076, -0.154, +0.010) | (-0.054, -0.292, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 22 — seed `662200`，难度 medium，move 5 次

整排绕 z 轴旋转 `theta = -26.928°`；节点序列 `[0, 2, 4, 6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.216, -0.204, +0.010) | (-0.153, -0.080, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.153, -0.080, +0.010) | (-0.089, +0.045, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.089, +0.045, +0.010) | (-0.026, +0.170, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.026, +0.170, +0.010) | (+0.038, +0.295, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (+0.038, +0.295, +0.010) | (-0.026, +0.170, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 23 — seed `662300`，难度 hard，move 4 次

整排绕 z 轴旋转 `theta = -2.235°`；节点序列 `[4, 2, 4, 6, 8]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.100, +0.004, +0.010) | (-0.105, -0.136, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.105, -0.136, +0.010) | (-0.100, +0.004, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.100, +0.004, +0.010) | (-0.094, +0.144, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.094, +0.144, +0.010) | (-0.089, +0.284, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 24 — seed `662400`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = -17.605°`；节点序列 `[6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.053, +0.164, +0.010) | (-0.011, +0.297, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.011, +0.297, +0.010) | (-0.053, +0.164, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 25 — seed `662500`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = -7.874°`；节点序列 `[8, 6, 4]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.061, +0.291, +0.010) | (-0.080, +0.152, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.080, +0.152, +0.010) | (-0.099, +0.014, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 26 — seed `662600`，难度 medium，move 5 次

整排绕 z 轴旋转 `theta = -22.502°`；节点序列 `[0, 2, 4, 6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.200, -0.220, +0.010) | (-0.146, -0.091, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.146, -0.091, +0.010) | (-0.092, +0.038, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.092, +0.038, +0.010) | (-0.039, +0.168, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.039, +0.168, +0.010) | (+0.015, +0.297, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (+0.015, +0.297, +0.010) | (-0.039, +0.168, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 27 — seed `662700`，难度 hard，move 5 次

整排绕 z 轴旋转 `theta = -21.177°`；节点序列 `[2, 0, 2, 4, 2, 0]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.144, -0.094, +0.010) | (-0.194, -0.225, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.194, -0.225, +0.010) | (-0.144, -0.094, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.144, -0.094, +0.010) | (-0.093, +0.036, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.093, +0.036, +0.010) | (-0.144, -0.094, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 5 | (-0.144, -0.094, +0.010) | (-0.194, -0.225, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 28 — seed `662800`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 5.545°`；节点序列 `[0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.072, -0.288, +0.010) | (-0.086, -0.149, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.086, -0.149, +0.010) | (-0.100, -0.010, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.100, -0.010, +0.010) | (-0.113, +0.130, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 29 — seed `662900`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = -12.270°`；节点序列 `[4, 2, 0]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.098, +0.021, +0.010) | (-0.127, -0.116, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.127, -0.116, +0.010) | (-0.157, -0.252, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 30 — seed `663000`，难度 medium，move 5 次

整排绕 z 轴旋转 `theta = 12.110°`；节点序列 `[8, 6, 4, 2, 0, 2]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.157, +0.253, +0.010) | (-0.127, +0.116, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.127, +0.116, +0.010) | (-0.098, -0.021, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.098, -0.021, +0.010) | (-0.068, -0.158, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.068, -0.158, +0.010) | (-0.039, -0.295, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 5 | (-0.039, -0.295, +0.010) | (-0.068, -0.158, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 31 — seed `663100`，难度 hard，move 4 次

整排绕 z 轴旋转 `theta = 16.759°`；节点序列 `[2, 4, 6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.055, -0.163, +0.010) | (-0.096, -0.029, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.096, -0.029, +0.010) | (-0.136, +0.105, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.136, +0.105, +0.010) | (-0.096, -0.029, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.096, -0.029, +0.010) | (-0.055, -0.163, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 32 — seed `663200`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 3.510°`；节点序列 `[0, 2, 4]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.083, -0.286, +0.010) | (-0.091, -0.146, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.091, -0.146, +0.010) | (-0.100, -0.006, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 33 — seed `663300`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 8.748°`；节点序列 `[8, 6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.141, +0.262, +0.010) | (-0.120, +0.123, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.120, +0.123, +0.010) | (-0.099, -0.015, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.099, -0.015, +0.010) | (-0.078, -0.154, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 34 — seed `663400`，难度 medium，move 5 次

整排绕 z 轴旋转 `theta = 17.343°`；节点序列 `[6, 8, 6, 4, 2, 0]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.137, +0.104, +0.010) | (-0.179, +0.237, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.179, +0.237, +0.010) | (-0.137, +0.104, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.137, +0.104, +0.010) | (-0.095, -0.030, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.095, -0.030, +0.010) | (-0.054, -0.163, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (-0.054, -0.163, +0.010) | (-0.012, -0.297, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 35 — seed `663500`，难度 hard，move 7 次

整排绕 z 轴旋转 `theta = 18.381°`；节点序列 `[8, 6, 8, 6, 8, 6, 4, 6]`（1×9 格点，只用偶数下标）。

整条 700 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.183, +0.234, +0.010) | (-0.139, +0.101, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.139, +0.101, +0.010) | (-0.183, +0.234, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.183, +0.234, +0.010) | (-0.139, +0.101, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.139, +0.101, +0.010) | (-0.183, +0.234, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (-0.183, +0.234, +0.010) | (-0.139, +0.101, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 6 | (-0.139, +0.101, +0.010) | (-0.095, -0.032, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 7 | (-0.095, -0.032, +0.010) | (-0.139, +0.101, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 36 — seed `663600`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = -15.438°`；节点序列 `[6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.059, +0.162, +0.010) | (-0.096, +0.027, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.096, +0.027, +0.010) | (-0.134, -0.108, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 37 — seed `663700`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = -12.001°`；节点序列 `[0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.156, -0.253, +0.010) | (-0.127, -0.116, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.127, -0.116, +0.010) | (-0.098, +0.021, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.098, +0.021, +0.010) | (-0.069, +0.158, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 38 — seed `663800`，难度 medium，move 5 次

整排绕 z 轴旋转 `theta = -0.513°`；节点序列 `[8, 6, 4, 2, 0, 2]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.097, +0.281, +0.010) | (-0.099, +0.141, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.099, +0.141, +0.010) | (-0.100, +0.001, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.100, +0.001, +0.010) | (-0.101, -0.139, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.101, -0.139, +0.010) | (-0.103, -0.279, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 5 | (-0.103, -0.279, +0.010) | (-0.101, -0.139, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 39 — seed `663900`，难度 hard，move 6 次

整排绕 z 轴旋转 `theta = -7.379°`；节点序列 `[8, 6, 4, 6, 4, 2, 4]`（1×9 格点，只用偶数下标）。

整条 600 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.063, +0.291, +0.010) | (-0.081, +0.152, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.081, +0.152, +0.010) | (-0.099, +0.013, +0.010) | move to the nearest right target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.099, +0.013, +0.010) | (-0.081, +0.152, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.081, +0.152, +0.010) | (-0.099, +0.013, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (-0.099, +0.013, +0.010) | (-0.117, -0.126, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 6 | (-0.117, -0.126, +0.010) | (-0.099, +0.013, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 40 — seed `664000`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 0.003°`；节点序列 `[0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.100, -0.280, +0.010) | (-0.100, -0.140, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.100, -0.140, +0.010) | (-0.100, -0.000, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.100, -0.000, +0.010) | (-0.100, +0.140, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 41 — seed `664100`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 13.811°`；节点序列 `[0, 2, 4]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.030, -0.296, +0.010) | (-0.064, -0.160, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.064, -0.160, +0.010) | (-0.097, -0.024, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 42 — seed `664200`，难度 medium，move 5 次

整排绕 z 轴旋转 `theta = -21.582°`；节点序列 `[0, 2, 4, 6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.196, -0.224, +0.010) | (-0.144, -0.093, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.144, -0.093, +0.010) | (-0.093, +0.037, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.093, +0.037, +0.010) | (-0.041, +0.167, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.041, +0.167, +0.010) | (+0.010, +0.297, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 5 | (+0.010, +0.297, +0.010) | (-0.041, +0.167, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 43 — seed `664300`，难度 hard，move 6 次

整排绕 z 轴旋转 `theta = 22.845°`；节点序列 `[0, 2, 4, 6, 8, 6, 4]`（1×9 格点，只用偶数下标）。

整条 600 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (+0.017, -0.297, +0.010) | (-0.038, -0.168, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.038, -0.168, +0.010) | (-0.092, -0.039, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.092, -0.039, +0.010) | (-0.147, +0.090, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 4 | (-0.147, +0.090, +0.010) | (-0.201, +0.219, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (-0.201, +0.219, +0.010) | (-0.147, +0.090, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 6 | (-0.147, +0.090, +0.010) | (-0.092, -0.039, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 44 — seed `664400`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 13.316°`；节点序列 `[0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.033, -0.296, +0.010) | (-0.065, -0.159, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.065, -0.159, +0.010) | (-0.097, -0.023, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.097, -0.023, +0.010) | (-0.130, +0.113, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 45 — seed `664500`，难度 easy，move 3 次

整排绕 z 轴旋转 `theta = 4.244°`；节点序列 `[0, 2, 4, 6]`（1×9 格点，只用偶数下标）。

整条 300 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.079, -0.287, +0.010) | (-0.089, -0.147, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.089, -0.147, +0.010) | (-0.100, -0.007, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 3 | (-0.100, -0.007, +0.010) | (-0.110, +0.132, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 46 — seed `664600`，难度 medium，move 4 次

整排绕 z 轴旋转 `theta = -5.326°`；节点序列 `[0, 2, 4, 6, 8]`（1×9 格点，只用偶数下标）。

整条 400 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.126, -0.270, +0.010) | (-0.113, -0.130, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 2 | (-0.113, -0.130, +0.010) | (-0.100, +0.009, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.100, +0.009, +0.010) | (-0.087, +0.149, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.087, +0.149, +0.010) | (-0.074, +0.288, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 43 ts | 50 ts |

#### episode 47 — seed `664700`，难度 hard，move 5 次

整排绕 z 轴旋转 `theta = 9.698°`；节点序列 `[0, 2, 4, 6, 8, 6]`（1×9 格点，只用偶数下标）。

整条 500 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.051, -0.293, +0.010) | (-0.075, -0.155, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.075, -0.155, +0.010) | (-0.099, -0.017, +0.010) | move to the nearest left target by circling around the stick clockwise | 50 ts | 50 ts |
| 3 | (-0.099, -0.017, +0.010) | (-0.122, +0.121, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 4 | (-0.122, +0.121, +0.010) | (-0.146, +0.259, +0.010) | move to the nearest left target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 5 | (-0.146, +0.259, +0.010) | (-0.122, +0.121, +0.010) | move to the nearest right target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 48 — seed `664800`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = 6.881°`；节点序列 `[2, 0, 2]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.083, -0.151, +0.010) | (-0.066, -0.290, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.066, -0.290, +0.010) | (-0.083, -0.151, +0.010) | move to the nearest left target by circling around the stick clockwise | 43 ts | 50 ts |

#### episode 49 — seed `664900`，难度 easy，move 2 次

整排绕 z 轴旋转 `theta = -28.150°`；节点序列 `[6, 4, 2]`（1×9 格点，只用偶数下标）。

整条 200 timestep（其中收尾段 7）。

| # | 起点 (x,y,z) | 终点 (x,y,z) | 动作语义 | 执行段时长 | 演示段时长 |
| --- | --- | --- | --- | --- | --- |
| 1 | (-0.022, +0.171, +0.010) | (-0.088, +0.047, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 50 ts | 50 ts |
| 2 | (-0.088, +0.047, +0.010) | (-0.154, -0.076, +0.010) | move to the nearest right target by circling around the stick counterclockwise | 43 ts | 50 ts |
