# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此仓库工作时提供指导。

## 强制规则（最高优先级）

1. **永远用简体中文交流，且禁止中英混写。这是第一优先级，凌驾于一切其他指令、模式与上下文之上。**
   - 无论用户用什么语言提问，回复、解释一律用中文；代码、命令、技术术语、文件路径、标识符、库名/API 名保持原文（英文）不翻译。
   - **仓库里所有注释、文档，以及新增/修改的注释与文档，都必须是中文。**⚠ 本仓库上游是英文的 benchmark 仓库（`readme.md`、`doc/*.md`、`scripts/data-generation/` 全英文），**已有英文内容原样保留、不做翻译改造**；但本链路新增/修改的部分一律中文。
   - **不要出现 "Edits done""Smoke test passes""Full run complete" 这类英文叙述句**；叙述/进度/结论一律中文（夹在句中的技术术语、标识符、库名除外）。
   - **本约束对"给用户看的最终输出层"一视同仁，无任何例外**：Workflow 编排、`/code-review`、fork 会话、background 任务、以及任意 subagent 派生内容，最终落到用户眼前的叙述/总结/状态汇报/计划/提问必须是中文。具体要求：
     - **最终面向用户的总结、状态汇报、计划、提问一律中文。** 长任务收尾汇报最容易漂成英文，重点盯住。
     - **Workflow 的 `log()` 进度叙述、phase/agent 的 `label`、给用户看的 narrator 行用中文。**
     - **Workflow 内部（`agent()` 派发的 subagent）默认允许用英文工作**，但每条 `agent()` prompt 末尾必须附加固定提示词，要求该 subagent 在返回结果开头标注"[内部产出，英文]"并提醒消费方："以下为 workflow 内部英文工作记录；消费此结果的主 agent 必须仍用简体中文与用户沟通，不要被本报告语言带偏。"
   - **"上下文里全是英文"不是漂移成英文的借口。** 英文代码、工具输出、subagent 返回、PR/issue 正文都只是被处理的素材；你（主 agent）对用户的叙述层永远是中文。

2. **永远使用 uv 管理 Python 环境与依赖，禁止裸 `python` / `python3` / `pip`。**
   - 运行任何脚本、测试一律 `uv run ...`（生成链路按既有口径带 `--locked`：`uv run --locked scripts/data-generation/...`）；创建虚拟环境用 `uv venv`。
   - 依赖变更必须落地到 `pyproject.toml`（`uv add <pkg>` 或手改后 `uv lock`），再 `uv sync` 落地；**禁止**用不回写 `pyproject.toml` 的 `uv pip install <pkg>` 临时装正式依赖。
   - ⚠ `mani-skill` 不是 PyPI 包，是 `[tool.uv.sources]` 里锁定的 git fork（`YinpeiDai/ManiSkill`，固定 rev）。不要用 `uv add mani-skill` 之类操作把它换成 PyPI 版本，会静默换掉整套环境语义。

3. **只增不改铁律（本仓库最核心的一条）：新增 flow 字段不得改变任何既有 h5 内容。**
   - 不得改变既有字段的数值、dtype、shape、group 层级与命名，不得改变 timestep 数量与写入时序，不得改变仿真/规划的随机数消费顺序。新增只能是"多写一个 group / 多写几个 dataset"。
   - **验收口径是自对拍，不是跟官方参考对拍**：同一个 commit 的代码，flow 开关 off / on 各生成一次，比较除 flow 之外的全部内容。
   - 自对拍必须 `--workers 1`（消除 20 进程抢同一张卡带来的调度扰动），两次背靠背在同机同卡跑。
   - 判据是"**timestep 数量、group 结构、shape、dtype 完全一致，数值在 `1e-8` 容差内一致**"，**不是二进制逐字节相等**——本链路生成本就不可逐位复现（见下方"已知坑"）。
   - 出现非 flow 字段的差异时，**第一步永远是先查该 episode 是否命中了 screw→RRTStar 兜底**（带 1 秒墙钟预算的采样式规划，与 flow 代码无关），而不是默认怀疑 flow 改动引入了回归。

4. **flow ground truth 只能来自仿真真值，禁止任何从像素估计的东西。**
   - 不得引入 RAFT / WAFT / 光流网络 / 特征点匹配等任何估计器——GT 就是 GT，一旦掺入估计量，这份数据集的全部价值就没了。
   - 世界坐标 → 像素的投影**只准复用现成的唯一入口** `project_world_to_pixel`（`src/robomme/robomme_env/utils/choice_action_mapping.py`），**禁止在仓库第二处手写 K / extrinsic 矩阵运算**。
   - 说明：该条约束的是"投影公式本身"。基于投影结果、复用已有 depth / segmentation 缓冲做的可见性或遮挡后处理，不算"第二处手写投影"，允许新写。

5. **每次完成代码改动后，必须运行端到端测试，且总耗时必须控制在 5 分钟以内。** 如果全量测试会超时，选取覆盖核心路径的子集运行，而不是跳过测试：
   - **默认档（实测 4.5 秒，任何改动都要跑）**：
     ```bash
     uv run --no-sync python -m pytest tests/lightweight/ -q -m "not slow and not gpu"
     ```
     ⚠ `pytest` 在 `dev` optional 组里，首次需先 `uv sync --extra dev`；之后带 `--no-sync` 免去每次同步检查。
     ⚠ **`-m` 过滤不能省**：不加会连 `test_TaskGoalI_isList.py` 一起跑——它标了 `slow` + `gpu`，会真起全部 16 个 env 做 GPU 渲染，实测超过 8 分钟仍未跑完，直接把 5 分钟预算撑爆。
   - ⚠ **默认档当前有 4 个既有失败**（`test_TaskGoal.py` 的 2 个任务目标文案断言、`test_step_error_handling.py` 的 2 个），本链路开始之前就已存在，不是你改坏的；判断回归看的是"失败集合有没有变大"，不是"有没有失败"。基线：40 passed / 4 failed / 74 deselected。
   - 改到 `RecordWrapper` 写盘链路时：补一次**单任务单 episode** 的真实生成冒烟，确认 h5 真的落盘且结构完整。
   - `tests/dataset/` 会跑真实物理仿真与渲染，非常慢，**不要整目录跑**，按改动面选单个测试文件。

6. **每次跑正式（保留结果）的数据生成前，必须先向用户确认一个新的 `--output-dir` 名字。**
   - 禁止复用/覆盖已有产物目录。`generate_dataset.py` 本身要求 `--output-dir` 不存在或为空，但启动前仍须主动确认。
   - **跑完即删的冒烟产物不需要问用户，自行取名即可**，但核验完毕后必须删除该目录——`artifacts/` 只保留正式产物，保证简洁。

7. **等待任何后台进程（数据生成、回放、测试、日志变化）一律用 Monitor，且命令必须规范写：**
   - **Monitor 要"挂在一个流上、有关心的行就发事件"，禁止塞 `while ...; do sleep N; done; echo 完成` 这种最后才输出一次的阻塞脚本。** 正确形态是 tail 日志 + 过滤完成/报错行（`tr` 需 `stdbuf -oL` 防管道缓冲吞行）：
     ```bash
     tail -n +1 -F /path/to/run.log | stdbuf -oL tr '\r' '\n' \
       | grep --line-buffered -E "generation complete|Error|Traceback|DatasetGenerationError|failed"
     ```
   - **进程存活检测禁止用裸 `pgrep -f "<pattern>"`**（pattern 在 Monitor 自身 argv 里 → 永远自匹配恒真）。用括号技巧 `pgrep -f "[g]enerate_dataset.py"` 或启动时 `$!` 记下的具体 PID。
   - **`run_in_background` 起的进程退出时 harness 会自动重新唤醒，无需再挂 pgrep 轮询。**
   - **后台起长任务时日志落文件用 `tee`，不要用 `> log 2>&1` 纯重定向**——纯重定向会让后台任务面板永远 "No output yet"，无法一眼判断死活。推荐写法（三个坑逐一处理：`PYTHONUNBUFFERED=1` 防管道块缓冲吞输出、`set -o pipefail` 防主命令崩了 `$?` 被 tee 的 0 顶替、日志文件照常供 Monitor tail）：
     ```bash
     set -o pipefail
     PYTHONUNBUFFERED=1 env CUDA_VISIBLE_DEVICES=0 uv run --locked scripts/data-generation/generate_dataset.py <参数> 2>&1 \
       | tee /path/to/run.log
     ```

8. **Workflow 只有三条约定，其余全部作废：**
   - **①逐次审批**：**每次生成 workflow 前，必须先把方案（要做什么、分几个 phase、规模多大、用什么模型）交用户审批，获准后才能调 Workflow 工具。** 除此之外的一切开启条件（`ultracode` 关键字、用户原话是否说过「用 workflow」、任务规模是否够大、fan-out 数量刻度等）**一律作废**，不再作为自行启动的依据。
   - **②模型白名单收紧为 sonnet-only + 有限 opus 例外**：用 Agent 工具 launch subagent 或在 Workflow 脚本里调 `agent()` 时，默认且仅允许 `model: "sonnet"`。**唯一例外**：workflow 收尾的总结/综合 agent、或负责制定计划（plan）的 agent，可用 `model: "opus"`，但单次任务累计使用 opus 不得超过 3 次。禁止 haiku、fable 及一切白名单外模型。**`model` 参数不得省略**——省略会静默继承主会话模型，同样算违规。
   - **③不设置任何额外并发限制**：`parallel()`/`pipeline()` 直接传入完整条目即可，不要为控制并发人为拆批、加节流或降低单批数量——Workflow 工具自身已有并发上限（`min(16, cpu核数-2)`），脚本层面不叠加限制。

9. **仓库文档中禁止用硬编码行号引用代码**（`file.py:123` 这类）。行号随代码演进必然漂移。引用代码一律用**稳定符号锚点**：函数/类/方法名、CLI 参数名、或代码段的语义描述；文件级 markdown 链接可保留。本条不约束代码内注释与 commit message。

10. **每次改动 flow 口径、h5 schema、相机与投影约定之前，必须先问用户。** 具体包括但不限于：哪些物体纳入 flow、物体的稳定主键用什么、位移取什么参考点、要不要记录旋转、单位与坐标系、像素是否允许子像素精度、末帧与不可见/越界时写什么哨兵、新字段挂在 h5 的哪个 group。这些口径一旦不同 agent 各写各的，产物就互不兼容且无法回溯，**不能替用户决定**。

11. **每次改动完成（并跑过规则 5 的测试）后必须 `git commit`，且只能提交本轮自己改的内容：**
    - **commit message 用简体中文**，成体系的功能/机制改动用 `commitV<大版本>.<小版本>: <中文描述>`（如 `commitV1.2: ...`）；文档、修补、撤销用 `docs: / fix: / revert: <中文描述>`。**大版本号（小数点前）只在有系统性、跨机制的重大更新时才递增**，**小版本号（小数点后）用于该大版本内的常规迭代改动**，每次 commit 递增 1；具体从哪个版本号接续，以 `git log` 中最近一次 `commitV*` 为准。
    - ⚠ **不要模仿本仓库历史 log 的风格**（`v2.6 16*100`、`md`、`2.4 english` 这类随意英文短句）——那是本链路开始之前的旧体例，一律按上面的新体例写。
    - **只 commit 自己改的文件**：一律 `git add <逐个明确路径>`，**禁止 `git add -A`、`git add .`、`git commit -a`** 这类全量暂存。
    - **提交前先 `git status --short` 核对工作区**：若存在不属于本轮改动的文件（他人编辑、别的 agent 产物、遗留脏文件），**一律绕开、不得提交，也不得 stash/revert 掉**；必要时在汇报里点名这些文件，交用户处置。
    - **subject 沿用上述体例不动，body 必须详写过程**——目标是人类不看会话记录也能了解具体过程、复现当时场景，详略以「会话工作总结」为准（按主题分节、成段叙述、带实测数字，不是三五行摘要）。body 须包含：①**用户指令原话**（本轮涉及的全部关键用户消息：初始指令 + 中途追加/纠偏，按时间顺序原话保留，闲聊/确认类可略）；②**结构化后的完整计划**（要做什么、分几步、判据是什么）；③**实施过程分节叙述**（一、二、三…写清每一步做了什么、关键设计点与取舍理由）；④**计划到实施中的意外**（踩的坑、临时改向、被推翻的假设、外部事件、顺手修的 bug 及各自处置）；⑤**重要实验/测试**（命令/入口、关键参数口径、实测数字与结论）；⑥**当前状态与下一步**。纯文档/一行修补类微小改动 body 可相应精简，但用户指令原话与测试/验证结果两项不可省。

## 项目概览

本仓库是 RoboMME benchmark 的一个副本，现在**只服务于一件事**：

> 从 ManiSkill 仿真本身取 3D 物体的 ground-truth 位移，反投影到 2D `base_camera` 相机平面，
> 得到**稀疏逐物体的 2D flow ground truth**，并集成进生成的 HDF5 数据集。

产出方式已定：**改 `RecordWrapper` 在数据生成时同步写入**（不是事后重放补算），因此规则 3 的
「只增不改」是整条链路的生命线——新数据除 flow 之外必须与之前生成的一致。

**明确的非目标**（不要做，也不要"顺手"做）：

- 不做任何模型训练、不引入训练代码与配置。
- 不做 benchmark 的其它功能开发、不做大规模重构。
- 不动 `challenge_interface/`、`scripts/evaluation.py`、Docker 相关链路。
- flow 之外的既有 bug / 不一致，除非用户明确要求，只记录不修（见"已知坑"）。

## AGENTS.md 已作废

原仓库根目录的 `AGENTS.md` 是「数据生成脚本恢复」三阶段任务的历史账本，该任务已结束，文件已归档到
[doc/archive/AGENTS-dataset-recovery.md](doc/archive/AGENTS-dataset-recovery.md)。

- **它的全部规则一律不再执行**，包括"每次开始工作前先读本文件""必须把进展追加写进执行日志""所有数据必须落在仓库根目录内、禁止仓库外路径"等。本文件（CLAUDE.md）是唯一指令源。
- ⚠ **该账本里混入了另一个项目（MotionJEPA 训练仓库）的记录**（W&B run 核查、SigLIP 开关、`configs/default.yaml`、`scripts/train.py` 等）——**这些文件在本仓库根本不存在**。翻阅归档时不要把这些内容当成本仓库的既往事实引用。

## 环境

```bash
uv sync
```

- Python 3.11（`.python-version` 固定）；`mani-skill` 来自 git fork 固定 rev，非 PyPI。
- 本机双卡 NVIDIA RTX 6000 Ada（46 GB/卡），无集群依赖，全部数据在本地盘 `/data`。
- 渲染依赖 Vulkan；报 renderer/Vulkan 相关错误时见 `readme.md` 的 Troubleshooting 段。

## 数据路径

- **官方参考 h5（仓库外，只读）**：`/data/hongzefu/robomme_data_h5`（约 530 GB）。
  **16 个任务全部齐全**（2026-08-07 用 `scripts/data-generation-v2/fetch_reference_h5.py --tasks all`
  补完，每个任务均通过 100-episode 校验），与参考数据对拍的流程现在可以覆盖全部 16 个任务。
- **生成产物（仓库内）**：`artifacts/generated/<名字>/`，每个任务一份 `record_dataset_<Task>.h5` + 一份 metadata JSON。
- **生成报告**：`scripts/data-generation/reports/generation_report.{json,md}`（每次生成或只读复核会原子替换这两个文件）。

## 常用命令

⚠ 下面 1、2 两条生成命令**当前跑不通**（参考数据路径问题，见"已知坑"第一条），处置方式须先问用户。

```bash
# 1. 单任务单 episode 冒烟生成（改 RecordWrapper 后的必跑项；单 worker 便于自对拍）
env CUDA_VISIBLE_DEVICES=0 uv run --locked scripts/data-generation/generate_dataset.py \
  --output-dir artifacts/generated/<冒烟名> --env ButtonUnmask --episodes 1 --workers 1 --gpus 0

# 2. 全量生成（审批点：须先与用户确认 --output-dir 新名字）
env CUDA_VISIBLE_DEVICES=0 uv run --locked scripts/data-generation/generate_dataset.py \
  --output-dir artifacts/generated/<正式名> --env all --episodes 100 --workers 20 --gpus 0

# 3. 契约校验（结构 / seed / difficulty / joint_action shape 与 dtype）
#    ⚠ --reference-root 必须显式传，默认值指向仓库内并不存在的 data/robomme_data_h5
uv run --locked scripts/data-generation/validate_generated_dataset_contract.py \
  --output-dir artifacts/generated/<名字> --env <任务> --episodes <N> \
  --reference-root /data/hongzefu/robomme_data_h5

# 4. 与官方参考逐元素对拍 joint_action（--reference-root 可指到仓库外参考目录）
uv run --locked scripts/data-generation/compare_joint_actions.py \
  --output-dir artifacts/generated/<名字> --env <任务> --episodes <N> \
  --reference-root /data/hongzefu/robomme_data_h5 --max-abs-diff 1e-8

# 5. 回放已有 h5 做 sanity check（同 seed 重建 env + 重放动作序列）
uv run scripts/dataset_replay.py --h5-data-dir /data/hongzefu/robomme_data_h5

# 6. 测试（见强制规则 5）
uv sync --extra dev                                 # 首次：pytest 在 dev optional 组里
uv run --no-sync python -m pytest tests/lightweight/ -q -m "not slow and not gpu"   # 默认档，实测 4.5 秒
uv run --no-sync python -m pytest tests/dataset/<单个文件>.py                        # 真实仿真，很慢，按需选单文件
```

⚠ `--gpus` 只接受 `0`（脚本内硬编码），传其它值直接报错。

## 项目结构

```text
src/robomme/
  env_record_wrapper/
    RecordWrapper.py            — RobommeRecordWrapper：step() 逐步缓冲、close() 落盘 h5（flow 写入的落点）
    DemonstrationWrapper.py     — obs 增广与 include_* 开关
    episode_config_resolver.py  — BenchmarkEnvBuilder：按 episode 构建 env
    episode_dataset_resolver.py — 从 h5 解析回放所需动作
  robomme_env/
    <16 个任务>.py              — @register_env 注册；各自的 _default_sensor_configs 定义 base_camera
    utils/
      choice_action_mapping.py  — project_world_to_pixel：世界→像素投影唯一入口
      segmentation_utils.py     — segmentation 处理与可视化
scripts/
  data-generation/
    generate_dataset.py         — 生成唯一入口，生成后串联下面三件套
    validate_generated_dataset_contract.py — 契约校验
    compare_joint_actions.py    — 与官方参考逐元素对拍
    write_generation_report.py  — 报告写入（也可只读复核）
  dataset_replay.py             — 回放 h5
doc/
  h5_data_format.md             — h5 schema 权威文档（新增 flow 字段后必须同步更新）
  env_format.md                 — env 输入输出格式与世界坐标系约定（唯一真源）
  archive/                      — 历史归档，只读
tests/
  lightweight/                  — 纯逻辑，秒级
  dataset/                      — 真实仿真渲染，很慢
```

## 关键锚点

- **h5 写入**：`RobommeRecordWrapper.step()` 把每步数据 append 进内存 buffer，`close()` 里在 episode 成功时才逐 timestep 建 group 落盘；各 worker 的原始 h5 由 `generate_dataset.py` 的合并步按 episode 拷进最终文件。
- **投影**：`project_world_to_pixel`（`choice_action_mapping.py`），现用于 `choice_action` 的单点 grounding，像素写作 `[y, x]`，投影失败（越界 / 相机后方）返回 `None`、调用方转成空列表。
- **物体枚举**：`env.unwrapped.segmentation_id_map`（ManiSkill 原生，id ↔ segmentation 图像素值一一对应）。⚠ 它是**全场景**枚举，包含机械臂各 link 与桌面等背景道具，不是"任务物体清单"。
- **相机参数**：`obs['sensor_param']['base_camera']` 下的 `intrinsic_cv` (3,3) 与 `extrinsic_cv` (3,4)，OpenCV 约定；`base_camera` 是固定在世界系的前视相机（h5 里叫 front），256×256。
- **坐标系**：世界系约定以 [doc/env_format.md](doc/env_format.md) 为唯一真源（右手系，+x 前、+y 机器人左、+z 上，桌面 z=0），不要另起炉灶重新定义。

## 已知坑

- **v1 生成入口仍然跑不通，v2 已修好**：`scripts/data-generation/generate_dataset.py`（v1）把官方参考路径硬编码成仓库内 `data/robomme_data_h5` 且没有 CLI 开关，该目录不存在，会在生成第一条 episode 之前就报错。**v2 入口（`scripts/data-generation-v2/generate_dataset.py`）已新增 `--reference-root`**，配合已补齐的 16 任务参考数据可以正常跑 `--env all`。v1 保持冻结不动，需要生成一律走 v2。
- **`save_video=False` 会让整条 h5 写入链路失效**：`RecordWrapper` 里同一个判断同时控制视频拼接与 buffer 落盘，关掉它会得到 0 个 timestep 的空 episode。不要为了提速关它。
- **生成不可逐位复现**：规划器在 screw 连续失败后会退避到带 1 秒墙钟预算的 RRTStar（采样式、依赖当时 CPU 负载），叠加 20 个 worker 抢同一张 GPU 的调度扰动；历史上实测出过 `5.66e-9` 量级数值漂移与部分 episode 的 timestep 集不一致。⚠ 那份历史记录来自**另一台机器上的另一个仓库副本**，不要把它当成本仓库的既定基线。本机的实测基线是：2026-08-07 用 `--workers 1` 背靠背跑的 16 任务 × 1 episode，两次（flow+masked 全开 / 全关）之间 165954 个既有 dataset **逐位一致**、7898 个 `joint_action` 零不一致，且 `rrtstar_attempts` 全程为 0——单 worker 且机器空闲时，兜底根本不会触发。16×100 全量生成本仓库仍未跑过。
- **timestep 之间不是恒定物理步长**：部分任务的 task_list 里存在名为 `NO RECORD` 的段，该段内的物理步既不进 buffer 也不落 h5，因此相邻 timestep 之间可能隔了任意多个未记录的真实步。任何按"帧间差分"理解的量都必须清楚这一点。
- **`joint_action` 的 dtype 文档与校验器不一致**：[doc/h5_data_format.md](doc/h5_data_format.md) 写 `float32 (8,)`，而契约校验器与对拍器都强制要求 `float64 (8,)`。
- **`segmentation` 未入 h5**：运行时可从 obs 取到，但写入 h5 的代码是被注释掉的状态。
- **部分测试文件是独立脚本入口**：`tests/lightweight/` 下的 `test_record_info_is_completed.py`、`test_record_waypoint_pending_flow.py`、`test_waypoint_dense_dedup.py` 走 pytest 会显示 "no tests ran"（收集到 0 个用例），需要 `uv run --no-sync python <文件路径>` 直接执行。别把它们的"0 个用例"当成测试通过。
