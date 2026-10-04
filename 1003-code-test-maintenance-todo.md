代码清理、测试重构与生成对拍计划（2026-10-03，第四版：三步串行——先清理 V7／V8，再重写全部测试，最后对拍）

> **权威性**：本文是唯一现行计划。第四版把三份文件合成一份：本文第三版（清理与噪声闸门）、`docs/plans/1003-test-redesign-plan.md`（Claude 的测试重设计，12.379）、`docs/plans/1003-benchmark-tests-refactor-plan.md`（Codex 的测试重构，12.380）；后两份已删除，原文用 `git show 63f34817:<路径>` 取。
>
> 代码锚点 `PLAN_BASE=86e5a015`（12.377；其后到 12.380 的提交只有文档），分支 `newtaskRelease-taskV9`，工作副本 `/data/hongzefu/robomme_benchmark_MotionJEPANewTask`。官方包锚点 `1fadc0ec`，噪声基线锚点 `f8f76fba`。**只规划不实施**：实施须用户说「执行」。原未定事项 U1～U6 已于 2026-10-03 裁决并写入第九节（Q12～Q17），只剩 xhard0 步数口径待定，不阻塞。
>
> 定下本版结构的用户原话（2026-10-03；全部 17 条原话见第二部分第十节）：
> - 「所有的都改到这里面就是我要v7v8的清理再做test的重构然后最后做对拍」
> - 「旧测试完全放弃。不作为基准」
> - 「参考Codex的意见一起整合成一份计划。告诉我还有什么没有定下来。」
> - 「你把第一部分彻底重写一下现在太乱了」

# 第一部分（给人看）

## 一、一句话与三步

把只服务 V7／V8 历史的代码从全库删掉，然后丢掉全部旧测试、针对清理后的代码重写一套覆盖整个 benchmark 的测试，最后在 GL 上把同一批 177 局重新生成一遍，逐局与噪声基线比对，证明生成结果没变。

| 步 | 做什么 | 靠什么判断做对了 |
|---|---|---|
| 第一步 清理 | 删 V7／V8 专用代码，带 v8 名字的现行文件改中性名，顺手修盘点发现的生产小问题 | 导入与命令行冒烟；官方代码与五份规格零改动；清理后 59 格 reset 与清理前快照逐格相同 |
| 第二步 测试 | 旧测试整体删除；按契约重写六层新测试；日常门禁纯 CPU | 每个源码文件都有契约归属且真被执行；日常门禁全绿且在 5 分钟内；60 次 reset 的仿真冒烟通过；故意改坏的地方都被测试抓到 |
| 第三步 对拍 | 噪声基线传 HF；GL A40 上重新生成 `43 格 × 3 局 + 16 任务 × 1 档 × 3 局 = 177` 局，逐局比 sha256，翻转的局重跑定性 | `GEN_REGRESS=PASS`（V9、xhard0 各一行） |

三步严格串行：测试针对清理完、改完名的最终代码写，只写一遍；对拍用的是清理和测试都合入后的最终提交。

## 二、已定口径

1. **清理判据是「谁还在调用它」**，不是文件名。被 V9 生成、V9 评估、V9 站点（8082）、噪声闸门、官方对拍任一处调用的保留；只被 V7／V8 历史调用的删。删掉的随时能从 git 历史取回。
2. **不改的东西**：`src/robomme/`（P2）与三个上游入口（P1）；五份交付规格与已交付 HDF5 的字节；已封存产物的格式名与键名（`hard-specs/4`、`v8-delivery/1`、`v8-shard/1`、`v9-eval-reused/1`、`reused.json` 的 `v8_manifest`／`v8_key`）；判定行前缀 `V8_*`；步数上限（`evaluation_hard.py` 的 `max_steps=1600`、`TIER_MAX_STEPS`，归 Oracle 计划）。
3. **旧测试完全放弃，不作基准**。`tests/lightweight/`、`tests/dataset/` 只当蓝本读，不迁移、不出新旧对照表、不要求新旧结果一致。
4. **测试范围是整个 benchmark 的现行部分**：两个包、四个入口、对拍与噪声工具、生成链路与站点、评估流水线、`challenge_interface/`、打包安装与上游来源。
5. **测试默认纯 CPU，GPU 只做 reset**。唯一用 GPU 的是仿真冒烟：`xhard0 16 任务 × 1 局 + xhard1～5 共 43 格 × 1 局 + 官方包 1 任务 × 1 局 = 60` 次 reset、单 worker、不 step、不生成轨迹；用户已给长期授权。
6. **对拍参照是噪声基线的两遍**（`v9-a`／`v9-b`、`x0-a`／`x0-b`，锚点 `f8f76fba`，GL A40），改后只生成一遍；闸门是「逐局 sha + 翻转重跑确认」，取代旧的「翻转少于 10%」。预算 199 条轨迹已确认。
7. **子代理全部用 opus**；局数一律写乘式（P5）。

## 三、第一步：清理 V7／V8

### 清理后的样子

- 规格只剩 `hard-specs/4` 一种格式；`/2`、`/3` 的读写校验全部删掉。
- V7 机制整套删除：母布局派生低档、分层回注、白名单、外环弧、BinFill 嵌套。
- V7.5 评估的一次性车道脚本、编排器、认领队列、xhard0「官方路线」复核工具删除。
- V8 专用的分片合并、1070 局清单构建分支、单次评估的站点分支删除。
- 噪声工具只留生成比对这条线（`gen-compare`、新增的 `gen-regress`、`selftest`），统计线与评估／reset 噪声的子命令删除。
- 名字带 v8 但实际是 V9 现行的文件和常量改中性名，例如 `v8_manifest.py` → `eval_manifest.py`、`load_specs_v8` → `load_specs`；格式名、键名、判定行前缀不改。

逐文件的「整删／删分支／改名」三张表在第二部分「清理细则」，共涉及约 80 个整删文件、20 个删分支的文件、十几处改名。

### 这一步同时做的两件事

- **生产小修（F 块）**：盘点与反例暴露了 8 处非受保护代码的问题，例如 `upstream_guard.py::check_upstream_bytes` 不加 `--require-upstream` 时放行字节差异且不守三个入口、`noise_gate::classify_pair` 把两个空 h5 判成 `byte_equal`、`hard_specs::validate_specs` 接受布尔和浮点的 seed。用户已定在这一步修掉（Q12），否则第二步会给一份已知有问题的代码写测试。
- **对拍工具（G 块）**：`noise_gate.py` 新增 `gen-regress`，`hard_parity.py generate` 新增 `--expect-ref`（边生成边比 sha），`hard_pull.py` 新增 `--identities`（只回传翻转局），并生成参照文件 `scripts/configs/noise-ref-20261003.json`。它们是代码改动，所以放在清理这一步做；真正上 GL 跑在第三步。

### 没有旧测试，这一步怎么验收

旧测试已放弃，清理块不再跑它们。每块合并前后只查不依赖测试的东西：

- 被改文件能导入、命令行 `--help` 能出；
- `uv run --no-sync python scripts/parity/upstream_guard.py check --require-upstream` 末行 `UPSTREAM_GUARD=PASS`；
- 五份 `specs.jsonl` 的 sha256 与改前相同（`MAINT_SPECS=PASS changed=0`）；`ls -1 scripts/*.py` 恰好四个入口；
- 只读审查子代理逐文件核对「删掉的分支 V9 走不到」（`MAINT_DEAD_BRANCH=PASS`）；
- 全部清理合入后，残留引用为空（`MAINT_NO_LEGACY=PASS`），并**重跑一次 59 格 reset，与清理前快照逐格比**：关节状态、目标文本、示教帧数、obs 形状、wrapper 链必须相同（`RESET_SNAPSHOT=PASS cells=59 same=59`）。清理前快照已经有了——本会话在 `86e5a015` 上跑过，`RESET_SWEEP=PASS cells=59 ok=59`，记录在 `docs/validation/test-redesign-20261003/records/reset-sweep.jsonl`。为什么这个对比有效：seed 与规格没变，reset 是确定性的，清理如果误伤了 V9 的环境构建路径，这里立刻不同。

清理是否改坏了「生成整局轨迹」，要到第三步对拍才有定论；评估流水线和站点不经过生成也不在 reset 里，这一步只有审查子代理把关（已列入盲区）。

## 四、第二步：测试重构

### 为什么要重写而不是整理

两个会话各自实测，结论一致——现在的测试没有覆盖全：

| 证据 | 数字 |
|---|---|
| 行覆盖率（被测试执行过的行） | 官方 wrapper 层 14.8%，hard 包发布契约层 36.5%，hard 任务环境 46.9%，`scripts/parity` 63.5% |
| 从未被任何测试导入 | `upstream_guard.py`（P1／P2 的总闸门）、`hard_pull.py`、`site_server.py`、四个入口、`challenge_interface/` 全部 |
| 真实交付数据 | 五份规格 800 局只被数过局数，没有 sha 钉值，builder 参数解析只抽了约 2 局 |
| 测的档不是交付的档 | BinFill、VideoRepick、两个 Swap 任务主要测 xhard4，V9 这些任务只交付 xhard1、xhard2 |
| 六个已复现的漏检 | 空 h5 判 `byte_equal`；规格校验接受 `candidate=True`、`attempt=0.5`、浮点 seed；零字节冻结文件判 `GATE_SET=PASS`；h5 根属性变化漏检 |
| 不算测试的测试 | 3 个文件 pytest 收集 0 项；约 120 处只扫源码字符串；4 个 `test_zz_*` 依赖执行顺序 |
| 日常门禁耗时 | 518 s，是 5 分钟预算的 1.7 倍；`test_v8_eval_orchestration.py` 一个文件占 172.8 s |

### 新测试的六条原则

1. **按「证明什么」分层**，不按版本号分文件；越贵的层用例越少。
2. **调用真实生产方法，期望值独立得出**。几何用手算坐标，身份用固定小表，状态机用手写事件序列；不在测试里复刻被测逻辑，不靠扫源码字符串。
3. **对真实交付数据跑**：800 局每一行都过校验、过 builder；合成数据只用来造负例。
4. **每个判定器都有负例**，「产物合法」与「两份相同」分开判——空文件相同不等于合法。写入方与读取方之间有贯通测试。
5. **每条契约只在一处断言，用例相互独立**：常量字面值只出现在一个文件里；不依赖执行顺序，不注入 `sys.modules`。
6. **「全覆盖」和「有牙齿」都要能机检**：一张契约清单登记每个源码文件归谁测；再对指定位置故意改坏，对应测试必须失败。

### 六层结构

| 层 | 目录 | 回答的问题 | 进日常门禁 |
|---|---|---|---|
| L0 静态与上游 | `tests/static/` | 官方代码与入口被动过吗？hard 包的复制件与官方只差白名单吗？每个源码文件都有契约归属吗？ | 是 |
| L1 契约 | `tests/contract/` | 交付的 800 局身份、规格、常量是否正确且没变？ | 是 |
| L2 单元 | `tests/unit/` | 每个纯逻辑模块、16 个任务各档的取值、布局、成功失败判定是否正确？ | 是 |
| L3 流水线 | `tests/pipeline/` | 录制读回、对拍、生成、评估、挑战接口、站点六条链路的记账与判定是否正确？ | 是（起 bash、ffmpeg 的标 `slow`，不进） |
| L4 仿真冒烟 | `tests/sim/` | 真仿真里每任务每档能否建出来，观测形状与规格回注是否正确？ | 否，有 GPU 时跑，约 3 分钟 |
| L5 生成一致性 | 第三步对拍 | 改代码后生成结果变没变？ | 否，GL |

日常门禁 = L0～L3 的非 `slow` 部分，目标 ≤ 120 s，硬上限 280 s（目标是估计，统一测时实测校准）。

几处关键机制，写到能直接核对的程度：

- **契约清单** `tests/contract/benchmark_contracts.json`：18 个责任域（C01 注册表与 shim … C18 打包与上游来源）逐条登记「源码锚点、独立期望、正例、负例、边界、对应用例、状态」。元测试 `tests/static/test_inventory.py` 保证 `src/robomme_hard/`、`scripts/`、`challenge_interface/` 下每个现行文件都在清单里（或写明豁免理由），且清单里的用例真被收集并执行；没有执行证据的条目不得标 `verified`。
- **800 局逐局核对**：`tests/contract/test_builder_800.py` 把 `gym.make` 换成「记录参数后抛哨兵异常」的替身，对 `16 任务 × 50 局 = 800` 局逐局调 `make_env_for_episode`，断言交给 `gym.make` 的 seed、difficulty、`sampling_config`、`native_episode_spec` 与规格行一致。纯 CPU，不起仿真。
- **16 任务成功／失败真值表**：每个任务一行正例加一组错误与边界（例如 PickXtimes：N 次完整拾放后按按钮为成功；N−1 次、N+1 次、错对象、持物按按钮为失败），用 CPU 替身直接调真实的 `evaluate`／`step`；官方三档与新值档分别测。
- **评估贯通用例**：`tests/pipeline/eval/test_seat_runner_e2e.py` 用假环境加假连接、真客户端，把成功、失败、上限超时、step 抛异常、server 断连、reset 额度耗尽几种回合从 `SeatRunner` 走到报告，核对分母与判定行。
- **仿真冒烟每格断言**（都是清理前那次扫描实际观测到的）：wrapper 链为 `FailAwareWrapper → DemonstrationWrapper → TimeLimitWrapper → OrderEnforcing → <任务类>`；obs 五个键，图像 `(256,256,3) uint8`、关节 `(7,) float32`；info 七个键且 `status == "ongoing"`；xhard1～5 的 43 格 `spec_binding` 的 `injected_mismatch == 0`——这是唯一必须起仿真才能证明的契约：规格回注真的被环境消费。
- **CPU 资源守卫**：pytest 插件 `tests/_support/resource_policy.py` 在收集前加载，日常门禁里一旦有用例去建真实场景、读模型权重或访问外网就直接失败；`tests/sim/` 只有显式带 `--allow-sim-reset` 才收集。
- **故意改坏验证**：在隔离副本里逐个植入约 20 处错误（规格某行 seed 加 1、`V9_CELLS` 某格加 1、builder 丢掉回注参数、比较器跳过一个数据集、报告分母改用结果行数……），每处都必须有测试失败；受保护的 `src/robomme/` 只做进程内、不落盘的改动。

18 个责任域的完整表、16 任务真值表、每层逐文件清单、植入清单都在第二部分「测试细则」。

### 旧测试怎么处置

`tests/lightweight/`（约 100 个文件）、`tests/dataset/`（7 个）、`tests/_shared/`、两个旧夹具目录整体 `git rm`。第二步一开始旧目录就不再被收集；写新测试的子代理可以从 `PLAN_BASE` 的 git 历史读它们当蓝本。

## 五、第三步：对拍

### 参照与期望

参照是噪声基线的四遍生成（V9 两遍、xhard0 两遍），目前只在本机 `artifacts/noise-baseline/gen/`（共约 171G、1890 个文件），所以先传到 HF 私有 bucket `HongzeFu/robomme-hard-v9-noise-baseline`，并在 GL 的纯 CPU job 里逐对象读回校验（`HF_VERIFY=PASS objects=1893`）。

参照文件 `scripts/configs/noise-ref-20261003.json` 给每一局一个期望：

| 类 | 哪些局 | 期望 |
|---|---|---|
| 稳定局 | V9 128 局、xhard0 46 局 | 新跑的 sha256 等于基线 |
| 确定性失败局 | xhard0 VideoPlaceOrder seed 610701、611101 | 新跑也失败，且失败产物 sha 相同 |
| 已知抖动局 | V9 BinFill xhard1 seed 16400000 | 不参与判定，只报告 |

为什么不用旧的「翻转少于 10%」：基线两遍之间 V9 只有 1 局不同、xhard0 是 0 局，10% 的线（V9 允许 12 局）比真实噪声大一个数量级，改坏一整个任务也能过。

### 一局不符合期望时

第一次跑不符合期望的局叫「翻转」。翻转的局在**同一台节点**上用两份代码各再跑 1 次（改后代码、旧代码 `f8f76fba`），按下表定性：

| 改后代码第二次 | 旧代码这一次 | 定性 |
|---|---|---|
| 回到基线 | 不看 | 噪声（偶发抖动） |
| 与第一次相同、不同于基线 | 回到基线 | **回归：代码改坏了** |
| 与第一次相同、不同于基线 | 也不同于基线 | 环境变了，交用户 |
| 与第一次也不同 | — | 每次都不同，交用户 |

通过条件（两个集合各自）：回归、环境变了、每次都不同都为 0；确认为噪声的翻转 V9 ≤ 2 局、xhard0 ≤ 1 局；结构不同与原因不明为 0。

### 怎么跑

- 地点 GL A40，2 个占位席，每席 4 worker（与基线相同负载）；V9 约 37 分钟，xhard0 约 10 分钟。
- 边生成边判：每局一完成就在节点上算 sha 并与参照比，相同的局直接删本地文件不回传，只回传翻转局。
- 预算：冒烟 2 条 + 首跑 `43 格 × 3 局 + 16 任务 × 1 档 × 3 局 = 177` 条 + 第二次跑 ≤ 20 条 = **≤ 199 条轨迹、reset ≤ 597**，用户已确认。
- FAIL 时不改参照、不改通过条件；按翻转局所属任务定位到是哪块清理导致的，修好后重跑（预算另报）。
- 限制：只在 A40 上成立；PASS 说明这 177 局没有检出超出噪声的变化，不证明全部 800 局逐字节等价。

三类期望的由来、陪跑局凑满并发、逐局报告格式、命令在第二部分「对拍细则」与 runbook。

## 六、验收

| 步 | 查什么 | 怎么查 | 过了说明什么 | 判定行 |
|---|---|---|---|---|
| 一 | 官方源码与入口未动 | `upstream_guard.py check --require-upstream` | P1、P2 守住 | `UPSTREAM_GUARD=PASS` |
| 一 | 交付规格未动 | 五份 `specs.jsonl` sha256 前后相同 | 生成输入不变 | `MAINT_SPECS=PASS changed=0` |
| 一 | 改动不越界 | `git diff --name-only` 逐文件归入清理细则或 F 块清单 | 没有清单外改动 | `MAINT_SCOPE=PASS files=<n>` |
| 一 | 删掉的分支 V9 走不到 | 审查子代理逐文件核对 | 删除不影响 V9 路径 | `MAINT_DEAD_BRANCH=PASS files=<n>` |
| 一 | 没有残留引用 | 对 `src scripts` grep `load_specs_v7\|SCHEMA_V7\|v75-lanes\|claim_queue\|derive_specs\|v7_site\|check-gen\|baseline-gen` 为空 | 清干净了 | `MAINT_NO_LEGACY=PASS` |
| 一 | 环境构建没变 | 59 格 reset 与清理前快照逐格比 | 清理没误伤 V9 的建场景路径 | `RESET_SNAPSHOT=PASS cells=59 same=59` |
| 一 | 参照文件可信 | `gen-regress build-ref` 重算四遍 h5 sha 并与 git 记录对照 | 每局期望来自真实文件 | `NOISE_REF=PASS v9=129 stable=128 jitter=1 xhard0=48 stable=46 fail=2 mismatch=0` |
| 二 | 每个源码文件有归属、每条契约真被执行 | 契约清单元测试 | 「覆盖所有部分」可机检 | `TEST_INVENTORY=PASS unclassified=0`；`TEST_CONTRACTS=PASS missing=0 pending=0` |
| 二 | 日常门禁 | runbook 的日常命令 | 关键 CPU 契约全过且在预算内 | `TEST_CORE=PASS failed=0 wall_s=<实测>` |
| 二 | 慢测试 | runbook 的慢测试命令 | bash、ffmpeg、websocket、wheel 通过；缺工具的项单列 | `TEST_SLOW=PASS failed=0 not_verified=<清单>` |
| 二 | 门禁没偷跑仿真 | 资源守卫事件账本 | 日常门禁是纯 CPU | `TEST_RESOURCE=PASS native_reset=0 gpu_init=0 violations=0` |
| 二 | 16 任务行为 | 真值表用例 | 成功失败判定被独立期望核对 | `TEST_TASKS_CPU=PASS tasks=16 missing=0` |
| 二 | 比较器不误接受坏输入 | 六个反例加扩展 | 空文件、类型错误、属性变化被拒 | `PARITY_VALIDITY=PASS false_accept=0` |
| 二 | 仿真冒烟 | `tests/sim`，60 次 reset | 16 任务全部档可建、回注零差 | `TEST_SIM=PASS cells=59 official=1 failed=0` |
| 二 | 测试有牙齿 | 植入清单逐个改坏 | 关键契约被改坏时确有测试报错 | `TEST_MUTATION=PASS seeded=<n> caught=<n> survived=0` |
| 二 | 覆盖率 | 同一条 coverage 命令换新目录 | 行覆盖率较现状上升，测不到的仿真路径单列 | `TEST_COVERAGE=PASS`，逐分区列「现状 → 新值」 |
| 三 | 基线已上 HF | GL 纯 CPU job 逐对象读回 | 参照有异地副本 | `NOISE_HF_UPLOAD=PASS objects=1893 …`；`HF_VERIFY=PASS objects=1893 sha_match=1893 …` |
| 三 | 生成结果没变 | `noise_gate.py gen-regress` | 177 局逐局与基线相同，或翻转已认定为噪声 | `GEN_REGRESS=PASS set=v9 n=129 … noise=<≤2> regress=0 env_changed=0 unstable=0 structural=0 unknown=0`；xhard0 同格式 `noise=<≤1>` |

生产代码确有问题而用户裁决不修的，对应契约记 `blocked`，判定行如实写 FAIL，不用预期失败冒充通过。

## 七、步骤

| 阶段 | 内容 | 判据 |
|---|---|---|
| 0 | 清理前快照：59 格 reset、行覆盖率、逐文件耗时（**已完成**） | `RESET_SWEEP=PASS cells=59 ok=59` |
| 0b | 主会话：清理 `.claude/worktrees/` 下 5 个旧子代理 worktree 及其分支（Q15；做法见第二部分第四节） | `git worktree list` 删前删后差集恰为这 5 个；主检出 `git status --short` 无新增改动 |
| 1a | 清理并行批：G（对拍工具与参照文件）、W1（`eval-official`）、W2（`injection-dev`）、F（生产小修） | 导入与 `--help` 冒烟；`UPSTREAM_GUARD`、`MAINT_SPECS`；`NOISE_REF`；每块 `PRE_MERGE_REVIEW=PASS` |
| 1b | 清理串行：W3（`parity` 历史分支，等 G）→ W4（`src/robomme_hard`，等 W1～W3）→ R（改名） | 同上，加 `MAINT_DEAD_BRANCH`、`MAINT_NO_LEGACY`、`MAINT_SCOPE` |
| 1c | 主会话：清理后 59 格 reset 与快照比 | `RESET_SNAPSHOT=PASS` |
| 2a | 主会话：`git rm` 旧测试；搭公共框架（`tests/_support/`、资源守卫、契约清单骨架、`pyproject.toml` pytest 段） | 守卫反证用例通过；收集无错 |
| 2b | 测试并行批：T1～T9 九块同时写（分工见第八节） | 各块定向通过，`PRE_MERGE_REVIEW=PASS` |
| 2c | 主会话统一测：日常门禁、慢测试、仿真冒烟、植入验证、覆盖率 | 第六节「二」的全部判定行 |
| 3a | 主会话：噪声基线上传 HF 与 GL 读回校验（不依赖代码，可在阶段 1 期间提前做） | `NOISE_HF_UPLOAD`、`HF_VERIFY` |
| 3b | GL 对拍：冒烟 2 局 → 首跑 177 局 → 翻转局第二次跑 → 逐局报告 | `GEN_REGRESS=PASS`（两个集合） |
| 4 | 文档与留档：`docs/1003-noise-baseline.md` 第六、七节；各 README；`AGENTS.md`「覆盖第 4 条」与 P1；待定清单 B5／C1／C2 | 全部判定行入档 |

阶段 2c 出红时：`RESET_SNAPSHOT` 已过而某个新测试红，优先怀疑测试期望写错；确认是生产代码问题的，回到清理块修，修完重跑 1c。

## 八、子代理分工与合并（简述）

**第一步七块，改生产代码**：G 管噪声工具与参照文件；W1 管 `scripts/eval-official/`；W2 管 `scripts/injection-dev/`；W3 管 `scripts/parity/` 的历史分支；W4 管 `src/robomme_hard/`；R 做改名；F 做生产小修。G、W1、W2、F 的文件互不相交，一起派；W3 与 G 共用 `hard_parity.py`，等 G 合入再派；W4 要删的常量在 W1～W3 的文件里还有人用，最后派；R 等前面全部合入。

**第二步九块，只在 `tests/` 下各自的新目录里写**：T1 静态与上游、打包；T2 hard 契约（规格、常量、800 局 builder）；T3 官方包单元与 16 任务原生判定；T4 hard 包单元与新值档判定；T5 录制与读回；T6 对拍与噪声工具；T7 生成与站点；T8 评估与挑战接口；T9 仿真冒烟。九块目录互不重叠，清理全部合入后一起派。

公共件（`tests/_support/`、`tests/conftest.py`、契约清单总表、`pyproject.toml`）、旧测试删除、统一测、仿真冒烟实跑、HF 上传、GL 对拍、文档都归主会话，避免多人写同一文件。

每块合并前派一个只读审查子代理：清理块审「改动没越出文件清单、删掉的分支 V9 走不到」；测试块审「真调生产方法、期望独立、有负例、没有字面常量」。每块合并后主会话跑当时能跑的检查（清理阶段是冒烟与两条守卫，测试阶段是已合入的新测试），通过即 push。由 Claude Code 按 `CLAUDE.md`「计划执行模式」执行（worktree 隔离、`sub/` 前缀提交），全部子代理用 opus。

## 九、已定与未定

### 已定（用户原话或经 AskUserQuestion 选定）

| 编号 | 事项 | 决定 |
|---|---|---|
| Q1 | 步数上限 | 本计划不处理，1600／1300 归 Oracle 计划 |
| Q2 | V7.5 xhard0「官方路线」复核工具 | 删除 |
| Q3 | 带 v8 名字的现行文件和常量 | 改中性名；格式名、键名、`V8_*` 判定行前缀不改 |
| Q4 | 噪声基线上 HF | 四遍全传，新建私有 bucket；校验在 GL 纯 CPU job 里做 |
| Q5 | 对拍闸门 | 逐局 sha + 翻转重跑确认；第二次改后代码与旧代码各 1 次；第三次默认不跑 |
| Q6 | 对拍预算 | 冒烟 2 + 首跑 177 + 第二次 ≤ 20 = ≤ 199 条，reset ≤ 597 |
| Q7 | 回传 | 边生成边比 sha，只回传翻转局 |
| Q8 | 仿真冒烟 reset | 长期授权，每次 60 次 reset |
| Q9 | 三件事的顺序 | 先清理，再测试重构，最后对拍，写在这一个文件里 |
| Q10 | 旧测试 | 完全放弃，不作基准 |
| Q11 | 子代理模型 | 全部 opus |
| Q12 | 8 处非受保护生产代码问题（原 U1） | 修，放在第一步（F 块；清单见第二部分清理细则末尾）。其中评估清单 xhard0 期望数那一条只读到写死、未实跑，先写复现用例，复现不了就不改 |
| Q13 | 受保护官方代码里的问题（原 U2） | 不改。测试锁定官方现状，登记为语义问题：`evaluation.py` 的 error 分支没给 `outcome` 赋值、`run_example._validate_episode_index(-1)` 与文档矛盾、PickHighlight 失败回调与语言冲突（候选，未实证） |
| Q14 | 测试做多深（原 U3） | 做 wheel 仓库外安装测试；做 8 个观测开关 × 4 种动作空间 = 1024 组合的全组合测试（放慢测试档）。真实浏览器交互测试不做，站点前端只测到路由与数据字段，交互登记为「未验证」 |
| Q15 | 谁执行与旧 worktree（原 U4） | Claude Code 执行；`.claude/worktrees/` 下 5 个旧子代理 worktree 清理掉、不合并 |
| Q16 | xhard0 步数口径（原 U5） | **待定**。入口对所有档写死 1600，`TIER_MAX_STEPS["xhard0"]` 是 1300；新测试对 xhard0 的上限取值不下断言，契约清单记 `conditional`，等待定清单 B5 |
| Q17 | 改名让历史命令无法原样复现（原 U6） | 不管；`scripts/README.md` 出新旧名对照表即可 |

### 未定

只剩 Q16（xhard0 步数口径），不阻塞本计划的任何一步。

# 第二部分（技术细节，供 agent 追踪）

> 本部分的「清理细则 2.1～2.5」「对拍细则 3.0～3.4」「G／H 逐项清单」「对拍预算」「对拍 runbook」由脚本从第三版逐字搬入，只改了节号的叫法（原「第 2.x 节」→「细则 2.x」，原「第 3.x 节」→「细则 3.x」，原 HF 上传一节 → 「细则 3.0」）。「测试细则」合并自 Claude 与 Codex 两份测试方案。

## 〇、红线

- R1：不改 `src/robomme/`、`scripts/{dataset_replay,evaluation,run_example}.py`、交付规格五份、`uv.lock`；不改格式名、`reused.json` 键名、`V8_*` 判定行前缀；不碰 `evaluation_hard.py` 的 `max_steps` 行与 `TIER_MAX_STEPS`。coverage 只用 `uv run --no-sync --with coverage` 临时环境，不加依赖。
- R2：参照文件 `scripts/configs/noise-ref-20261003.json` 生成后只读；对拍 FAIL 时不改参照、不改通过条件。
- R3：GPU 只允许两处——`tests/sim/` 的 60 次 reset（含清理后快照对比那一次），与第三步 GL 生成（预算表内）。其余全部 CPU。worktree 内不跑 `tests/sim/`。
- R4：不新增 `scripts/` 顶层文件；`scripts/` 不得 import `tests/`；测试夹具不放生产模块。
- R5：worktree 内用 `UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv PYTHONPATH=<worktree>/src uv run --no-sync`，先打印 `robomme_hard.__file__` 确认指向 worktree。
- R6：HF 只新建并写入 `HongzeFu/robomme-hard-v9-noise-baseline`；不碰其他 bucket。token 只走环境，不落文件。
- R7：本机 `artifacts/noise-baseline/gen` 只读，上传与比对都不改它。
- R8：新测试不得用 AST／字符串扫描代替行为验证（L0 的逐字节与 diff 白名单除外）；不得复刻被测公式；不得注入 `sys.modules`；不得依赖用例顺序；常量字面值只许出现在 `tests/contract/test_constants.py` 与钉值文件。
- R9：受保护的 `src/robomme/` 与三个上游入口，植入验证只做 tests 进程内可恢复、不落盘的改动；非受保护源码的植入在隔离副本里做，不改主检出。
- R10：`.claude/worktrees/` 下的 5 个旧 worktree 按阶段 0b 清理（Q15）；除此之外，不属于本计划分配表的 worktree 一律不动。

## 一、清理细则

> **合并版对本节的四条更正**（表格原文逐字保留，以这四条为准）：
> 1. 表里凡提到旧测试文件的迁移、改用夹具、保留测试（`tests/` 那一行、`test_v8_regression_cmds.py` 改用 `/4` 夹具、`tests/_shared/v7_tier_values.py` 并入等），一律作废——旧测试整体丢弃（已定口径 4），清理块不维护旧测试。
> 2. 细则 2.3漏列 `scripts/injection-dev/generate_h5.py` 的单文件 `/2` continue 分支（`--redo`、`--tasks`、`--self-check`）：`/2` schema 删除后它是死代码，随 W2 一并删。
> 3. 细则 2.5保留 `noise_gate run-fresh` 的理由不成立：`noise_run_gl.sh` 用到的 `RUN_FRESH` 行由 `noise_run.py::check_out_root` 打出；`noise_gate.run_fresh` 只认评估抽取格式，删掉 `eval-extract` 后成死代码，随 G 块一并删。
> 4. `scripts/parity/hard_pull.py` 现在没有 `--identities` 参数，细则 3.4「只回传翻转局」依赖的是 G 块要新写的功能（第二部分已列），不是现有能力。

### 细则 2.1 清理后的样子

- 规格只剩一种格式 `hard-specs/4`（V9 用的就是它）。`/2`（V5～V6 单档）和 `/3`（V7 母布局派生）的读写校验代码全部删掉。
- V7 那一整套机制从包和脚本里删掉：「母布局 → 派生低档」「分层回注」「白名单」「外环弧」「BinFill 嵌套」。
- V7.5 评估的一次性车道脚本、编排器、认领队列、xhard0「官方路线」复核工具删掉。
- V8 专用的分片合并、V8 1070 局清单的构建分支、V8 单次评估的站点分支删掉。
- 噪声工具里只服务「统计线」和「评估／reset 噪声」的子命令删掉，只留生成比对（细则 2.5）。
- 名字带 v8、但实际是 V9 现行的文件和常量，改成中性名（细则 2.4）。

### 细则 2.2 整文件删除

| 位置 | 文件 | 为什么能删 |
|---|---|---|
| `scripts/eval-official/v75-lanes/` | 整个目录（`gl/` 25 个 .sh、`local/` 25 个 .sh、README） | V7.5 评估当时的一次性车道脚本，没有任何代码或测试引用；V8／V9 评估用的都是重写过的席位脚本 |
| `scripts/eval-official/` | `orchestrate.py`、`watchdog.sh` | V7.5 通用编排器，只被 v75-lanes 调用 |
| 同上 | `claim_queue.py` | V7.5 的 NFS 认领队列；先删掉 `env_client.py`、`run_seat.sh` 里的 `--queue` 分支 |
| 同上（用户决定：删） | `official_observer/`（8 个文件）、`policy_replay.py`、`run_policy_replay.sh`、`step6_summary.py`、`compare.py` | V7.5 的 xhard0「官方路线」复核工具：旁路录制、开环回放、第 6 步汇总。它们依赖的三份官方检出与 `artifacts/v7.5eval/` 已在资源清理中删掉，现在已经跑不起来 |
| `scripts/injection-dev/` | `derive_specs.py` | V7 母布局派生（产出 `/3` 规格）；V9 每档独立冻结，不用它 |
| 同上 | `_report.py` | 生产代码没有引用，只有一个测试导入 |
| 同上 | `v8_watchdog.py` | V8 gen1 接续脚本的看门狗，V9 留档里没有使用记录 |
| `scripts/injection-dev/site/` | `v7_site.py`、`v7_site.html`、`v7_site_catalog.py`、`v7_subgoal_lengths.py`、`v7_site_browser_check.py`、`v7_oracle_browser_check.py` | V7 站点全套，只互相引用 |
| `src/robomme_hard/env_metadata/test-hard/` | `layout_whitelist.json` | V7 白名单，V9 builder 不读；交付规格五份不动 |
| `tests/` | `_shared/v7_specs_fixture.py`、`fixtures/v7_specs_sample/`、`fixtures/injection_legacy/` | 只服务 V7 测试。`test_v8_regression_cmds.py` 里有反例借用了 `v7_specs_sample`，先把它改用 `/4` 夹具；`injection_legacy` 全库无引用 |

### 细则 2.3 文件内删分支（文件保留）

| 文件 | 删掉 | 保留 |
|---|---|---|
| `src/robomme_hard/env_record_wrapper/hard_specs.py` | `SCHEMA`(/2)、`SCHEMA_V7`(/3)、`SCHEMAS`、`V7_TIERS`、`V7_XHARD4_ONLY`、`V7_SEED_OFFSET`、`load_specs_v7`、`_check_layout_parent`；`validate_specs` 的 /2、/3 分支；`IDENTITY_KEYS_BY_SCHEMA` 的 /2、/3 项；`seed_rule_for`／`SEED_PROFILES` 的 v5、v7 项；`V8_CELLS`／`_v8_cells`（先把 `_v9_cells` 里对它的循环与集合断言改成直接用档位表）；`CELL_TABLES["v8"]` | `/4` 读写校验、V9 格表、seed 偏移、`TIER_MAX_STEPS`（一字不动） |
| `src/robomme_hard/env_record_wrapper/hard_builder.py` | `layout_parent` 透传与 v7 注释 | 只读 `/4` 的现行逻辑、`max_steps + 2` 写法 |
| `src/robomme_hard/robomme_env/utils/episode_spec.py` | `SPEC_KIND_LAYERED`、`NEST_RULES`、`nest_binfill_targets`、`nest_outer_arc`、`SpecRecorder` 的 layered 分支 | `native-newvalue` 全量规格（V9 现行） |
| `BinFill.py`、`utils/unmask_swap_xhard.py`、`utils/unmask_distractor_sampler.py` | layered 判断与 `_choose_outer_arc` | 其余部分（V9 现行取值） |
| `scripts/injection-dev/_freeze.py` | `freeze()` 的 /2、/3 分支、`_FOUR`、`DEFAULT_SELECT` | /4、`V8_DEFAULT_CANDIDATES`（V9 仍用它核对每格局数）、分层选签 |
| `scripts/injection-dev/freeze_specs.py` | `--seed-profile v7`、`candidates_v7`、`--whitelist`；默认 profile 改成 v8 | v8 profile（V9 的 MoveCube 就用它） |
| `scripts/injection-dev/_rollout.py` | V7 候选池整段（`initial_pool`、`sync_drop_and_backfill`、`run_continue_v7`、`V7_DELIVERY_SET`）、`run_replay` 的 v7 根、`merge_v8` 与 V8 四席分片表 | `split_v8`、`aggregate_v8`、`load_v8_root`、`run_continue_v8`（V9 现行） |
| `scripts/injection-dev/generate_h5.py` | `replay`／`continue` 的 v7 分支、`--mode merge` | `split`／`continue`／`aggregate`（V9 用） |
| `scripts/injection-dev/eval_video_mover.py` | `--mode v7`；默认改成 v8 | v8 账本模式（V9 用） |
| `scripts/injection-dev/v8_continue_after_gen.py` | V8 gen1 专用的等报告、守卫步骤与心跳 | `--site-only --cells v9` 建站路径（8082 用） |
| `scripts/injection-dev/site/v8_site_catalog.py` | V8 单次评估运行分支（`eval_run`、`xhard0_eval`） | V9 复用口径 |
| `scripts/eval-official/env_client.py` | `--queue`、`--canary` 分支与 `claim_queue` 导入 | `--v8` 模式；非 v8 的 `--identities` 路线（尚未开工的 Oracle 计划要用） |
| `scripts/eval-official/run_seat.sh` | `--queue`、`--canary`、`--client-per-task`、`--no-record`；默认 `SMVLA_PY` 指向已删目录，改成必须显式传入 | `--v8` 与非 v8 的 `--identities` 路线 |
| `scripts/eval-official/v8_manifest.py` | V8 1070 局的 `build()` 分支 | `build_v9`，以及读取 V8 清单做对账的函数 |
| `scripts/parity/hard_regression.py` | `layout-shared`、`prefix-geometry` 两个子命令及辅助函数；`_step_headroom_v7` 与 `--v7`；`reset-replay`／`eval-smoke` 的 v7 口径；`xhard0-eval-parity` | `delivery-set`、`tier-values`、`reset-replay`、`xhard0-reset-parity`、`step-headroom`、`movecube-layout`、`env-digest` 三件套、`delivery_index` |
| `scripts/parity/hard_parity.py` | `generate --tier xhard`（V6 四档）与 `--tier v8`、`compare` 里对应的分支、`import-delivery --tier v8` | `native`、`xhard0`、`v9`、`anchor`、`binding`、`export-xhard0-manifest`；`publish` 的 `BUCKET` 常量指向已删 bucket，归 HF 发布方案处理，本计划不动 |

### 细则 2.4 改名（文件仍在用，只是名字误导）

| 现名 | 新名 |
|---|---|
| `scripts/eval-official/run_v8_gl.sh` | `run_eval_gl.sh` |
| `scripts/eval-official/v8_manifest.py`、`v8_report.py` | `eval_manifest.py`、`eval_report.py` |
| `scripts/injection-dev/v8_continue_after_gen.py` | `site_build.py` |
| `scripts/injection-dev/site/v8_*.py`、`v8_site.html` | 去掉 `v8_` 前缀 |
| `scripts/injection-dev/site/v7_render_xhard0.py` | `render_xhard0.py`（V9 站的 xhard0 视频由它产出） |
| `scripts/configs/newtask-v7/xhard0_manifest.json` | `scripts/configs/xhard0/xhard0_manifest.json`（内容是官方 xhard0 192 局清单，不是 V7 数据） |
| `hard_specs.py` 里的 `V8_EXEC_CAP`、`V8_TIERS`、`SCHEMA_V8`、`V8_LAYOUT_RULE`、`load_specs_v8`、`_validate_specs_v8` | `EXEC_CAP`、并入 `TIERS`、`SCHEMA`、`LAYOUT_RULE`、`load_specs`、`_validate_specs` |
| `tests/_shared/v7_tier_values.py` | 并入新测试结构（见测试细则） |

改名后要同步改所有引用点：
- `noise_run.py`、`noise_gate.py` 里按路径加载 `v8_manifest.py`／`v8_report.py` 的常量；
- `site/*` 之间按文件名 `importlib` 加载的字符串；
- `docs/1003-noise-baseline.md` 第七节回归命令里的 `scripts/configs/newtask-v7/xhard0_manifest.json`。

`scripts/README.md` 加一张新旧名对照表。`docs/validation/**` 历史留档里的旧命令不回改。

### 细则 2.5 噪声工具瘦身

噪声基线已经测完，用户口径是以后只测生成噪声。所以噪声工具只留生成这一条线，外加对拍细则新增的逐局闸门：
- `scripts/parity/noise_gate.py`：
  - **保留** `gen-compare`、`run-fresh`（`noise_run_gl.sh` 判 `RUN_FRESH` 要用）、`selftest`；
  - **删除** `eval-extract`、`baseline-reset`、`baseline-gen`、`baseline-eval`、`freeze`、`verify`、`check-reset`、`check-gen`、`check-eval`，以及只为它们服务的统计函数（`binom_cdf`、`cp_upper` 等）和 `_extract_v8_root`／`extract_legacy`；
  - **新增** `gen-regress`（对拍细则）。
- `scripts/parity/noise_run.py`：删 `eval-shard`。
- `scripts/parity/noise_run_gl.sh`：删 `--kind eval|digest` 分支。
- 以上每一项先由审查子代理核实「只有评估／统计在用」才删。`run-fresh` 如果在 gen 路径上也读评估抽取结果，就把那部分改成只认 gen 输出，而不是整个删掉。

### F 块：生产小修清单（Q12 已定：修）

| 编号 | 文件::锚点 | 改什么 | 关闭态（不改时） |
|---|---|---|---|
| F-1 | `scripts/parity/upstream_guard.py::check_upstream_bytes` | 默认严格（字节不等即 FAIL），保留 `--allow-pending` 逃生阀并打醒目警告；新增 `check_entry_scripts`，核三个上游入口与 `git show 1fadc0ec:scripts/<名>.py` 逐字节相同 | 不加 `--require-upstream` 时放行；入口不受守护 |
| F-2 | `scripts/eval-official/v8_manifest.py::check_source` | `xhard0_expected` 改读 `hs.xhard0_prefix()`；先写复现用例，复现不了则不改 | 写死 `len(ALL_TASKS) * XHARD0_PER_TASK` |
| F-3 | `scripts/eval-official/v8_report.py::build_reuse` | 800 总表 `totals.cells` 与 `hs.V9_CELLS` 逐格比，不等记 `count_mismatch` | 只核「新评 80 + 复用 720」 |
| F-4 | `scripts/eval-official/run_seat.sh` | 轮询间隔读 `SEAT_POLL_S`（默认 10）、`SEAT_READY_POLL_S`（默认 2）；生产默认行为不变 | 写死 `sleep 10`、`sleep 2` |
| F-5 | `scripts/parity/noise_gate.py::classify_pair` | 先判两侧是合法 h5（能打开、非空），再判字节关系 | 两个空文件判 `byte_equal` |
| F-6 | `src/robomme_hard/env_record_wrapper/hard_specs.py::_validate_specs_v8` | `candidate`／`attempt`／`seed` 必须是 `int` 且不是 `bool`；先用五份现有规格验证更严校验仍通过 | 接受 `True`、`0.5`、浮点 seed |
| F-7 | `scripts/parity/gate_set.py::check` | 冻结文件为空或解析失败即 FAIL | 零字节文件判 `GATE_SET=PASS` |
| F-8 | `scripts/parity/train_split_parity.py::compare_h5_pair` | 比较范围加 HDF5 根属性与组属性 | 根属性变化 `field_mismatch=0` |

F-1～F-4、F-8 的文件 R 块要改名或 W 块要动，F 块须在 R 之前合入；F-5、F-7 与 G 块同文件，由 G 块一并做；F-6 与 W4 同文件，由 W4 一并做。

## 二、测试细则

> xhard0 的步数上限待定（Q16）：下文凡涉及 `TIER_MAX_STEPS` 与入口 `max_steps` 的断言，xhard1～5 的 1600 照常断言；xhard0 的取值（表里 1300、入口 1600）不下断言，契约清单记 `conditional`。入口 diff 测试只断言 `evaluation_hard.py` 与 `evaluation.py` 恰好差 3 个单行 hunk 及其位置，不断言 `max_steps` 的数值。
>
> 下文沿用清理前的文件名（`v8_manifest.py`、`v8_report.py`、`load_specs_v8` 等）；新测试实际针对改名后的名字写，对照见细则 2.4。凡写「以其为蓝本」「取代某旧文件」处，旧文件只作参考，不迁移。

### 细则 4.3 契约清单：把「所有部分」变成可检查的矩阵

`tests/contract/benchmark_contracts.json` 每条记录含 `id／source／symbol／oracle／positive／negative／boundaries／nodeids／resource／mutants／status`；`status` 区分 `planned／verified／blocked／conditional`，没有执行证据不得填 `verified`。18 个责任域是首版，实施时继续细拆；全部现行源码文件（Python 之外含 shell、HTML、JSON 资产）逐个归类，纯 shim／vendor／一次性出图脚本可写明理由豁免，不准无记录排除。

| 编号 | 生产责任与符号锚点 | 新测试必须实际守住的内容 |
|---|---|---|
| C01 | 两包 `__init__`、注册表、shim | 官方独立进程、hard 独立进程、两种导入顺序；16 ID 精确集合、类与函数归属；错指向与污染拒绝 |
| C02 | 两个 `BenchmarkEnvBuilder`、`episode_config_resolver` | train/val/test/test-hard、16 任务；四个 Unmask train 覆盖；元数据优先级；非法 dataset/action/episode；真实传给构建边界的 seed、difficulty、spec 和开关 |
| C03 | `hard_specs`、`seed_layout`、`resolve_identity` | 类型、schema、canonical hash、未知键、重签后语义校验；candidate/attempt/seed 整数；身份双向映射、顺序、缓存隔离、跨档无碰撞 |
| C04 | `sampling_config`、各任务 `native_blocks`、`SpecRecorder/spec_binding` | 16 任务默认配置；native 冻结；合法收窄与非法范围；RNG 消费不漂移；冻结值实际消费、未消费拒绝、深拷贝、输入输出不别名 |
| C05 | 16 原生与 hard 任务 `evaluate/step`、任务列表 | 本节后面的逐任务真值表；原生与新值分别覆盖，不用 hard 用例冒充原生覆盖 |
| C06 | `sequential_task_check`、失败强制转换、计时与场景运动 | 失败优先、一次只推进一项、首末项、切换许可、缓存清除；CPU actor 姿态首中末帧，演示数据不污染执行 |
| C07 | `task_goal`、动作匹配、投影、route/adjacent、OBB/SAT | 目标语言与实际对象/次数/方向绑定；独立几何算例、阈值等号、对称与平移性质、不可达路径、可见性、非有限输入 |
| C08 | 四 action wrapper、`_augment_obs_and_info` | joint_angle/ee_pose/waypoint/multi_choice；真实 shape/dtype、CPU Tensor→NumPy；8 个开关全部256组合及强制相机交互；字段长度、无原地污染 |
| C09 | `DemonstrationWrapper`、`planner_denseStep` | reset 的演示与初始动作时序；NO RECORD、演示→在线、重复文案不同 index、终态额外底层步；异常恢复钩子；真实规划边界替换为 CPU spy |
| C10 | `RobommeRecordWrapper.step/close/reset` 及 `_video_*` | 真实写入→关闭→h5py→resolver；视频开关与H5独立性；is_completed、terminated/truncated、info.success、episode_success互不替代，不新增H5字段；跨局缓存、幂等关闭、FK失败；真实视频合成/overlay/命名/编码失败 |
| C11 | `EpisodeDatasetResolver`、`dataset_replay::_build_action_sequence/process_episode` | timestep数字排序、稀疏/缺失、演示过滤、joint/ee/choice/waypoint；相邻去重而非全局去重；序列与resolver同一独立夹具核验；真实process_episode的动作顺序、obs=None错误输出、终态/timeout、关闭异常与结果标签 |
| C12 | `_draw/_extract/_freeze/_rollout`、追加与子集 | 抽签预算、选签与采样来源、真实 run_batch 消费；重复/额外/错绑定拒绝；旧 tried＋新结果中断恢复；零计数字段序列化；累计预算与不重复执行 |
| C13 | 评估 client/server、`SeatRunner`、recorder、manifest/report、两个evaluation入口 | 真实packaged identity→清单→客户端→记录器→账本→报告；独立task_success与分母；动作转换、首推理、A→B→A隔离；普通失败不重试；唯一接受与必填身份；入口错误分支outcome和清理，以测试子进程实际执行 |
| C14 | `challenge_interface` 的 client/server、HTTP、codec、`Policy`、`phase1_eval` | 真实 WebSocket/HTTP handler；reset/infer 协议、断连/超时/非法回复；NumPy shape/dtype/端序；精确成功状态与固定分母；异常清理、reset 等待有限结束 |
| C15 | train/hard 比较器、`gate_set/noise_gate/hard_regression` | 空文件/空集拒绝；实际身份集合相等；逐帧结构、根与组属性、group↔dataset；动作与状态 finite；1 ULP、RGB/depth/完成字段；独立参照来源与有限噪声结论 |
| C16 | 席位与接续 shell、锁、watchdog | 真子进程＋假引擎；端口占用、server 先死、首推理超时、TERM/KILL、重启预算、收尾与接续幂等；真实 JSON 生产者到真实守卫，不能打印 PASS 替代 |
| C17 | site catalog/subgoal/semantic/transcode、HTTP、HTML | 独立身份表、连续段和演示过滤；语义标签与真实差异；微型媒体转换；HEAD/Range/白名单/路径；真实浏览器筛选、导航、错误态与播放 |
| C18 | `pyproject`、wheel、UPSTREAM、四入口、当前文档 | 构建 wheel、仓库外非 editable 安装与资源字节；固定来源、模块实际位置、生产不依赖 tests；严格官方对齐、入口白名单、当前链接不指删除脚本 |

对上表的三处裁决（与用户已定口径冲突处，以此为准）：
- C08 的 8 个 `include_*` 开关：日常门禁跑 18 组（全关、全开、8 项单开、8 项单关）加明确交互；四种动作空间 × 256 全组合放慢测试。
- C17 的真实浏览器交互不做（Q14）：只测不依赖浏览器的最小面（路由、Range、白名单、catalog 字段、html 引用的路由与字段 ⊆ 服务端实际提供的），前端交互在契约清单里登记为「未验证」。
- C05 的真值表是 CPU 方法调用，不是 reset 或 rollout；真实仿真只在细则 4.5.5的冒烟层出现。

#### 16 个任务的最小行为真值表

每任务分别运行原生 `easy/medium/hard` 和该任务实际支持的新值档的 CPU 方法测试；输入只含所需的 actor/robot/时钟状态。它是方法调用组合，**不是 reset 或 rollout 的授权数量**。每项还共同要求：未完成不成功、失败终态稳定、演示→在线切换、重复帧去重、重建或 reset 后 episode 状态清零。

| 任务 | 正例 | 错误／边界 |
|---|---|---|
| BinFill | 逐色正确数量入箱，再按按钮 | 少/多一块、错色/错箱、提前按；相等数量与对象移出后计数 |
| PickXtimes | N 次完整拾放后按钮 | N−1/N/N+1、持续抓住、错对象、持物按按钮 |
| SwingXtimes | 右→左 N 轮后放下按钮 | 左右反序、重复停留、距离/高度阈值；xhard5 支持范围 |
| VideoRepick | 交换后仍拾同一 actor N 次 | 用原位置代替身份、交换窗口首尾、演示次数混入 |
| VideoUnmask | 演示后按目标颜色选择 | 错容器、双选顺序、两次选择间放下、揭示窗口 |
| ButtonUnmask | 首按钮揭示后选择 | 跳过按钮、错颜色、按钮深度等号、单/双选 |
| VideoUnmaskSwap | 交换后跟随被遮挡对象 | 原位置误选、1/2/3 次交换、干扰容器、交换首尾 |
| ButtonUnmaskSwap | 两个不同按钮后选正确对象 | 重复同一按钮、同帧两按钮、缺一步、跨局按钮列表残留 |
| VideoPlaceButton | 按按钮前后指定演示落点 | before/after 反转、错 cube、额外演示干扰、交换后 identity |
| VideoPlaceOrder | 演示第 k 次放置目标 | 空间序冒充时间序、首/末序数、按钮插入、闭包捕获错误 |
| PickHighlight | 各个目标拾取均满足 | 漏目标、错对象、重复同一目标；首按钮失败回调与末按钮语言冲突 |
| StopCube | 第 N 次窗口内停止并确认 | N−1/N+1、窗口两端、过期、锁存步不重写、成功后继续 |
| InsertPeg | 同 peg 同抓取端、正确端与方向 | 换 peg/换端/反向、等距端判定、方向近零、延迟成功 |
| MoveCube | 演示指定推/抓方式与区域 | 错方式/工具、区域完整物体边界、距离阈值、三种移动方式 |
| PatternLock | 同按钮序列完整重走 | 跳节点/错序、仅相同后缀、连续同按钮去抖、额外错误触碰 |
| RouteStick | 同节点且沿指定侧绕行 | 节点对但方向反、叉积正/负/零、无轨迹、退化线段、失败锁存 |

### 细则 4.4 分层与目录

| 层 | 目录 | 回答的问题 | 手段 | 进日常门禁 |
|---|---|---|---|---|
| L0 静态与上游 | `tests/static/` | 官方代码与入口被动过吗？复制件只差白名单吗？源码都有契约归属吗？wheel 装出来资源齐吗？ | 逐字节比对、diff 白名单、契约清单元测试；wheel 安装标慢 | 是（wheel 除外） |
| L1 契约 | `tests/contract/` | 交付的 800 局身份、规格、常量是否正确且没变？ | 读真实包内规格逐行核对；常量唯一断言处 | 是 |
| L2 单元 | `tests/unit/robomme/`、`tests/unit/hard/`、`tests/unit/common/` | 每个纯逻辑模块、每个任务的取值／布局／成功失败判定是否正确？ | 纯函数；CPU 替身 actor／robot／时钟调真实 `evaluate`／`step`；离线场景跑真实 `_load_scene` | 是 |
| L3 流水线 | `tests/pipeline/{recording,parity,gen,eval,challenge,site}/` | 录制读回、对拍、生成、评估、挑战接口、站点各链路的记账与判定是否正确？ | 真实组件小闭环；假 runner、假环境、假策略、微型 h5 | 是 |
| L3 慢 | 同上目录里标 `slow` 的用例、`tests/process/` | 真进程监督、bash 席位脚本、ffmpeg、websocket、wheel 安装、1024 全组合 | 真子进程 + 假引擎 | 否 |
| L4 仿真冒烟 | `tests/sim/` | 真仿真里每任务 × 每档能否建出来、观测与规格回注是否正确？ | 每格一次 `make` + `reset`，不 step | 否（有 GPU 时跑） |
| L5 生成一致性 | 不在 pytest 内 | 改代码后生成结果变没变？ | 对拍细则的 `gen-regress`（GL A40） | 否 |

公共件：`tests/_support/`（CPU 替身 actor／robot／时钟、离线场景、生成世界与唯一一份 FakeRunner、评估替身、按路径加载脚本的 `loaders.py`、资源守卫插件）、`tests/fixtures/`（微型 h5／JSON／短媒体与来源摘要）、`tests/mutation/`（植入清单与执行器）。

日常门禁 = L0～L3 的非 `slow` 部分，目标 ≤ 120 s，硬上限 280 s；目标是按现有纯函数用例耗时外推的估计，统一测时实测校准，超了就把最慢的用例降为 `slow`，不删断言。

### 细则 4.5 各层具体守什么

#### 细则 4.5.1 L0 静态与上游（`tests/static/`）

- **`test_upstream_bytes.py`**：进程内调 `upstream_guard` 的各检查函数。正例对真实仓库跑（`src/robomme` 102 个文件与官方 `1fadc0ec` 逐字节相同、三个入口与 `git show 1fadc0ec:scripts/<名>.py` 相同）；负例把模块级 `REPO`／`HARD`／`MANIFEST` 指到 `tmp_path` 下的小目录树，逐个造「改 1 字节、多 1 文件、shim 多 1 行、非法绝对导入、清单被篡改」，每个都必须 FAIL。为什么能逐字节：`src/robomme` 按 P2 冻结，官方 commit 在本仓库 git 对象里可取。
- **`test_copies_vs_upstream.py`**：hard 包三个复制件与官方的 diff 必须恰好等于白名单——`RecordWrapper.py` 只差 `fail_safe_limit` 2000→5000 与一行 import，`OraclePlannerDemonstrationWrapper.py` 只差一行 import，`DemonstrationWrapper.py` 逐字节相同；`UPSTREAM.json` 的 18 个 shim 与自签 sha 成立。取代三个只扫官方源码的 `test_record_*`。
- **`test_entry_scripts.py`**：`evaluation_hard.py` 与 `evaluation.py` 的 diff 恰好 3 个单行 hunk（import、`dataset="test-hard"`、`max_steps`）；`scripts/*.py` 恰好四个入口；`scripts/` 不 import `tests/`；`run_example.EPISODE_LIMITS` 与 metadata 局数一致。
- **`test_inventory.py`**：契约清单元测试（细则 4.3）；另核 `scripts/*.py` 之外没有未登记的现行文件。

#### 细则 4.5.2 L1 契约（`tests/contract/`）

- **`test_constants.py`**：全套件唯一写字面数字的地方。`V9_CELLS` 逐格值、`43 格`、每任务 50 局、`16 任务 × 50 局 = 800`、开关打开时 `800 + 16 任务 × 12 局 = 992`、`TIER_MAX_STEPS`、按档 seed 偏移、`XHARD0_EPISODES`、`XHARD4_ONLY`、16 任务名单与注册 id 集合相等。
- **`test_packaged_specs.py`**：五份 `specs.jsonl` 的文件字节 sha256 钉值（钉值表 `tests/contract/packaged_specs.sha256` 进 git）；逐份 `load_specs` 通过；逐行核对 `spec.task == row.task`、`spec.identity` 的 seed／difficulty 与行一致、`sampling_config` 键集合等于任务集合、`exec_steps ≤ 1600`；seed 全局唯一（盘点核过 1518 行唯一）且与官方 metadata 的 seed 不相交。过了说明：交付规格没被动过，且每一行内部自洽。
- **`test_builder_800.py`**：把 `gym.make` 换成「记录参数后抛哨兵异常」的替身，对 `16 任务 × 50 局 = 800` 局逐局调 `make_env_for_episode`，断言交给 `gym.make` 的完整 kwargs（runtime 四项、seed、difficulty、`sampling_config`、`native_episode_spec`）与规格行一致；开关打开时 992 局、xhard0 的 seed 等于官方 test 集 hard 子集；规格根覆盖与各拒绝路径。
- **`test_tier_table.py`**：唯一一份 V9 档位取值表，同时对三处：进程内 `native_blocks`、包内 header 的 `sampling_config`、包内逐行规格。取代 `_shared/v7_tier_values.py` 与散在各 v4／v5 文件里的取值断言。
- **`test_regression_on_packaged.py`**：对包内真实规格进程内跑 `hard_regression` 的 `delivery-set`、`tier-values`、`step-headroom`、`movecube-layout`（包内 MoveCube 50 局）。
- **`test_schema_v4.py`**：`hard-specs/4` 校验器的负例（篡改、重签、越界、跨档 seed 相交）。
- **`test_gate_set.py`**（129／48 身份集，现有用例质量好，以其为蓝本重写）、**`test_v9_subset_specs.py`**（以其为蓝本重写，补 assemble 两条拒绝分支）、**`test_metadata.py`**（官方 train／val／test 每 split 16 文件、局数、episode 连续；hard 包四个 Unmask 任务 train 元数据各 400 条）、**`test_registry.py`**（三种导入顺序后 16 个 id 归 `robomme_hard`；起子进程，标 `slow`）。

#### 细则 4.5.3 L2 单元

**官方包（`tests/unit/robomme/`）**——官方代码不能改，测试的意义是锁定行为契约：

| 文件 | 守什么 |
|---|---|
| `test_env_builder.py` | `BenchmarkEnvBuilder`：dataset／action_space 白名单、`resolve_episode`、`get_task_list` 顺序、`max_steps + 2`；替身 `gym.make` 下四种动作空间的 wrapper 链类名与顺序 |
| `test_fail_paths.py` | `FailAwareWrapper` 把异常转成 `(None, 0.0, True, False, {status, error_message, exception_type})`；ee wrapper IK 失败的返回形状；取代污染 `sys.modules` 的 `test_step_error_handling` |
| `test_demo_wrapper_status.py` | 终局判定优先级 success > fail > timeout > ongoing、无示教步数截断、动作维度规整（stick 7 维、其余 8 维） |
| `test_step_batch.py` | `planner_denseStep` 的 batch 构造与拼接（决定 obs 的 dict-of-lists 形状） |
| `test_dataset_resolver.py` | 合成 h5 上的 waypoint 去重、multi_choice 读取、joint 补 8 维；收编三个「0 条用例」文件里的 `_case_*` |
| `test_choice.py` | label 匹配、3D 最近、像素投影与最近、`_resolve_command` 的 `[y,x]→[x,y]`；去掉错标的 `gpu` |
| `test_task_goal.py`、`test_vqa_options.py` | 16 任务的目标文本与选项（修正 2 条与官方不符的断言：未知环境返回 `[]`、`back-and-forth`） |

**hard 包（`tests/unit/hard/`）**——按任务一个文件，不再按版本号：

- 公共夹具 `tests/_support/offline_scene.py`：把现有最完整的 `test_v5_xhard_pickswing::OfflineScene`（`object.__new__` 造实例 + 假 `TableSceneBuilder`／`build_cube`／`get_actor_obb`，再调真 `_load_scene`）提成唯一一份，取代 6 个文件里各自复制的 `_FakeActor`。
- `test_<任务>.py` × 14（PickXtimes／SwingXtimes／PickHighlight 合一，PatternLock／RouteStick 合一，其余各一）：**参数化维度 = 该任务 V9 实际交付的档**。每格断言：离线 `_load_scene` 得到的数量、间距、判失败集合（干扰块在 `non_target_cubes` 里、误抓判失败）；自导出规格回放零差；**包内该格前 3 行规格作 `native_episode_spec` 回放，`mismatches == 0`**。
- `test_swap_planning.py`：V9 实际走的均衡外环、内环预规划、S5 均衡（现在零覆盖的约 10 个函数）。
- `test_native_golden.py`：原三档（easy／medium／hard）离线导出的摘要等于金标准，取代约 10 个文件里的「原三档逐字不变」AST 锁与 `test_v8_native_blocks_unchanged`。
- 纯函数模块各一：`test_collision.py`、`test_unmask_sampler.py`、`test_home_site.py`、`test_peg_flip.py`、`test_route_walk.py`、`test_segmentation.py`（从 `test_audit_fix` 迁入）、`test_goal_text.py`（16 任务新值档目标文本）、`test_sampling_guard.py`、`test_episode_spec.py`（含 `spec_binding` 非分层路径：`injected_mismatch`、`recorded_drift` 的 1e-5 容差、`unused`）。

#### 细则 4.5.4 L3 流水线

**对拍（`tests/pipeline/parity/`）**：`test_h5_comparators.py`（同一批合成 h5 变体同时喂三个比较器，逐个钉死各自的比较范围，含「两侧都新增同一字段且只在该字段不同」）；`test_gen_compare.py`（五类互斥，补缺的负例：重复行、档位冲突、h5 打不开、dtype 改变、帧号不连续）；`test_hard_parity_compare.py`（native／xhard0／v9 的终态与分母负例，从将删的 v8 档迁来）；`test_mover_ship_pull.py`（`Mover.handle` → `noise_run ship --finalize` → `hard_pull` 贯通）；`test_xhard0_reset_verdict.py`；`test_env_digest.py`；`test_noise_run.py`；`test_train_split.py`；`test_configs.py`（容差文件自洽）；`test_noise_run_shell.py`（6 个 bash 用例，`slow`）。`gen-regress` 与参照文件的测试由 G 块写，落在本目录。

**生成（`tests/pipeline/gen/`）**：唯一一份 FakeRunner 放 `tests/_support/gen_world.py`。`test_freeze.py`（`/4` 契约与三个拒绝分支、选签、MoveCube 逐方式 17／17／16、dry-run 预算数）；`test_rollout_state_machine.py`（全部改用 `/4`：失败递补、基础设施重试、崩溃恢复、恢复歧义、超配额、回写身份变化）；`test_run_batch.py`（monkeypatch `subprocess.run`，替身直接写 `results.json`／partial／不写）；`test_shard_aggregate.py`（分片不重不漏、聚合四种状态、rebase 三种错误、A40 检查）；`test_eval_identities.py`；`test_site_server.py`（媒体白名单、Range、不跟随符号链接；进程内线程 + 端口 0）；`test_site_catalog.py`（V9 小子表进门禁，59 格全量标 `slow`）；`test_site_build.py`。

**评估（`tests/pipeline/eval/`）**：公共替身（`FakeConn`、假 env、假录制器）收进 `tests/_support/eval_fakes.py`。

- **`test_seat_runner_e2e.py`**（新，核心）：参数化七种回合——成功、失败、上限超时、step 抛非基础设施异常、step 抛基础设施异常（重试）、server 断连（重试后 missing）、reset 额度耗尽——走真 mme／smvla 客户端加假连接，跑完把产物目录直接喂 `v8_report.build_report`，核对分母、结局计数、判定行。
- `test_identity_contract.py`（6 档 `TIER_MAX_STEPS` 含 xhard0 1300；三处 key 函数一致）、`test_attempt_ledger.py`、`test_env_session.py`、`test_policy_clients.py`、`test_eval_manifest.py`（只测 `build_v9`；**导出产物直接喂清单**，开关开／关两种）、`test_eval_report.py`（进程内调用；分母负例补全；800 总表逐格等于 `V9_CELLS`）。
- 标 `slow`：`test_smvla_server_protocol.py`、`test_recorder.py`（ffmpeg）、`test_eval_video_mover.py`（ffmpeg）、`test_seat_scripts.py`（bash）。

#### 细则 4.5.5 L4 仿真冒烟（`tests/sim/`，唯一用 GPU 的层）

**`test_reset_matrix.py`**：`xhard0 16 任务 × 1 局 + xhard1～5 共 43 格 × 1 局 = 59` 次 reset，单进程顺序跑，每格只 `make_env_for_episode` + `reset`，不 step。本会话已实跑一遍（`RESET_SWEEP=PASS cells=59 ok=59`，162.6 s），每格断言的内容都是那次扫描里实际观测到的：

- wrapper 链恰为 `FailAwareWrapper → DemonstrationWrapper → TimeLimitWrapper → OrderEnforcing → <任务类>`，任务类来自 `robomme_hard`；
- obs 恰有五个键，`front_rgb_list`／`wrist_rgb_list` 为 `(256,256,3) uint8`，`joint_state_list` 为 `(7,) float32`，`eef_state_list` 为 `(6,) float64`，`gripper_state_list` 为 `(2,) float32`，五个列表等长；
- info 恰有七个键（`elapsed_steps`、`success`、`fail`、`simple_subgoal_online`、`grounded_subgoal_online`、`task_goal`、`status`），`status == "ongoing"`，`task_goal` 为 1～4 条非空字符串；
- 带示教的 9 个任务（四个 Video 系、VideoUnmaskSwap、InsertPeg、MoveCube、PatternLock、RouteStick）帧数 > 1，其余 7 个 = 1；
- xhard1～5 的 43 格：`spec_binding` 的 `mode == "replay"`、`spec_sha256` 等于规格行、`injected_mismatch == 0`、`unused == 0`——**证明规格回注真的被环境消费**，这是唯一必须起仿真才能证明的契约；
- `unwrapped` 的 seed、difficulty 与规格行一致。

**`test_official_one_reset.py`**：官方 `robomme` 包 1 次 `make` + `reset`（`ee_pose`，全部 `include_*` 打开），断言 depth／内外参的形状与 `available_multi_choices`；再发 1 步不可达的 ee 动作，断言 `status == "error"`（只做 IK，不推进仿真）。

每次跑 L4 = `59 + 1 = 60` 次 reset、0 条轨迹生成。用户已给长期授权（Q8）：以后任何会话跑 `tests/sim/` 的这 60 次 reset 不再逐次申请。

#### 细则 4.5.6 Codex 方案补入的四块（上面各节未覆盖的责任域）

- **录制与读回闭环（`tests/pipeline/recording/`，C08～C11）**：独立事件表 → CPU 替身接口 → 真实 `RobommeRecordWrapper.step` → 真实 `close` → h5py → 真实 `EpisodeDatasetResolver`，逐键核对；`action_t` 对应 `obs_after_t`，reset 帧不入记录。视频用至少 64×64 的合成帧实际调 `_video_prepare_step_frames／_video_apply_overlays／_video_append_step_frame／_video_flush_episode_files`，核 h5 原像素不被 overlay 修改、`NO RECORD` 过滤、不补 reset 帧、成功／FAILED 命名。`dataset_replay::_build_action_sequence` 与 resolver 用同一独立夹具做差分。hard 包的 `RecordWrapper` 复制件同样跑一遍（它与官方只差 `fail_safe_limit` 与一行 import）。
- **16 任务成功／失败判定（`tests/unit/robomme/tasks/`、`tests/unit/hard/tasks/`，C05～C06）**：按上面的真值表，用 CPU 替身直接调各任务的 `evaluate`／`step` 与 `sequential_task_check`；原生三档与新值档分别覆盖，不用 hard 用例冒充原生覆盖。
- **挑战接口（`tests/pipeline/challenge/`，C14）**：真实 WebSocket／HTTP handler（loopback）；reset／infer 协议、断连、超时、非法回复；NumPy shape／dtype／端序的编解码往返；`phase1_eval` 的成功状态精确匹配（`unsuccessful／not_success／success_pending` 不得计成功）与固定分母；异常仍清理。
- **打包与来源（`tests/static/test_package.py`，C18，标 `slow`）**：构建 wheel、在仓库外非 editable 安装到临时 uv 环境、核规格与元数据资源字节；生产代码不 import `tests`。

### 细则 4.6 CPU 资源守卫

`tests/_support/resource_policy.py` 作为 pytest 插件在收集前加载（`pyproject.toml` 的 `addopts` 里 `-p tests._support.resource_policy`）：默认档拒绝真实 scene／GPU 初始化、真实引擎 reset、模型权重读取与外网；CPU 替身的 `reset／step` 允许；子进程继承同一档。`tests/sim/` 只有显式选择该目录并带 `--allow-sim-reset` 才收集（只按 marker 过滤不够，pytest 会先导入模块）。守卫本身要有反证用例：故意调用被禁入口必须先被拒、且原生调用没有发生。必验套件选空、收集出错、关键用例被 skip、未登记的 xfail 都算失败；缺 ffmpeg 的条件项记「未验证」，不计 PASS。守卫是测试执行约束，不宣称能挡住任意绕过。

### 细则 4.7 旧测试处置

- `tests/lightweight/`（约 100 个文件）与 `tests/dataset/`（7 个文件）、`tests/_shared/`、`tests/fixtures/v7_specs_sample/`、`tests/fixtures/injection_legacy/` **整体删除**，不迁移、不出对照表、不作为基准。
- 写新测试时可以读旧文件当蓝本（哪些负例有价值、哪些替身手法可靠），下文各节写「以其为蓝本」的地方都是这个意思；旧文件从 `PLAN_BASE` 的 git 历史读，不要求新用例与旧用例一一对应。
- 时点：阶段 2a 由主会话一次性 `git rm`，`testpaths` 只列新目录。
- 原计划「6 个长期失败逐条改法」随之作废；其中一条提醒保留：`EndeffectorDemonstrationWrapper.step` 在 IK 失败时显式返回 `status="error"`，新测试按这个官方行为写。

## 三、对拍细则

### 细则 3.0 噪声基线上传 HF

**现状**（2026-10-03 22:2x 只读核查）：
- `hf buckets list HongzeFu` 显示，V9 交付集在公开 bucket `HongzeFu/robomme-hard-v9` 上（1604 个对象，即 `16 任务 × 50 局 = 800` 局的 h5 与 mp4 加索引）。V9 这 129 局的交付 h5 都在里面。
- 噪声基线的四遍**不在 HF 上**。它们只存在本机 `artifacts/noise-baseline/gen/`：`v9-a` 69G、`v9-b` 68G、`x0-a` 17G、`x0-b` 17G，共 1890 个文件，其中 h5 有 `(43 格 × 3 局) × 2 遍 + (16 任务 × 1 档 × 3 局) × 2 遍 = 258 + 96 = 354` 个。dataset／model repo 也查过，只有 `panda-demonstrations`、`sam2act_robomme` 两个无关仓库。
- xhard0 原先的官方参照在 `HongzeFu/robomme-hard-parity` 里。这个 bucket 已按 V9 发布方案进入整删流程：留档 `docs/validation/newtask-v9/hf-20261003.md` 写的是已删，但本次列表里它仍然显示（该留档属于并行会话、尚未提交，本计划不碰）。删除之后，`x0-a`／`x0-b` 就是 xhard0 参照唯一的远端副本：它们能成功的 46 局与官方参照逐字节相同，2 局失败的产物也与官方相同。

**做法**（用户选定「四遍全传，新私有 bucket」）：
- 新建私有 bucket `HongzeFu/robomme-hard-v9-noise-baseline`。用 `hf buckets sync` 把 `artifacts/noise-baseline/gen/{v9-a,v9-b,x0-a,x0-b}` 整目录传上去（h5、mp4、`results.jsonl`、`summary.json`、`launch-*.json`、`generate.log` 原样上传）。两个冒烟遍 `smk-*` 不传。
- 另传三份清单：
  - `SHA256SUMS`：1890 行。h5 与 mp4 的 sha 不在本机重算，直接取生成时节点上逐局算出、暂存与拉回时都复核过的 `SHIPPED` 记录（每个局目录一份）；只有 json、log 等 MB 级小文件在本机计算；
  - `identities.jsonl`：`129 × 2 + 48 × 2 = 354` 行，每行写遍名、task、tier、seed、h5 相对路径、sha256、成功或失败；
  - `manifest.json`：写锚点 `f8f76fba`、四遍各自的节点与作业号（gl1525／63153922、gl1527／63153924、gl1525／63153923、gl1527／63153925）、驱动 595.71.05、对应的 git 记录路径。
- **校验不在本机做**（用户 2026-10-03 原话「上传HUGingFace的文件需要校验。但是校验不要在本机进行你可以生成一个在greatlake上的纯CPUJ0B来实现。以后都要这么做写进AgentMetarule」，已写进正本 `463eba2`：第 15 条，以及 `greatlakes.md`「HF 上传校验 job」）：
  - 传完后在 greatlakes 提交一个纯 CPU job：`standard` 分区、chaijy2、4 CPU／8G／12 h，直接 `sbatch`，跑完即退；
  - job 内逐个对象从 HF 流式读回，边下边算 sha256，不落盘；与 `SHA256SUMS` 逐行比对，并核对对象数与字节数；
  - 先用 1 个小对象冒烟，再跑全量；
  - token 只经环境变量传入（`--export=ALL`），GL 侧没有 token 来源时先问用户。
- 公开的 `robomme-hard-v9` 保持只有交付集，不动。
- 本机 `artifacts/noise-baseline/gen` 保留，比对时直接读本机文件，HF 是异地副本。[`1003-resource-cleanup-plan.md`](1003-resource-cleanup-plan.md) 清理细则已补一行把它列为保留项。
- 预计约 15 分钟（上次 V9 上传实测约 208 MB/s）。不占 GPU，不做任何生成。

### 细则 3.1 现行闸门为什么不够准

`docs/1003-noise-baseline.md` 第六节的现行判据是：改后生成一遍，与永久参照（V9 交付 h5、xhard0 官方参照）比较，非逐字节相同的局少于 n 的 10%，即 V9 129 局里不超过 12 局、xhard0 48 局里不超过 4 局；另要求结构不同 = 0、原因不明 = 0。

问题出在**余量比真实噪声大一个数量级**。实测基线（`records/compare/*.jsonl`）：
- V9 两遍跨节点只有 1 局不同（BinFill xhard1 seed 16400000，第 2 遍失败）；
- xhard0 两遍 0 局不同（VideoPlaceOrder seed 610701、611101 两遍都确定性失败，失败产物逐字节相同）。

照 10% 的线，改坏一整个任务也能过。V9 里一个任务约 8 局（例如 SwingXtimes 在 5 个档里各 3 局 = 15 局，StopCube 也是 15 局），某个任务的局全部翻转仍可能不超过 12。

### 细则 3.2 新闸门：每一局都有自己的期望

参照文件 `scripts/configs/noise-ref-20261003.json` 进 git。它由第二部分 G 块的 `gen-regress build-ref` 生成：从本机四遍 h5 重算 sha256，与 git 里的比对记录交叉核对一致后，把每一局归入三类之一。

| 类 | 局 | 期望 |
|---|---|---|
| 稳定局 | V9：除 BinFill xhard1 seed 16400000 外的 128 局（含 MoveCube xhard4 seed 23400200，它两遍彼此相同，只是与交付 h5 不同，参照以基线为准）；xhard0：除 VideoPlaceOrder seed 610701、611101 外的 46 局 | 新跑的 sha256 ∈ {a 遍 sha, b 遍 sha}。稳定局两遍 sha 本来相同，所以等价于「与基线逐字节相同」 |
| 确定性失败局 | xhard0 VideoPlaceOrder seed 610701、611101 | 新跑也必须失败，且失败产物 sha 与基线相同（800 字节，sha256 前缀 `26c4d449632ea072`） |
| 已知抖动局 | V9 BinFill xhard1 seed 16400000（a 遍成功，b 遍失败；交付集里本就是 18 局不可复现之一） | 不参与判定，结果写进报告：与 a 同、与交付同、走另一条轨迹还是失败 |

**一局稳定局（或确定性失败局）的结果不符合期望，就叫「出问题」（翻转）。** 只看第一次跑无法判断原因。噪声基线里已有反例：BinFill xhard1 seed 16400000 两遍新跑在第 819 步一起偏离交付 h5，走的是同一条新轨迹；MoveCube xhard4 seed 23400200 两遍新跑彼此相同，却与交付 h5 不同。也就是说，同一份代码换时间、换节点，也可能稳定地走出另一条轨迹，因此「两次相同但和之前不同」不能直接判为代码改坏了。

所以出问题的局要再跑一轮，在**同一台节点**上用两份代码各跑 1 次：改后代码 1 次，旧代码（噪声基线锚点 `f8f76fba`）1 次，作对照。之后按下表定性（用户 2026-10-03 确认）：

| 改后代码第二次 | 旧代码这一次 | 定性 | 含义 |
|---|---|---|---|
| 与 a 或 b 逐字节相同 | （不看） | **噪声** | 改后代码仍能跑出基线结果，第一次只是 RRT* 墙钟预算下的偶发抖动。这一局登记进抖动名单：写回参照文件的 `jitter_observed`，须经用户确认 |
| 与第一次相同，不同于基线 | 与 a 或 b 相同 | **回归**（代码改坏了） | 旧代码在同一节点仍能出基线结果，新代码稳定地不同 |
| 与第一次相同，不同于基线 | 也不同于基线 | **环境变了** | 新旧代码在这台节点上都出不了基线结果，原因在节点或驱动，不在代码；交用户裁决 |
| 与第一次不同，也不同于基线 | — | **每次都不同**（不稳定） | 交用户裁决，不自行归类 |

**第三次默认不跑**：两轮之后每一局都已落进上表某一格。只有用户看了逐局表后点名要求，才另报预算再跑。

**逐局报告**：只列出问题的局和已知抖动局。每行写：
- 任务、档、seed；
- 第一次、改后第二次、旧代码这一次各自的 sha 前缀，以及成功或失败；
- 三者两两是否相同；
- 与基线从第几步开始分叉、在哪个子目标（拉回本机对照 a 遍 h5 算出）；
- 定性结论。

### 细则 3.3 通过条件（`GEN_REGRESS=PASS`）

两个集合（V9、xhard0）各自都要满足：
1. 回归 = 0，每次都不同 = 0，环境变了 = 0；
2. 确认为噪声的翻转：V9 ≤ 2 局，xhard0 ≤ 1 局。超出时不判 PASS，把逐局明细交用户裁决；
3. 结构不同 = 0（字段缺失、dtype／shape 变化、第 0 帧不同、`setup` 组不同），原因不明 = 0（文件打不开、缺文件、sha 与记录不符）。出现任何一局，直接 FAIL，不进重跑；
4. 跑法前提：GL A40、`--workers 4`、每局都有结果、`RUN_FRESH=PASS`、`BUDGET=PASS`。不满足则本遍无效，重跑，不判通过或失败；
5. 只报告、不判定：已知抖动局的结果；翻转按任务的分布；与 V9 交付 h5 的附带比较（沿用 `gen-compare --ref delivery.local.json`，供对照历史）。

**为什么比 10% 准**：每一局都有自己的期望。只要一局在改后代码上稳定地变了，就会被抓到；真正的偶发抖动由第二次跑认出来，不会误报。旧代码同时跑一次作对照，能把「代码改坏了」和「环境变了」分开，而不是只凭「两次相同」下结论。

**限制**：
- 只在 GL A40 上成立。换 GPU 型号后整文件不再一致，历史上 RTX 6000 Ada 对 A40 是 0/108。驱动版本按来源报告核对，与基线的 595.71.05 不同时先报告用户。
- PASS 说明「177 局里没有检出超出噪声的变化」，不证明全部 800 局逐字节等价。
- 新闸门写进 `docs/1003-noise-baseline.md` 第六节，取代 10% 判据（用户选定）。旧判据原文保留在该节末尾，作为历史记录。

### 细则 3.4 改后实跑一次

- **时机**：清理细则与测试细则的全部代码清理、改名、测试重构都合并完成后，跑且只跑一次（原话 5「你需要在改之后重新生成一次」）。
- **内容**：同一批局各生成一遍，与基线命令相同，只换代码版本（命令见第二部分 runbook）：
  - V9 `43 格 × 3 局 = 129`；
  - xhard0 `16 任务 × 1 档 × 3 局 = 48`。
- **地点**：GL A40，2 个占位席（V9、xhard0 各一席，1 A40／4 CPU／48G）。V9 约 37 分钟，xhard0 约 10 分钟。
- **两份代码**：
  - NFS 上的 `robomme_benchmark-noise` **保持在 `f8f76fba` 不动**，作为旧代码对照。
  - 改后代码另建一个 NFS 检出 `robomme_benchmark-maint`，切到合并后的 HEAD，不建 venv。运行时借用 noise 克隆的 `.venv`，加 `PYTHONPATH=<maint 检出>/src`（editable 指向的是 noise 克隆的 src，所以必须先打印 `robomme_hard.__file__`，确认指向 maint 检出）。前提是 `uv.lock` 零 diff，否则停下另报。
- **预算**（P3／P5，用户选定方案时一并授权，见第二部分预算表）：
  - 首跑 `43 格 × 3 局 + 16 任务 × 1 档 × 3 局 = 177` 条；
  - 第二次跑：每个出问题的局 2 条（改后 1 + 旧代码 1）。出问题的局不足 4 个时用陪跑局凑满（见下条），总数为 `2 × max(出问题局数, 4)`，上限 20 条。出问题的局超过 10 个就不进第二次，直接交用户；
  - 合计 197 条，reset 上限按每条 3 次计 `197 × 3 = 591`。
  - 冒烟：V9、xhard0 各 1 局，共 2 条、reset 6（AGENTS 第 4 条）。
  - 总上限 199 条、reset 597，用户 2026-10-03 已确认。
- **边生成边判定，只回传有问题的局**（用户 2026-10-03 原话：「现在每次都要回传Turbo的Data能否不用回传?直接现场计算计算完了有问题的再回传。」「是否可以每次一边生成一边计算SHA256。」「要生成完了统一计算就是async的去做。」——按「不要等生成完了统一算，要异步地边生成边算」理解）：
  - **sha 本来就是边生成边算的**：`hard_parity.py generate` 里的 `Mover` 是一个后台线程，每 5 秒扫一次各轮的 `results.partial.jsonl`。某一局一完成，它就在节点上算这局 h5 的 sha256，写一行 `identities.jsonl`，打印 `EPISODE_DONE … sha=<前 12 位>`。这时其他 worker 还在继续生成，所以已经是异步的。现在缺的只是「拿这个 sha 当场和参照比」这一步。
  - **新增 `generate --expect-ref <参照文件>`**（G 块）：`Mover.handle` 算完 sha 后立刻查参照里这一局的期望，在同一行 `identities.jsonl` 写入 `verdict`。
    - `match`：稳定局 sha 与基线相同，或确定性失败局失败且 sha 相同。直接删掉节点 `/tmp` 里的 h5 和 mp4，**不复制到 NFS**。这份字节本机和 HF 上都已经有了。
    - `jitter_info`：已知抖动局。照常复制到 NFS，供报告使用。
    - `flip`：期望不符，也包括稳定局生成失败。照常复制到 NFS 并核对 sha，同时追加一行到 `flips.jsonl`（格式可直接作为 `--identities` 使用），打印 `EPISODE_FLIP <tier>/<task>/<seed>`。
  - **当场就能看到**：Monitor 盯 `EPISODE_FLIP`，第一局翻转出现就会通知，不用等 37 分钟跑完。生成结束时，翻转清单已经现成，紧接着在同一席位上起第二次跑（改后代码与旧代码各一遍，只含翻转局），同样带 `--expect-ref`、边跑边判定。旧代码 `f8f76fba` 没有 `--expect-ref`，所以旧代码那一遍不带此参数，照常复制到 NFS（局数 ≤ 10，体量小）。
  - **生成本身一字不改**：仿真、worker、运行器都不动，只改生成后的搬运线程，所以被测的生成路径与基线相同。没给 `--expect-ref` 时，行为与现在完全一样。
  - **收尾判定很快**：`gen-regress check` 读 `identities.jsonl` 里已经写好的 sha 与 verdict 汇总出判定行，不重读 h5，在 GL 登录节点或占位作业里秒级完成。`noise_run.py ship --finalize` 相应改成认 `verdict=match` 的局「按设计不复制」，不算 missing。
  - **只回传翻转局**：`hard_pull.py --identities <flips.jsonl>` 只拉这些局（首跑和重跑的 h5、mp4），以及各遍的 `results.jsonl`、`identities.jsonl`、`summary.json`、来源报告。到本机后与 a 遍 h5 跑 `compare_h5`，区分「结构不同」和「走了另一条轨迹」，并给出分叉步。没有翻转时只拉报告，约几 MB。NFS 上本来就只有翻转局，判定落档后逐目录列名删除。
  - **不会漏判**：结构不同只需要对翻转局判。sha 相同的局与基线逐字节相同，结构必然相同。
- **第二次跑的 worker 与负载**（用户 2026-10-03「同意这个补法」）：
  - 沿用第一次跑的同一席位、同一节点，`--workers 4`；先跑改后代码那一遍，再跑旧代码那一遍。两遍不同时跑，避免 8 个进程挤在 4 个 CPU 上。
  - 每席 4 worker 是闸门前提：基线就是在每席 4 worker 下测的。RRT* 有 1 秒墙钟预算，同席位并发的 worker 数会改变每局能分到的算力，从而改变轨迹。
  - **陪跑局凑满并发**：出问题的局少于 4 个时，实际干活的 worker 会少于 4 个，CPU 负载比基线轻，可能把「噪声」和「回归」判反。因此从同一集合、同一档里，按身份顺序挑第一次跑已经与基线逐字节相同的稳定局补足 4 个；同档不够时从相邻档补。两遍（改后、旧代码）用同一组陪跑局。陪跑局的结果只报告、不判定：陪跑局再跑出与基线不同，只在报告里标注，作为这台节点当时负载状况的旁证。
  - 陪跑局计入第二次跑的 20 条上限，总预算不增加。
- **FAIL 时**：不改参照、不改判据。按翻转局所属任务定位到是哪块改动导致，回退或修好那一块后重跑。重跑预算另报。

### G／H 逐项清单

> 更正：下面凡提到在 `tests/lightweight/` 里加用例、或「阶段 6 由 T2 移到 `tests/parity/`」的，一律作废——G 块只改生产代码，对应测试由第二步的 T6 块写在 `tests/pipeline/parity/`。

清理细则的表格就是逐文件清单。以下为补充：

**G 块（新增 `gen-regress`）**——`scripts/parity/noise_gate.py`：
- `gen-regress build-ref --runs v9=artifacts/noise-baseline/gen/v9-a,artifacts/noise-baseline/gen/v9-b --runs xhard0=artifacts/noise-baseline/gen/x0-a,artifacts/noise-baseline/gen/x0-b --identities-v9 scripts/configs/gate-set-v9-129.json --identities-xhard0 scripts/configs/gate-set-xhard0-48.json --records docs/validation/noise-baseline-20261003/records/compare --out scripts/configs/noise-ref-20261003.json`
  - 每局写入 `{id, task, tier, seed, class: stable|known_fail|jitter, shas: [a, b] 去重, ok_a, ok_b, h5_a, h5_b}`，顶层写 `anchor=f8f76fba`、`hf_bucket`、剔除自身后的 canonical sha；
  - 交叉核对规则：记录里 `byte_equal` 的局，两遍 sha 必须相同；记录里有 `ref_sha256`／`new_sha256` 的，必须与重算值相同。不符即打印 `NOISE_REF=FAIL`；
  - 失败局的 sha 从 800 字节占位 h5 直接计算（记录里失败侧 sha 为 None）。
- `gen-regress check --ref scripts/configs/noise-ref-20261003.json --set {v9,xhard0} --new <新跑根> [--rerun <重跑根> ...] --out <jsonl> --rerun-identities-out <jsonl>`
  - 首跑时不给 `--rerun`。有翻转就输出 `GEN_REGRESS=NEED_RERUN flip=<n>`，并把翻转局写成 `hard_parity.py generate --identities` 可直接用的格式；
  - 翻转局不足 4 个时，`--rerun-identities-out` 自动按细则 3.4补陪跑局（行内 `filler=true`），判定只取非陪跑行；
  - 给 `--rerun-new <改后第二次根> --rerun-old <旧代码根>` 时，按细则 3.2四格定性，打印最终判定行，并输出逐局报告 `<out>.episodes.md`（细则 3.2「逐局报告」各列）；
  - 默认读各遍 `identities.jsonl` 里由 `Mover` 边生成边写的 sha 与 `verdict`（不重读 h5），在 GL 上秒级出判定行；翻转局类别先写 `flip_pending`；
  - `--local-ref-root artifacts/noise-baseline/gen`（只在本机给）：对已回传的翻转局复用 `compare_h5` 对照 a 遍 h5，把 `flip_pending` 细分为 `structural`／`diverge`／`gen_fail`；
- `scripts/parity/hard_pull.py` 加 `--identities <jsonl>`：只拉清单里的局目录与各遍顶层报告文件（不传时行为不变）。
- `scripts/parity/hard_parity.py`：`generate` 加 `--expect-ref`；`Mover.__init__` 载入参照，`Mover.handle` 在算出 sha 后写 `verdict`，`match` 时删本地大文件而不调 `_ship`，`flip` 时追加 `flips.jsonl` 并打印 `EPISODE_FLIP`；不给参数时代码路径不变。测试用假 `results.partial.jsonl` 与假 h5 覆盖 match／jitter_info／flip／失败局四种。
- `scripts/parity/noise_run.py ship --finalize`：`verdict=match` 的局不要求有 `SHIPPED`。
- 删除细则 2.5所列子命令与函数；`selftest` 同步删掉对应自检项。
- 测试：`tests/lightweight/test_noise_gate.py` 加合成夹具六情形，测试重构由独立计划T6提取有效契约到 `tests/parity/`；观察分类与因果证明分开。

**H 块（主会话）**：
- 一次性脚本放 scratchpad，生成三份清单；`SHA256SUMS` 的 h5／mp4 行由各局 `SHIPPED` 拼出，并核对 `SHIPPED` 里 h5 的 sha 与 `identities.jsonl` 一致。
- `hf buckets create` 建私有 bucket。参数先用 `/home/hongzefu/.local/bin/hf buckets create --help` 核实，并用绝对路径的 hf 1.8.0（venv 里的旧版没有 `buckets`）。
- 逐遍 `hf buckets sync artifacts/noise-baseline/gen/<遍> hf://buckets/HongzeFu/robomme-hard-v9-noise-baseline/<遍>`，三份清单用 `hf buckets cp`。
- 读回校验：在 GL 跑校验脚本 `<NFS>/hfverify/verify.py`（一次性脚本，不进仓库）。它用 `huggingface_hub` 列出 bucket 对象，逐个对象分块流式读取并算 sha256，与 `SHA256SUMS` 比对，末行打印 `HF_VERIFY=`。
  - 提交命令：`sbatch --account=chaijy2 --partition=standard --nodes=1 --ntasks-per-node=1 --cpus-per-task=4 --mem=8G --time=12:00:00 --job-name=noise-hfverify --output=<NFS>/hfverify/%x_%j.out --export=ALL <NFS>/hfverify/run.sh`；
  - 先提交只校验 1 个小对象的冒烟 job，再提交全量；
  - JobID 记入本会话清单；
  - 结束后把判定行拷进留档，并删除 NFS 上的 `hfverify/` 目录（逐个列名删除）。
- 对象数 = 1890 + 3 = 1893。

**主会话文档**：
- `docs/1003-noise-baseline.md` 第六节改成新闸门（10% 原文移到节末「历史判据」）；第七节比较命令改成 `gen-regress check`，`xhard0_manifest.json` 路径随 R 块更新；
- `1003-resource-cleanup-plan.md` 清理细则保留清单补一行（本次已补）。

## 四、子代理分配表

派发前核对：`worktree.baseRef="head"`；主检出 `git status --short --ignore-submodules=dirty -- . ':!docs/subagent-stats'` 为空；`git check-ignore -q .claude/worktrees/probe`；记 `BASE`；`git worktree list` 存档，阶段 0b 清理之后既有的 worktree 一律不动（R10）。由 Claude Code 执行（Q15），全部子代理 `model: "opus"`（含审查）。

**阶段 0b：清理 5 个旧 worktree（主会话，每条 git 单独执行）**。对象是 2026-10-03 另一会话按旧方案派出的子代理，登记如下；其中两个分支带未合并提交，按用户「清理」的裁决丢弃，sha 记在这里以便从 reflog 取回。

| worktree | 分支 | tip | 相对 `86e5a015` 的提交 |
|---|---|---|---|
| `.claude/worktrees/agent-a5b486d14a4879912` | `worktree-agent-a5b486d14a4879912` | `201e2ddb` | 1 个（`sub/TA`：官方包测试重组） |
| `.claude/worktrees/agent-a813d7ac8b643b1f5` | `worktree-agent-a813d7ac8b643b1f5` | `2eb14c07` | 1 个（`sub/TC`：契约与对拍测试搬目录） |
| `.claude/worktrees/agent-ab3e875d0581c5c95` | `worktree-agent-ab3e875d0581c5c95` | `86e5a015` | 0 |
| `.claude/worktrees/agent-ae0b2c65c02600987` | `worktree-agent-ae0b2c65c02600987` | `86e5a015` | 0 |
| `.claude/worktrees/agent-af004b519cb7413d0` | `worktree-agent-af004b519cb7413d0` | `86e5a015` | 0 |

步骤：①确认没有会话还在用它们（worktree 内无在跑进程；锁住的四个先看 `git worktree list --porcelain` 的 lock 原因），仍在用则停下交用户；②`git worktree list` 存档；③逐个 `git worktree unlock <路径>`（已锁的）→ 核对目录里没有实体产物（`artifacts/`、大文件）→ `git worktree remove <路径>`，有未跟踪文件时才加 `--force`；④三个零提交分支逐个 `git branch -d`；两个带 `sub/` 提交的分支逐个 `git branch -D`（丢弃依据 Q15，执行前再次核对 tip 与上表一致）；⑤`git worktree list` 删后对比，差集恰为这 5 个。

**第一步（清理，改生产代码；验收都在 worktree 内、CPU）**

| 编号 | 目标 | 可写集合 | 禁触 | 依赖／合并顺序 | 验收命令与判定 |
|---|---|---|---|---|---|
| G | 对拍工具 + 参照文件 + 噪声工具瘦身（含 F-5、F-7） | `scripts/parity/noise_gate.py`、`noise_run.py`、`noise_run_gl.sh`、`gate_set.py`（只 F-7）、`hard_pull.py`（加 `--identities`）、`hard_parity.py` 的 `Mover` 类与 `generate` 参数段（加 `--expect-ref`）、`scripts/configs/noise-ref-20261003.json`（新） | `artifacts/noise-baseline/`（只读）、他块文件、`tests/` | 1a 并行，第 1 个合并 | `python noise_gate.py --help`、`selftest` 通过；`gen-regress build-ref` 打印 `NOISE_REF=PASS …`（读主检出的基线目录，绝对路径只读） |
| W1 | `eval-official` 清理 | `scripts/eval-official/` 下细则 2.2、2.3 所列（不含改名） | 噪声工具、他块文件、`tests/` | 1a 并行 | 存活脚本逐个 `--help`／`bash -n`；`python -c` 按路径加载每个存活 `.py` |
| W2 | `injection-dev` 清理（含 `generate_h5.py` 的 `/2` 分支） | `scripts/injection-dev/` 下细则 2.2、2.3 所列 | 同上 | 1a 并行 | 同上；`v8_continue_after_gen.py --site-only --cells v9 --help` |
| F | 生产小修 F-1～F-4、F-8（Q12） | `scripts/parity/upstream_guard.py`、`train_split_parity.py`（只 `compare_h5_pair`）、`scripts/eval-official/v8_manifest.py`（只 `check_source`）、`v8_report.py`（只 `build_reuse`）、`run_seat.sh`（只轮询间隔） | 其余一切 | 1a，**等 W1 合入后派**（与 W1 共用三个 eval 文件，同一文件不并行写） | `upstream_guard.py check` 末行 `UPSTREAM_GUARD=PASS`；每项附一段最小复现脚本的前后输出 |
| W3 | `parity` 历史分支 | `scripts/parity/hard_regression.py`、`hard_parity.py` 中细则 2.3 所列分支 | `env-digest` 三件套、`delivery_index`、`generate --tier v9|xhard0`、噪声工具、`tests/` | 1b，等 G 合入 | 存活子命令逐个 `--help` |
| W4 | 包内 V7 清理（含 F-6） | `src/robomme_hard/` 中细则 2.2、2.3 所列 | 交付规格五份、`TIER_MAX_STEPS`、`tests/` | 1b，等 W1～W3 合入 | `python -c "import robomme_hard"`；五份规格 `load_specs_v8` 通过；`MAINT_SPECS=PASS changed=0` |
| R | 改名 | 细则 2.4 所列文件及全部引用点（噪声工具路径常量、`site/*` 的 importlib 字符串、`docs/1003-noise-baseline.md` 第七节路径） | 格式名、键名、判定行前缀、`tests/` | 1b，最后 | 全部存活脚本 `--help`；`MAINT_NO_LEGACY=PASS` |

**第二步（测试，只新建文件；验收 `pytest <自己的目录> -q`，worktree 内、CPU）**

| 编号 | 目标（责任域） | 可写集合 | 禁触 |
|---|---|---|---|
| T1 | 静态与上游、打包（C01 的 shim、C18） | `tests/static/` | 生产代码；其他测试目录；`tests/_support/`（只读，要改先报主会话） |
| T2 | hard 契约：常量、五份规格、800 局 builder、档位表、schema、身份集（C02～C04 的 hard 部分） | `tests/contract/`（契约清单总表除外） | 同上 |
| T3 | 官方包单元：builder、失败路径、终局判定、选择与投影、目标文本、16 任务原生三档真值表（C05～C07 原生部分） | `tests/unit/robomme/`、`tests/unit/common/` | 同上 |
| T4 | hard 包单元：按任务的离线场景与包内规格回放、新值档真值表、Swap 规划、纯函数模块（C04～C07 的 hard 部分） | `tests/unit/hard/` | 同上 |
| T5 | 录制与读回（C08～C11） | `tests/pipeline/recording/` | 同上 |
| T6 | 对拍与噪声工具（C15，含 `gen-regress`、参照文件、`Mover` → `ship` → `pull` 贯通） | `tests/pipeline/parity/` | 同上 |
| T7 | 生成与站点（C12、C16 的接续部分、C17） | `tests/pipeline/gen/`、`tests/pipeline/site/` | 同上 |
| T8 | 评估与挑战接口（C13、C14、C16 的席位脚本） | `tests/pipeline/eval/`、`tests/pipeline/challenge/` | 同上 |
| T9 | 仿真冒烟 | `tests/sim/` | 同上；worktree 内只 `--collect-only`（应收集到 `59 + 1` 条），不实跑 |
| 主会话 | 2a 公共框架与旧测试删除；2c 统一测、植入执行、覆盖率；1c 与 2c 的仿真实跑；3a、3b；文档 | `tests/_support/`、`tests/conftest.py`、`tests/fixtures/`、`tests/mutation/`、`tests/contract/benchmark_contracts.json`、`pyproject.toml` pytest 段、旧测试目录（删）、各 README、`AGENTS.md`、`docs/` | — |
| 审查 | 每块合并前一个，只读 | — | 一切写入 |

T1～T9 无先后依赖，合并顺序按完成先后；每块各自的具名植入定义放自己目录的 `mutants.json`，由主会话的执行器读取。共享文件裁决：`pyproject.toml`、契约清单总表、`tests/_support/**` 只归主会话；各块往总表加条目时交一份增量 JSON，由主会话合入。

## 五、闸门总表与植入清单

| 时点 | 判定行 |
|---|---|
| 每块合并前 | `PRE_MERGE_REVIEW=PASS`；`git diff --name-only <BASE>..<TIP>` ⊆ 可写集合 |
| 清理块合并后 | 冒烟；`UPSTREAM_GUARD=PASS`；`MAINT_SPECS=PASS`；`ls -1 scripts/*.py` 恰好四个；`POST_MERGE_REVIEW=PASS` |
| G 合并后 | `NOISE_REF=PASS` |
| 1b 末 | `MAINT_DEAD_BRANCH`、`MAINT_NO_LEGACY`、`MAINT_SCOPE` |
| 1c | `RESET_SNAPSHOT=PASS cells=59 same=59` |
| 测试块合并后 | 已合入的新测试目录全过；`UPSTREAM_GUARD=PASS` |
| 2c | `TEST_INVENTORY`、`TEST_CONTRACTS`、`TEST_CORE`、`TEST_SLOW`、`TEST_RESOURCE`、`TEST_TASKS_CPU`、`PARITY_VALIDITY`、`TEST_COLLECT`、`TEST_SIM`、`TEST_MUTATION`、`TEST_COVERAGE` |
| 3a | `NOISE_HF_UPLOAD=PASS`、`HF_VERIFY=PASS` |
| 3b | 冒烟 2 局通过 → 首跑 → `GEN_REGRESS=PASS`（v9、xhard0 各一行） |

`RESET_SNAPSHOT` 的比对字段：`joint`（5 位小数）、`task_goal`、`n_frames`、`obs` 各键形状与 dtype、`chain`、`info_keys`、`status` 必须相同；`frame_sha` 只报告相同格数（渲染是否逐位可复现未验证）。

植入清单（每项先确认原版在同环境通过，再确认指定断言因该语义错误失败；语法错误、导入失败不算抓到）：

| 编号 | 植入的错误 | 必须失败的责任域 |
|---|---|---|
| M01 | `src/robomme` 任一文件改 1 字节（进程内替换读到的字节） | C18 上游字节 |
| M02 | 上游入口 `evaluation.py` 加一行（同上） | C18 入口守卫 |
| M03 | hard 包 `RecordWrapper.py` 复制件 `fail_safe_limit` 改回 2000 | C18 复制件 diff 白名单 |
| M04 | 包内 `xhard1/specs.jsonl` 某正式行 seed 加 1（不重签） | C03 规格 sha 与签名 |
| M05 | 同一行重签后再改 `spec` 里一个取值 | C03 重签后的语义校验、C04 档位表 |
| M06 | candidate／attempt／seed 改成非整数并重算签名 | C03 类型校验 |
| M07 | `V9_CELLS` 某格 +1 | C03 常量与 800 局 |
| M08 | `TIER_MAX_STEPS["xhard1"]` 改 1500 | C03 常量、C13 身份契约 |
| M09 | `hard_builder._hard_env_kwargs` 丢掉 `native_episode_spec` | C02 builder 800 局、C04 冻结值消费 |
| M10 | 交换两个身份但总数不变 | C03、C13、C15 集合绑定 |
| M11 | 某任务成功次数提前一步；失败优先级反转 | C05、C06 |
| M12 | 阈值 `<` 与 `<=` 互换；before／after 互换 | C05、C07 |
| M13 | 删除跨局缓存清理或 policy reset | C09、C10、C13 的连续 A→B→A |
| M14 | 录制丢一个 h5 字段、改根属性、写入非有限动作 | C10、C11、C15 |
| M15 | `noise_gate.compare_h5` 跳过一个数据集；冻结文件清空；遗漏身份用重复行补齐 | C15 |
| M16 | `env_client` 把 timeout 记成 fail；普通失败按基础设施重试 | C13 |
| M17 | 报告分母改用结果行数；counts 缺项默认 0 | C12、C13 |
| M18 | 回写前中断后重复派发已完成身份 | C12 恢复幂等 |
| M19 | 挑战接口把含 `success` 字样的错误状态计成功 | C14 |
| M20 | 站点 HTTP 放行越界路径；Range 返回整个文件 | C17 |

## 六、预算（P3、P5）

| 项 | 乘式 | 轨迹 | reset 上限 |
|---|---|---|---|
| 冒烟（已确认） | V9 PickXtimes xhard1 seed 16100000 × 1 + xhard0 PickXtimes seed 510300 × 1 | 2 | 6 |
| 首跑 | V9 43 格 × 3 局 + xhard0 16 任务 × 1 档 × 3 局 | 129 + 48 = 177 | 531 |
| 第二次跑 | max(出问题局数, 4) 局（不足 4 局时用陪跑局凑满）×（改后 1 + 旧代码 1），合计上限 | ≤ 20 | ≤ 60 |
| 合计 | — | ≤ 199 | ≤ 597 |

基础设施重试默认 0（节点故障时另报）。翻转局超过 10 个时，不进入重跑，直接交用户（此时通过条件 2 已经不可能满足）。其余阶段 0 条。

仿真 reset（不生成轨迹，长期授权 Q8）：

| 项 | 乘式 | reset | 轨迹 |
|---|---|---|---|
| 清理前快照（已做） | 探针 1 任务 × 1 档 × 1 局 + xhard0 16 任务 × 1 局 + 43 格 × 1 局 | 1 + 59 = 60 | 0 |
| 1c 清理后快照对比 | xhard0 16 任务 × 1 局 + 43 格 × 1 局 | 59 | 0 |
| 2c 仿真冒烟 | 上一行 + 官方包 1 任务 × 1 局 | 59 + 1 = 60 | 0（另 1 步不可达 ee 动作） |
| 失败重跑上限 | 2 次 × 60 | ≤ 120 | 0 |

除上表与对拍预算外，其余阶段 0 次 reset、0 条轨迹。

## 七、runbook

测试命令（第二步完成后可用；其中资源守卫插件与 `--allow-sim-reset` 是拟新增接口）：

```bash
# 日常门禁
timeout 280s uv run --no-sync python -m pytest tests/static tests/contract tests/unit tests/pipeline -m 'not slow' -q --durations=20
# 慢测试（bash、ffmpeg、websocket、wheel、1024 全组合）
uv run --no-sync python -m pytest tests/static tests/contract tests/unit tests/pipeline -m 'slow' -q
# 仿真冒烟与清理后快照（先 nvidia-smi 选空闲卡）
CUDA_VISIBLE_DEVICES=1 uv run --no-sync python -m pytest tests/sim --allow-sim-reset -q
# 覆盖率（超过 5 分钟进 tmux，会话名前缀 tcov-）
COVERAGE_FILE=artifacts/test-coverage/.coverage uv run --no-sync --with coverage python -m coverage run --include='src/*,scripts/*,challenge_interface/*' -m pytest tests/static tests/contract tests/unit tests/pipeline -m 'not slow' -q -p no:cacheprovider
```

阶段 1c 在 `tests/sim/` 还不存在时，用清理前同一份扫描脚本重跑并比对（脚本随留档保存在 `docs/validation/test-redesign-20261003/records/reset_sweep.py`）。

对拍命令（逐字搬入）：

```bash
# 阶段 3a（本机，主会话）
H=/home/hongzefu/.local/bin/hf
$H buckets create --help        # 核实私有参数后再建
for p in v9-a v9-b x0-a x0-b; do  # 实际执行时每遍一条命令，日志 tee 到 artifacts/noise-baseline/hf/
  $H buckets sync artifacts/noise-baseline/gen/$p hf://buckets/HongzeFu/robomme-hard-v9-noise-baseline/$p
done
# 阶段 3b（GL；开工先占两席：1 A40／4 CPU／48G／48h，--gpu_cmode=shared，JobID 记入本会话清单）
# 两份代码（每条 git 单独执行）：<NOISE>=robomme_benchmark-noise 保持 f8f76fba 不动（旧代码对照）；
#   <MAINT>=NFS 新检出 robomme_benchmark-maint：git clone <本仓库 origin> <MAINT>；git -C <MAINT> checkout <合并后 HEAD sha>
#   改后代码一律用 <NOISE>/.venv/bin/python 加 PYTHONPATH=<MAINT>/src，先打印 robomme_hard.__file__ 确认以 <MAINT>/src/ 开头
# 下文 <克隆> 在改后代码的步骤里指 <MAINT>（解释器仍取 <NOISE>/.venv）
# 身份清单：uv run --no-sync python scripts/parity/gate_set.py export --set {v9,xhard0} --kind generate --out <文件>
# 生成：与 docs/1003-noise-baseline.md 第七节相同，--pass rg-v9 / rg-x0，--attempts 129／48，--resets 387／144，--retries 0
# 生成命令末尾加 --expect-ref <克隆>/scripts/configs/noise-ref-20261003.json，边生成边判定；Monitor 另盯 EPISODE_FLIP
# 生成结束、ship --finalize 之后汇总（GL，占位作业内辅助步骤，不带 --gpu_cmode=shared）：
srun --jobid=<占位作业> --overlap --ntasks=1 <克隆>/.venv/bin/python <克隆>/scripts/parity/noise_gate.py gen-regress check \
  --ref <克隆>/scripts/configs/noise-ref-20261003.json --set v9 --new <NFS>/gen/rg-v9 \
  --out <NFS>/regress/rg-v9.regress.jsonl --rerun-identities-out <NFS>/regress/rg-v9.rerun.jsonl
# 若 NEED_RERUN：rerun.jsonl（= flips.jsonl；不足 4 局时 gen-regress 按细则 3.4补陪跑局并标 filler=true）作 --identities，在同一席位、同一节点依次生成（--workers 4）
#   rg-v9-new2：改后代码（maint 检出，借 noise 克隆 .venv + PYTHONPATH=<maint>/src，带 --expect-ref）
#   rg-v9-old2：旧代码（noise 克隆 f8f76fba 原样，不带 --expect-ref）
# 再 gen-regress check … --rerun-new <NFS>/gen/rg-v9-new2 --rerun-old <NFS>/gen/rg-v9-old2 汇总
# 只回传翻转局（无翻转时只拉报告）：
uv run --no-sync python scripts/parity/hard_pull.py --stage <NFS>/gen --dest artifacts/maint-regress \
  --segments rg-v9,rg-v9-new2,rg-v9-old2 --identities <NFS>/regress/rg-v9.rerun.jsonl
# 本机细分翻转类别：gen-regress check … --new artifacts/maint-regress/rg-v9 --rerun-new … --rerun-old … --local-ref-root artifacts/noise-baseline/gen
# 收尾：按清单 scancel 自己的两个 JobID；判定行与 regress jsonl 拷进留档后，NFS 暂存逐目录列名删除（不跨运行 glob）
```

Monitor 过滤词：`EPISODE_FLIP|NOISE_RUN_START|EXIT_CODE=|RUN_FRESH=|BUDGET=|NO RECORD|reset 拒绝|svulkan2|EXCLUSIVE|RRT|Traceback|Error`，每份日志各挂一个。

## 八、风险登记

| 风险 | 应对 |
|---|---|
| 删分支后，V9 路径上有地方隐式依赖被删常量 | 审查子代理逐文件核对 + 合成测试 + 阶段 3b 实跑，三重兜底 |
| 改后代码在 GL 上换到新节点或新驱动，出现未见过的抖动 | 第二次跑同节点带旧代码对照，判为「环境变了」交用户；驱动与基线 595.71.05 不同时先报告用户再跑 |
| 噪声认定的翻转把真实小改动也放过（重跑恰好回到基线） | 改动造成的差异是确定性的，重跑回到基线说明改后代码仍能产出基线字节；放过的上限是 V9 2 局、xhard0 1 局，且逐局列出 |
| 参照文件被手改 | 顶层 canonical sha 防篡改；`test_noise_ref.py` 守三类计数 |
| HF 上传中断 | `hf buckets sync` 断点续传；以读回判定为准 |
| 改名让 `docs/validation/**` 的历史命令无法原样复现 | 用 `scripts/README.md` 的新旧名对照表说明 |
| `run-fresh` 与评估抽取耦合，删不干净 | G 块先核实；如有耦合，只改成认 gen 输出 |
| 清理与测试串行后，清理改坏评估或站点路径要到第二步才暴露 | 清理块的审查子代理逐文件核 V9 可达性；第二步出红时回到清理块修，修完重跑 1c |
| 新测试期望写错，把错误行为钉成契约 | 期望必须独立得出（R8）；审查子代理逐块核；植入验证证明断言对语义敏感 |
| 离线场景替身与真仿真行为漂移 | 仿真冒烟 59 格每格核 `spec_binding` 零差 |
| 钉了规格文件 sha 后，合法的规格更新要同步改钉值 | 钉值文件单独一份，更新规格的 commit 必须同时改它 |
| 门禁 120 s 目标达不到 | 2c 实测后把最慢用例降为 `slow`，不删断言；硬上限 280 s |
| `tests/sim/` 与他人评估进程抢卡 | 只在主会话串行跑，先看 `nvidia-smi`；实测约 3 分钟 |
| ffmpeg、第三方子模块缺失导致整域 skip | 条件项记「未验证」，不计 PASS；必验集合被 skip 即 FAIL |

## 九、盲区诚实清单

- 新闸门只覆盖 177 局，PASS 不等于 800 局逐字节等价。
- 稳定局的认定只基于两遍样本；某局真实抖动率很低时可能没被观察到，只能靠第二次跑兜底；第二次只跑 1 次改后代码，某局真实抖动率高于一半时可能被判成「每次都不同」而交用户，不会被误放过。
- 借用 noise 克隆 venv 跑改后代码依赖 `PYTHONPATH` 覆盖 editable 指向；起跑前打印 `__file__` 核实，不符即停。
- 评估侧不实跑，前提是 `--v8` 主路径不改；审查若发现必须改主路径，暂停并另报。
- `robomme-hard-parity` 的删除状态以并行会话为准，本计划不验证、不操作。
- 尚未开工的 Oracle 计划依赖 `env_client.py`／`run_seat.sh` 的非 v8 `--identities` 路线，本计划保留它；该计划引用的 `policy_replay.py::extract_defs` 删除后需从 git 历史取回。
- 仿真冒烟只 reset 不 step：环境的 step 逻辑、子目标推进、规划器、真实物理接触，在 CPU 上只有纯函数与替身驱动的部分被测；整局行为靠对拍的 177 局与已封存的 800 局交付，不靠 pytest。
- 清理是否改坏评估流水线、站点、挑战接口，没有独立参照（它们不经过生成也不在 reset 里），只靠审查与新测试。
- 行覆盖率不计子进程里执行的脚本；现状数字对靠子进程测的文件偏低，重测时进程内调用增多，上升里有一部分是口径效应。
- 六份盘点是静态阅读；F-2 是否真会失败未实跑；Q13 里的 PickHighlight 冲突是候选、未实证；SwingXtimes `too_many_swings`、StopCube xhard5 运行路径、`mani_skill` 在纯 CPU 下导入 wrapper 是否可行，实施时遇到再定。
- 除仿真冒烟（实测 162.6 s）外，测试耗时都是估计。
- 站点前端的真实浏览器交互不测（Q14）；xhard0 步数上限的取值不被任何测试钉住（Q16 待定）。
- 官方字节相同不能证明官方算法正确；全部植入被抓到也不是数学意义上的完全正确证明。能承诺的是：全部现行责任完成登记，CPU 可验证的关键契约有独立的正反例与边界证据，条件项、生产失败和未验证范围单列。

## 十、留档、commit 纪律与用户原话全表

- 每块合并提交按 `<大>.<小> <中文描述>` 递增，body 详写（第 11 条）；子代理提交用 `sub/<编号>: ` 前缀。
- 清理前实测留档：`docs/validation/test-redesign-20261003/`（行覆盖率、reset 快照）、`docs/validation/test-reconstruction-20261003/`（六个反例）。第二步的契约执行报告、植入结果、覆盖率追加到前者。
- HF 留档：`docs/validation/noise-baseline-20261003/hf.md`。对拍运行留档：`docs/validation/maintenance-regress-<日期>/README.md` + `records/`（regress jsonl、重跑身份、来源报告、预算账本）；h5 不进 git，闸门 PASS 后新跑的 h5 是否删除交用户决定。
- 自检：`grep -c '^# 第一部分\|^# 第二部分' 1003-code-test-maintenance-todo.md` 必须等于 2。

用户原话全表（2026-10-03，按时间）：

1. 「你这个项目只需要部署上限的问题和清理V7V8的就用例以及短测内容的问题就是纯代码的改动」
2. 「然后写的时候也分开写这三个点分别怎么改。然后如何保证噪声的一致性」
3. 「完全彻底重构这个计划只保留我说的这些部分。」
4. 「TMMAXTEP这个问题我没有看懂。然后这个清理B7V8指的是所有代码库里面全部清理了不要只清理测试然后核心短测内容怎么改我也没看懂就是你要详细的说可以彻底重构所有的test」
5. 「参考最新的noise baseline做好对拍的设置你不再需要生成两次了而是和之前的生成的结果做对拍。你看一下这个结果在HUGingFace上有没有如果没有的话需要上传你需要在改之后重新生成一次。还是这些episode然后和之前生成的做对比」
6. 「现在步数上线这个已经废弃了只负责全代码库清理测试的重构。」
7. 「给我你现在的噪声闸门我用户订的是10不一致你能不能订一个更加准确的闸门。」
8. 「现在的test是否完全覆盖了所有所有的内容就是你可以破坏性的对整个test进行修改我需要覆盖所有关键都是正确的。然后都尽可能不要跑GPU的任务如果有GPU任务就只做一个最简单的初始或者reset这样的 可以彻底重构这个test你可以派出SubAgent确定方案也可以实测然后再给我一个重构的计划我希望重构完的test能够覆盖这个benchmark的所有部分」
9. 「就是你可以结合现在的test作为蓝本根据你对于一个正确项目的test应该怎么设计的一个思想完全重新设计这个test。」
10. 「subagent全部opus」
11. 「你现在测试的reset我一并授权直接开始。」
12. 「仿真冒烟的长期 reset 授权 同意」「为什么不是并在一个计划里同时做完清理和重构然后再进行测试。」
13. 「旧测试完全放弃。不作为基准」
14. 「参考Codex的意见一起整合成一份计划。告诉我还有什么没有定下来。」
15. 「你把第一部分彻底重写一下现在太乱了」「所有的都改到这里面就是我要v7v8的清理再做test的重构然后最后做对拍」
16. 「改完了commit之后告诉我还有什么没定下来。」
17. 「1修 2 不改 3 bc 4 claude执行 清理 5待定 6不管」「先修改计划 不直接执行」
