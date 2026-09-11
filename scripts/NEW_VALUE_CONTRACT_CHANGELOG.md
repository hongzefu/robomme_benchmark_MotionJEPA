# 注入取值域约定 JSON：v1、v2 与 v3 的变化与用户决策

> **三份文件**：[configs/newtask-v2/injection_contract_v1.json](configs/newtask-v2/injection_contract_v1.json)（= 现状口径，`20260910-new-values-04` 就是按它冻结的）、[configs/newtask-v2/injection_contract_v2.json](configs/newtask-v2/injection_contract_v2.json)（= v1 + BinFill 对齐 heldout 三处，`20260911-contract-v2-05` 按它冻结）、[configs/newtask-v2/injection_contract_v3.json](configs/newtask-v2/injection_contract_v3.json)（= v2 + 三个 xhard 组，`20260911-contract-v3-06` 按它冻结；见第八节）。
> **一句话**：契约只管事件表的三列——事件叫什么、能取哪些值、怎么铺满 100 条；几何常量（按钮盒尺寸、孔板边长、锚点坐标、避让间距、`region_half_size`）仍只在 [configs/newtask-v2/native_sampling.json](configs/newtask-v2/native_sampling.json)。
> 链路代码在 [injection/](injection/)（2026-09-11 从 `tests/_shared/` 搬入，不依赖 `tests/`）；整体流程见 [NEW_VALUE_INJECTION_PIPELINE.md](NEW_VALUE_INJECTION_PIPELINE.md)。

## 一、为什么要这份 JSON

改之前，「每个字段能取什么、怎么分配」在四处各写一遍：生成器 `specs.py` 用 `itertools` 现算候选、补零类别表 `categories.py` 再算一遍、静态复核 `_static_problems` 第三遍、事件表 `event_tables.py` 的文案第四遍。事件表 125 行里只有 8 类行的「取值域」真正从配置算出（BinFill 三行 × 3 档、RouteStick `L`、VideoUnmaskSwap `n_swaps`／`n_picks`／`layout_type`、VideoRepick `n_swaps`），其余区间数字（按钮／孔板／方块区间、`[-30°, 30°]`、`0/2/4/6/8`、`[0, 180]`、偏移上限 `0.0425`、`1～256`）与**全部**「分配」列文案是硬编码。要把 BinFill 的两个区间和一条分配规则对齐 heldout，得同时改四处还不能漏。

用户 2026-09-11 决定：把现有 11 组的三列写成机器可读的 **约定 JSON v1**，修改后的 BinFill 计为 **v2**，「候选分布怎么产生」必须读这个 JSON 作为派生依据。

## 二、schema 速览

顶层：`contract_schema_version`（1）、`contract_version`（`v1`／`v2`）、`generator_seed`（20260909）、`group_size`（100）、`derives_from`（原值文件路径）、`derives_from_operands_sha256`、`excluded_groups`、`overrides`（有意偏离原值的白名单，v1 为空）、`groups`（11 个键 `"<任务>/<难度>"`，每组 `task`、`difficulty`、`初始化`[]、`事件`[]，**列表顺序就是事件表行序**，取代了原来手写的节归属表）。

字段五键：`key`（机器名）、`label`（事件表行名）、`domain`、`domain_text`（取值域列原文）、`allocation`、`allocation_text`（分配列原文）。

| `domain.kind` | 含义 | `allocation.kind` | 含义 |
|---|---|---|---|
| `int_range` | 闭区间，`closed: true`，`values == range(lo, hi+1)` | `quota` | 发牌：k 类各 floor/ceil(100/k)，再摊到 10 批 |
| `int_range_half_open` | 半开，`values == range(lo, high_exclusive)`（唯一用例 `VideoRepick.num_repeats`） | `stratify` | 分层：10 粗箱 × 10 细层；`resample` 只描述拒绝后怎么重抽 |
| `enum`／`permutations_of`／`combinations` | 有序机器值列表 `values`，顺序与生成器消费的 `itertools` 调用同式 | `balanced` | 合法候选内挑用得最少的 |
| `continuous` | `components: {分量: {lo, hi, unit, derivation}}` | `rng_ep` | 每条 episode 自己的随机流 |
| `constant` | 定值（bin=4 时的 `layout_type`） | `constant` | 不消费随机数 |
| `derived`／`coupled` | 推出量／受其他字段约束的量，`coupled` 可带 `rule`（BinFill `target_count`：`allow_zero` 或 `each_target_at_least_one`） | `derived` | 由其他字段确定性算出 |

`derivation` 三件套：`recipe`（`injection/contract.py::RECIPES` 白名单纯函数）、`inputs`（依赖键：无前缀 = `native_sampling.json` 路径如 `positions.BinFill.board.x_offset.subtract`，`const:` = 代码常量如 `const:cube_half_size`，嵌套字典 = 一层嵌套 recipe）、`expr`（人读字符串，不 eval）。两个片段：

```json
{ "key": "spawn_total", "label": "`spawn_total`（生成几块）",
  "domain": { "kind": "int_range", "closed": true, "lo": 8, "hi": 10, "values": [8, 9, 10],
              "derivation": { "recipe": "closed_int_range", "inputs": { "pair": "parameters.BinFill.configs.medium.spawn_cubes" },
                              "expr": "[pair[0] … pair[1]] 闭区间（torch.randint(lo, hi+1) 消费）" } },
  "domain_text": "8～10", "allocation": { "kind": "quota" }, "allocation_text": "配额" }
```

```json
{ "key": "board_pose", "label": "`board.xy`、`board.yaw_deg`（孔板）",
  "domain": { "kind": "continuous", "closed": "[]", "components": {
    "board_x":   { "lo": -0.05, "hi": 0.15, "unit": "m", "derivation": { "recipe": "base_minus_subtract_span", "inputs": { "base": "positions.BinFill.board.base_position[0]", "subtract": "positions.BinFill.board.x_offset.subtract", "scale": "positions.BinFill.board.x_offset.scale" }, "expr": "[base - subtract, base - subtract + scale]（x_expression 叠 base）" } },
    "board_y":   { "lo": -0.2,  "hi": 0.2,  "unit": "m", "derivation": { "recipe": "subtract_span", "inputs": { "subtract": "positions.BinFill.board.y_offset.subtract", "scale": "positions.BinFill.board.y_offset.scale" }, "expr": "[-subtract, -subtract + scale]；⚠ 不叠 base_position[1]，与 y_expression 一致" } },
    "board_yaw": { "lo": -20.0, "hi": 20.0, "unit": "deg", "derivation": { "recipe": "subtract_span", "inputs": { "subtract": "positions.BinFill.board.yaw_deg.subtract", "scale": "positions.BinFill.board.yaw_deg.scale" }, "expr": "[-subtract, -subtract + scale]" } } } },
  "domain_text": "x∈[-0.05,0.15] y∈[-0.2,0.2]，yaw∈[-20°,20°]", "allocation": { "kind": "stratify", "resample": "none" }, "allocation_text": "分层" }
```

⚠ 契约里的数值不是第二个权威源：`check` 的 `CONTRACT_DERIVED` 每次拿 `native_sampling.json` 按 `derivation` 回算比对（连续端点容差 `1e-12`）。想改这类数字，要么改 `native_sampling.json`，要么登记 `overrides`（需要用户拍板）；直接改契约里的数会被当场抓住。

## 三、v1 = 现状口径，怎么证明

v1 不是手写的：`uv run --no-sync python -m scripts.injection.contract_build build-v1` 用 `RECIPES` 从 `native_sampling.json` 现算全部数值域，离散域的 `values` 顺序与生成器此前的 `itertools.combinations(range(3), n)`、`permutations(INITIALIZE_COLOR_DEFS)`、`permutations(range(3), 2)`、`range(lo, hi+1)` 同式产出；`domain_text`／`allocation_text` 是原事件表两列的原文，搬进 builder 后事件表里的硬编码文案与 `BIN_HALF`、`SECTION_OF` 一并删除，builder 成为唯一来源。

| 证据 | 命令 | 实测 |
|---|---|---|
| 每个派生域等于原值回算 | `contract_build check --contract injection_contract_v1.json` | `CONTRACT_DERIVED=PASS fields=155 mismatches=0 overrides=0 problems=0` |
| 生成器改读契约后对 04 冻结规格逐位相同 | 11 组各 `build_group(…, v1, 20260909)` 对 `artifacts/injection/20260910-new-values-04/specs/` 逐条 `spec_sha256` | `V1_EQUIVALENCE=PASS compared=1100 differences=0`（日志 `artifacts/logs/stage-a-move/v1_equivalence.log`） |
| 事件表两列改取契约后文档零漂移 | `event_tables.py --run-id 20260910-new-values-04 --contract …_v1.json --check` | `EVENT_TABLES=PASS groups=11 rows=125 drift=0` |
| 搬迁后（代码从 `tests/_shared` 到 `scripts/injection`）对 04 全部判定不变 | `python -m scripts.injection.campaign check --run-id 20260910-new-values-04` | `SPEC_SCOPE`／`COVERAGE_QUOTA`／`STATIC_GEOMETRY`／`COLLISION_GEOMETRY`／`COLLISION_SWEEP min_g_m=0.00042638`／`SPEC_REPRODUCIBLE compared=1100 differences=0` 全 PASS，`CHECK=PASS elapsed_s=359.0` |
| 契约文件与 builder 现场重建逐字节相同 | `tests/lightweight/test_injection_contract.py` | 通过 |

## 四、v2 改了什么

依据：RoboMME 分支 `cvpr2026Challenge-heldOutSeed-4-5/4`，commit `2fa5660d8b78f31a6735538660d18a8e830bff63`（heldout seed v1）。与本仓库原值基线 `94449db` 相比，该分支 BinFill 只有难度区间与目标数分配规则两类实质差异；颜色数、目标色数、投入总数、方块避让 `min_gap = 0.02`、生成区域、重试 256 次、按钮与孔板范围逐字相同。它另有独立随机流 `task_generator`（`seed + 1003`）与 halton 联合放置，位置与数量由外部规格定死后与本链路无关，未移植。

| # | 组／字段 | v1（原值） | v2（heldout） | 源码锚点 |
|---|---|---|---|---|
| 1 | `BinFill/medium` `spawn_total` | `[8, 10]` | `[6, 8]` | `BinFill.config_medium['spawn_cubes'] = [6, 8]` |
| 2 | `BinFill/hard` `spawn_total` | `[10, 12]` | `[8, 10]` | `BinFill.config_hard['spawn_cubes'] = [8, 10]` |
| 3 | `BinFill/*` `target_count.rule` | `allow_zero`：多色时把总数逐个随机分给目标色，某色可为 0 | `each_target_at_least_one`：先每目标色各 1 块，余量再逐个随机分；单色不变 | `_load_scene` 多色分支 `for color_idx in active_color_indices: target_numbers[color_idx] += 1`，再分 `total_target - min_required_targets` |

前两条登记在 `overrides`（`CONTRACT_DERIVED` 回算会报 6 处不一致——两组各 `lo`／`hi`／`values`——全部被白名单覆盖）；第三条是 `coupled` 域的规则、没有派生表达式，另记在顶层 `target_count_rule_override`。v1 → v2 的文件差异恰好 21 处：两档 `spawn_total` 的 `lo`／`hi`／`values`／`domain_text`（8 处）、三档 `target_count` 的 `rule`／`note`／`domain_text`（9 处）、`contract_version`／`contract_note`／`overrides`／`target_count_rule_override`（4 处）。其余 9 组逐字相同。

事件表文案只变 5 行：`BinFill/medium` 与 `hard` 的 `spawn_total` 取值域（`8～10`→`6～8`、`10～12`→`8～10`），三档 `target_count` 的取值域（`投入数逐个随机分给目标色，允许 0` → `单色直接给总数；多目标色每色先各 1，余量逐个随机分（heldout 规则，不允许 0）`）。⚠ `BinFill/easy` 文案变但规格逐位不变——easy 恒为单色，规则不起作用。

影响面（05 对 04）：`BinFill/medium`、`hard` 两组规格全变——多色时目标数分配少了「目标色数」次 `rng_ep.integers` 调用，之后的余量分配、生成序打乱、每块方块的落位尝试全部错位，位置也随之不同，这是预期结果；`BinFill/easy` 与其余 8 组 100 条 `spec_sha256` 逐条相同。脚注：heldout 多色分支抽的是 `randint(max(put_in_numbers[0], 目标色数), put_in_numbers[1] + 1)`，三档配置下 `max(...)` 恒等于 `put_in_numbers[0]`（medium 2 对 ≤2、hard 3 对 2～3），所以 `put_in_total` 的取值域不变；生成器里留了一道硬闸，总数少于目标色数时报缺口而不是静默。

05 的实测数字（规格、静态检查、拒绝数、目标数分布前后对比）见 [NEW_VALUE_INJECTION_TEST_PLAN.md](../NEW_VALUE_INJECTION_TEST_PLAN.md) 第 5.9.4 节与 [injection-before-2d/NEW_VALUE_DISTRIBUTION_BEFORE.md](injection-before-2d/NEW_VALUE_DISTRIBUTION_BEFORE.md)。

## 五、用户决策原话（逐字）

> 能否改为对齐heldout

> 按照这个方案改 把现有的…写作为json约定 v1 修改后的binfill计为v2 候选分布怎么产生 需要读取这个json配置作为派生的依据 并且在scripts/增加一个md 写json的变化和用户决策

> injection_contract_v1.json / _v2.json native_sampling.json这些加入git追踪 关键小产物都加入git

> 对应的候选分布产生，生成h5，对拍，出图都不要放在test内 不要依赖test 全部放在 …/scripts

追问答复：契约只写三列、几何仍读 `native_sampling.json`；v2 包含「区间 + 每色至少 1 块」；本轮重冻结并重写分布文档；v1／v2 两个文件。据此：04 原样保留作 v1 对照；两轮的 `specs/`、`manifest.json`、`plan_stats.json`、`check_result.json` 入库（`.gitignore` 对 `artifacts/injection/*/` 做反选，01～03 开发迭代目录继续忽略）。

## 六、怎么核对

```bash
# 离线：契约对原值回算（v1 期望 overrides=0，v2 期望 overrides=2、problems=0）
uv run --no-sync python -m scripts.injection.contract_build check --contract scripts/configs/newtask-v2/injection_contract_v2.json
# 在线：某次冻结的完整静态检查（契约按清单 contract_path / contract_sha256 加载，散列不符直接拒绝）
uv run --no-sync python -m scripts.injection.campaign check --run-id 20260911-contract-v2-05
# 单测
uv run --no-sync python -m pytest tests/lightweight/test_injection_contract.py tests/lightweight/test_scripts_do_not_import_tests.py -q
```

判定行 `CONTRACT_DERIVED=PASS fields=<n> mismatches=<n> overrides=<n> version=<v> problems=0`：`fields` 是参与回算的域／分量数，`mismatches` 是回算不一致数（必须全部在 `overrides` 内），`problems` 是未登记的漂移与陈旧登记之和，非 0 即 FAIL。

## 七、不改什么

- `native_sampling.json` 一个字节不动：`parameters`／`positions` 的形状与数值都不动（`generate_dataset_newseed.py::load_sampling_config` 的严格形状校验照旧通过），仿真运行时仍只读它。
- `src/robomme` 与 `scripts/generate_dataset_newseed.py` 不动：规格已定死，任务在原创建点消费规格里的**结果**（`spawn_count`／`target_count`），不消费区间。
- 规格文档（`specs/<任务>/<难度>.json`）顶层不加字段：契约身份只写 `manifest.json`。
- `operand_sha256` 口径不动：契约散列另起 `contract_sha256`，04 的清单仍可复核。
- `_static_problems` 继续直连 `native_sampling.json`，作为不经过契约的独立几何校验链；`bin_half` 的公式在那里保留一份内联。
- 04 运行目录只读，不写任何新文件。

## 八、v3 = v2 + 三个 xhard 组（2026-09-11）

依据：用户决定给三个任务加第四档 `xhard`，计划见 [../XHARD_DIFFICULTY_PLAN.md](../XHARD_DIFFICULTY_PLAN.md)。

**用户决策原话（逐字）**：

> 给出方案 给videorepick和videpunmaskswap加入swap 4-5次 作为xhard难度模式
>
> 其他和videorepick medium videpunmaskswap hard保持一致
>
> 给routestick增加xhard模式 和hard保持一致 但是走的段数增加8-10

追问三选一答复：RouteStick 段数「落在 8～10」；第 4、5 次 swap 的发起者「循环沿用 3 个发起者」；「契约 v3 + 新 run 只跑 3 个 xhard 组」。

### 8.1 改了什么

| # | 组 | 取值域 | 来源 |
|---|---|---|---|
| 1 | `RouteStick/xhard` | `L` = `[8, 9, 10]`（配额 34/33/33），`edge.backtrack = true`，其余与 hard 逐字同式 | `RouteStick.config_xhard = {'length': [8, 10], 'backtrack': True}` |
| 2 | `VideoUnmaskSwap/xhard` | `n_swaps` = `[4, 5]`（配额 50/50），`n_picks` = `[2]`，`layout_type` 常量 region4，其余与 hard 同式 | `VideoUnmaskSwap.config_xhard = {"bin": 4, "swap_min": 4, "swap_max": 5, "pick_min": 2, "pick_max": 2}` |
| 3 | `VideoRepick/xhard` | `n_swaps` = `[4, 5]`（配额 50/50），`tail`／`target`／`layout_type` 与 medium 同式 | `VideoRepick.config_xhard = {"cube": 3, "swap_min": 4, "swap_max": 5}` |

两个视频组的 `swap_pairs` 域文案加一句「第 k 次发起者 = swap_initiators[k mod 3]（4～5 次时循环沿用 3 个发起者）」；三档文案逐字不变。**没有新 recipe、没有新字段、没有新 override**：`overrides` 与 `target_count_rule_override` 原样继承 v2。顶层多两个键：`contract_version = "v3"`、`added_groups_v3`。

**发起者循环规则**：源码只有 3 个发起者槽位（`swap_pair1/2/3_idx1`），对象数不变（Repick 3 块、Unmask 4 个容器）时 4～5 次 swap 必须重复发起者。约定第 k 次（k 从 0 起）发起者 = 循环基 `swap_initiators[k mod 3]`，即 a、b、c、a、b——相邻两次发起者必不同，不会出现「同一块自己换回去」。规格 `objects.swap_initiators` 仍存 3 个循环基，`actions.swap_pairs` 存实际 n 段（搭档仍按每段起始时的水平最近邻逐段模拟）。`campaign check` 的 `STATIC_GEOMETRY` 新增此项校验，对旧 11 组恒成立。

### 8.2 取值域散列改为按难度作用域

源码加了 `config_xhard`、`native_sampling.json` 多了 `configs.xhard` 之后，全量 `operand_sha256` 必变，会让 04／05 的 `check` 一开头就以「依据漂移」拒绝、v1／v2 契约的逐字节测试变红。`specs.py::operand_sha256(sampling, difficulties)` 改为只保留本契约／本清单消费到的难度键（`positions` 不动）：

| 场景 | 作用域 | 散列 |
|---|---|---|
| v1／v2 契约、04／05 清单复检 | `{easy, medium, hard}` | `124e49f8…`（与冻结值逐位相同） |
| v3 契约、06 清单 | `{easy, medium, hard, xhard}` | `97c9af660ca5…` |

与该函数既有 docstring 的立论一致：「纯源码改动不该把已冻结规格判成依据漂移」。⚠ 与之配套：`generate_dataset_newseed.py::SAMPLING_OPERAND_PATHS` 里三任务的 `configs` 从整块改为按 `.easy/.medium/.hard` 三条，固定基线 `94449db` 只担保原三档；`native_sampling.json` 与 `src/robomme` 必须同版本——旧快照配新源码会在 `load_sampling_config` 报「缺少字段 ['xhard']」。

### 8.3 怎么证明旧的没变

| 证据 | 命令 | 实测 |
|---|---|---|
| v1／v2 文件零字节改动 | `git diff --quiet -- injection_contract_v1.json injection_contract_v2.json` | 通过 |
| v3 只追加三组 | `tests/lightweight/test_operand_scope.py`（v2→v3 同名 11 组逐字相同、`added_groups_v3` 三组、builder 逐字节重建） | 通过 |
| v3 回算 | `contract_build check --contract injection_contract_v3.json` | `CONTRACT_DERIVED=PASS fields=200 mismatches=6 overrides=2 problems=0`（6 处不一致全是 v2 登记的 BinFill 覆盖项） |
| 05 在新代码、新快照下仍可验收 | `campaign check --run-id 20260911-contract-v2-05` | `CHECK=PASS elapsed_s=357.3` |
| 06 的旧 11 组规格与 05 逐条相同 | `campaign specs-diff --left 20260911-contract-v2-05 --right 20260911-contract-v3-06` | `OLD_GROUPS_EQUIVALENCE=PASS compared=1100 differences=0 shared_groups=11` |
| 三档仿真产物逐位不变 | 用 05 规格四任务各跑 1 条，`campaign compare … --subset-only` | `OLD_TIER_PARITY=PASS compared=4 differences=0` |

06 冻结：`PLAN=OK groups=14 specs=1400 elapsed_s=340.0`；xhard 组候选用量 `plan_stats.json`：RouteStick 0、VideoUnmaskSwap 最多 4、VideoRepick 最多 39（medium 是 33），`MAX_CANDIDATES=256` 远未耗尽；两个视频 xhard 组 100 条的 `min_g_m` 分别 0.00014／0.00419。

### 8.4 复现命令

```bash
uv run --no-sync python -m scripts.injection.contract_build build-v3 --base scripts/configs/newtask-v2/injection_contract_v2.json --out scripts/configs/newtask-v2/injection_contract_v3.json
uv run --no-sync python -m scripts.injection.contract_build check --contract scripts/configs/newtask-v2/injection_contract_v3.json
uv run --no-sync python -m scripts.injection.campaign plan  --run-id 20260911-contract-v3-06 --contract scripts/configs/newtask-v2/injection_contract_v3.json
uv run --no-sync python -m scripts.injection.campaign check --run-id 20260911-contract-v3-06
uv run --no-sync python -m scripts.injection.campaign specs-diff --left 20260911-contract-v2-05 --right 20260911-contract-v3-06
```
