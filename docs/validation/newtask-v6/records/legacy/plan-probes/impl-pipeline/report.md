# V6 S1 难度档管道改造：实施报告（副本 worktree 草稿）

> 2026-09-25。副本 `/data/hongzefu/v6-draft/pipeline`，分支 `v6-draft-pipeline`（由 `e1755f9` 切出），commit **`891180f`**
> `12.139-draft-pipeline …`，没有 push（这个分支没有 upstream）。主仓库源码没有改动，本报告放在主仓库 artifacts 下，已被 gitignore。
> 分工：共用件与 scripts 由主 agent 改；16 个环境文件分 8 组交给 opus subagent 并行改，主 agent 负责合并和复核。

## 〇、结论

- 管道现在认 `xhard1 < xhard2 < xhard3 < xhard` 这个新值族。业务分支里 `== "xhard"` 的字面判断已清零，全部改成族判断：
  - 用 `is_newvalue_difficulty()` 判断是否属于新值族；
  - 用 `decision[self.difficulty]` 取本档的数值子树。
- 13 个有梯度的环境各加了 `config_xhard1/2/3` 和同结构的 decision 子树，数值按计划 2.3～2.12 填入。
- StopCube / MoveCube / InsertPeg 不加档，传入新档名会抛 `ValueError`。
- 原三档与 xhard 的 reset 取值与主仓库逐字相同：16 环境 × 4 档 × 2 个 seed，共 128 局，spec 全文与全部 actor 位姿的 sha 都一致。
- V0：`NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0`。
- LIGHTWEIGHT：失败集合与主仓库基线（46 failed / 12 errors）完全相同。

## 一、改了哪些文件和符号

### 共用件（`src/robomme/robomme_env/utils/`）

| 文件 | 符号 | 改动 |
|---|---|---|
| difficulty.py | `NATIVE_DIFFICULTIES`、`NEWVALUE_DIFFICULTIES`、`VALID_DIFFICULTIES`、`is_newvalue_difficulty`、`newvalue_tier`、`NO_TIER_ENVS`、`require_xhard_only` | 七档白名单；族判断；档位号 xhard1=1 … xhard=4；不加档的环境收到新档名时明确报错 |
| sampling_config.py | `NEWVALUE_KEYS`、`V6_ADDED_KEYS`、`_strip_xhard`、`_xhard_shape`、`assert_native_decision`、`fill_missing_newvalue`（新增） | 见下方说明 |
| episode_spec.py | `spec_kind_for` | 改为族判断，新值族四档都是 `native-newvalue/1` |
| task_goal.py | `_unmask_pick_count` | 族判断。直接判断档名是否在四档之内，不用相对导入，因为单测会按文件单独加载这个模块 |
| xhard_home_site.py | `validate_demo_plan`、`NO_RETURN`、`RETURN_LAST_ONLY`、`NEWVALUE_RETURN_POLICIES` | 族判断；新值族放行三种策略。`return_last_only` 只放行名字，标了 TODO S2 |
| unmask_swap_xhard.py | 外环入口 | 按 `decision[env.difficulty]` 取子树 |
| unmask_distractors.py | — | 只改了注释 |

sampling_config.py 的三处改法：
- **剥离**：`_strip_xhard` 一次剥掉四个新值键。
- **结构核对**：按档核对。快照里出现的档，键结构必须与源码申报一致；没出现的档不核对，所以 V5 快照照样放行。
- **补齐**：`fill_missing_newvalue` 只在同一层已经有 xhard 时才补 xhard1/2/3。V4 以前的快照连 xhard 都没有，一律不补，行为与 V5 逐字相同。

### 环境文件（16 个）

每个环境的新档都沿用 xhard 的生成机制，只改数值。实际填入的值：

| 环境 | xhard1 | xhard2 | xhard3 | 说明 |
|---|---|---|---|---|
| PickXtimes | 次数 [5,7]，干扰 1 | [6,9]，2 | [7,12]，3 | 干扰色取 `DISTRACTOR_COLORS` 的前 k 个 |
| SwingXtimes | 轮数 [3,4]，干扰 1 | [4,6]，2 | [5,8]，3 | 同上 |
| BinFill | 总块 12，投入 [4,5] | [4,6] | [5,6] | native.put_in_color 也加了新档兜底 |
| PickHighlight | pick [4,4]，spawn [7,7] | [4,5] / [8,8] | [5,6] / [8,9] | 保留 spawn_lo ≥ pick_hi 断言 |
| PatternLock | 节点 [9,12] | [13,17] | [18,22] | 搜索预算 20000，耗尽抛错 |
| RouteStick | L [8,10] | [11,12] | [13,14] | 新值族缺键抛错；原三档静默回退 easy 的行为原样保留 |
| VideoUnmask | 8 / pick 2 / 干扰 8 / 含 cube [4,4] | 8 / 3 / 10 / [5,5] | 8 / 3 / 13 / [6,7] | 环带等其余字段沿用 xhard |
| ButtonUnmask | 8 / 2 / 7 / [3,4] | 8 / 3 / 9 / [4,5] | 8 / 3 / 12 / [6,6] | 同上 |
| VideoUnmaskSwap | swap [4,5] / pick 2 / 外环 4（含 cube [2,2]）/ 50 步 | [5,7] / 3 / 6（[3,3]）/ 33 步 | [7,9] / 3 / 8（[4,4]）/ 33 步 | 含 cube 数由实施方自定，取一半；`parameters.configs` 缺新档时补齐 |
| ButtonUnmaskSwap | swap [3,4]，其余同 VUS | [4,5] | [5,6] | native.bin_count 缺新档时补齐 |
| VideoRepick | 块 4 / swap [3,5] / repick [2,3] | 5 / [5,7] / [3,4] | 6 / [6,9] / [4,5] | 族判断放在 hard 聚簇分支之前；repick 在代码里写成半开区间 high=hi+1 |
| VideoPlaceButton | (k1, return_to_origin) | (k2, no_return) | (k2, no_return) 占位，并加 `TODO(V6 S2)` 注释 | native.color 缺新档时补齐 |
| VideoPlaceOrder | (k1, v[2,4], 放回) | (k2, v[2,3], no_return) | (k2, v[2,4], no_return) | v 区间放在源码常量 `NEWVALUE_VISIT_COUNT_RANGE` 里 |
| StopCube / MoveCube / InsertPeg | 不加档，`require_xhard_only` 会拒绝 | — | — | 其余字面改为族判断 + `decision[self.difficulty]`；StopCube 的 xhard 旧快照兜底保持原写法 |

### scripts（没有新增顶层文件，`scripts/*.py` 仍是 5 个）

- **`parity/v4_specs.py`**：
  - 新增 `NEWVALUE_TIERS`、`V6_SEED_OFFSETS`、`seed_rule_for()`、`_known_seed_rule()`。
  - draw 新增 `--difficulty`（默认 xhard）和 `--seed-profile {v5,v6}`（默认 v5，只许 xhard）。
  - 默认参数下 header 和行与 V5 逐字节相同。
  - v6 档位的 seed 偏移：xhard 6e6、xhard1 8e6、xhard2 10e6、xhard3 12e6。
  - freeze 和 validate 一律按 header 里的档位与 seed 规则核验。
- **`parity/train_split_runner.py`**：jobs 可以带 `seed_rule`，按档核验身份；不带时与原来一样。
- **`parity/v4_rollout.py`**：档位和 seed 规则从 header 取；用 V5 快照时生成的 jobs 与原来相同。
- **`parity/v5_generation.py`**：pipeline 新增 `--difficulty` 和 `--seed-profile`；取非默认值时按档分目录，落点为 `…/<run_id>/<tier>/…`。
- **`parity/train_split_config.py`**：`RELEASE_NOTES` 加了 `newtask-v6`。
- **`scripts/eval/v4_eval.py`**：没有改。每行的 difficulty 直接取自快照，已经兼容新档（只读兼容）。
- 冻结文件不受影响：RecordWrapper.py 和 evaluation.py 对 `e1755f9` 的 `git diff` 为空。

## 二、剩余的 `"xhard"` 字面（src 从 130 处降到 40 处）

业务分支里的 `== / != "xhard"` 为 0。剩下的 40 处都属于下面几类：
1. **档位表和 decision 子树键的定义**：各环境的 `NEWVALUE_*["xhard"]`，以及 `_native_decision` 里原样保留的 `"xhard": …`，覆盖 PickXtimes、SwingXtimes、PH、PL、RS、VU、BU、VUS、BUS、VPB、VPO、StopCube、MoveCube、InsertPeg。
2. **`configs` 字典里的 `"xhard": config_xhard`**：InsertPeg、MoveCube 用的是双引号，其余环境是单引号，grep 不到。
3. **VUS 的 `NATIVE_SAMPLING.parameters.xhard`**：这是固定键名，受全等铁闸锁定，NATIVE_SAMPLING 又不许改，所以保留，共 4 处。
4. **族成员常量**：`difficulty.py` 的 `NEWVALUE_DIFFICULTIES`，`task_goal.py` 的四档成员元组，`sampling_config.XHARD_KEY`。
5. **docstring**：InsertPeg 和 MoveCube 各一行。

## 三、测试

- **lightweight**（`-m 'not gpu and not slow'`）：
  - 78 个文件分 3 组并行跑，每组 ≤ 3 分钟：174 s、70 s、48 s。
  - 结果：48 failed / 12 errors，与主仓库基线的失败集合逐条相同，没有新增，也没有消失。基线是 46 failed / 12 errors，整跑 372 s。
  - 先前多出的 2 条 `test_real_swap_resolution_matches_baseline_and_preserves_ties[*-VideoRepick]`，原因是 exec 命名空间里缺 `is_newvalue_difficulty`，补上后已恢复。
- **新增 `test_v6_difficulty_tiers.py`**，覆盖：
  - 族判断与档位号；
  - 守卫按档核对结构；
  - V5 快照补齐与 V4 以前快照不补；
  - v4_specs 默认参数与 V5 字节一致；
  - v6 各档 seed 区段互不重叠；
  - draw 行带上档位与规则。
- **`test_sampling_config_split::test_snapshot_matches_source`**：改为「源码提取 → 剥掉 xhard1/2/3 → 与 V5 快照逐字相同」，这就是 V0 加上 xhard 不变的离线核验。V6 快照的导出留给 S4。
- **V0 静态核对**：在主仓库和副本两边分别导出 16 环境的 `config_easy/medium/hard/xhard`、`NATIVE_SAMPLING`，以及剥掉新档后的 decision，逐字相同。BinFill、BUS、VPB、VPO 的 native 只多出新档键。结论：`NATIVE_DEFS_UNCHANGED=PASS envs=16 changed_keys=0`。

## 四、冒烟结果（本机 GPU，obs_mode=state，seed 6000123 / 6000456；表中两个值分别对应这两个 seed）

判定方法：
- 原四档：spec 全文 sha 和全部 actor 位姿 sha 都与主仓库同 seed、同脚本的 reset 逐字相同，记为「同」。
- 新档：`ok`、`spec_kind=native-newvalue/1`、`env_difficulty` 等于档名三条都满足，记为「ok」。

| 环境 | easy | medium | hard | xhard | xhard1 | xhard2 | xhard3 |
|---|---|---|---|---|---|---|---|
| BinFill | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| ButtonUnmask | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| ButtonUnmaskSwap | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| InsertPeg | 同/同 | 同/同 | 同/同 | 同/同 | ValueError ×2 | ValueError ×2 | ValueError ×2 |
| MoveCube | 同/同 | 同/同 | 同/同 | 同/同 | ValueError ×2 | ValueError ×2 | ValueError ×2 |
| PatternLock | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| PickHighlight | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| PickXtimes | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| RouteStick | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| StopCube | 同/同 | 同/同 | 同/同 | 同/同 | ValueError ×2 | ValueError ×2 | ValueError ×2 |
| SwingXtimes | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| VideoPlaceButton | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| VideoPlaceOrder | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| VideoRepick | 同/同 | 同/同 | 同/同 | 同/同 | SceneGen/ok（换 6000125 ok） | SceneGen/ok（换 6000125 ok） | ok/ok |
| VideoUnmask | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |
| VideoUnmaskSwap | 同/同 | 同/同 | 同/同 | 同/同 | ok/ok | ok/ok | ok/ok |

- **xhard 逐位复现**：两个 seed 下 16 个环境全部相同，这是 X0 在 reset 层面的核验；h5 层面的 X0 留给 S5。
- **数值落地的实测**（抽查新档实例的属性）：
  - VUS/BUS 的「交换次数 / pick / 每段步数 / 外环干扰 / 外环交换对数」与表一致，外环对数等于交换次数；
  - VU/BU 内环 8 个，干扰容器全部落在环带内；
  - PH 与 PickXtimes/Swing 的 actor 数与块数对得上。
- 冒烟用的脚本和产物都在会话 scratchpad `s1/` 下：`smoke.py`、`ref_main.jsonl`、`final_all.jsonl`、`v0_dump.py`、`v0_cmp.py`。

## 五、与计划不一致的发现（需要用户或后续步骤处置）

1. **VideoRepick 新档的 reset 成功率低于计划的估计**：
   - 30 个 seed 实测：xhard1 19/30、xhard2 17/30、xhard3 18/30、xhard 18/30。计划 2.5 写的是 ≈0.9 / ≈0.75 / 0.59 / 0.59。
   - 块数少时，每个发起者只有「最近 3 个」候选，靠近按钮或孤立的块更容易一个可行搭档都没有。
   - 计划的数值多半是按 S5（全部可行对）估的，S5 属于 S2。建议 S2 落地 S5 后复测；也可以在 S3 的抽签上限里预留余量。
2. **VP 的 no_return 语义有副作用**（按简报做的最小实现：不建落点，方块停在最后访问的台上）：
   - 执行段的 after 问题，答案台可能正是方块停着的台，题目变容易。VPB 约 50% 的局是 after；VPO 约 40% 的局答案台就是答案方块自己停的台。
   - swap 会把目标台从方块底下瞬移走。
   - VPO 执行段约 10% 的局，答案台被另一个方块占着。
   - VPO 的演示段加了「后一块避开前一块停留的台」约束，xhard3 第二块的 v 实际上界因此是 3，演示放置次数期望约 5.5，低于计划的 6（仍高于 xhard2 的 5）。
   - 需要用户决定：接受现状，还是改成「各自放到不同的 goal_site」或重新定义「不放回」。
   - VPB xhard3 的 `return_last_only` 目前用 (k2, no_return) 占位，演示放置次数是 4，不是计划的 5，S2 实现后会变。
3. **VPO 的 v 区间没有放进 decision**：往 xhard 子树加键会让 V5 快照过不了按档的结构核对，所以放在源码常量里，代价是不能通过 sampling_config 覆盖。
4. **同 seed 下新档布局与 xhard 高度重合**：例如 PickXtimes/Swing 的 xhard3 与 xhard 的 pose_sha 相同，因为只有次数不同。V6 按档用独立的 seed 区段（6e6/8e6/10e6/12e6），可以避开。
5. **协调方补充的两处都已处置**：
   - ① VUS 的次数实际读 `native.parameters.configs[档]`：快照里缺这个键时 setdefault 取类属性；显式给出但缺新档时按类属性补齐。已在类属性 `config_xhard1/2/3` 里挂好，实测数值生效。decision 的 `swap_count_range` / `pick_count_range` 在 VUS 上本来就没有代码读，这是 V5 的现状，没有改。
   - ② `validate_demo_plan` 已改为族判断，并按档放行 `return_to_origin` / `no_return` / `return_last_only`，不再写死 xhard。
6. **`fill_missing_newvalue` 的语义与简报不同**：简报原来要求「无条件补」。实施中定为「只在同一层已有 xhard 时补 xhard1/2/3」，理由是保持 V5 口径 13：V4 以前的快照在新值档上照旧报错。StopCube 自己的 xhard 兜底保持原写法。
7. **其他小项**：
   - VUS/BUS 外环的「含 cube 数」计划没有给，实施方取 xhard「10 个里含 5 个」的一半：[2,2] / [3,3] / [4,4]。
   - 归因标签 `unmask_swap_xhard` 里的 `"xhard.distractor_swap.initiator_rule"` 仍然写死 xhard。它只是标签，不影响取值。
   - VR 新档报错文案的前缀仍然是「xhard:」。

## 六、未完成项

- 计划 2.0 表里的测试 `test_episode_action_sampling` 参数化没有扩到 7 档：这个文件有 20 条基线失败，扩了意义不大，留到 S4。
- `scripts/README.md` 没有更新（S7）。
- V6 快照 `scripts/configs/newtask-v6/sampling_config.json` 没有导出（S4）。
- V1（144 条 h5）、X0 的 h5 层面、TIER_MONOTONE 都没有做（S3/S5）。
- S2 的内容本步都不涉及：S5 均匀化、M5、MoveCube 统一区域 U、VPB `return_last_only`。
- 新档只做到 reset，没有跑完整演示和录像。
