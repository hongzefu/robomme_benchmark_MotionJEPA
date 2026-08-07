# No-Patch Dataset Generation Report

## Run Provenance

- Status: generated
- Current HEAD: 5010225d55637f2b5cb385664981ee632177093a
- uv.lock SHA-256: 983de83f7b22c98b96c3c25a39958b4f5920e3232cfaa209c89542ef5639ac03
- Report time (UTC): 2026-08-07T01:46:54.470964+00:00
- Report mode: generation

## Debug Environment

- Snapshot time (UTC): 2026-08-07T01:52:34.080356+00:00
- Host: sled-vail
- OS: Linux 6.8.0-1018-nvidia-lowlatency
- Kernel: 6.8.0-1018-nvidia-lowlatency
- Architecture: 64bit; Machine: x86_64
- libc: glibc 2.39

### CPU, Memory, and Storage

| Item | Value |
| --- | --- |
| OS CPU count | 32 |
| CPU affinity count | 32 |
| CPU affinity IDs | 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31 |
| CPU model | AMD EPYC 9334 32-Core Processor |
| CPU sockets | 1 |
| Threads per core | 1 |
| Total memory | 405257068544 bytes (377.43 GiB) |
| Repository filesystem | /data/hongzefu/robomme_benchmark_MotionJEPA |
| Filesystem capacity | 15240752955392 bytes (13.86 TiB) |
| Filesystem used | 9728752422912 bytes (8.85 TiB) |
| Filesystem available | 4743834255360 bytes (4.31 TiB) |
- The complete lscpu --json raw fields are available in JSON at debug_environment.cpu.lscpu.raw.

### GPU (nvidia-smi)

- nvidia-smi available: True
- nvidia-smi version: 570.211.01
- nvidia-smi CUDA version: 12.8

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
| 0 | Dynamic | power_draw_w | 23.01 |
| 0 | Dynamic | temperature_c | 38 |
| 0 | Dynamic | utilization_gpu_percent | 0 |
| 0 | Dynamic | utilization_memory_percent | 0 |
| 0 | Dynamic | pstate | P2 |
| 0 | Dynamic | graphics_clock_mhz | 210 |
| 0 | Dynamic | memory_clock_mhz | 405 |
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
| 1 | Dynamic | power_draw_w | 27.86 |
| 1 | Dynamic | temperature_c | 32 |
| 1 | Dynamic | utilization_gpu_percent | 0 |
| 1 | Dynamic | utilization_memory_percent | 0 |
| 1 | Dynamic | pstate | P2 |
| 1 | Dynamic | graphics_clock_mhz | 210 |
| 1 | Dynamic | memory_clock_mhz | 405 |
| 1 | Static | max_graphics_clock_mhz | 3105 |
| 1 | Static | max_memory_clock_mhz | 10001 |
| 1 | Dynamic | pcie_link_gen_current | 4 |
| 1 | Static | pcie_link_gen_max | 4 |
| 1 | Dynamic | pcie_link_width_current | 16 |
| 1 | Static | pcie_link_width_max | 16 |
| 1 | Static | persistence_mode | Disabled |
| 1 | Static | addressing_mode | Not set |
| 1 | Dynamic | fan_speed_percent | 30 |

### Python, Tools, and Runtime

| Item | Value |
| --- | --- |
| Python implementation | CPython |
| Full Python version | 3.11.14 (main, Feb  3 2026, 22:51:56) [Clang 21.1.4 ] |
| Python ABI / cache tag | cpython-311-x86_64-linux-gnu / cpython-311 |
| Python executable | /data/hongzefu/robomme_benchmark_MotionJEPA/.venv/bin/python3 |
| venv / prefix | /data/hongzefu/robomme_benchmark_MotionJEPA/.venv / /data/hongzefu/robomme_benchmark_MotionJEPA/.venv |
| base prefix | /home/hongzefu/.local/share/uv/python/cpython-3.11.14-linux-x86_64-gnu |
| uv | uv 0.10.2 (/home/hongzefu/.local/bin/uv) |
| git | git version 2.43.0 (/usr/bin/git) |
| Torch | 2.9.1+cu128 |
| Torch compiled CUDA | 12.8 |
| cuDNN | 91002 |
| Torch CUDA available / visible count | True / 1 |

| Torch CUDA index | Name | Compute capability | Total memory |
| --- | --- | --- | --- |
| 0 | NVIDIA RTX 6000 Ada Generation | 8.9 | 47673769984 bytes (44.40 GiB) |

### Restricted Runtime Environment

| Category | Variable | Value |
| --- | --- | --- |
| Runtime | CUDA_VISIBLE_DEVICES | 0 |
| Runtime | OMP_NUM_THREADS | Not set |
| Runtime | MKL_NUM_THREADS | Not set |
| Runtime | CUDA_HOME | Not set |
| Runtime | PYTHONPATH | Not set |
| Slurm allocation | SLURM_JOB_ID | Not set |
| Slurm allocation | SLURM_JOB_GPUS | Not set |
| Slurm allocation | SLURM_GPUS_ON_NODE | Not set |
| Slurm allocation | SLURM_CPUS_PER_TASK | Not set |
| Slurm allocation | SLURM_CPUS_ON_NODE | Not set |
| Slurm allocation | SLURM_MEM_PER_NODE | Not set |
| Slurm allocation | SLURM_MEM_PER_CPU | Not set |
| Slurm allocation | SLURM_NNODES | Not set |
| Slurm allocation | SLURM_NODELIST | Not set |

### Dependencies

- Total distributions: 111.
- The complete distribution list is available in the same JSON at debug_environment.packages.distributions.

| Core dependency | Version |
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

## Parameters

    {
      "output_dir": "/data/hongzefu/robomme_benchmark_MotionJEPA/artifacts/generated/flow-16env",
      "env": "all",
      "episodes": 1,
      "workers": 1,
      "requested_gpus": "0",
      "metadata_root": "/data/hongzefu/robomme_benchmark_MotionJEPA/src/robomme/env_metadata/train",
      "reference_root": "/data/hongzefu/robomme_data_h5",
      "max_abs_diff": 1e-08,
      "seed_attempts_per_episode": 1,
      "save_video_for_recording": true,
      "record_flow": true,
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
        "0"
      ]
    }

## Scope

- Task count: 0
- Episodes: []
- Expected trajectory count: 0
- Complete 16x100: False

## Generation and Contract

- Successful workers: 16
- Failed workers: 0
- Metadata errors: 0
- Generated HDF5 errors: 0
- Official HDF5 errors: 0
- Official final completions: 0/0
- Generated final completions: 0/0

## Element-wise joint_action Comparison

- Vectors: 0
- Elements: 0
- Different elements: 0
- Comparison errors: 0
- Maximum absolute difference: None
- Maximum-difference location: None
- Maximum allowed absolute difference: None
- Within tolerance: False

## File Manifest

- Status: not collected
- Official reference revision: a5e4e25ffe8af34f64944f9533d06455ce5f8337
- Generated files: 0
- Generated bytes: 0
- Official reference HDF5 files: 0
- Official reference HDF5 bytes: 0

## Conclusion

- Full acceptance passed: None

## Artifacts

- JSON: /data/hongzefu/robomme_benchmark_MotionJEPA/scripts/data-generation-v2/reports/generation_report.json
- Markdown: /data/hongzefu/robomme_benchmark_MotionJEPA/scripts/data-generation-v2/reports/generation_report.md
