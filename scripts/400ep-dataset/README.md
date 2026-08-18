# 400ep 数据集：四个 Unmask 系 env 各 400 条（ep0–399）

> 状态：**已完成（2026-08-18）**。1600 条 h5 全部就位、终验全过、metadata 已写回。

本目录沉淀 2026-08-18 这次数据集扩展的全部决策、复现步骤、过程 log 与结果，
目标是**不看会话记录也能完整复现**。机器可读凭据（run_parameters / run_summary 副本、
metadata diff）随同收入本目录；逐段运行记录见 [run-log.md](run-log.md)。

## 一、目标与最终口径

| 项 | 口径 |
| --- | --- |
| 环境 | ButtonUnmask / VideoUnmask / ButtonUnmaskSwap / VideoUnmaskSwap |
| 规模 | 每 env 400 条 episode（ep0–399），共 1600 条 |
| 产物 | 逐 episode h5（`{task}_ep{N}_seed{M}.h5`），**不合并**成官方单文件格式 |
| metadata | `src/robomme/env_metadata/train` 的 4 个 json 从 100 条扩到 400 条；**ep0–99 原样保留一字不动** |
| 难度 | ratio `211`（每 4 条 easy,easy,medium,hard，按绝对 episode 号取），与原 train 一致 |

## 二、决策记录（用户指令原话 + 取舍缘由）

按时间顺序：

1. 初始指令：「生成400个全新episode 的h5，接续 `src/robomme/env_metadata/train`，
   只要 buttonunmask videounmask buttonunmaskswap videounmaskswap，并且写入 train metadata」，
   并问「h5 现在和原版 <https://huggingface.co/datasets/Yinpei/robomme_data_h5> 格式有什么区别」（答案见第六节）。
2. 追问澄清后用户改口径：**「每个 env 各 400 条」**、h5 **不合并**。
3. 再改：**「改为从ep0开始的400个」**（即 ep0–399，不是接续 ep100 起算 400）。
4. 探针取舍（关键决策）：原 train metadata 里有 8 个 episode 当年 attempt=1（seed 尾号 1）。
   当前环境代码与 2025-12 有行为漂移（见 `scripts/data-generation-newSeed/CLAUDE.md` 第十三节：
   2026-08-17 实测这 8 个 seed 现在全部 attempt=0 一次通过），无 seed 生成会得到尾号 0 的 seed，
   与现有 metadata 不一致。用户选择：**「ep0–99 保留原 metadata」**。
5. 沉淀要求：「把这次的决策、结果、过程log 全部写 scripts 新建文档 400ep dataset 保证之后可复现」，
   后明确为「scripts 下面的文件夹，其中包括 readme 文档」——即本目录。
6. ep0–99 来源再改（执行中途）：**「ep0–99 直接拼接现有数据集 不用再验证 拼接现有的
   Yinpei/robomme_data_h5 副本」** —— 不重新生成、不做数值验证，直接把本地官方数据副本
   `/data/hongzefu/robomme_data_h5` 按 episode 组拆成逐 episode 文件。此前已尝试用复现链路
   重新生成 ep0–99，因该链路硬性要求仓库内 `data/robomme_data_h5` 参考数据而启动失败
   （详见 run-log 第 2 节），此口径变更后复现段整体取消。

最终的**两段式方案**：

- **ep0–99**：**拼接官方数据副本**——用本目录 `split_official_h5.py` 把
  `/data/hongzefu/robomme_data_h5/record_dataset_{task}.h5` 的 `episode_0..99` 组逐个拆成
  `{task}_ep{N}_seed{M}.h5`（merge 的严格逆操作），seed 与现有 metadata 天然逐条一致
  （官方数据本就按 train metadata 的 seed 生成，含 8 条尾号 1 的探针）；
- **ep100–399**：走生成型链路 `scripts/data-generation-newSeed/generate_dataset_newseed.py`
  （seed 按公式自算、失败自动 attempt+1 换 seed），并把结果**追加**进 train metadata。

⚠️ **字段集因此不均一**（已知且接受）：ep0–99 来自官方数据，每 timestep 27 个字段；
ep100–399 由当前代码生成，21 个字段（官方的真子集，差异见第六节）。按公共 21 字段读取则两段无差别。

## 三、代码改动清单

本次为支撑 ep100–399 生成所做的改动（commit 号见 git log，subject 含「400ep」）：

| 文件 | 改动 |
| --- | --- |
| `scripts/data-generation-newSeed/generate_dataset_newseed.py` | 加 `--episode-start`（默认 0）；`--episodes` 改为「每个环境的条数」并去掉 100 上限；新增 seed 越块护栏（最大可能 seed 不得越过下一代布局 offset 500000）；`run_parameters.json` 记录 `episode_start` |
| `scripts/data-generation-newSeed/utils/append_train_metadata.py` | 新增：把生成输出的 metadata 追加进 `env_metadata/train`，两阶段（全部校验通过才统一落盘），断言无重叠、合并后连续，支持 `--dry-run`；序列化口径与现有文件逐字一致（indent=2、结尾无换行），git diff 呈现为纯追加 |
| `tests/lightweight/test_seed_layout.py` | 精确断言收窄到原始 ep0–99 段（ep100+ 允许新的 attempt≠0，只验合法域与难度）；新增 ep100+ seed/难度锚点用例 |
| `tests/lightweight/test_append_train_metadata.py` | 新增：追加脚本的合并/拒绝/两阶段语义测试 |

## 四、复现步骤

前提：仓库根目录，`.venv` 就绪（`uv sync`）。seed 公式（唯一定义在
`scripts/data-generation-newSeed/seed_layout.py`）：

```
seed = env_code * 1000 + episode * 100 + attempt      # train 布局
env_code: VideoUnmaskSwap=5, VideoUnmask=6, ButtonUnmaskSwap=7, ButtonUnmask=8
难度: "211" → [easy, easy, medium, hard]，按 episode % 4 取
```

### 4.1 ep0–99 拼接段（拆分官方数据副本，纯 IO）

前提：本地存在官方数据副本（HuggingFace `Yinpei/robomme_data_h5` 解包后的
`record_dataset_{task}.h5`，本机在 `/data/hongzefu/robomme_data_h5`）。

```bash
uv run python scripts/400ep-dataset/split_official_h5.py \
  --official-dir /data/hongzefu/robomme_data_h5 \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask \
  --episodes 100 \
  --output-dir scripts/data-generation-newSeed/outputs/train-ep0-99-official
```

不重跑仿真、不做数值验证（用户口径）；唯一防错检查是每个 episode 组的
`setup/seed` 必须等于 train metadata 里该 episode 的 seed（防拼错来源/错位）。
已有目标文件自动跳过，可安全续跑。

### 4.2 ep100–399 生成段（无 seed 自算，约 56 分钟）

```bash
uv run python scripts/data-generation-newSeed/generate_dataset_newseed.py \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask \
  --episode-start 100 --episodes 300 --difficulty 211 \
  --gpus <空闲卡号> --workers 32 \
  --output-dir scripts/data-generation-newSeed/outputs/train-ep100-399
```

workers=32 单卡是 2026-08-17 标定的吞吐最优（56.12 ep/min，W=44 会崩，双卡无收益，
CPU 是唯一瓶颈——本机 32 核 EPYC 9334；详见 `scripts/data-generation-newSeed/CLAUDE.md` 第十节）。
验收：`run_summary.json` 的 `exhausted_count=0`，1200/1200 成功。

> 复现性说明：seed 是纯函数 `f(env_code, episode, attempt)`，并行度与执行顺序不影响结果；
> 但 attempt 演进取决于环境代码行为，换代码版本重跑可能在个别 episode 上选中不同 seed
> （这正是 ep0–99 要走复现链路的原因）。用**本仓库当前 commit** 重跑则结果逐条可复现。

### 4.3 写回 train metadata

```bash
uv run python scripts/data-generation-newSeed/utils/append_train_metadata.py \
  --input-dir scripts/data-generation-newSeed/outputs/train-ep100-399 \
  --env VideoUnmaskSwap,VideoUnmask,ButtonUnmaskSwap,ButtonUnmask --dry-run
# 核对输出后去掉 --dry-run 正式写入
```

### 4.4 汇总交付目录（硬链接，零拷贝）

两段的 h5 硬链接进单一目录 `scripts/data-generation-newSeed/outputs/train-ep0-399/hdf5_files/`
（命令见 run-log.md），两段原始运行目录保持自洽不动。

## 五、结果

| 项 | 值 |
| --- | --- |
| 交付目录 | `scripts/data-generation-newSeed/outputs/train-ep0-399/hdf5_files/`（硬链接汇总） |
| 文件数 | **1600 个 h5，每 env 恰 400**（ep0–399），合计 **301 GB** |
| ep0–99 段 | 官方副本拆分 400 条 / 77 GB，256.7 s，seed 防错检查全过，8 条探针文件在列 |
| ep100–399 段 | 生成 1200/1200 成功、**全部 attempt=0**、零重试，41.7 分钟（28.79 ep/min） |
| metadata | 4 个 train json 各 100 → 400 条，diff 纯追加，ep0–99 一字未动 |
| 终验 | 文件名↔metadata 双向逐条对应 / h5 抽查（12 条）/ resolver 冒烟（400 条、探针保留、难度正确）全过 |
| 测试 | `test_seed_layout` + `test_append_train_metadata` 共 15 项通过（写回后复跑） |

两段原始运行目录（各自带日志、jsonl、run_summary）保留在
`outputs/train-ep0-99-official/` 与 `outputs/train-ep100-399/`；本目录存有生成段
`run_parameters.json` / `run_summary.json` 副本。过程细节与逐段数字见 [run-log.md](run-log.md)。

## 六、h5 与原版官方数据（Yinpei/robomme_data_h5）的格式差异

2026-08-17 逐项比对结论（比对细节见 `scripts/data-generation-newSeed/CLAUDE.md` 第十四节）：

1. **字段集**：生成侧每 timestep 21 个字段，是原版 27 个的**真子集**，无任何多余字段。
   缺的 8 个：`action/eef_action_raw/{pose,quat,rpy}`、`obs/eef_state_raw/{pose,quat,rpy}`、
   `setup/fail_recover_mode`、`setup/fail_recover_seed_anchor` —— 上游 commit `68a65a0`
   （2026-03-01）有意删除，非缺陷。
2. **存储形态**：原版是每 task 一个合并文件 `record_dataset_{task}.h5`（内部 `episode_N` 组）；
   生成侧是逐 episode 文件 `{task}_ep{N}_seed{M}.h5`。需要官方形态时用
   `scripts/data-generation-newSeed/merge_episode_h5.py` 合并（本次不合并）。
3. **数值**：同 seed 的 392 条中 389 条 `action/joint_action` 逐位相同（<1e-8），
   其余 3 条最大差 2.146e-06，为浮点沿轨迹累积噪声（集中在连续关节 j3、夹爪 j7 恒为 0、
   峰值在轨迹末段），无逻辑分叉 —— **数值层面等价**。
