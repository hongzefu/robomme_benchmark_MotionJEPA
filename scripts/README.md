# robomme-ICL 四个入口

日常只使用本目录的四个脚本。`src/robomme_icl` 保留可导入的库实现，旧控制台命令和模块入口已经移除。旧工具位于 [legacy/](legacy/README.md)；`challenge_interface` 和原版 `src/robomme` 保持原样。旧生成数据和报告已在新批次验收后清理，只保留本次交付产物；官方参考数据未触碰。

| 入口 | 输入 | 输出 |
| --- | --- | --- |
| [prepare_suite.py](prepare_suite.py) | 两份配置，或已有冻结清单 | `suite/suite.json` 和认证记录 |
| [generate_dataset.py](generate_dataset.py) | 已认证清单 | 逐 episode HDF5、生成 MP4、分布图 |
| [replay_dataset.py](replay_dataset.py) | 单个HDF5、数据目录或整批根目录 | 严格回放HDF5、回放MP4 |
| [plot_distribution.py](plot_distribution.py) | 已认证清单 | 四任务配额/布局/散点图和分层统计 |

所有命令从本仓库根目录运行，使用同一份uv环境：

```bash
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
uv sync --locked --extra dev
uv run scripts/prepare_suite.py --help
```

## 先生成环境清单

用默认两份配置生成新清单；默认四任务各24条、每档8条、两卡0/1及32 workers。`--task-config` 和 `--position-config` 可指定修改后的配置。单条控制过程墙钟上限默认1200秒。

```bash
uv run scripts/prepare_suite.py \
  --task-config src/robomme_icl/configs/task_distribution.json \
  --position-config src/robomme_icl/configs/position_distribution.json \
  --output-dir artifacts/generated/robomme-icl/my-run \
  --gpus 0,1 --workers 32
```

入口迁移会改变源码指纹。已有认证清单可按下面的方式创建下一批：保持原spec全文、seed、位置、次数和GPU绑定，每条当前两次物理运行都与来源记录的原始帧严格比较，不重新搜索候选。输入批次与输出批次必须分开。

```bash
uv run scripts/prepare_suite.py \
  --source-suite artifacts/generated/robomme-icl/scripts-v1/suite/suite.json \
  --output-dir artifacts/generated/robomme-icl/next-run \
  --workers 32
```

`--source-suite` 不能与两份新配置或候选上限同时使用。新配置模式允许 `--max-candidates` 缩小诊断搜索上限；源清单模式不搜索候选。首次真实验证先使用 `--tasks BinFill --episodes-per-task 1 --workers 1`，随后再扩大范围。

## 生成HDF5、视频和分布图

```bash
uv run scripts/generate_dataset.py \
  --suite artifacts/generated/robomme-icl/scripts-v1/suite \
  --output-dir artifacts/generated/robomme-icl/scripts-v1 \
  --workers 32 --video-workers 4
```

必须先有认证清单。生成阶段不会重编译场景、替换seed或改变任务配额。`--tasks`、`--episodes-per-task` 可选择清单中的子集，沿用原seed；绘图使用同一子集，并明确标出没有样本的任务/难度。

保持当前ICL HDF5的 `setup/steps` 结构，不合并为任务级文件。视频是前视与腕部RGB横拼、演示红框，当前为512×256、20fps；FPS来自spec控制频率。编码使用FFmpeg、libx264、yuv420p、CRF18、单编码线程。原始RGB不被修改，逐位一致性仍比较HDF5数据，MP4用于观看。

视频必须成功保存后，整批生成才标记完成。每条视频的同名JSON保存输入内容哈希、spec_hash、帧数、FPS、编码参数和视频哈希。编码失败保留已完成HDF5，重复相同命令会校验后复用完整记录，只补缺失媒体；未知或不匹配文件不会被覆盖。

## 严格回放并保存视频

```bash
uv run scripts/replay_dataset.py \
  --input artifacts/generated/robomme-icl/scripts-v1/hdf5_files \
  --output-dir artifacts/generated/robomme-icl/scripts-v1/replay \
  --workers 32 --video-workers 4
```

`--input` 也可以是单个HDF5或含 `hdf5_files/` 的批次根。目录扫描排除隐藏暂存、认证副本和回放子目录，发现重复task/seed直接报错。输出不能与输入指向同一个文件。回放使用HDF5自带的完整spec、原动作精度和原GPU绑定，不读取旧train metadata。

## 单独生成或核对分布图

```bash
uv run scripts/plot_distribution.py \
  --suite artifacts/generated/robomme-icl/scripts-v1/suite \
  --output-dir artifacts/generated/robomme-icl/scripts-v1/distributions
```

生成脚本会自动调用同一绘图实现；独立入口不运行仿真，可读取本批清单，也可用保留的 `provenance/source_suite.json` 来源快照绘图。四任务各一张组合图，包含按难度的次数配额、单局布局、跨episode散点与支持范围。`distribution_summary.json` 记录实际计数、位置分层覆盖及来源哈希。同来源完整图可验证后复用，缺图可以补齐，不能把不同清单的图混入同一目录。

## 产物目录与恢复

```text
artifacts/generated/robomme-icl/<批次>/
├── suite/suite.json
├── hdf5_files/<Task>/seed_<seed>.h5
├── videos/<Task>/seed_<seed>.mp4
├── videos/<Task>/seed_<seed>.json
├── distributions/                    四张PNG、逐图来源和distribution_summary.json
├── replay/hdf5_files/<Task>/
├── replay/videos/<Task>/
├── run_parameters.json
├── episode_results.jsonl
├── run_summary.json
└── logs/                             各次阶段结果；正式运行另留完整控制台日志
```

按子集生成时额外保存 `selection/suite.json`，仅用于准确描述该子集。重新运行同一命令会检查数据身份与入口实现哈希；可调整并发参数，但不能在原输出目录中换清单、改配置或混入来源不明数据。相同输出目录不得同时启动两个控制进程。原版及参考数据目录禁止写入。

本次交付统一放入 `scripts-v1/`，报告位于 `artifacts/reports/robomme-icl/scripts-v1/`。旧v3清单的来源快照保留在本次产物的 `provenance/` 中；原v3大数据及其他历史生成产物按用户指令清理。清理后的来源路径仅作历史说明，后续重新认证使用仍完整保留的本次 `suite/suite.json` 及其认证记录。

本批96条环境已全部通过重新认证、生成和严格回放，每遍63,689帧原始记录逐位一致；96个生成视频、96个回放视频和四张分布图均已保存并独立验收。清理后再次核对本批完整性，详见 [最终交付报告](../artifacts/reports/robomme-icl/scripts-v1/FINAL.md)。

## 正式运行

预计超过五分钟的命令按根 `AGENTS.md` 放入已登记的detached tmux，从干净提交启动。以下是生成阶段的形式，其余入口同样处理：

```bash
mkdir -p artifacts/generated/robomme-icl/scripts-v1/logs
tmux new-session -d -s gen-icl-scripts-v1 \
  'set -o pipefail; cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask; PYTHONUNBUFFERED=1 uv run scripts/generate_dataset.py --suite artifacts/generated/robomme-icl/scripts-v1/suite --output-dir artifacts/generated/robomme-icl/scripts-v1 --workers 32 --video-workers 4 2>&1 | tee artifacts/generated/robomme-icl/scripts-v1/logs/generate.log; echo "EXIT_CODE=$?" >> artifacts/generated/robomme-icl/scripts-v1/logs/generate.log'
```

生成/回放默认32个物理工作名额、视频导出4个CPU工作进程；实际物理仍为CPU单环境，GPU只按冻结绑定选择。不要设置 `CUDA_VISIBLE_DEVICES` 重新编号。所有输出必须是仓库内实体路径，不能覆盖参考集或通过符号链接写到仓库外。
