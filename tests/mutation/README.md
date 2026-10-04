# 植入执行器（tests/mutation）

计划 `1003-code-test-maintenance-todo.md` 第二部分「五、闸门总表与植入清单」的公共件：读取各测试块自己维护的
`tests/**/mutants.json`，逐项把一处**语义错误**植入生产逻辑，确认该项 `expect_fail` 里的用例因此失败，给出判定行

```
TEST_MUTATION=PASS|FAIL seeded=<n> caught=<n> survived=<n> not_executable=<n> baseline_fail=<n>
```

通过条件：`survived=0` 且 `baseline_fail=0`（且 `seeded>0`）；`not_executable` 只报告、不影响判定。

本目录文件都不以 `test_` 开头、不在 `pyproject.toml` 的 `testpaths` 里，不进日常门禁。

## 文件

| 文件 | 作用 |
|---|---|
| `run_mutants.py` | 执行器：读取、归一、建隔离副本、跑基线与植入、汇总判定行与逐项记录 |
| `recipes.py` | 配方补充表：mutants.json 只有文字描述的 A 类条目，在这里落成精确替换点或数据改写函数 |
| `plugins/mut_inproc.py` | 进程内植入插件（`MUT_INPROC=<块>:<编号>`），覆盖受保护目录与须导入后改常量的 B 类条目 |
| `plugins/outcome_recorder.py` | 结果记录插件：把每个用例各阶段结局与异常类型写到 `MUT_OUTCOME_FILE` |

## 三类

- **A 文本替换／数据改写**：mutants.json 自带 `patch: [{file, old, new}]`，或 `recipes.py` 里有同键配方。
  执行器把仓库的 `src`、`scripts`、`tests`、`challenge_interface`、`pyproject.toml` 复制到 tmp 隔离副本
  （每个并发一份，先打印并核对 `robomme_hard.__file__`／`robomme.__file__` 指向副本），逐字替换（每个 `old` 必须恰好命中
  1 次，否则记为不可执行并报出）或调用改写函数（规格 jsonl 重签等），跑完把被改文件按原字节还原并核对 sha256。
  点名 `src/robomme/` 或三个上游入口（`scripts/dataset_replay.py`、`scripts/evaluation.py`、`scripts/run_example.py`）
  的 A 类配方一律拒绝落盘，记为不可执行（红线 R9）。
- **B 进程内插件**：不落盘，在仓库本身运行（`PYTHONDONTWRITEBYTECODE=1`、`-p no:cacheprovider`，只读）。
  - T4 块沿用 `tests/unit/hard/mutants_plugin.py`：`PYTHONPATH` 加 `tests/unit/hard`，`-p mutants_plugin`，
    环境变量 `T4_MUTANT=<名>`（名字从 mutants.json 的 `method` 里解析）；
  - 其余块用 `plugins/mut_inproc.py`：`-p tests.mutation.plugins.mut_inproc`，`MUT_INPROC=<块>:<编号>`。
    静态块改 `pathlib` 读到的字节，契约块改导入后的常量或包装函数，录制／官方单元／包装器块替换方法；
    每项实现照抄对应 mutants.json 的描述。
- **C 仅描述、无法机检**：没有 `expect_fail`（如挑战块 M19，用户裁决不修）或找不到配方的条目，计入
  `not_executable`，不计入 `seeded`。

## 判定口径

1. **基线**：按运行环境分组（A 在一份原版副本；B 每个插件一组，插件已加载但不设植入变量），把组内全部
   `expect_fail` 用例并集跑一遍；某项有用例不过时对该项单跑复核，仍不过记 `baseline_fail`，不再植入。
   要求每个 `expect_fail` 至少收集到一个实例且全部通过（跳过也算不过）。
2. **植入后**：至少一个 `expect_fail` 用例（函数级编号按 `编号[` 前缀匹配参数化实例）在 setup／call 阶段失败，
   且异常类型不是 `ImportError`／`ModuleNotFoundError`／`SyntaxError`／`IndentationError`、所在文件没有收集错误，
   才记抓到（caught）；否则记存活（survived）。存活项不得改测试凑数，交主会话裁决。
3. 资源守卫照常装着（仓库 `pyproject.toml` 的 `addopts` 在副本里同样生效）；不起仿真、不访问外网。

## 运行

worktree 里没有 `.venv`，须指向主检出的环境：

```bash
UV_PROJECT_ENVIRONMENT=/data/hongzefu/robomme_benchmark_MotionJEPANewTask/.venv \
  uv run --no-sync python tests/mutation/run_mutants.py --jobs 4
```

- `--list`：只打印每项归到哪一类，不运行；
- `--only <块前缀或键>...`：只跑部分（如 `--only unit/ static`、`--only pipeline/site:M20a`），配 `--tag <批次名>`
  写 `last_run.<批次名>.jsonl`；分批跑完后 `--merge` 合并为 `last_run.jsonl` 并打印总判定行（缺项或重复即 FAIL）；
- 隔离副本建在 `$TMPDIR`（默认 `/tmp`），跑完删除；
- 逐项记录写 `artifacts/maint-regress/mutation/last_run.jsonl`（不进 git）：来源文件、编号、类别、基线结果、
  植入后各用例结局与异常类型、是否抓到、失败用例列表。

全量 107 项（A 60、B 47）在 sled-vail 上 4 并发一次跑完约 2～3 分钟，单个 pytest 进程设 280 秒超时。

## 新增植入

在本块 `mutants.json` 加条目并写好 `expect_fail`；能写成精确替换的直接给 `patch`（非受保护文件），否则：
非受保护文件在 `recipes.py` 补同键配方，受保护文件或须导入后改的在 `plugins/mut_inproc.py` 补实现并加入 `SUPPORTED`。
跑 `--list` 确认不落在 C 类，再跑 `--only <块>` 确认基线过、植入被抓到。
