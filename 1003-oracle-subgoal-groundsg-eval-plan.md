> **本方案是四个模型接入本仓库评估链路、并按三档闸门在 Great Lakes 跑完的完整计划。** 2026-10-04 按用户新口径整篇重写，取代此前「两模型、每 job 串行、原入口必须完全一致」的版本（旧版见 `git show 25f4fe6b:1003-oracle-subgoal-groundsg-eval-plan.md`）。本轮只改本计划文件；代码、下载、作业、评估都要等用户确认本计划后才开始。
>
> **锚点**：工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`，分支 `newtaskRelease-taskV9`，规划依据 `cfcc302c`。第三方锁定：MME-VLA 子模块 `ecf086c3be7c2223167d9bb2f6ef1f0a6e24353b`；PonderPounce `723df35762bb641e1d520e4fa9359b98644adc21`；vla-eval PyPI `0.7.0`；Astra-on-RoboMME `4c3fd6a8667e7a219e547fe1a533a4b9726fc6db`；官方环境 `856bc3a189d4172f3f47dbee4424d585f8d78db3`（其 `src/robomme` 与本仓库、与对拍锚点 `1fadc0ec` 逐字节相同）。提交编号沿用 `12.<小版本>`。
>
> **用户原话（2026-10-04，按时间顺序）**：
> 1. 「我需要加入3档的闸门对拍 https://worv-ai.github.io/ponderpounce/ 这个也要移植 第一档 改完重新生成任务 需要和原本一致 第二档用原版代码库接口 测试 vs 用改完的接口 测试 xhard0 一致 第三档 开始进行新的真正的xhard eval」
> 2. 「用户完整确认之后再开始写代码。」
> 3. 「所有的测试都在gl上进行。」
> 4. 「第二档报告不阻塞结论。」
> 5. 「你告诉我接线增加hard0会增加哪些内容同时现在改完之后1300步 1600步都要对应好,hard0都是一千三百步 新的都是一千600步。」
> 6. 「把所有的查表功能都去掉。……都是只在这里留一个接口。」（附官方 `BenchmarkEnvBuilder(..., max_steps=1300)` 写法）
> 7. 「照官方（我推荐）：允许第 1301 步，与原版接口行为相同……确认」
> 8. 「改完之后在本机器上测一个episode然后测出CPUmemory和GPU的显存占用如果有超过占位job的需要重新启动job反正就是在本机先做好测试不要上了集群的J0B之后再报错。」
> 9. 四项「这些都同意」：V9 保留执行满 1600 步即记超时、数值取 builder 的 `max_steps`；PonderPounce 第二、三档都跑；放行下载 `worv-ai/ponderpounce-9b-robomme` 到 NFS；第一档按噪声基线口径。
> 10. 「做好并行可能性的评估尤其是第一、第二、第三档是否都可以并行来做。」
> 11. 「写入计划第一部份整合成一个比较粗略的内容。就像我刚才问你的完整流程一样这样就足够了第二部分你所有的细节都要到位你可以使用SubAgebt来确定细节。」
> 12. 「评估一下保存视频需要多大保存压缩后的视频」「把所有的保存视频都改为压缩视频是否可以就是现在的对拍完全靠Xhard0来实现。」
> 13. 「https://github.com/bingaochen/Astra-on-RoboMME把这个也加在一起测了但是这个因为要调用GPT-6Astra的API你要先测试联通性先把API存下来然后只跑原接口和现接口XHARD0 16*1 个 总共32次」
> 14. 「所有使用Astra的你要严格让用户审批episode的数量 包括本机的测试等」
> 15. 「预检测结束之后再申请。reatlakes占用的J0B按照所有预检测之后的占用的并集合如果有些需要两张卡才能跑起来的。单独给他申请job不要和其他的混起来。你最多占用10张卡你自己来分配。」
> 16. 「批准Astra本机御检两局。如果失败可以增加到6局。如果6局配额用完了还失败就停止。继续做其他任务」
> 17. 「我在授权你用Astra跑新的xhard12345 只跑1局 确保接口通畅」（按「合计 1 局」的保守读法执行）
>
> 沿用的更早决定：「不要下载」已被第 9、13 条对 PonderPounce 权重与 Astra 的放行覆盖，其余资产一律用本机已有副本；「我只关心怎么去改现在的这个 repo，让它和官方的这个 evaluation 是对齐的」仍是接线原则——不改任何第三方模型实现。

# 第一部分（给人看）

## 一、目标

在本仓库接好四个模型的评估，新增 xhard0 独立入口，删掉步数查表，然后按三档闸门在 Great Lakes 上跑完。

| 模型 | 来源 | 第二档（xhard0 原版对改后） | 第三档（V9 正式评估） |
|---|---|---|---|
| GroundSG + Oracle | `third_party/mme-vla` 已有实现 | 16 任务 × 1 档 × 12 局 = 192 局，两侧各一遍 | V9 全量 800 局 |
| GroundSG + QwenVL | 同上 | 192 局，两侧各一遍 | 800 局 |
| PonderPounce | 新引入，官方仓库加 27 GB 权重 | 192 局，两侧各一遍 | 800 局 |
| Astra | 新引入，调用付费的 GPT-6 Astra 接口 | 16 任务 × 1 档 × 1 局 = 16 局，两侧各一遍，共 32 局 | 不做正式评估，只用 1 局确认 V9 接口通 |

V9 的 800 局 = `3任务×2档×17 + 3任务×1档×16 + 2任务×5档×10 + 2任务×2档×13 + 2任务×2档×12 + 7任务×2档×25 + 2任务×1档×50`（任务与档的对应见 `hard_specs.py::_v9_cells`）。

## 二、已定口径

1. **三档闸门**：第一档生成对拍是硬闸门，不过不进后面；第二档只出报告、不阻塞；第三档是正式评估。
2. **全部实跑在 GL**；本机只做改码后的纯 CPU 短测和上集群前的预检。
3. **步数上限只有一个入口**：创建 `BenchmarkEnvBuilder` 时传 `max_steps`，xhard0 传 1300，V9 传 1600；按档查表全部删除。
4. **xhard0 的结束方式照各模型的官方循环**；V9 保留「执行满 1600 步即记超时」。
5. **落盘的画面只有压缩视频**；第二档对比靠每步的状态、动作、文本和画面哈希，不保存原始画面。
6. **Astra 的局数逐项审批**：已批 GL 上 32 局、本机预检 2 局（失败可加到 6 局，用完仍失败就停掉 Astra）、V9 接口连通 1 局；其余一律不跑。
7. **占位 job 在预检之后申请**，单卡席位的规格取各模型实测峰值的并集；需要两张卡的模型单独申请、不与别的模型混用；总共最多 10 张卡。

## 三、流程

**第 0 步：接线（只改本仓库，不动 `src/robomme/`，不改第三方源码）**

- 新增数据集 `test-hard0`，只含 xhard0 的 192 局；默认的 `test-hard` 仍是 V9 的 800 局。
- 删除步数查表，评估链路的步数从启动命令一路传到 builder。
- GroundSG 两组：加一个适配器，在本仓库的环境上运行官方单局循环和官方预测器。
- PonderPounce：加一个按它的协议收发的客户端；它的模型服务原样使用。
- Astra：加一个驱动，把它的原循环接到本仓库的 builder 上。
- 每个模型另加一个「原侧」驱动：用模型原版代码加官方环境，只跑 hard 的那些局。
- 录像逐局转成压缩视频后才同步；清单、报告、对比工具按新的数据集和模型扩展。

**第 1 步：本机预检**

- 每个模型的每条路线在本机跑通 1 局，测 CPU 内存峰值、显存峰值、单局耗时。
- 任何一条路线报错，修好重跑通过后才上集群。
- 内存超出席位规格就按实测值申请；显存超过 A40 的 48 GB 就停下交用户。

**第 2 步：申请占位 job**

- 按预检结果定规格和数量，最多 10 张卡；Astra 按官方要求用单独的两卡 job。

**第 3 步：第一档，生成对拍（硬闸门）**

- 用改完的代码重新生成 V9 每格 3 局（43 格 × 3 = 129 局）和 xhard0 每任务 3 局（16 × 3 = 48 局），与噪声基线比。
- 占 1 个席位约 45 分钟；这期间其余席位只做每条路线 1 局的 smoke。
- 不一致就停，不放量。

**第 4 步：第二档和第三档同时放量**

- 第二档：每个模型在 xhard0 上跑原侧和新侧，同一身份的两侧放在同一席、同一张卡上先后跑；差异写进报告，不拦第三档。
- 第三档：GroundSG 两组和 PonderPounce 各跑 V9 的 800 局，按身份清单切到多个席位。
- Astra 只跑第二档的 32 局，外加 V9 的 1 局连通确认。

**第 5 步：交付**

- 每个模型的成绩表（V9、新入口 xhard0、原版入口 xhard0）、第二档差异表、全部压缩视频、留档。
- 产物搬回 `/data`，NFS 不留大文件，按清单释放自己的 job。

## 四、并行安排

| 组合 | 结论 |
|---|---|
| 第一档与第二、三档 | 不同时放量。第一档只要约 45 分钟，同时放量最多省这点时间，却可能让整批评估作废；这段时间只跑 smoke。 |
| 第二档与第三档 | 同时跑，各用各的席位。 |
| 模型之间、同一模型的分片之间 | 同时跑。 |
| 同一身份的原侧与新侧 | 不并行，同席同卡先后跑。 |
| 写代码、拷资产、建环境 | 同时进行。 |

## 五、怎么算完成

| 项目 | 判据 |
|---|---|
| 接线 | 两个数据集不串、默认 V9 不变；步数只来自启动命令；本机短测通过 |
| 预检 | 每条路线跑通 1 局，有内存、显存、耗时数字 |
| 第一档 | 两个集合都 `GEN_REGRESS=PASS` |
| 第二档 | 两侧身份齐全，差异表生成；判定为 `INFO` |
| 第三档 | 每个模型 800 局都有唯一终态，无缺失、无重复；视频齐全可解码 |
| 预算与收尾 | 局数不超过第二部分的预算表；job 与临时文件按清单清理 |

## 六、子代理分工与合并（简述）

代码按文件切成七块交给写入型子代理，各自在独立 worktree 里改：数据集与删查表、评估客户端与清单、GroundSG 适配、PonderPounce 接入、Astra 接入、启动脚本与转码、对比与报告。先合前两块，中间三块并行，最后合启动脚本和报告。每次合并前由主会话复跑该块测试并派一个只读审查，合并后跑日常门禁再推送。子模块、新环境的依赖声明、契约总表、两份 README、本机预检和全部集群运行由主会话自己做。

## 七、还需要用户处理的事

1. **PaliGemma 分词器的访问许可**：PonderPounce 启动时要读 `google/paligemma-3b-pt-224` 的分词器，该仓库需要在 HF 上手动申请。没有许可时 PonderPounce 整条线起不来。
2. **密钥已出现在对话里**：跑完后可在 OpenAI 后台作废重发。

# 第二部分（技术细节，供 agent 追踪）

## 〇、红线

- R1 不改 `src/robomme/**`（P2），不改 `scripts/dataset_replay.py`、`evaluation.py`、`run_example.py`（P1），`scripts/` 顶层不新增文件。
- R2 不改任何第三方源码与既有 gitlink；新增第三方只以「子模块 + 锁定 gitlink」引入。`third_party/mme-vla/third_party/robomme_benchmark` 保持空目录。
- R3 `hard_specs.EXEC_CAP`、已封存规格、`packaged_specs.sha256`、`XHARD0_IN_TEST_HARD` 开关、`xhard0_prefix()` 一律不动——它们属于生成侧，第一档对拍靠它们保持字节不变（xhard0 生成遍仍以 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1` 运行）。
- R4 Astra 的每一局都在已批额度内：本机 ≤6、GL 第二档 32、V9 连通 1。额度外不发起任何会调用 GPT 的运行；Astra 的基础设施重试额度为 0。
- R5 密钥只在 `~/.config/astra/openai.key`（本机，600）与 GL 登录节点同路径文件里，运行时以环境变量传入；不进仓库、日志、留档、命令行参数。
- R6 第一档 FAIL 不改参照、不改判据；第二档有差异不重跑挑结果；正常 fail／timeout 不重试。
- R7 占位 job 合计 ≤10 张卡；只 `scancel` 本轮清单里的 JobID；tmux 只按精确名清理。
- R8 现有主环境 `.venv` 与 `uv.lock` 不动；新依赖全部进独立环境。

## 一、逐文件改动清单

### 1.1 数据集 `test-hard0` 与删除步数查表（S1）

| 文件::锚点 | 现状 | 改成 |
|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_specs.py::TIER_MAX_STEPS` 及其上方注释 | `{"xhard0":1300,"xhard1":1600,…}` | 删除 |
| 同文件模块级 `assert all(TIER_MAX_STEPS[tier]==EXEC_CAP …)` | 导入期断言 | 随表删除（不删则 import 即失败） |
| 同文件 `EXEC_CAP`、`XHARD0_IN_TEST_HARD`、`xhard0_prefix`、`XHARD0_EPISODES`、`XHARD0_PER_TASK` | 生成侧常量与开关 | 不动（R3） |
| `env_record_wrapper/__init__.py` | 再导出 `TIER_MAX_STEPS`、`TEST_HARD` | 去掉前者，新增导出 `TEST_HARD0` |
| `hard_builder.py::_ALLOWED_DATASETS` | `{"train","test","val",TEST_HARD}` | 加 `TEST_HARD0 = "test-hard0"` |
| `hard_builder.py::BenchmarkEnvBuilder.__init__` | 只有 `TEST_HARD` 分支 | 父类参数：`dataset in {TEST_HARD, TEST_HARD0}` → `"test"`；`override_metadata_path` 的拒绝扩到 `TEST_HARD0`；新分支 `self._episode_map = dict(enumerate(_xhard0_entries(env_id, self.metadata_index)))`、`self.metadata_index = {}`，不读规格根；`TEST_HARD0` 下传入 `specs_root` 抛 `ValueError`；保留 `env_id in ALL_TASKS` 校验 |
| `hard_builder.py::_xhard0_entries`、`resolve_identity`、`_hard_env_kwargs`、`make_env_for_episode` | 对 xhard0 条目已可用 | 不改逻辑，只更新 docstring |
| `hard_builder.py::_test_hard_entries(env_id, xhard0, root)` | 签名被植入插件 M10 依赖 | 签名不动 |
| `scripts/evaluation_hard.py` | `dataset="test-hard", max_steps=1600` | **不改**（`tests/static/test_entry_scripts.py` 钉死它与官方入口只差三处）；xhard0 的用法写进 README：把这两个实参改成 `"test-hard0"`、`1300` |
| `scripts/parity/hard_regression.py::cmd_reset_replay` | builder 无步数，逐局传 `TIER_MAX_STEPS[tier]` | builder 传 `max_steps=1600`，逐局不传 |
| 同文件合作者入口 | builder 1300、逐局查表、docstring 与事实不符 | builder 传 1600，逐局不传，改 docstring |
| 同文件 `_env_digest_one` | 逐局 `TIER_MAX_STEPS[tier]`，builder 已是 1300 | 删逐局参数 |
| 同文件 `_step_headroom_v8` | `x0cap = hs.TIER_MAX_STEPS["xhard0"]` | 模块常量 `XHARD0_STEP_CAP = 1300` |
| `scripts/injection-dev/site/subgoal_lengths.py::tier_caps` | 读 `TIER_MAX_STEPS["xhard0"]` | 本地常量 1300 |
| `tests/sim/test_reset_matrix.py::test_reset_cell` | `max_steps=hard_specs.TIER_MAX_STEPS[tier]` | `1300 if tier == XHARD0 else 1600` |
| `tests/contract/test_constants.py::test_tier_max_steps_new_tiers_1600_xhard0_unpinned`、`NEW_TIER_MAX_STEPS` | 断言查表 | 删除；`EXEC_CAP` 断言保留 |
| `tests/contract/test_builder_800.py::test_rejections` | 允许集合不含 `test-hard0` | 补接受与拒绝用例 |
| 新 `tests/contract/test_builder_hard0.py` | — | 16 任务逐局 `gym.make` 参数、`resolve_identity` 字段、局数 192、官方 hard 子集被破坏时报错、`specs_root` 被拒、规格读取函数打桩为「调用即失败」 |
| `tests/pipeline/site/test_site_catalog.py` | 期望值读表 | 常量 1300 |
| `tests/contract/mutants.json::M08`、`tests/mutation/plugins/mut_inproc.py`（M08 分支与预校验里的 `"xhard1" in hs.TIER_MAX_STEPS`） | 植入查表 | 删除 M08 及其预校验 |
| `tests/contract/contracts.delta.json` | `C03-CONSTANTS`、`C03-TIER-MAX-STEPS-XHARD0`、`C18-EVAL-HARD-MAX-STEPS` 引用查表 | 改 symbol／oracle 文字，删已失效条目，新增 `test-hard0` 契约条目 |

### 1.2 评估客户端、清单、报告（S2）

**`scripts/eval-official/env_client.py`**

| 锚点 | 改成 |
|---|---|
| `MAX_STEPS`、`tier_max_steps()`、`SeatRunner.tier_max` | 删除 |
| `build_parser` 的 `--max-steps` | 无默认值、必填 |
| 新参数 `--dataset {test-hard,test-hard0}`（必填）、`--strict-cap`（开关）、`--mme-variant {ground-sg-oracle,ground-sg-qwenvl}`、`--qwenvl-groundsg-adapter`、`--trace-root` | 见下 |
| `--policy` 的 `choices` | `["mme","smvla","mmesg","pp"]`；模块仍按 `load_sibling(f"{policy}_client")` 加载 |
| `EnvSession.__init__`／`EnvSession.builder` | 新增 `dataset` 形参，替换写死的 `"test-hard"` |
| `EnvSession.build` | `make_env_for_episode(self.builder_episode)`，不再逐局传步数 |
| `SeatRunner.builder_for` | 缓存键 `(task, dataset)`；`BenchmarkEnvBuilder(env_id=task, dataset=args.dataset, action_space="joint_angle", max_steps=args.max_steps)` |
| `validate_v8_identity`、`check_identity` | 去掉 `tier_max` 形参与 `effective_max_steps` 校验；身份模式由 `--dataset` 决定：`test-hard` 沿用现有 V8 严格校验（`spec_sha256` 为 64 位串）；`test-hard0` 要求 `tier=="xhard0"`、`candidate is None`、`spec_sha256 is None`、`source_episode` 为整数且与 builder 解析结果相等 |
| `V8_IDENTITY_KEYS` | 去掉 `effective_max_steps`，与 `eval_manifest.SHARD_ROW_KEYS` 同步 |
| `SeatRunner.run_one` | `eff = args.max_steps`；`EnvSession(max_steps=eff, step_cap=eff if args.strict_cap else None)`；`conn_info` 增加 `dataset`、`mme_variant`、`qwenvl_groundSG_adapter_path`、`trace_dir`、`policy_context`（仅进程内对象，不进 JSON） |
| `SeatRunner.base_record` 与结果行 | 保留键 `max_steps`、`effective_max_steps`（下游站点在读），值都取 `args.max_steps`；新增 `dataset`、`policy_variant`、`strict_cap` |
| 账本（`--ledger`、`--reset-budget`、`--infra-retry-budget`） | 与身份模式、`--strict-cap` 解耦，两个数据集都启用 |
| `StepCapReached`／`cap_hit` | 机制不变，只在 `--strict-cap` 时生效 |

启动约定：`test-hard` → `--max-steps 1600 --strict-cap`；`test-hard0` → `--max-steps 1300`，不带 `--strict-cap`。

**`scripts/eval-official/eval_manifest.py`**

- 新增 `--mode {v9-new,v9-full,hard0}`，默认 `v9-new`（现有行为不变）。
- `v9-full`：`--identities` + `--delivery`，不要求 `--exclude-evaluated`，产出 800 行；判定行 `EVAL_SHARDS=PASS mode=v9-full total=800 cells=43 missing=0 extra=0 duplicate=0 xhard0=0`。
- `hard0`：直接由 `BenchmarkEnvBuilder(task, dataset="test-hard0")` 枚举，不读交付清单；`--per-task N`（默认 12）取每任务前 N 局；判定行 `EVAL_SHARDS=PASS mode=hard0 total=<16×N> xhard0=<16×N>`。行键与 `SHARD_ROW_KEYS` 相同，`spec_sha256=None`、`candidate=None`、`key=<task>_xhard0_<seed>`。
- `join_delivery` 不再写 `effective_max_steps`；`check_exec` 删去对应项，`xhard0==0` 的要求只在 V9 两种模式下保留。
- `--pair-shards`：`hard0` 模式下同一身份的原侧与新侧分到同一分片，文件 `shard-NN.json` 两侧共用。

**`scripts/eval-official/eval_report.py`**

- 新增 `--dataset`；`test-hard0` 时身份必备字段不含 `spec_sha256`，不做 `exec_over_cap` 判定（官方循环允许第 1301 步）。
- `--policies` 接受任意 `<policy>[:<variant>]` 列表；`--expect-total` 由调用方给 800 或 192。
- 判定行前缀参数化：`EVAL_COVERAGE=PASS dataset=… policy=… expected=… missing=0 extra=0 duplicate=0 conflicting_terminal=0 error_final=0`、`EVAL_VIDEOS=PASS … decode_fail=0`。

**测试**：`tests/pipeline/eval/` 下 `test_identity_contract.py`、`test_eval_manifest.py`、`test_eval_report.py`、`test_env_session.py`、`test_seat_runner_e2e.py`、`eval_fakes.py`（`tier_cap` 改常量、`real_builder` 加 `dataset`）同步；期望值一律手写 1300／1600，不读被测代码；同目录 `contracts.delta.json`、`mutants.json` 同步。

### 1.3 GroundSG 两组（S3）

**官方行为（已核实，`third_party/mme-vla/examples/robomme/`）**

- `eval.py::EpisodeEvaluator.eval_each_episode(env_runner, subgoal_predictor, video_save_dir)`：每局新建 `MMEVLAWebsocketClientPolicy(host, port)`；先 `env_runner.step(action)`、`count += 1`，再判 `count > max_steps` 记 `timeout`——`max_steps=1300` 时真实执行第 1301 步，且该步终态被覆盖为超时。
- `env_runner.py::EnvRunner.__init__(env_id, video_save_dir, max_steps=1300)`：官方 builder、`dataset="test"`、`action_space="joint_angle"`；Oracle 文本取自 `self.info["grounded_subgoal_online"]`，`info` 每步更新。
- `subgoal_predictor.py::build_subgoal_predictor` 优先级 gemini > qwenvl > memer > oracle，多开时静默取高优先级；`QwenVLSubgoalPredictor` 构造即加载模型，临时目录 `<save_dir>/<env_name>/ep<episode_id>`，`end_episode` 时 `rmtree`，日志 `ep<id>_QwenVL_log.jsonl` 在其父层保留。
- `subgoal_prediction/qwenvl/api.py::Qwen3VLModel`：`PtEngine('Qwen/Qwen3-VL-4B-Instruct', adapters=[adapter_path], attn_impl='flash_attention_2')`，`RequestConfig(max_tokens=128, temperature=0)`，没有 seed。
- 官方命令（`scripts/eval.sh`）：server `--seed=7 --port=$PORT policy:checkpoint --policy.dir=…/symbolic-grounded-subgoal/79999 --policy.config=mme_vla_suite`；配置由 checkpoint 父目录的 `history_config.txt`（内容 `symbolic-grounded-subgoal.yaml`）选定；客户端 `--args.use-oracle` 或 `--args.use-qwenvl`，加 `--args.subgoal-type=grounded_subgoal`。

**新文件**

| 文件 | 内容 |
|---|---|
| `scripts/eval-official/official_defs.py` | `extract_defs(path, names, extra)`：用 `ast` 从官方源文件取顶层函数、类、单目标赋值的原文并执行，返回命名空间并记 `__source_sha256__`（旧 `policy_replay.py` 已在 `27d209d5` 删除，按 `git show 27d209d5^:scripts/eval-official/policy_replay.py` 的同名函数重写）。另负责官方模块头部不会被摘走的三项环境设置：`IMAGE_MAX_TOKEN_NUM=256`、`VIDEO_MAX_TOKEN_NUM=64`、`FPS_MAX_FRAMES=10` |
| `scripts/eval-official/mmesg_client.py` | 新侧。`run_episode(session, identity, conn_info, recorder) -> dict`。从官方 `eval.py` 取 `EpisodeEvaluator`、`Args`，从 `subgoal_predictor.py` 只取所选变体需要的类（Oracle 变体不加载 Qwen；QwenVL 变体取 `QwenVLSubgoalPredictor`、`Qwen3VLModel`，不取 Gemini／MemER），构造前断言 `use_oracle` 与 `use_qwenvl` 恰有一个为真。runner 适配对象提供 `env_id`、`episode_id`、`difficulty`、`info`、`get_init_obs()`、`step()`、`simple_subgoal_oracle`、`grounded_subgoal_oracle`，内部委托 `session.reset()`／`session.step()`，每步同步 `info`。预测器与 evaluator 由 `SeatRunner` 以 `policy_context` 持有、整席只建一次。Qwen 临时目录 `<trace_dir>/qwen-tmp/<dataset>/<key>.a<attempt>/`，与录像目录分开；`unknown` 或异常早退时由适配器清理本次登记的目录。官方 `unknown` 记为 `status="error"`、`error="success_flag=unknown"`，不中止整席。`StepCapReached` 在适配入口收住后原样交回 `run_one` 记 `timeout` |
| `scripts/eval-official/official_hard_runner.py` | 原侧。独立进程，`sys.path` 只加官方 `examples/robomme` 与本仓库 `src`；启动时断言 `robomme.__file__` 在仓库 `src/robomme/` 下、`"robomme_hard" not in sys.modules`。读 `hard0` 分片，对每个 `(task, source_episode)` 调官方 `EnvRunner(task, video_dir, max_steps=args.max_steps).make_env(source_episode)` 与 `EpisodeEvaluator.eval_each_episode`；在 MME 层以委托方式包住 `EnvRunner.get_init_obs`／`step` 与客户端 `infer` 记录轨迹，不碰 `src/robomme` 的任何方法 |

**server**：两个变体共用 `symbolic-grounded-subgoal/79999`，`--seed=7`；`run_seat.sh` 的 `MME_YAML_EXPECT` 参数化（见 1.6）。QwenVL 变体与 VLA 同卡时 `XLA_PYTHON_CLIENT_MEM_FRACTION` 由预检定值（现为 0.75，需给 Qwen 4B 让出约 10 GB）。

**Qwen 运行约束**：`USE_HF=1`（ms-swift 默认走 ModelScope，本机该缓存残缺）、`HF_HUB_OFFLINE=1`、`TRANSFORMERS_OFFLINE=1`、`HF_HOME=<NFS hf-cache>`；`attn_impl='flash_attention_2'` 不改，客户端环境编译安装 `flash-attn==2.8.3`，编译失败报告用户，不改成 `sdpa`。

### 1.4 PonderPounce（S4）

**官方行为（已核实）**

- 模型以 vla-eval 的模型服务形式运行：`python -m ponderpounce.eval.robomme_server --args.checkpoint_path <目录> --port <端口>`；`GET /health` 返回 200 即权重已加载。
- 协议（`vla_eval.protocol`、`vla_eval.connection.Connection`，0.7.0 与 HEAD 一致）：msgpack 二进制帧；`HELLO` 握手 → 每局 `EPISODE_START`（无应答）→ 循环 `OBSERVATION`／`ACTION` → `EPISODE_END`。图像默认 PNG 无损。
- 驱动顺序（`vla_eval.runners.sync_runner.SyncEpisodeRunner.run_episode`）：`reset` → 首条观测（带 `video_history`、`task_description`）→ `for step in range(max_steps)`：发观测、收动作、`step`、已结束则 `break`（最后一帧不再发送）→ `EPISODE_END`。上限是恰好 `max_steps` 个动作。
- 观测键（`benchmark.py::RoboMMEBenchmark.make_obs`）：`images.agentview`、`images.wrist`、`states`（7 关节 + 1 夹爪，float32）、`task_description`；首条另带 `video_history = front_rgb_list[:-1]`。返回 `{"actions": float32 (1, D)}`，环境取前 8 维。
- 噪声种子 `crc32(f"{seed}:{sid}:{n}")`：`sid` 取 `EPISODE_START` 里的 `recording.sid`，缺省是每次启动随机的 uuid；`n` 是该 `sid` 在服务进程内的累计局数。官方默认下每次运行噪声都不同。
- 官方评估用 Docker 加 CPU 软件渲染；vla-eval 支持不走 Docker 的进程内运行，`RoboMMEBenchmark.configure_render("gpu")` 不改任何环境变量。
- 依赖：Python 3.11，`torch 2.14.0`（CUDA 13 构建）、`transformers 5.13.1`；可选内核 `flash-linear-attention`、`causal-conv1d`（后者只有源码包，需编译），不装则回退到慢数倍的纯 PyTorch 实现。启动时读 `Qwen/Qwen3.5-9B` 的配置与分词器、`google/paligemma-3b-pt-224` 的分词器，均未钉 revision，代码没有离线开关。

**本仓库的处理**

| 项目 | 做法 |
|---|---|
| 源码 | 子模块 `third_party/PonderPounce` @ `723df357…`，服务环境在该目录 `uv sync --frozen`（其 `uv.lock` 即可复现面） |
| 新 `scripts/eval-official/pp_client.py` | 新侧。`run_episode(session, identity, conn_info, recorder)`；用 `vla_eval.connection.Connection(url, timeout=300.0)`，顺序与 `SyncEpisodeRunner` 一致；观测由 `session` 的原始观测按 `make_obs` 同样规则打包；动作取 `actions[0][:8]`。`EPISODE_START` 带 `{"task": {"name","env_id","episode_idx"}, "recording": {"sid": <固定>, "eid": <固定>, "eval_id": "", "db_path": ""}}` |
| 新 `scripts/eval-official/pp_official_runner.py` | 原侧。独立进程，只导入官方 `robomme`（同 1.3 的断言）；`RoboMMEBenchmark.configure_render("gpu")` → `RoboMMEBenchmark(tasks=[task], action_space="joint_angle", max_steps=1300)` → 对分片里每个 `source_episode` 调 `SyncEpisodeRunner().run_episode(bench, {**t, "episode_idx": ep}, conn, max_steps=1300, recorder=<固定 sid 的记录器>)`；外围自己处理 `TimeoutError`、`ConnectionClosed`、`RuntimeError` 并 `reconnect` |
| 固定 `sid` | xhard0：`<task>|<source_episode>|<seed>`；V9：`<task>|<tier>|<seed>`。两侧各起自己的服务进程，同一 `sid` 在一个进程内只用一次，保证 `n=0`；基础设施重试前重启服务 |
| 步数 | xhard0 两侧都是恰好 1300 个动作（它的官方行为）；V9 `--max-steps 1600 --strict-cap` |
| 渲染 | 两侧都用 GPU 渲染，与本仓库其他模型一致；与论文的 CPU 渲染设置不同，报告里写明成绩不能直接对照论文数字 |
| 加速内核 | 预检时装与不装各测 1 局耗时（不装的那一局计入预检局数）；采用哪种由耗时决定，两侧与全部席位一致，并记入留档 |
| 离线 | 权重用本地目录；`HF_HOME` 指向 NFS 缓存，预先放入两套分词器文件后设 `HF_HUB_OFFLINE=1` |
| 驱动兼容 | 本机驱动 570.211、GL 上次为 595.71，CUDA 13 构建能否加载由预检第一步 `torch.cuda.is_available()` 判定；不行则报告用户，不擅自换 torch 构建 |

### 1.5 Astra（S5）

**官方行为（已核实，`examples/champ/`）**

- `run.sh <cases.json> <新目录>`：要求 `VLA_PYTHON`、`SIM_PYTHON`、`VLA_CHECKPOINT`、`MONITOR_BASE`、`MONITOR_ADAPTER`、`OPENAI_API_KEY`；`VLA_GPU` 与 `MONITOR_GPU` 相同即 `exit 2`；`PYTHONPATH` 被覆盖为指向它自己子模块的 `src`；VLA 以 `--seed=42` 启动且拿不到密钥；输出目录已存在即拒绝。
- `prepare_cases.py --dataset test --episodes 3` 产出 16 任务 × 第 3 局的清单；`validate_cases` 只接受 `test`／`val`、局号 0～49。
- `runner.py::episode(args, task, ep, builder, monitor, planner, client)` 是模块级函数，builder 由参数传入；只用到 `builder.make_env_for_episode`、`builder.resolve_episode`、环境的 `reset`／`step`／`close`、四个 `*_list` 观测键与 `info` 的 `task_goal`、`status`、`error_message`。循环 `while t < max_steps`，恰好 1300 步。
- 每次规划请求：`gpt-6-astra`、`reasoning.effort=medium`、`max_output_tokens=2048`、`store=False`、高细节图像；两次请求至少间隔 20 秒；只对 429 重试；出现规划服务错误会停掉整个分片。每局规划次数上限 24。
- 监视器：`PtEngine(base, adapters=[adapter], torch_dtype=bfloat16, attn_impl='flash_attention_2')`，`temperature=0`。
- 每局产物：`identity.json`、`decisions.jsonl`、`actions.npy`、`result.json`、`rollout.mp4`（imageio 压缩视频）、`monitor_inputs/`、`planner_calls/`。
- 它的 `src/`、`scripts/`、`packages/` 与本仓库 MME 子模块 `ecf086c3` 逐文件相同，动作模型就是 GroundSG 用的 `symbolic-grounded-subgoal/79999`。

**本仓库的处理**

| 项目 | 做法 |
|---|---|
| 源码 | 子模块 `third_party/Astra-on-RoboMME` @ `4c3fd6a8…`；它嵌套的 `third_party/robomme_benchmark`（`856bc3a`）只在这个子模块内初始化，供原侧使用 |
| 原侧 | 原样运行它的 `run.sh`：`prepare_cases.py --dataset test --episodes 3` → `VLA_GPU=0 MONITOR_GPU=1 PORT=<端口> bash examples/champ/run.sh <cases> <新目录>` |
| 新 `scripts/eval-official/astra_hard_runner.py` | 新侧。`sys.path` 加 Astra 的 `examples/champ` 与本仓库 `src`；`import robomme_hard.robomme_env`；`builder = BenchmarkEnvBuilder(task, dataset=<test-hard0 或 test-hard>, action_space="joint_angle", gui_render=False, max_steps=<1300 或 1600>)`；构造 Astra 的 `Monitor`、`Planner`、`ResponsesClient` 与 websocket 客户端后直接调用 `runner.episode(...)`，不经过它的 `main()`（其中的 `metadata_index` 与 50 局断言对本仓库 builder 不成立）。输出目录结构与原侧相同 |
| 新 `scripts/eval-official/run_astra.sh` | 新侧启动器：环境变量与 VLA 启动命令逐项照抄 `run.sh`（含 `--seed=42`、`XLA_PYTHON_CLIENT_PREALLOCATE=false`、`USE_HF=1`、`HF_HUB_OFFLINE=1`、`IMAGE_MAX_TOKEN_NUM=128`、`env -u OPENAI_API_KEY` 启动 VLA），只把 `PYTHONPATH` 的环境源换成本仓库 `src`；另设 `NO_PROXY=127.0.0.1,localhost`；启动前打印 `robomme_hard.__file__` 与 `robomme.__file__` |
| 身份 | 第二档：16 任务各取官方第 3 局（本地局号 0）；V9 连通：`VideoUnmask` 的 xhard1 第一局（规划次数少的任务） |
| 步数 | xhard0 两侧 1300；V9 连通局 1600 |
| 两卡 | 按官方要求一张卡给 VLA、一张给仿真与监视器，单独的两卡 job |
| 仿真版本 | 官方文档在仿真环境里把 SAPIEN 覆盖到 3.0.3；本计划两侧都用 3.0.2（官方环境锁文件与本仓库一致的版本），差异写进报告 |
| 密钥 | 启动行 `OPENAI_API_KEY="$(cat ~/.config/astra/openai.key)"`；GL 上从登录节点 tmux 启动，变量经 `srun` 传入计算节点 |
| 对比 | 规划来自在线模型，两侧不会逐步相同；只比成功率、每局子任务序列、规划与监视次数 |
| 停机 | Astra 自带「规划服务出错即停整个分片」保留；停下后剩余局不自动重跑，报告用户 |

### 1.6 启动脚本与转码（S6）

| 文件 | 改动 |
|---|---|
| `scripts/eval-official/run_seat.sh` | 新参数 `--dataset`、`--max-steps`、`--strict-cap`、`--mme-variant`、`--qwenvl-groundsg-adapter`、`--pp-ckpt`、`--trace-root`，在 `start_client` 处透传给 `env_client.py run`。策略号：`smvla=0`、`mme=1`、`mmesg=2`、`pp=3`（端口 `18000 + 100×席号 + 10×策略号`）。`start_server` 新增 `mmesg`（与 `mme` 同命令，`MME_YAML_EXPECT` 取 `symbolic-grounded-subgoal.yaml`）与 `pp`（`cd third_party/PonderPounce && setsid env … "$PP_PY" -m ponderpounce.eval.robomme_server --args.checkpoint_path "$PP_CKPT" --args.device cuda:0 --port $port`，就绪判定用 `/health`）。`BENCH_PY` 对 `mmesg`、`pp` 默认取客户端扩展环境。不传新参数时行为与现在相同 |
| `scripts/eval-official/run_eval_gl.sh` | 透传上述参数；`--policies` 接受 `mmesg`、`pp`；`COND` 改为由参数给出；每局录像在同步前就地转码：复用 `scripts/injection-dev/site/eval_transcode.py` 的参数（`libx264 -preset veryfast -crf 23 -pix_fmt yuv420p -movflags +faststart`，30 fps），核对帧数一致后删除节点上的原始帧，只把 mp4 与 `summary.json` 发布到 NFS。判定行 `SEAT_REC_SYNC=PASS … transcoded=<n> frame_mismatch=0` |
| 新 `scripts/eval-official/run_official_hard.sh` | 原侧席位启动器：起模型服务（同上命令）→ 跑 `official_hard_runner.py` 或 `pp_official_runner.py` → 转码与同步 → `trap` 清理；判定行 `OFFICIAL_SEAT_DONE seat=NN policy=… outcome=… rc=…`、`EXIT_CODE=` |
| 新 `scripts/eval-official/pair_seat.sh` | 第二档一席的串行链：同一分片先原侧后新侧，同一张卡，前一侧的服务完全退出、显存释放后再起后一侧 |

### 1.7 轨迹记录、对比、报告、资源探针（S7）

| 文件 | 内容 |
|---|---|
| 新 `scripts/eval-official/trace_writer.py` | 每局一个 `trace.jsonl`：每步 `{step, front_sha256, wrist_sha256, state(float32×8 的 hex), action(float32×8 的 hex), subgoal, terminated, truncated, status}`，首行含演示帧数与各帧哈希。原侧与新侧驱动都调用它；哈希在画面进入编码器之前计算 |
| 新 `scripts/eval-official/gate2_compare.py` | 读两侧 `trace.jsonl` 与结果行，按 `(task, source_episode, seed)` 配对；输出逐身份表：是否同终态、首个分叉步、分叉类型（画面／状态／文本／动作／停止步）。判定行 `GATE2=INFO policy=… compared=192 same_terminal=<n> identical_trace=<n> first_diverge_{obs,state,text,action}=<n> missing=0`。两侧身份不齐为 `GATE2=INCOMPLETE`。Astra 模式只比终态与子任务序列 |
| 新 `scripts/eval-official/model_eval_report.py` | 汇总各模型、各数据集、各入口的覆盖与成功率（按任务、按档），并入第二档差异与预算账本；判定行 `MODEL_EVAL_REPORT=PASS sets=<n> …`、`EVAL_BUDGET=PASS attempts<=… resets<=…` |
| 新 `scripts/eval-official/resource_probe.py` | 预检用。单个常驻进程，每秒读一次给定 PID 的进程树 `/proc/<pid>/status` 里的 `VmRSS`、`VmHWM`，以及 `nvidia-smi --query-compute-apps=pid,used_memory --format=csv -i <指定卡>`；输出 `PREFLIGHT=PASS route=… rss_peak_gb=… vram_peak_mb=… episode_s=… cpu_cores_used=…` |

### 1.8 主会话自做

| 项目 | 理由 |
|---|---|
| 两个新子模块的 gitlink、`.gitmodules` | 第三方来源与 gitlink 归主会话 |
| 新 `scripts/eval-official/client-env/{pyproject.toml,uv.lock}` | 依赖声明归主会话。内容：本仓库（路径依赖，含 `eval-client` 组）+ `ms-swift==3.11.1`、`qwen-vl-utils==0.0.14`、`transformers==4.57.3`、`peft==0.18.1`、`imageio`、`imageio-ffmpeg`、`vla-eval==0.7.0`；`flash-attn==2.8.3` 在环境建好后带 `--no-build-isolation` 编译安装并记录构建信息。供 QwenVL 预测器、PonderPounce 客户端、Astra 的仿真与监视器共用。解析冲突（如 `websockets` 版本）时拆成两个环境 |
| `tests/contract/benchmark_contracts.json` 合并、新文件登记 | 公共件 |
| `scripts/README.md`、`src/robomme_hard/README.md`、`AGENTS.md` 中对 `evaluation_hard.py` 的过期描述、`docs/1002-pending-decisions.md` 的 B5 | 文档 |
| 资产拷贝与核对、本机预检、全部 GL 运行、留档 | 资源与预算归主会话 |

## 二、子代理分配表

`BASE` 在派发时记当前 HEAD。公共禁触：`src/robomme/**`、`third_party/**`、`uv.lock`、`pyproject.toml`、`.gitmodules`、`tests/_support/**`、`tests/conftest.py`、`tests/contract/benchmark_contracts.json`、`scripts/` 顶层、其他块的文件。验收环境：`UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync python -m pytest <路径> -q`，先打印 `robomme_hard.__file__` 确认指向 worktree。全部是 CPU 测试，不占 GPU、端口随机、不起 tmux。

| 编号 | 目标 | 可写文件集合 | 依赖 | 合并顺序 | 验收与判定行 |
|---|---|---|---|---|---|
| S1 | 数据集与删查表 | 1.1 表内全部文件 | 无 | 1 | `tests/contract tests/unit/hard tests/pipeline/site tests/pipeline/parity -m 'not slow'`；`HARD0_INTERFACE=PASS tasks=16 per_task=12 total=192 specs_reads=0`、`STEP_LOOKUP=PASS tier_max_steps_refs=0` |
| S2 | 评估客户端、清单、报告 | `scripts/eval-official/{env_client,eval_manifest,eval_report}.py`；`tests/pipeline/eval/` 下 1.2 列出的测试与 `eval_fakes.py`、`contracts.delta.json`、`mutants.json` | S1 | 2 | `tests/pipeline/eval -m 'not slow'`；`DATASET_ROUTING=PASS crossed=0 default_changed=0`、`EVAL_SHARDS=PASS mode=hard0 total=192` |
| S3 | GroundSG | 新 `official_defs.py`、`mmesg_client.py`、`official_hard_runner.py`；新 `tests/pipeline/evalx/groundsg/` | S2 的 `conn_info` 与 `run_episode` 约定 | 3（与 S4、S5 无先后） | 固定输入下新适配与官方循环的请求、动作、终态一致（Qwen 引擎用不加载权重的替身）；`OFFICIAL_ADAPTER=PASS variants=2 payload_diff=0 exec_diff=0 terminal_diff=0`、`OFFICIAL_HARD_SOURCE=PASS robomme_hard_imported=0` |
| S4 | PonderPounce | 新 `pp_client.py`、`pp_official_runner.py`；新 `tests/pipeline/evalx/pp/` | S2 | 3 | 假服务下新客户端与 `SyncEpisodeRunner` 的消息序列逐帧相同；`PP_PROTOCOL=PASS frames_diff=0 order_diff=0` |
| S5 | Astra | 新 `astra_hard_runner.py`、`run_astra.sh`；新 `tests/pipeline/evalx/astra/` | S1 | 3 | 规划、监视、VLA 全部替身，零外联；`ASTRA_WIRING=PASS api_calls=0 builder_dataset_ok=1` |
| S6 | 启动脚本与转码 | `run_seat.sh`、`run_eval_gl.sh`、新 `run_official_hard.sh`、`pair_seat.sh`；`tests/pipeline/eval/test_seat_scripts.py`、`seat_fake_engine.py` | S2～S5 的参数名 | 4 | `bash -n` 四个脚本；`-m slow tests/pipeline/eval/test_seat_scripts.py`；`EVAL_WIRING=PASS routes=<n> dataset_mismatch=0 variant_mismatch=0` |
| S7 | 轨迹、对比、报告、探针 | 新 `trace_writer.py`、`gate2_compare.py`、`model_eval_report.py`、`resource_probe.py`；新 `tests/pipeline/evalx/report/` | S3～S5 的轨迹字段 | 5 | 夹具覆盖缺身份、重复、动作改 1 bit、画面哈希改变；`GATE2_SELFTEST=PASS` |

共享文件裁决：`env_client.py` 只归 S2；两个现有启动器只归 S6；`trace_writer.py` 归 S7，S3～S5 先按 1.7 的字段约定写调用，S7 合入后由主会话核对；各块新增的契约条目写在自己目录的 `contracts.delta.json`，由主会话并入总表。每块合并按 `CLAUDE.md`「计划执行模式」做合并前审查与合并后审查。

## 三、资产与环境

| 资产 | 本机来源 | NFS 落点（`N=/nfs/turbo/coe-chaijy-unreplicated/hongzefu`） | 大小 |
|---|---|---|---|
| GroundSG 动作模型 | `/data/hongzefu/robomme_policy_learning-vqa-test/runs/ckpts/mme_vla_suite/symbolic-grounded-subgoal/{79999,history_config.txt}` | `$N/sg-eval/ckpt/mme/symbolic-grounded-subgoal/`（真实目录，不用符号链接） | 11 GB |
| QwenVL GroundSG 适配器 | 同上仓库 `runs/ckpts/vlm_subgoal_predictor/qwenvl/grounded_subgoal/checkpoint-1200` | `$N/sg-eval/ckpt/qwenvl-groundsg/checkpoint-1200` | 1.3 GB |
| Qwen3-VL-4B 底座 | `~/.cache/huggingface/hub/models--Qwen--Qwen3-VL-4B-Instruct`（revision `ebb281ec…`） | `$N/hf-cache/hub/` | 8.3 GB |
| openpi 分词器 | `artifacts/v8-evaluation/openpi-data/big_vision/paligemma_tokenizer.model`（sha256 `8986bb4f…`） | `$N/sg-eval/openpi-data/` | 小 |
| PonderPounce 权重 | 需下载 `worv-ai/ponderpounce-9b-robomme` @ `5691e056…`（已放行） | `$N/sg-eval/ckpt/pp/ponderpounce-9b-robomme/` | 27 GB |
| Qwen3.5-9B 与 PaliGemma 的分词器文件 | 需下载（后者需访问许可） | `$N/hf-cache/hub/` | 小 |
| Astra 监视器适配器 | 需下载 `bingaochen/Astra-on-RoboMME-Monitor` @ `18ac2831…`，`sha256sum -c SHA256SUMS` | `$N/sg-eval/ckpt/astra-monitor/` | 小 |

- 拷贝只用 `rsync -a`，逐文件 sha256 写入 `artifacts/sg-evaluation/<run>/inputs/assets.sha256`，两端比对；判定行 `ASSETS=PASS files=<n> mismatch=0`。
- 环境：主环境 `.venv`（不动）；`third_party/mme-vla/.venv`（GroundSG 与 Astra 的 VLA 服务）；`scripts/eval-official/client-env`（客户端扩展）；`third_party/PonderPounce/.venv`（PonderPounce 服务）。GL 侧解释器用 NFS 上 uv 管理的 3.11.14，`UV_LINK_MODE=copy`，`uv sync` 不中途打断。
- GL 执行副本：新建 `$N/robomme_benchmark-sgeval`（`git clone --no-hardlinks` 自本机，检出本轮冻结提交，`git -c protocol.file.allow=always submodule update --init`）；席位脚本开头核 HEAD 与工作区干净。

## 四、本机预检

| 路线 | 局 | 说明 |
|---|---|---|
| 生成 smoke | V9 `PickXtimes` xhard1 seed 16100000、xhard0 `PickXtimes` seed 510300，各 1 局 | 单 worker |
| GroundSG + Oracle | 原侧 xhard0 1 局、新侧 xhard0 1 局、新侧 V9 1 局 | 3 局 |
| GroundSG + QwenVL | 同上 | 3 局 |
| PonderPounce | 同上，另加「不装加速内核」1 局 | 4 局 |
| Astra | 原侧 1 局、新侧 1 局；失败可追加，合计 ≤6 局 | 已批 |

- 任务选 `VideoUnmask`（Astra 同）；V9 取 xhard1。本机两张卡，非 Astra 的路线一次并行两条。
- 每条路线由 `resource_probe.py` 采样，记录服务进程、客户端进程各自与合计的内存峰值、显存峰值、单局耗时。
- 判读：内存峰值 × 1.25 向上取整为该模型的 `--mem` 需求；显存峰值超过 44 GB 视为单张 A40 放不下。席位规格 = 各单卡模型需求的最大值。
- 预检全部通过后输出 `PREFLIGHT_SUMMARY=PASS routes=<n> failed=0`，并给出席位规格与分配表。

## 五、闸门与运行手册

**占位 job**（预检后提交，登记到 `$N/gl-hold-logs/hold-jobs-sgeval-<日期>.txt`）

```bash
# 单卡席位；--cpus-per-task 与 --mem 取预检并集，下面是上一轮规格
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:a40:1 --gpu_cmode=shared \
  --cpus-per-task=4 --mem=48G --time=48:00:00 --job-name=sgev-hold-<NN> --wrap='sleep infinity'
# Astra 专用两卡 job
sbatch --account=chaijy2 --partition=spgpu --nodes=1 --ntasks-per-node=1 --gres=gpu:a40:2 --gpu_cmode=shared \
  --cpus-per-task=6 --mem=<预检值> --time=48:00:00 --job-name=sgev-astra-hold --wrap='sleep infinity'
```

暂定分配：Astra 1 个两卡 job；其余 8 张卡为单卡席位，三个模型按「局数 × 单局耗时」比例分。PonderPounce 若单卡放不下，改为单独的两卡 job 并相应减少单卡席位。合计不超过 10 张卡。

**第一档**（1 个单卡席位；沿用 `docs/validation/maintenance-regress-20261004/` 的做法）

1. 身份清单：`gate_set.py export --set {v9,xhard0} --kind generate`（129 行、48 行）。
2. 改后代码的执行副本借用 `$N/robomme_benchmark-noise/.venv`，`PYTHONPATH=<副本>/src`；前提是 `uv.lock` 与 `f8f76fba` 零差异，起跑打印 `IMPORT_CHECK=PASS`。
3. 每遍：`noise_run_gl.sh --pass <遍名> --kind gen --out-root <暂存> --attempts n --resets 3n --retries 0 -- hard_parity.py generate --side H2 --tier v9 --manifest … --identities … --specs-root … --workers 4 --gpu 0 --out /tmp/<遍名> --stage <暂存> --expect-ref scripts/configs/noise-ref-20261003.json`；xhard0 遍 `--side H --tier xhard0` 并设 `ROBOMME_HARD_XHARD0_IN_TEST_HARD=1`。
4. 判定：`noise_gate.py gen-regress check --ref … --set {v9,xhard0} --new … --out … --rerun-identities-out …`。`GEN_REGRESS=PASS` 才放量；`NEED_RERUN` 时同席同节点先改后代码、再旧代码各跑一遍重跑清单，按四格定性；翻转超过 10 局或判为回归即 FAIL，停下交用户。
5. 驱动与基线 `595.71.05` 不同先报告用户。

**第二档**（GroundSG 两组与 PonderPounce）

1. `eval_manifest.py --mode hard0 --shards <席数> --pair-shards` 产出分片。
2. 每席 `pair_seat.sh`：原侧 `run_official_hard.sh` → 新侧 `run_eval_gl.sh --dataset test-hard0 --max-steps 1300`。
3. 每条路线先跑 1 局 smoke，再放到 192 局。
4. `gate2_compare.py` 出差异表；结果不影响第三档。

**第二档（Astra）**：两卡 job 内先原侧 16 局、后新侧 16 局；起跑前在计算节点上做一次不产生费用的模型查询确认代理可达；第一局即视为试跑，失败则停下报告，不自行重跑。随后跑 V9 连通 1 局。

**第三档**：`eval_manifest.py --mode v9-full --shards <席数>`；每席 `run_eval_gl.sh --dataset test-hard --max-steps 1600 --strict-cap --policies <模型>`；`eval_report.py` 出覆盖与视频判定。

**通用**

- GL 上的长任务在登录节点 tmux 里以 `launch_seat.sh` 形式启动（会话名前缀 `sgev-`），日志 `tee` 落盘并以 `EXIT_CODE=` 结尾；每份日志各挂一个监听，过滤词含 `EXIT_CODE=`、`RUN_BLOCKED`、`INFRA`、`svulkan2`、`EXCLUSIVE`、`Traceback`、`CUDA`。同时在跑的长 ssh 不超过 9 条。
- 只有干活的 `srun` 带 `--gpu_cmode=shared`；跨 job 的 `srun` 先清 `SLURM_*` 变量。
- 本机常驻 `eval_video_mover.py` 把压缩视频与结果搬回 `artifacts/sg-evaluation/<run>/`，两端 sha256 相同才删 NFS 源。
- 从第一档起跑到全部结束，执行副本的 HEAD 冻结；文档改动在起跑前提交完。

## 六、预算

| 用途 | 乘式 | 轨迹 | reset 上限 |
|---|---|---:|---:|
| 第一档首跑 | V9 43 格 × 3 局 + xhard0 16 任务 × 3 局 | 177 | 531 |
| 第一档 smoke 与重跑 | 2 + ≤20 | 22 | 66 |
| 本机预检（非 Astra） | GroundSG 2 模型 × 3 局 + PonderPounce 4 局 | 10 | 20 |
| 本机预检（Astra） | ≤6 局 | 6 | 12 |
| GL smoke（非 Astra） | 3 模型 × 3 路线 × 1 局 | 9 | 18 |
| 第二档 | 3 模型 × 2 侧 × 16 任务 × 1 档 × 12 局 | 1152 | 2304 |
| 第三档 | 3 模型 × 800 局（乘式见第一部分） | 2400 | 4800 |
| Astra 第二档 | 2 侧 × 16 任务 × 1 档 × 1 局 | 32 | 64 |
| Astra V9 连通 | 1 局 | 1 | 2 |
| 基础设施重试 | 非 Astra 每模型 ≤10 次；Astra 0 | 30 | 60 |
| **合计** | | **3839** | **7877** |

评估每局按 build 与 reset 各 1 次计；正式成绩 3552 局（GroundSG 两组与 PonderPounce 各 1184）外加 Astra 32 局。正常 fail／timeout 不重试；smoke 不进正式分母；账本持久化，重启不重新获得额度。用户确认本计划即视为对本表一次性授权；超出本表的任何运行先停下申请。

## 七、风险与盲区

- **PonderPounce 的 CUDA 13 构建**能否在本机与 GL 驱动上加载未验证；**PaliGemma 分词器**需要访问许可；**显存**（官方称单服务至少 32 GB）与同卡仿真渲染能否共存于 A40 未验证。三项都在预检第一步暴露。
- **`flash-attn` 编译**在本机与 GL 节点架构上未验证；QwenVL 与 Astra 监视器都硬依赖它。
- **GL 计算节点到 OpenAI 的连通性**未验证（登录节点已通）；Astra 起跑前在节点上先查一次。
- **Astra 每局的规划次数**没有实测，估计每局 2～10 次、上限 24 次；记忆页多的任务请求体很大，接口对图像数量的限制未知。
- **第二档对 PonderPounce 的可比性**依赖固定会话号这一非官方默认行为；与官方的差别（固定会话号、GPU 渲染）写入报告。
- **新建的客户端扩展环境**可能出现依赖冲突，届时拆成两个环境，不动主环境。
- **第一档只证明生成链路未变**，不证明评估适配正确；评估适配靠 S3～S5 的固定输入测试与第二档报告。
- **上一轮环境敏感局** `MoveCube` xhard4 seed 23400200 已登记为抖动局，本轮仍可能再现，只报告。
- 本计划的全部判定行均为待实施，没有任何一项已运行。

## 八、留档与提交

- 档案名 `sg-eval-gl-<起跑日期>-01`，起跑前建 `docs/validation/<档案名>/launch.md`（冻结提交、第三方锁定、资产哈希、环境、席位清单、完整命令、预算、tmux 与 JobID 清单），跑完写 `result.md` 与 `records/`（判定行原文、清洗后日志、差异表、视频索引），并在 `docs/validation/README.md` 加一行。
- 一次性的 GL 侧脚本逐字归档到 `records/*.sh.txt`（上一轮 `launch.sh` 未入库的教训）。
- 子代理提交用 `sub/<编号>: ` 前缀，主会话 `--no-ff` 合并，每次合并后推送；主会话提交按 `12.<小版本>` 接续。
- 收尾：`scancel` 本轮清单内的 JobID，逐目录列名删除 NFS 暂存，核对 `squeue` 为空，输出 `EVAL_CLEANUP=DONE jobs_released=<n>`。
