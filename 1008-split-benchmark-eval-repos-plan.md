# 1008 仓库拆分方案：benchmark 仓回到「官方 + 两个文件夹」，评估独立成仓（第二稿，已按 2026-10-08 裁决定稿，待开工令）

> **权威性**：只规划不实施；用户已逐项裁决（§一「已定口径」），开工仍等用户明确说「开工」。
> **代码锚点**：现仓库 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，方案初稿 HEAD `9c78c076`（12.540）。
> **官方锚点**：`RoboMME/robomme_benchmark` HEAD `016ac1c4ef3df2b88488abc19db08f3de83647b5`（2026-10-03）。实测 `src/robomme/`（102 文件）、`challenge_interface/`、三个官方入口、`Dockerfile`、`assets/`、`LICENSE` 与之逐字节零差异；只有 `readme.md`、`.gitignore`（多 13 行）、`doc/Wechat.jpg`、`doc/submission/ponderpounce.md` 四处不同。
> **外部依赖锚点**：四个子模块 gitlink 不动——`mme-vla@ecf086c3`、`SimpleMemVLA@c564c17d`、`PonderPounce@723df357`、`Astra-on-RoboMME@4c3fd6a8`。
> **体例**：新仓库 commit subject 沿用 `<大>.<小>[.<修订>] <中文描述>`；本文件放根目录是用户要求，审核后移入 `docs/plans/`。

# 第一部分（给人看）

## 一、要做什么

用户原话（2026-10-08）：「相比于官方的benchmark只多多出一个scripts和一个source文件夹 然后所有Evaluation的内容单独出一个Repo。然后这个repo来fork所有的repo就不在现有的repo里面实现。另外我还需要就是删除所有的生成ENV的工具只保留这个EVUation的工具然后EVUation只能生出来这个Xhard0和ood」「只保留 official video 就行 expert demo 按这个来 一个是带 text 部分的，一个是不带的只有红框」「你需要保留最原始的这个和最原始的action让我可以恢复成转换成别的其他的内容」「eval 仓最好也要整理得比较清楚最好是一个模型加一个epsode。包装成一个方式就一个函数对外我们需要保留一个在本机器上运行的方式然后对内我们需要能够在函数的基础上包成gl来执行」「全部改为存有损的……用最先进的压缩」「policy改为常驻 然后episode单独分装 否则每次都要load」。

三句话：

1. **现仓库一分为二。** benchmark 仓从官方 HEAD `016ac1c4` 直接分出，相对官方只多 `src/robomme_hard/` 和 `scripts/hard/` 两个文件夹；eval 仓承接全部评估代码、四个模型仓的 fork 子模块、评估测试与评估留档，以 submodule 依赖 benchmark 仓。
2. **生成工具全删，评估只认两个数据集。** `scripts/injection-dev/`、`scripts/parity/`、`scripts/configs/`、46 个生成类测试、94 MB 生成留档不进新仓；`robomme_hard` 的 builder 只认 `hard-verify`（＝xhard0，16 任务 × 12 局 = 192）与 `ood`（16 任务 × 50 局 = 800）。
3. **eval 仓两层接口。** `Policy`（常驻：按模型 + seed 加载一次、服务进程跨局活着）与 `run_episode(policy, dataset, episode, out_dir)`（只跑一局，不加载任何东西）；本机入口与 GL 入口都是「起一个 Policy，然后循环调 run_episode」；每局产物固定为官方版式视频 + AV1 有损原始帧 + 原始动作与逐步记录。

```text
RoboMME/robomme_benchmark @016ac1c4（官方，只读）
        │ fork（git 历史接在官方 HEAD 之后）
        ▼
benchmark 仓 hongzefu/robomme_benchmark_hard
  官方全部文件（零改动）+ src/robomme_hard/ + scripts/hard/evaluation_hard.py（+ tests/robomme_hard/、规则三件）
        │ submodule（gitlink 钉 40 位 sha）
        ▼
eval 仓 hongzefu/robomme_hard_eval
  third_party/{robomme_benchmark, mme-vla, SimpleMemVLA, PonderPounce, Astra-on-RoboMME}
  src/robomme_hard_eval/（Policy 常驻对象 + run_episode 单局函数 + 记录 + 汇总）
  scripts/run_local.py（对外，本机）  scripts/gl/（对内，占位 job）
现仓库 newtaskRelease-taskV9 → tag archive-newtask-v9-20261008，只读归档
```

**已定口径**（2026-10-08 用户「其他的我都确认了」，对应初稿 Q1～Q9 与产物六问的推荐项）：

1. benchmark 仓是 GitHub 对官方的真 fork，名 `hongzefu/robomme_benchmark_hard`；eval 仓新建 `hongzefu/robomme_hard_eval`。
2. 评估入口放 `scripts/hard/evaluation_hard.py`；环境包测试放 benchmark 仓第三个目录 `tests/robomme_hard/`；`AGENTS.md`、`CLAUDE.md`、`greatlakes.md` 两仓各一份。
3. 入口 `ood` 步数上限改 1800（与 10-06 接口冻结一致），`hard-verify` 1300 不变；数据集 id 保持 `hard-verify`，README 写明「xhard0 = hard-verify」。
4. `robomme_hard` 五处裁剪全做（§二表）；六个评估留档目录随 eval 仓；本机副本、`artifacts/`、HF、站点不动。
5. 产物：`rollouts/<模型>/<数据集>/seed<N>/` 分两棵树各一份 `log.json`；终态命名 `success|fail|timeout`，`error` 并入 `fail` 并在 `result.json` 保留原因；`ep<N>` 沿用发布工具口径（`ood` 用 0～49 局号，`hard-verify` 用官方原 episode 号）；专家演示带字版用官方版式文字区；本机入口除 `DummyModel` 外带一个真实模型示例（GroundSG+Oracle）。
6. 原始帧全部改存有损，编码定 **AV1 4:4:4（libaom，crf 24，cpu-used 4）**，依据 §四实测。

## 二、benchmark 仓

相对官方的全部差异：`A src/robomme_hard/**`、`A scripts/hard/**`、`A tests/robomme_hard/**`、`A {AGENTS,CLAUDE,greatlakes}.md`、`M pyproject.toml`（wheel 多一行）、`M uv.lock`、`M readme.md`（多一节 Hard evaluation）、`M .gitignore`（多 13 行 `runs/` 与媒体文件）；不允许 `D`。机检 `BENCH_DELTA=PASS added_dirs=3 added_files=3 modified=4 deleted=0`。

`src/robomme_hard` 搬入时只删生成专用分支，16 个环境类、33 个 utils、五份 `env_metadata/ood/xhard{1..5}/specs.jsonl`（3.4 MB，sha 不变）一个不动：

| 锚点 | 改成 |
|---|---|
| `hard_builder.py::_ALLOWED_DATASETS` | 只剩 `{"hard-verify", "ood"}`，传 `train/test/val` 一律 `ValueError` |
| `HARD_TRAIN_TASKS`、`_resolve_metadata_path` train 分支、`env_metadata/train/*.json` | 删除 |
| `from_v4_specs`、`v4_episodes` | 删除 |
| `hard_specs.py::XHARD0_IN_TEST_HARD`（环境变量 `ROBOMME_HARD_XHARD0_IN_TEST_HARD`） | 删除，`ood` 永远只有 xhard1～5 的 800 局 |
| `hard_specs.py::SPECS_ROOT_ENV`、`_override_cells` | 删除，只读包内规格 |

入口 `scripts/hard/evaluation_hard.py` 与官方 `evaluation.py` 保持只差 3 处单行 + 1 段（`DATASET_MAX_STEPS = {"hard-verify": 1300, "ood": 1800}`）。

## 三、eval 仓：常驻 Policy、单局函数、两个入口

```text
robomme_hard_eval/
├── third_party/robomme_benchmark          ← submodule，钉 benchmark 仓 40 位 sha
├── third_party/{mme-vla, SimpleMemVLA, PonderPounce, Astra-on-RoboMME}   ← 四个 gitlink 原样
├── src/robomme_hard_eval/
│   ├── policy.py       Policy = load_policy(model, policy_seed)   ← 常驻：加载权重／起服务、编译缓存、首推理预热全在这里一次做完，跨局复用；with 语句退出才 stop()
│   ├── episode.py      run_episode(policy, dataset, episode, out_dir) -> EpisodeResult   ← 单局：第一句 policy.reset() → 建环境 → 循环 policy.act(obs) → step；不加载任何东西
│   ├── models/         每模型一个 Policy 实现：load() / new_episode(goal) / act(obs) / close()；framesamp_modul、groundsg、smvla、pp、astra、dummy
│   ├── record.py       原始帧（AV1）+ actions.npz + trace.jsonl 落 raw/；官方版式视频落 videos/
│   └── report.py       results.jsonl → log.json
├── scripts/run_local.py    对外：本机单卡，`with load_policy(...) as p: for ep in ...: run_episode(p, ...)`；可只跑一局；自带 dummy 与 GroundSG+Oracle 示例
├── scripts/gl/             对内：占位 job 内每席位起一个 Policy，循环从共享动态队列领局调 run_episode（不再静态分片）；预算账本、重试、服务挂掉重起 Policy、NFS 发布
├── scripts/render_expert_demos.py   从 V9 h5 离线渲染专家演示两版视频
├── tests/、docs/validation/（六个评估留档目录 + legacy-names.md）、pyproject.toml、规则三件
```

- 为什么分两层：模型加载动辄几十秒到几分钟（服务进程、权重、编译缓存），一局才十几秒，按局加载不可接受；现有席位脚本就是「起一次 server、常驻客户端跑完全部局」，新接口把这件事收进 `Policy` 对象，`run_episode` 只管一局。
- 速度口径（2026-10-08 裁决，用户原话「编译预热都在里面做完 做完了之后一定要做一次reset 就是在runepisode开头做一次reset」）：按 [`docs/plans/0929-eval-reload-cost-plan.md`](docs/plans/0929-eval-reload-cost-plan.md) 与 [`docs/plans/0929-eval-throughput-plan.md`](docs/plans/0929-eval-throughput-plan.md) 的实测，常驻本身只省 1～4%（SimpleMemVLA 每段加载约 275 s、占 3.6%；逐步推理占 68%；每局环境重建加仿真占 32%，seed 是 `gym.make` 构造参数、演示段在线执行，不可免），真正的提速在接口外的调度层。因此定死三条：
  1. **编译与预热全在 `load_policy` 里一次做完**：JAX 类策略把持久编译缓存目录落 `<STORE_ROOT>` 下按 GPU 型号分目录（缓存键含 GPU 型号，A40 与 RTX 6000 Ada 不通用），加载后做一次首推理预热；`OMP_NUM_THREADS=1` 随 Policy 启动口径一起设（不设时预处理 8 ms 变 288 ms）。
  2. **`run_episode` 的第一句必须是 `policy.reset()`**：清缓冲、重设种子，预热留下的状态绝不带进正式局；之后才建环境、跑这一局。对应现 `client.reset()`／`reseed()`，一致性只承诺到「行为一致」层级（RRT* 1 s 墙钟预算本就不逐位复现）。
  3. **循环体消费共享动态队列，不做静态分片**：v7 静态 LPT 分片单轮片间 100～147 min，动态队列每轮省 12～14%，加席位才线性有效；单局异常只杀该局、Policy 活着领下一局，CUDA／JAX 状态坏掉才 `close()` 再 `load()` 重建并记基础设施重试（次数上限写死）；每局产物按身份幂等落盘，中断后从队列断点续跑不重消耗预算；server 型 Policy 必带 `trap cleanup EXIT`（本机刚清掉一个跑了 3 天 19 小时的 `serve_policy.py` 孤儿）。
- 现有 `scripts/eval-official/` 的 55 文件按职责拆进上面四块：四个 `*_client.py` 与三个服务外壳进 `models/`（每个模型的 `Policy.load()` 就是起它的 server 并连上），`env_client.py` 的环境链进 `episode.py`，预算、看门狗、NFS 发布进 `scripts/gl/`；`recorder.py`、`trace_writer.py` 并进 `record.py`；`render_official_video.py` 保留为官方版式渲染器（经 `importlib` 调官方 `RolloutRecorder`，不复制不改写）；`official_hard_runner.py` 等原侧对照工具与 `orig_observer/` 一并带走。
- 「fork 所有 repo 都在这个仓接」：四个模型仓以 submodule 锁 gitlink；改模型代码只在各自 fork 分支，benchmark 仓永远不含模型代码。
- 数据集限制：`run_episode` 的 `dataset` 只接受 `hard-verify`／`ood`，步数配对 1300／1800 写死在函数里，不再由 CLI 传。`policy_seed` 属于 `Policy`（加载时定），不属于局。

## 四、产物标准（每局三样，别的不要）

```text
rollouts/<模型>/<数据集>/seed<N>/          数据集 ∈ {hard-verify, ood}；N ∈ {0, 7, 42}
├── log.json                               16 任务各自 success_rate + total_success_rate（任务成功率的平均）
├── videos/<Task>_ep<N>_<success|fail|timeout>_<task_goal>_<tier>.mp4   官方版式（顶部 Frame/Task Goal/Action/State/Subgoal 文字区 + 演示段 10px 红框，512×496，30 fps）
└── raw/<Task>_ep<N>_<tier>/
    ├── front.mkv、wrist.mkv               AV1 4:4:4 有损，256×256，可重渲染任何版式
    ├── actions.npz                        每步原始动作 float64
    ├── trace.jsonl                        每步观测索引、模型回包、终态
    └── result.json                        本局成败、步数、seed、task_goal、error 原因
expert_demos/<数据集>/
├── <Task>_ep<N>_<task_goal>_<tier>.mp4              无字只红框（官方 evaluation.py 的 VideoRecorder 版式，512×256），放网站
└── <Task>_ep<N>_<task_goal>_<tier>_annotation.mp4   官方版式带文字区，自己看；原始素材就是 h5，不另存
```

**编码实测**（2026-10-08，InsertPeg xhard4 一局前视 254 帧，源 FFV1 23.2 MB，按解码顺序逐帧对 RGB 算 PSNR）：

| 编码 | 体积 | PSNR | 说明 |
|---|---|---|---|
| H.264 libx264 crf18 4:4:4 | 226 KB | 39.1 dB | 基线 |
| HEVC libx265 crf20 4:4:4 | 225 KB | 37.4 dB | 不如 H.264 |
| AV1 libsvtav1 crf24 4:2:0 | 231 KB | 33.9 dB | 4:2:0 在 256×256 彩色方块上色度损失大 |
| **AV1 libaom crf24 4:4:4** | **168 KB** | **44.1 dB** | 定此；每路约 6 s CPU，浏览器可播 |
| AV1 libaom crf18 4:4:4 | 206 KB | 45.6 dB | 备选高质量档 |
| H.266 libvvenc qp26 | 172 KB | 33.1 dB | 只能 4:2:0（4:4:4 被静默降级），浏览器／OpenCV 不能解；不选 |
| AV1 av1_nvenc cq24 4:2:0 | 340 KB | 33.2 dB | 硬编快但差 |

体量：FFV1 每局两路平均 187 MB（160 局实测，最长超时局单路 187 MB）；改 AV1 4:4:4 后每局约 0.35 MB，5 模型 × 3 seed × 992 局 ≈ 14880 局 ≈ 5 GB，可上传可分发。本机 ffmpeg 6.1 的 libaom 已够用；带 VVC 的 ffmpeg master 静态构建已下到 scratchpad 验证，不装进系统。

## 五、验收判定行

| 判定行 | 怎么查 |
|---|---|
| `BENCH_DELTA=PASS added_dirs=3 added_files=3 modified=4 deleted=0` | `git diff --name-status 016ac1c4 HEAD` 逐行按 §二规则分类 |
| `BENCH_UPSTREAM=PASS files=0` | `git diff --quiet 016ac1c4 HEAD -- src/robomme challenge_interface scripts/{dataset_replay,evaluation,run_example}.py Dockerfile doc assets` |
| `BENCH_SPECS_SHA=PASS files=5` | 五份 `specs.jsonl` sha256 对现仓库 `tests/contract/packaged_specs.sha256` |
| `BENCH_DATASETS=PASS rejected=4 hard_verify=192 ood=800` | builder 对 `train/test/val/xhard1` 抛错，两数据集局数乘式成立 |
| `BENCH_ENTRY_DIFF=PASS hunks=4` | `diff scripts/evaluation.py scripts/hard/evaluation_hard.py` |
| `BENCH_SMOKE=PASS resets=2` | `DummyModel`、MoveCube、两数据集各 1 局（2 次 reset） |
| `EVAL_IMPORT=PASS` | eval 仓里 `robomme_hard.__file__` 指向 `third_party/robomme_benchmark/src/` |
| `EVAL_EPISODE=PASS files=7 loads=1` | `run_local.py` 用 dummy 跑 2 局，`Policy.load()` 只被调一次，`raw/` 四文件 + `videos/` + `result.json` + `log.json` 齐全，mkv 为 AV1 4:4:4 |
| `EVAL_RENDER_EQ=PASS psnr>=40` | 从 `raw/` 重渲染官方版式与直出的 `videos/*.mp4` 逐帧 PSNR ≥ 40 dB |
| `EVAL_TESTS=PASS` | 迁来的 91 个评估测试 + 新函数单测，`timeout 280s … pytest -m 'not slow' -q` |
| `EVAL_SMOKE`（待授权） | 真实模型 1 局，需 GPU 与权重，第一次正式评估前跑 |

## 六、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| S0 | 用户说「开工」 | — |
| S1 | 建 benchmark 仓（官方 fork）、搬入裁剪 `robomme_hard`、入口、测试、规则三件 | `BENCH_*` 六行 |
| S2 | 建 eval 仓：子模块、`src/robomme_hard_eval/`（Policy + run_episode + 记录 + 汇总）、`run_local.py` | `EVAL_IMPORT`、`EVAL_EPISODE`、`EVAL_RENDER_EQ` |
| S3 | `scripts/gl/` 外壳、原侧对照、测试与留档迁入 | `EVAL_TESTS` |
| S4 | `render_expert_demos.py` 出 800 局两版演示视频（本机，纯 CPU） | 1600 个 mp4、帧数等于 h5 帧数 |
| S5 | 归档 tag、两仓 push、规则正本 `sync-targets.json` 登记 | `git status -sb` 无 ahead |

## 七、子代理分工与合并（简述）

按「计划执行模式」分五块、串行合并：H1 `robomme_hard` 裁剪、H2 入口与 README、H3 测试搬迁（benchmark 仓）；E1 `Policy`、`run_episode` 与 `record.py`（含 AV1 编码）、E2 `scripts/gl/` 外壳与原侧对照（eval 仓）；建仓、子模块、`pyproject.toml`/`uv.lock`、专家演示渲染、tag 与 push 归主会话。每块合并前由只读 sonnet 审查，合并后主会话跑核心短测再审一次。

# 第二部分（技术细节，供 agent 追踪）

## 〇 红线

- R1 benchmark 仓里官方文件与 `016ac1c4` 逐字节相同；任何改动按 P2 逐个批准，本方案不申请。
- R2 五份 `specs.jsonl` 字节不变。
- R3 四个模型 fork 的 gitlink 不动；benchmark 仓不含模型代码；官方 `RolloutRecorder` 不复制不改写，只经 `importlib` 调用。
- R4 现仓库与归档分支不 `git rm`、不改写历史、不 force push。
- R5 预算：`BENCH_SMOKE` 2 次 reset，`EVAL_EPISODE` 2 次 reset（dummy），`EVAL_SMOKE` 另行授权；专家演示渲染不跑仿真。
- R6 开工令：等用户明确说「开工」。
- R7 `uv.lock`、`pyproject.toml`、`.gitmodules`、gitlink 一律主会话改。
- R8 原始帧编码参数固定 `libaom-av1 -cpu-used 4 -crf 24 -b:v 0 -pix_fmt yuv444p`，写进 `record.py` 常量并由 `EVAL_EPISODE` 用 ffprobe 核 `codec_name=av1 pix_fmt=yuv444p`。

## 一 benchmark 仓逐文件清单

| 路径 | 动作 | 说明 |
|---|---|---|
| 官方全部文件 | 保持 | fork 自带，零改动 |
| `src/robomme_hard/**`（环境类、utils、wrapper、`ood/*/specs.jsonl`） | 搬入，字节不动 | `__init__.py` 里指向 `scripts/parity/upstream_guard.py` 的注释改为指向 git 守卫 |
| `src/robomme_hard/env_record_wrapper/hard_builder.py` | 裁剪 | 删 `HARD_TRAIN_TASKS`、train 分支、`from_v4_specs`、`v4_episodes`；`_ALLOWED_DATASETS = {OOD, HARD_VERIFY}`；「先以 `dataset="test"` 过父类校验再改回」的 shim 保留；`_ood_entries` 的 xhard0 入参固定空列表 |
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | 裁剪 | 删 `XHARD0_IN_TEST_HARD`、`SPECS_ROOT_ENV`、`_override_cells`、`resolve_cell_table` 覆盖分支 |
| `src/robomme_hard/env_metadata/train/*.json` | 不搬 | — |
| `src/robomme_hard/README.md` | 重写 | 包结构、两个数据集、逐文件复制／借用表 |
| `scripts/hard/evaluation_hard.py` + `README.md` | 搬入 / 新写 | `ood` 1800；README 写局数乘式与 diff |
| `tests/robomme_hard/**` | 搬入裁剪 | 来自 `tests/{unit/hard,unit/robomme,unit/wrappers,unit/common,contract,static,sim,_support}`；删断言 train 元数据、开关、规格根、`upstream_guard` 的用例 |
| `pyproject.toml`、`uv.lock`、`.gitignore`、`readme.md` | 改 | wheel 加包；13 行忽略；「Hard evaluation」一节 |
| `AGENTS.md`、`CLAUDE.md`、`greatlakes.md` | 新写 | `sync_rules.py apply` 落标记块；P1 改为「三官方入口 + `hard/`」 |

## 二 eval 仓逐文件清单

| 路径 | 动作 | 来源 |
|---|---|---|
| `.gitmodules`、`third_party/*` 五个 gitlink | 新增 | benchmark 仓 sha + 现 `.gitmodules` 四条 |
| `src/robomme_hard_eval/policy.py` | 新写 | `class Policy`：`load()`（起 server／加载权重、编译缓存、首推理预热，只一次；`OMP_NUM_THREADS=1`）、`reset()`（清缓冲、重设种子，对应现 `client.reset()`／`reseed()`；`run_episode` 第一句必调）、`new_episode(task_goal)`（每局开头给目标）、`act(obs) -> action`、`close()`；`load_policy(model: str, policy_seed: int) -> Policy` 工厂；上下文管理器退出即 `close()` |
| `src/robomme_hard_eval/episode.py` | 新写 | 抽自 `env_client.py::EnvSession` + 图 4a 环境链；签名 `run_episode(policy: Policy, dataset: str, episode: int, out_dir: Path) -> EpisodeResult`；内部固定 `DATASET_MAX_STEPS = {"hard-verify": 1300, "ood": 1800}`，`ood` strict-cap；函数第一句 `policy.reset()`，随后只调 `policy.new_episode()` 与 `policy.act()`，绝不调 `load()` |
| `src/robomme_hard_eval/models/{framesamp_modul,groundsg,smvla,pp,astra,dummy}.py` | 新写 | 每个是一个 `Policy` 子类：`load()` 抽自三个服务外壳（起 server 进程 + 就绪探测），`act()` 抽自四个 `*_client.py` 的 websocket 收发 |
| `src/robomme_hard_eval/record.py` | 新写 | 合并 `recorder.py`、`trace_writer.py`；写 `raw/` 四文件（AV1 参数 R8）与 `result.json`；视频经 `render_official_video.py` 的官方渲染路径直出 `videos/` |
| `src/robomme_hard_eval/report.py` | 新写 | `results.jsonl` → `log.json`（16 任务 + `total_success_rate`） |
| `scripts/run_local.py` | 新写 | 参数 `--model --dataset --seed [--episodes a:b]`；主体 `with load_policy(model, seed) as p: for ep in range: run_episode(p, dataset, ep, out)`；`--model dummy` 与 `--model groundsg-oracle` 可直接跑 |
| `scripts/gl/{run_eval_gl.sh,run_seat.sh,seat_media_lib.sh,budget_ledger.py,publish.py}` | 平移改造 | 每席位起一个 `Policy` 后从共享动态队列领局循环调 `run_episode`（不再静态分片）；单局异常不连坐 Policy，server 挂掉由看门狗 `close()` 再 `load()`、记基础设施重试；每局产物按身份幂等落盘可续跑；预算、NFS 发布保留 |
| `scripts/orig/{official_hard_runner.py,run_official_hard.sh,official_defs.py,pp_official_runner.py,pair_seat.sh,orig_observer/}` | 平移 | 原侧对照，不改语义 |
| `scripts/render_official_video.py`、`official_media_check.py`、`gate2_compare.py`、`model_eval_report.py` | 平移 | 路径字符串改 |
| `scripts/render_expert_demos.py` | 新写 | 读 V9 h5 → 无字红框版（`evaluation.py` 的 VideoRecorder 版式）+ 官方版式带字版 |
| `tests/`（`pipeline/eval`、`evalx`、`challenge`、`recording` + `_support`、`conftest.py`）+ 新增 `tests/test_episode.py` | 平移 + 新写 | `EVAL_EPISODE` 与 `EVAL_RENDER_EQ` 的单测版 |
| `docs/validation/{sg-eval-gl-20261004-01,sg-eval-gl-20261006-02,sg-eval-gl-20261006-03,v7.5eval,v8-two-policy-gl10-20261002-01,v9-two-policy-gl10-20261002-01}`、`legacy-names.md` | 平移 | 留档内 `artifacts/` 路径不改写 |
| `pyproject.toml`、三个子 venv 的 `pyproject.toml`/`uv.lock` | 新写 / 平移 | `robomme = { path = "third_party/robomme_benchmark", editable = true }`；`pebble`、`openpi-client`、`eval-client`、`server` 组 |

## 三 子代理分配表（开工后才派）

| 子任务 | 目标 | 可写集合 | 禁触 | 合并顺序 | 判定行 |
|---|---|---|---|---|---|
| H1（opus，worktree） | `robomme_hard` 裁剪 | `src/robomme_hard/**` | 官方文件、`pyproject.toml` | 1 | `BENCH_DATASETS`、`BENCH_SPECS_SHA` |
| H2（opus，worktree） | 入口与 README | `scripts/hard/**`、`readme.md` | `src/**` | 2 | `BENCH_ENTRY_DIFF` |
| H3（opus，worktree） | 测试搬迁 | `tests/robomme_hard/**` | 其余 | 3 | 核心短测 `TEST_RESOURCE=` |
| E1（opus，worktree） | `Policy`、`run_episode`、六个模型 Policy、`record.py`、`report.py`、`run_local.py`、`test_episode.py` | `src/robomme_hard_eval/**`、`scripts/run_local.py`、`tests/test_episode.py` | `scripts/gl/**`、`third_party/**` | 4 | `EVAL_EPISODE`、`EVAL_RENDER_EQ` |
| E2（opus，worktree） | `scripts/gl/`、`scripts/orig/`、迁入测试 | `scripts/gl/**`、`scripts/orig/**`、`tests/pipeline/**` | `src/**` | 5 | `EVAL_TESTS` |
| 主会话 | 建仓、fork、子模块、`pyproject.toml`/`uv.lock`、`BENCH_DELTA`/`BENCH_UPSTREAM`/`BENCH_SMOKE`/`EVAL_IMPORT`、`render_expert_demos.py`（可派 E3）、tag、push、规则同步 | — | — | 0 与 6 | 其余判定行 |
| 审查（sonnet，只读） | 每块合并前一次 | 无 | — | 每块后 | `PRE_MERGE_REVIEW=PASS|FAIL` |

worktree 环境取法：`UV_PROJECT_ENVIRONMENT=<仓 .venv> PYTHONPATH=<worktree>/src uv run --no-sync …`，先打印 `robomme_hard.__file__` 核实指向 worktree。

## 四 runbook（开工后按实际 sha 填）

```bash
# S1 benchmark 仓
gh repo fork RoboMME/robomme_benchmark --clone=false --fork-name robomme_benchmark_hard   # Q1 定名
git clone https://github.com/hongzefu/robomme_benchmark_hard && git -C robomme_benchmark_hard checkout -b hard-release 016ac1c4ef3df2b88488abc19db08f3de83647b5
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask archive 9c78c076 src/robomme_hard scripts/evaluation_hard.py | tar -x -C robomme_benchmark_hard --exclude='src/robomme_hard/env_metadata/train'
git -C robomme_benchmark_hard diff --quiet 016ac1c4 HEAD -- src/robomme challenge_interface scripts/dataset_replay.py scripts/evaluation.py scripts/run_example.py Dockerfile doc assets && echo BENCH_UPSTREAM=PASS files=0
# S2 eval 仓
git submodule add https://github.com/hongzefu/robomme_benchmark_hard third_party/robomme_benchmark
UV_LINK_MODE=copy uv sync && uv run python -c "import robomme_hard;print(robomme_hard.__file__)"     # EVAL_IMPORT
uv run python scripts/run_local.py --model dummy --dataset ood --seed 0 --episodes 0:1 --out artifacts/smoke   # EVAL_EPISODE
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,pix_fmt -of csv=p=0 artifacts/smoke/rollouts/dummy/ood/seed0/raw/*/front.mkv   # av1,yuv444p
# S5 归档
git -C /data/hongzefu/robomme_benchmark_MotionJEPANewTask tag archive-newtask-v9-20261008 9c78c076 && git push origin archive-newtask-v9-20261008
```

## 五 风险与盲区

| 条目 | 处置 |
|---|---|
| `robomme_hard` 导入即 `register_env(override=True)` 接管官方 16 个 env id | 原侧对照保持独立进程（现状如此） |
| 官方父类 `_ALLOWED_DATASETS` shim 依赖官方实现细节 | `BENCH_DATASETS` 钉住；fork 跟官方时先跑 |
| `env_client.py` 1700 行拆成 Policy + 单局函数 + 外壳，行为漂移 | `EVAL_TESTS` 迁入的 91 个测试 + `gate2_compare.py` 对 10-06 第三阶段结果做一次逐身份回归（新标准产物里取 `result.json`） |
| AV1 libaom 每路 6 s CPU，GL 席位上转码占 CPU | 席位脚本里转码放后台队列（现 `run_eval_gl.sh` 同步循环已是此结构）；占位 job 按 2 CPU 申请 |
| 三个子 venv 与 `openpi-client` 指向子模块路径 | README 第一步 `git submodule update --init --recursive`（`mme-vla` 检出约 7 GB） |
| 盲区：`tests/contract` 里涉及 train 元数据与开关的用例数未逐条数；`EVAL_TESTS` 基线用例数未统计；`render_expert_demos.py` 读 h5 的帧与 `is_video_demo` 标志字段名待在 S4 前核 | 各在对应阶段开工前核 |

## 六 留档与 commit 纪律

- 本文件审核后单独提交；HTML 单页随之提交，PNG 不进 git。
- 两个新仓首个 commit body 写来源 sha `9c78c076`、官方 sha `016ac1c4`、搬入与裁剪清单、判定行原文；`sub/H*`、`sub/E*` 前缀按计划执行模式保留。
- 归档 tag message：「此后 newtaskRelease-taskV9 不再提交，后续工作在 robomme_benchmark_hard 与 robomme_hard_eval」。
