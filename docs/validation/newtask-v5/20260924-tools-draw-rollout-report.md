# V5 工具链子任务报告：抽签多 worker、一条命令、生成报告（S4～S6 准备）

- 日期：2026-09-24；worktree `/data/hongzefu/robomme_v5_wt/tools`（分支 `v5wt-tools`，基于 `f5b6a17`），未 commit。
- 范围：只改 `scripts/parity/`、`tests/lightweight/` 新测试、`scripts/README.md` 与 `scripts/parity/README.md`；未碰 `src/robomme/`，`scripts/` 顶层仍恰好五个 `.py`。

## 一、改动清单

| 文件 | 锚点 | 改了什么 | 为什么 | 怎么验的 |
|---|---|---|---|---|
| `scripts/parity/v4_specs.py` | `build_draw_header`、`draw_task`、`merge_task_rows`、`draw_rows`、`_draw_worker_init`、`_parse_gpus`、`cmd_draw`、`draw` 子命令参数 | 把原 `cmd_draw` 的 header 构造与单环境循环原样抽成函数；新增 `--workers N`（默认 1）与 `--gpus`（默认沿用环境）。N>1 时每个环境作为一个任务提交给 spawn 进程池，子进程初始化时从队列按轮转领 GPU 写进 `CUDA_VISIBLE_DEVICES` 并注册环境；结果经 `merge_task_rows` 按 header 任务序拼接，并复核每环境 (episode, attempt, seed) 的推进规则 | 任务 2：抽签多 worker，产物与单 worker 格式与行序完全一致 | 单测（线程池 + 假 reset，2/3/8 worker 与单 worker 逐行相同，合并产物 freeze 直接读）；真机冒烟（见三） |
| `scripts/parity/v4_rollout.py` | `_run_batch` 的 runner 命令、`run` 子命令 `--gpu`、模块 docstring | 原来写死的 `--gpu 0` 改为透传 `--gpu`（默认 `"0"`，与改动前相同）；docstring 补 V5 用法 | 任务 3：检查写死项。本文件没有写死 newtask-v4 路径或 `v4-01`（落点都来自 `--specs`／`--output`／`--label`），唯一写死的是 GPU 号 | 单测 monkeypatch `subprocess.run` 截获 runner 命令 |
| `scripts/parity/train_split_config.py` | `DEFAULT_RELEASE`、`RELEASE_NOTES`、`extract --release`、`--output` 缺省推导 | 新增 `--release {newtask-v4,newtask-v5}`（默认 v4），决定默认落点 `scripts/configs/<release>/sampling_config.json` 与快照 `note`；V4 的 note 逐字保留 | 任务 1：S4 能直接输出到 newtask-v5；V4 命令及 `--verify` 字节不变 | 单测：v5 note 与落点、v4 缺省 note 不变；`test_sampling_config_split`（v4 --verify）照旧通过 |
| `scripts/parity/v5_generation.py`（新） | `report`、`pipeline` 两个子命令；`build_report`、`render_markdown`、`plan_pipeline`、`count_demo_frames`、`parse_pair` 等 | `pipeline`：按 release/run id 推导全部落点，子进程依次跑 draw → freeze → run → report，失败即停，支持 `--resume`／`--dry-run`。`report`：读 drafts/specs/results/h5/rng_trace，打印 `V5_GENERATION=REPORT …` 并写 `generation_report.md` 与 `.json` | 任务 3、4 | 单测（假数据、N/A 路径、真实小 h5、落点与 resume）；V4 产物自测（见三） |
| `tests/lightweight/test_v5_generation_tools.py`（新） | 15 条 | 覆盖以上全部新逻辑 | 任务 6 | 15/15 通过 |
| `scripts/README.md` | 新增「第五节 V5：生成工具链与 V1 对拍」，开头目录加第 5 条 | S4 重导、S6 一条命令（含参数表与等价分步写法）、报告字段口径、S5 V1 调用法 | 任务 5、7 | 命令与 `pipeline --dry-run` 打印逐字对照过 |
| `scripts/parity/README.md` | 顶部引言后加 V5 提示段 | 指向 `../README.md` 第五节 | 任务 7 | — |

## 二、关键设计点

1. **多 worker 与单 worker 产物一致的依据**：原抽签循环里每个环境的 seed 只由 `(task, episode, attempt)` 经 `SEED_RULE` 决定，环境之间没有共享状态，因此按环境切分不改变任何一行；合并按 header 的 `tasks` 顺序拼接，每环境内保持抽签先后，正是单 worker 的行序。header 仍只构造一份（父进程），字段集合不变，freeze 的 `_exact_keys` 不受影响。唯一不同的是墙钟量 `wall_s`（本来单 worker 两次跑也不同）。
2. **`--workers 1` 逐字不变**：走原来的本进程顺序循环（`draw_task` 的语句与打印和原 `cmd_draw` 循环体一致），`--gpus` 不给时不碰环境变量。
3. **子进程反序列化**：`v4_specs` 常以 `-m` 运行成 `__main__`，进程池里提交的函数用 `importlib.import_module("scripts.parity.v4_specs").draw_task` 按包名取，避免子进程找 `__main__` 属性。
4. **子进程崩溃**：`_draw_one` 本身捕获普通异常并记失败类别；只有段错误这类硬崩溃会让 future 抛异常，此时汇总所有未完成环境后整体报错，**不写 drafts**（不产出残缺快照）。
5. **报告容错**：外环交换（`actions.distractor_swap_pairs`、`objects.n_swaps`）与 VideoRepick 搭档（`actions.swap_pairs.<k>`）的字段名集中在 `v5_generation.py` 顶部常量；容器兼容 `{"0":…}` 字典与列表两种形态，一对交换兼容 `[a,b]`、`{"pair":[…]}`、`{"initiator","partner"}` 等键名，身份号兼容整数与 `bin_3`；认不出或缺字段记 `N/A` 并在「提示」写明。`*_choice`（候选下标）不当成方块身份。VideoRepick 在规格里取不到时退回 rng_trace 的运行时 record（V4 就是这种形态）。另外若环境侧日后在运行时逐窗 record 外环交换（前缀 `actions.distractor_swap_windows.` 或 `actions.distractor_swaps.`），报告会一并核对。
6. **报告的规格来源**：优先 specs.jsonl，缺失时退回 drafts 的成功行（episode 编号相同）；specs 缺失时正式局目标数按 index 0/3/6 推算。h5 路径优先用 results.jsonl 记录的绝对路径，找不到就退回 `episodes/<Task>_episode_<n>/hdf5_files/*.h5`。
7. **`pipeline --resume`**：drafts／specs 已存在就跳过对应步骤，实跑目录已有 `results.jsonl` 就跳过实跑，报告每次重出；实跑目录存在但没有 `results.jsonl`（上次中断）时直接拒绝，交人工处置。陈旧产物由下游 freeze／run 的来源核验拦住（源码指纹、配置全文）。
8. **自定细节**（规则 5）：封套 schema 名 `v4-drafts/1`／`v4-specs/1` 与 `RECOVERY_RULE` 文本不改（它们描述文件格式，改了会让 V4 文件读不了，且计划说 freeze「代码只做参数化」）；报告文件名 `generation_report.{md,json}`；报告目录 `artifacts/<release>/<run>/report/`；判定行里取不到的量写 `N/A`；`demo_frames_out_of_band` 只数成功且有 h5 的局。

## 三、测试与实测数字

- **轻量测试**：`timeout 290s … pytest tests/lightweight/ -m 'not gpu and not slow'` → `46 failed, 855 passed, 22 skipped, 74 deselected, 12 errors in 137.92s`；失败集合 58 条与 `wt_baseline_failset.txt` **逐条相同**（基线 840 passed，多出的 15 条正是新测试）。
- **新测试**：`tests/lightweight/test_v5_generation_tools.py` 15/15 通过（约 4 s）；`test_v4_specs.py` 8/8 照旧通过。
- **抽签多 worker 真机冒烟**（本机，V4 快照 + 本 worktree 代码，只用来验工具）：4 个环境（PatternLock、RouteStick、StopCube、MoveCube），每环境 2 条候选、最多 3 次，单 worker（GPU 1）用时 32 s，`--workers 4 --gpus 1,0` 用时 18 s；两份 drafts **header 相同、8 行去掉 wall_s 后逐行相同**（`DRAFT_HEADER_EQUAL True DRAFT_ROWS_EQUAL True`），两份都能 freeze，冻结出的 8 行规格**完全相同**（`SPEC_ROWS_EQUAL True`）。脚本与日志：`artifacts/newtask-v5/tools-selftest/draw_smoke.sh`、`artifacts/logs/tools-draw-smoke.log`。
- **报告脚本在 V4 产物上自测**（V4 产物只读，输出到 `artifacts/newtask-v5/tools-selftest/v4-01-report/`，用时约 1.6 s）：

```text
V5_GENERATION=REPORT tasks=16 draft_ok=160 rollout_ok=47 backfilled=3 selected_shortfall=1 demo_frames_out_of_band=5 outer_swap_mismatch=N/A bin_collision=1 vr_min_participants=3
# Swap 外环窗口数：7 局全部取不到（字段缺失或形状认不出），记 N/A
```

  与 V4 自己的 `summary.json` 对得上（rollout_ok 47、backfilled 3、selected_shortfall 1）；PatternLock 演示帧数 649/683/757、RouteStick 650/600/600，与 V5 计划 2.10/2.11 引用的 V4 实测逐个相同，其中 5 局落在 750～1050 之外；BinCollisionError 1（VideoUnmaskSwap ep3）；VideoRepick 3 局参与方块数 6/5/3（取自 rng_trace；ep3 的 5 与计划 2.15「bin_1 一次没动」一致），最小值 3；V4 规格没有外环字段，所以 outer_swap_mismatch 记 N/A，符合预期。逐环境表、逐局明细见该目录的 `generation_report.md`。
- **V0 静态**：本改动不触及 `src/robomme/`，`config_easy/medium/hard` 与 `NATIVE_SAMPLING` 零改动；`ls -1 scripts/*.py` = 5。

## 四、V5 正式一条命令

```bash
cd <V5 合并后的仓库根>
uv run --no-sync python scripts/parity/train_split_config.py extract --release newtask-v5          # S4，先做
tmux new-session -d -s v5-gen "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.parity.v5_generation pipeline \
  --run-id v5-01 --draw-workers <抽签并行数> --draw-gpus 0,1 --workers <实跑并行数> --rollout-gpu 0 \
  --official-root artifacts/train-parity/local-smoke-01/official-src \
  2>&1 | tee artifacts/logs/v5-gen-v5-01.log; echo \"EXIT_CODE=\$?\" >> artifacts/logs/v5-gen-v5-01.log"
```

等价分步写法与 V1 调用法见 `scripts/README.md` 第五节。V1 比较行：`train_split_parity.py compare --run base=<基线侧目录> --run v5=<V5 侧目录> --pair base/B:v5/B` → `H5_PARITY pair=base.B|v5.B compared=144 sha_equal=… field_mismatch=…`。

## 五、与计划不符之处

1. 计划第二部分「三、runbook」的 V1 写法 `train_split_parity run --subset 16x9` 与 `compare <dir> <dir>` 在代码里**不存在**：144 条子集就是 `run` 的默认 manifest（`scripts/configs/newtask-v3/subset_manifest.json`，144 行），用 `--paths B` 跑；比较用 `compare --run base=… --run v5=… --pair base/B:v5/B`。README 第五节已按实际写法给出，没有改代码。
2. 计划 runbook 的 S6 链路只写到 `v4_rollout run`；本次把报告作为第四步并入 `pipeline`。
3. 实跑侧 runner 只接受一个 GPU 号（`train_split_runner --gpu`，worker 写进 `CUDA_VISIBLE_DEVICES`），所以实跑是「单卡多 worker」；抽签侧才能按 `--draw-gpus` 轮转两张卡。改 runner 做多卡轮转超出本任务范围，没有做。

## 六、待用户决策

无（改变设计意图的问题本任务没有碰到）。

## 七、给合并者的注意事项

- **新 API**：
  - `v4_specs.draw_rows(tasks, samplings, candidates_per_env, max_reset_attempts, workers=1, gpus=None, *, draw_one=None, executor_factory=None) -> list[row]`；`draw_task(task, sampling, candidates_per_env, max_reset_attempts, draw_one=None)`；`merge_task_rows(tasks, rows_by_task)`；`build_draw_header(run_id, sampling_document, tasks)`。
  - CLI：`v4_specs draw … --workers N --gpus 0,1`；`v4_rollout run … --gpu <id>`；`train_split_config.py extract --release newtask-v5 [--verify]`；`v5_generation pipeline|report`（参数见 `--help` 与 README 第五节）。
- **字段名对接**：外环交换与 VideoRepick 搭档的规格路径是按计划 2.5／2.15 的名字写的（`actions.distractor_swap_pairs`、`objects.n_swaps`、`actions.swap_pairs.<k>`）。环境侧实现落定后若名字或形状不同，只改 `v5_generation.py` 顶部的 `N_SWAPS_PATHS`／`OUTER_PAIRS_PATHS`／`OUTER_TRACE_PREFIXES`／`VR_PAIRS_PATHS`／`PAIR_KEYS` 即可；认不出时报告写 `N/A`，不会崩。建议合并后用第一局 V5 draft 跑一次 `report` 确认这三项不是 N/A。
- **`test_sampling_config_split` 的 v4 --verify**：它跑的是缺省 `extract --verify`（即 newtask-v4 快照）。等环境侧 xhard 改动合入后这条会因 V4 快照与源码不再一致而失败——这是 V4 作废的预期后果，届时应改成 `--release newtask-v5`（S4 之后）。本任务没有改它。
- `scripts/README.md` 顶部标题仍是「V4 xhard 档」，第一～四节是 V4 记录；S7 写总报告时如要改标题请一并处理。
- 自测产物（`artifacts/newtask-v5/tools-selftest/`、`artifacts/logs/tools-*.log`）只在本 worktree，合并时不必带走。
