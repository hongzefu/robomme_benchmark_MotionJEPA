# S3 启动与软件路径只读核查

本次未启动仿真、未修改运行进程或依赖。核查对象是正在运行的 PID 1843953、基线 `artifacts/newtask-v6/v1/base` 和当前 `artifacts/newtask-v6/v6-s3-20260926-01`，源码比较 `13e5151..38488db`。

- 基线结果明确 `worker=official._worker`、`workers=1`、`elapsed_seconds=2994.218`；当前冒烟结果同样是 `official._worker`，不是附带随机流追踪的镜像 worker。
- 两侧都用 `train_split_runner::main` 的 `ProcessPoolExecutor(mp_context=spawn,max_workers=1)`，一次提交全部身份，未设置逐条回收进程。当前只是把 144 身份拆成 1 条冒烟和剩余 143 条，不能把整批约八倍变慢归于逐条重启。
- 两侧官方入口都是 `artifacts/train-parity/local-smoke-01/official-src/scripts/data-generation/generate_dataset.py`。`_worker` 同样传入 `obs_mode=rgb+depth+segmentation`、`control_mode=pd_joint_pos`、`render_mode=rgb_array`、`reward_mode=dense` 并开启视频。基线 `src_root` 指向 `artifacts/newtask-v6/v1/base-source`；当前指向主仓库。这是有意比较的环境源码差异。
- 两份 `run_config.json` 的九项 `environment` 完全一致，包括 Python 3.11.14、驱动 570.211.01、GPU 0、锁文件和项目声明散列。它们没有保存全部已安装包或动态库指纹，因此不能声称完整软件环境已逐字确认一致。
- 当前 `/proc/1843953/exe` 指向 uv 的 CPython 3.11.14；`maps` 证实加载主仓库 `.venv` 下 SAPIEN、Torch、CUDA runtime，以及系统驱动 `libcuda.so.570.211.01` 和 NVIDIA Vulkan 相关库。SAPIEN 扩展、`libsvulkan2.so`、`libtorch_cuda.so` 的 ctime 均为 2026-09-07，早于同日两次运行，没有这三项在两次运行之间被替换的迹象；这不是历史文件散列证明。
- 当前进程环境可见 `CUDA_VISIBLE_DEVICES=0`、`OMP_NUM_THREADS=1`、`MKL_NUM_THREADS=1`。基线未保存这些线程变量，不能宣称线程环境全等。
- `src/robomme/__init__.py` 与 `robomme_env/__init__.py` 两提交之间无差异。录像器唯一差异是步数保护 2000→5000；对未到 2000 步的成功局不引入额外逐步工作。runner 的新增身份公式和镜像 worker 选项在本次 B 路默认参数下不启用。

可复现的低开销核查：`jq '.environment' <两侧run_config.json>`、`jq 'del(.results)' <两侧results/B.json>`、`git diff 13e5151 38488db -- scripts/parity/train_split_runner.py scripts/parity/train_split_worker.py src/robomme/env_record_wrapper/RecordWrapper.py`、读取 `/proc/1843953/{cmdline,maps}`、`stat` 上述三份动态库。所用命令退出码为 0；未生成额外轨迹。

结论：已排除逐条重建 worker、镜像追踪开关和显式渲染模式更换这三个解释；本次静态及文件元数据证据没有建立八倍差异的因果机制。NVIDIA 锁等待的动态证据应由主调查合并，不能由此报告单独断言根因。
