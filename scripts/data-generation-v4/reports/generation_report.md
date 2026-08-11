# 数据生成报告（v2：带 2D flow ground truth）

## 运行来源信息

- 状态：generated
- 当前 HEAD：3d7d5dc0d842ebad9cae6df7b219231ea08f880d
- uv.lock SHA-256：983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03
- 报告时间（UTC）：2026-08-11T03:06:04.674556+00:00
- 报告模式：generation

## 调试用环境快照

- 快照时间（UTC）：2026-08-11T03:29:13.261500+00:00
- 主机名：sled-vail
- 操作系统：Linux 6.8.0-1018-nvidia-lowlatency
- 内核：6.8.0-1018-nvidia-lowlatency
- 架构：64bit；机器类型：x86_64
- libc：glibc 2.39

### CPU、内存与存储

| 项目 | 取值 |
| --- | --- |
| 操作系统报告的 CPU 数 | 32 |
| CPU 亲和性可用数 | 32 |
| CPU 亲和性 ID 列表 | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31 |
| CPU 型号 | AMD EPYC 9334 32-Core Processor |
| CPU 插槽数 | 1 |
| 每核线程数 | 1 |
| 总内存 | 405257068544 bytes (377.43 GiB) |
| 仓库所在文件系统 | /data/hongzefu/robomme_benchmark_MotionJEPA |
| 文件系统容量 | 15240752955392 bytes (13.86 TiB) |
| 文件系统已用 | 10392715591680 bytes (9.45 TiB) |
| 文件系统可用 | 4079871086592 bytes (3.71 TiB) |
- 完整的 lscpu --json 原始字段见 JSON 报告的 debug_environment.cpu.lscpu.raw。

### GPU（nvidia-smi）

- nvidia-smi 是否可用：True
- nvidia-smi 版本：570.211.01
- nvidia-smi 报告的 CUDA 版本：12.8

| GPU | Category | Field | Value |
| --- | --- | --- | --- |
| 0 | Static | index | 0 |
| 0 | Static | uuid | GPU-590b693c-56db-a2b6-c4e3-5e20108f92d7 |
| 0 | Static | serial | 1713224014062 |
| 0 | Static | name | NVIDIA RTX 6000 Ada Generation |
| 0 | Static | pci_bus_id | 00000000:01:00.0 |
| 0 | Static | pci_device_id | 0x26B110DE |
| 0 | Static | pci_sub_device_id | 0x16A110DE |
| 0 | Static | driver_version | 570.211.01 |
| 0 | Static | vbios_version | 95.02.59.00.09 |
| 0 | Static | compute_capability | 8.9 |
| 0 | Static | memory_total_mib | 46068 |
| 0 | Dynamic | memory_used_mib | 1017 |
| 0 | Dynamic | memory_free_mib | 44449 |
| 0 | Static | power_limit_w | 300.00 |
| 0 | Dynamic | power_draw_w | 84.58 |
| 0 | Dynamic | temperature_c | 47 |
| 0 | Dynamic | utilization_gpu_percent | 0 |
| 0 | Dynamic | utilization_memory_percent | 0 |
| 0 | Dynamic | pstate | P2 |
| 0 | Dynamic | graphics_clock_mhz | 2715 |
| 0 | Dynamic | memory_clock_mhz | 9501 |
| 0 | Static | max_graphics_clock_mhz | 3105 |
| 0 | Static | max_memory_clock_mhz | 10001 |
| 0 | Dynamic | pcie_link_gen_current | 4 |
| 0 | Static | pcie_link_gen_max | 4 |
| 0 | Dynamic | pcie_link_width_current | 16 |
| 0 | Static | pcie_link_width_max | 16 |
| 0 | Static | persistence_mode | Disabled |
| 0 | Static | addressing_mode | Not set |
| 0 | Dynamic | fan_speed_percent | 30 |
| 1 | Static | index | 1 |
| 1 | Static | uuid | GPU-c58b7cba-c0e5-971b-e77a-0dd73bf26a9e |
| 1 | Static | serial | 1713224013719 |
| 1 | Static | name | NVIDIA RTX 6000 Ada Generation |
| 1 | Static | pci_bus_id | 00000000:02:00.0 |
| 1 | Static | pci_device_id | 0x26B110DE |
| 1 | Static | pci_sub_device_id | 0x16A110DE |
| 1 | Static | driver_version | 570.211.01 |
| 1 | Static | vbios_version | 95.02.59.00.09 |
| 1 | Static | compute_capability | 8.9 |
| 1 | Static | memory_total_mib | 46068 |
| 1 | Dynamic | memory_used_mib | 6 |
| 1 | Dynamic | memory_free_mib | 45461 |
| 1 | Static | power_limit_w | 300.00 |
| 1 | Dynamic | power_draw_w | 60.32 |
| 1 | Dynamic | temperature_c | 41 |
| 1 | Dynamic | utilization_gpu_percent | 0 |
| 1 | Dynamic | utilization_memory_percent | 0 |
| 1 | Dynamic | pstate | P2 |
| 1 | Dynamic | graphics_clock_mhz | 2115 |
| 1 | Dynamic | memory_clock_mhz | 9501 |
| 1 | Static | max_graphics_clock_mhz | 3105 |
| 1 | Static | max_memory_clock_mhz | 10001 |
| 1 | Dynamic | pcie_link_gen_current | 4 |
| 1 | Static | pcie_link_gen_max | 4 |
| 1 | Dynamic | pcie_link_width_current | 16 |
| 1 | Static | pcie_link_width_max | 16 |
| 1 | Static | persistence_mode | Disabled |
| 1 | Static | addressing_mode | Not set |
| 1 | Dynamic | fan_speed_percent | 30 |

### Python、工具链与运行时

| 项目 | 取值 |
| --- | --- |
| Python 实现 | CPython |
| Python 完整版本 | 3.11.14 (main, Feb  3 2026, 22:51:56) [Clang 21.1.4 ] |
| Python ABI / cache tag | cpython-311-x86_64-linux-gnu / cpython-311 |
| Python 可执行文件 | /data/hongzefu/robomme_benchmark_MotionJEPA/.venv/bin/python3 |
| venv / prefix | /data/hongzefu/robomme_benchmark_MotionJEPA/.venv / /data/hongzefu/robomme_benchmark_MotionJEPA/.venv |
| base prefix | /home/hongzefu/.local/share/uv/python/cpython-3.11.14-linux-x86_64-gnu |
| uv | uv 0.10.2（/home/hongzefu/.local/bin/uv） |
| git | git version 2.43.0（/usr/bin/git） |
| Torch | 2.9.1+cu128 |
| Torch 编译时的 CUDA | 12.8 |
| cuDNN | 91002 |
| Torch CUDA 可用 / 可见设备数 | True / 2 |

| Torch CUDA 序号 | 名称 | 算力 | 显存总量 |
| --- | --- | --- | --- |
| 0 | NVIDIA RTX 6000 Ada Generation | 8.9 | 47673769984 bytes (44.40 GiB) |
| 1 | NVIDIA RTX 6000 Ada Generation | 8.9 | 47673769984 bytes (44.40 GiB) |

### 受限的运行时环境变量

| 类别 | 变量 | 取值 |
| --- | --- | --- |
| 运行时 | CUDA_VISIBLE_DEVICES | 0,1 |
| 运行时 | OMP_NUM_THREADS | Not set |
| 运行时 | MKL_NUM_THREADS | Not set |
| 运行时 | CUDA_HOME | Not set |
| 运行时 | PYTHONPATH | Not set |
| Slurm 分配 | SLURM_JOB_ID | Not set |
| Slurm 分配 | SLURM_JOB_GPUS | Not set |
| Slurm 分配 | SLURM_GPUS_ON_NODE | Not set |
| Slurm 分配 | SLURM_CPUS_PER_TASK | Not set |
| Slurm 分配 | SLURM_CPUS_ON_NODE | Not set |
| Slurm 分配 | SLURM_MEM_PER_NODE | Not set |
| Slurm 分配 | SLURM_MEM_PER_CPU | Not set |
| Slurm 分配 | SLURM_NNODES | Not set |
| Slurm 分配 | SLURM_NODELIST | Not set |

### 依赖

- 已安装的发行包总数：111。
- 完整的发行包列表见同一份 JSON 报告的 debug_environment.packages.distributions。

| 核心依赖 | 版本 |
| --- | --- |
| torch | 2.9.1 |
| torchvision | 0.24.1 |
| mani-skill | 3.0.0b21 |
| sapien | 3.0.2 |
| mplib | 0.1.1 |
| gymnasium | 0.29.1 |
| numpy | 1.26.4 |
| h5py | 3.15.1 |
| opencv-python | 4.11.0.86 |
| setuptools | 80.9.0 |
| robomme | 0.1.0 |

## 运行参数

    {
      "output_dir": "/data/hongzefu/robomme_benchmark_MotionJEPA/artifacts/generated/v4seg-16env-20ep",
      "env": "all",
      "episodes": 20,
      "workers": 16,
      "requested_gpus": "0,1",
      "metadata_root": "/data/hongzefu/robomme_benchmark_MotionJEPA/src/robomme/env_metadata/train",
      "reference_root": "/data/hongzefu/robomme_data_h5",
      "max_abs_diff": 1e-08,
      "seed_attempts_per_episode": 1,
      "save_video_for_recording": true,
      "record_flow": true,
      "record_masked_rgb": false,
      "record_segmentation": true,
      "reference_validation": false,
      "tasks": [
        "PickXtimes",
        "StopCube",
        "SwingXtimes",
        "BinFill",
        "VideoUnmaskSwap",
        "VideoUnmask",
        "ButtonUnmaskSwap",
        "ButtonUnmask",
        "VideoRepick",
        "VideoPlaceButton",
        "VideoPlaceOrder",
        "PickHighlight",
        "InsertPeg",
        "MoveCube",
        "PatternLock",
        "RouteStick"
      ],
      "gpus": [
        "0",
        "1"
      ]
    }

## 范围

- 任务数：0
- episode 列表：[]
- 预期轨迹条数：0
- 是否完整的 16x100：False

## 生成与契约校验

- 成功的 worker 数：320
- 失败的 worker 数：0
- metadata 错误数：0
- 生成侧 HDF5 错误数：0
- 官方侧 HDF5 错误数：0
- 官方侧末帧完成数：0/0
- 生成侧末帧完成数：0/0

## joint_action 逐元素对拍

- 向量条数：0
- 元素总数：0
- 存在差异的元素数：0
- 对拍错误数：0
- 最大绝对差异：None
- 最大差异出现的位置：None
- 允许的最大绝对差异：None
- 是否在容差内：False

## 文件清单

- 状态：未采集
- 官方参考数据 revision：a5e4e25ffe8af34f64944f9533d06455ce5f8337
- 生成文件数：0
- 生成字节数：0
- 官方参考 HDF5 文件数：0
- 官方参考 HDF5 字节数：0

## 结论

- 是否通过完整验收：None

## 报告文件

- JSON：/data/hongzefu/robomme_benchmark_MotionJEPA/scripts/data-generation-v4/reports/generation_report.json
- Markdown：/data/hongzefu/robomme_benchmark_MotionJEPA/scripts/data-generation-v4/reports/generation_report.md
