# 实跑结果

运行：`20260912-contract-v3-10`；用途：`delivery`。

结果按唯一键保存；reset 通过只表示能建环境，不表示可以完成任务。

| 组 | HDF5 正式 | HDF5 备用 | HDF5 失败 | reset 正式 | reset 备用 | reset 失败 |
|---|---:|---:|---:|---:|---:|---:|
| BinFill/easy | 134 | 16 | 5 | 50 | 95 | 0 |
| BinFill/medium | 133 | 16 | 4 | 50 | 97 | 0 |
| BinFill/hard | 133 | 6 | 14 | 50 | 97 | 0 |
| RouteStick/easy | 100 | 15 | 0 | 50 | 35 | 0 |
| RouteStick/medium | 100 | 15 | 0 | 50 | 35 | 0 |
| RouteStick/hard | 100 | 15 | 0 | 50 | 35 | 0 |
| VideoUnmaskSwap/easy | 100 | 15 | 0 | 50 | 35 | 0 |
| VideoUnmaskSwap/medium | 100 | 15 | 0 | 50 | 35 | 0 |
| VideoUnmaskSwap/hard | 100 | 15 | 0 | 50 | 35 | 0 |
| VideoRepick/easy | 134 | 16 | 5 | 50 | 95 | 0 |
| VideoRepick/medium | 133 | 13 | 7 | 50 | 97 | 0 |
| RouteStick/xhard | 100 | 15 | 0 | 50 | 35 | 0 |
| VideoUnmaskSwap/xhard | 100 | 13 | 2 | 50 | 35 | 0 |
| VideoRepick/xhard | 133 | 11 | 9 | 50 | 97 | 0 |

## 视频状态

{'complete': 1818, 'frame_mismatch': 3, 'no_close': 21}

## 失败记录

| 类型 | 组 | episode | seed | 异常 |
|---|---|---:|---:|---|
| h5 | BinFill/easy | 10 | 5000 | DatasetGenerationError |
| h5 | BinFill/easy | 83 | 12300 | DatasetGenerationError |
| h5 | BinFill/easy | 125 | 16500 | BinFillDemoError |
| h5 | BinFill/easy | 146 | 18600 | BinFillDemoError |
| h5 | BinFill/easy | 151 | 19100 | DatasetGenerationError |
| h5 | BinFill/hard | 4 | 4400 | DatasetGenerationError |
| h5 | BinFill/hard | 23 | 6300 | DatasetGenerationError |
| h5 | BinFill/hard | 28 | 6800 | DatasetGenerationError |
| h5 | BinFill/hard | 31 | 7100 | DatasetGenerationError |
| h5 | BinFill/hard | 32 | 7200 | DatasetGenerationError |
| h5 | BinFill/hard | 38 | 7800 | DatasetGenerationError |
| h5 | BinFill/hard | 45 | 8500 | DatasetGenerationError |
| h5 | BinFill/hard | 58 | 9800 | DatasetGenerationError |
| h5 | BinFill/hard | 65 | 10500 | DatasetGenerationError |
| h5 | BinFill/hard | 90 | 13000 | DatasetGenerationError |
| h5 | BinFill/hard | 93 | 13300 | DatasetGenerationError |
| h5 | BinFill/hard | 117 | 15700 | DatasetGenerationError |
| h5 | BinFill/hard | 130 | 17000 | DatasetGenerationError |
| h5 | BinFill/hard | 152 | 19200 | BinFillDemoError |
| h5 | BinFill/medium | 30 | 7000 | DatasetGenerationError |
| h5 | BinFill/medium | 32 | 7200 | DatasetGenerationError |
| h5 | BinFill/medium | 128 | 16800 | DatasetGenerationError |
| h5 | BinFill/medium | 132 | 17200 | DatasetGenerationError |
| h5 | VideoRepick/easy | 0 | 9000 | EpisodeWallClockTimeout |
| h5 | VideoRepick/easy | 26 | 11600 | EpisodeWallClockTimeout |
| h5 | VideoRepick/easy | 46 | 13600 | EpisodeWallClockTimeout |
| h5 | VideoRepick/easy | 125 | 21500 | EpisodeWallClockTimeout |
| h5 | VideoRepick/easy | 148 | 23800 | EpisodeWallClockTimeout |
| h5 | VideoRepick/medium | 26 | 11600 | EpisodeWallClockTimeout |
| h5 | VideoRepick/medium | 39 | 12900 | EpisodeWallClockTimeout |
| h5 | VideoRepick/medium | 44 | 13400 | EpisodeWallClockTimeout |
| h5 | VideoRepick/medium | 76 | 16600 | EpisodeWallClockTimeout |
| h5 | VideoRepick/medium | 91 | 18100 | EpisodeWallClockTimeout |
| h5 | VideoRepick/medium | 114 | 20400 | EpisodeWallClockTimeout |
| h5 | VideoRepick/medium | 137 | 22700 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 5 | 9500 | DatasetGenerationError |
| h5 | VideoRepick/xhard | 49 | 13900 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 50 | 14000 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 68 | 15800 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 70 | 16000 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 83 | 17300 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 100 | 19000 | BinCollisionError |
| h5 | VideoRepick/xhard | 106 | 19600 | EpisodeWallClockTimeout |
| h5 | VideoRepick/xhard | 145 | 23500 | EpisodeWallClockTimeout |
| h5 | VideoUnmaskSwap/xhard | 7 | 5700 | EpisodeWallClockTimeout |
| h5 | VideoUnmaskSwap/xhard | 26 | 7600 | EpisodeWallClockTimeout |

候选角色：`{'test/primary': 700, 'test/spare': 858, 'train/failed': 46, 'train/primary': 1600, 'train/spare': 196}`。

完整交付缺口组：`[]`。局部运行不冒充完整交付。
