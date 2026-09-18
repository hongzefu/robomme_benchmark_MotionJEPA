# 注入重构实施留档

## 阶段 0：基线冻结

用户指令原话：`/data/hongzefu/robomme\_benchmark\_MotionJEPANewTask/INJECTION\_REFACTOR\_PLAN.md`、`开始实现`。

实施起点为 `newtask-v2.1refractor` 的 `2bcd9cc`（11.08），初始工作区干净。按计划先冻结旧代码、配置、依赖锁和运行 10 已跟踪的小产物；阶段 1 建立候选包并验证 3400 条旧规格。阶段 2 及之后按计划的阶段边界另行推进。

[`baseline.sha256`](baseline.sha256) 保存旧注入工具、跑前图工具、生成器、种子布局、配置、全部已跟踪环境源码、依赖声明和锁、运行 10 已跟踪的小产物及计划的文件字节散列。大型 HDF5 与视频不在本阶段重新扫描，阶段 7 迁移前另做完整清单和散列核验。

在仓库根执行下列命令，退出 0 表示冻结清单中的文件未变：

```bash
sha256sum -c docs/validation/newtask-v2/20260917-injection-refactor/baseline.sha256 --quiet
```

本阶段实测退出 0。`command -v uv` 返回 `/home/hongzefu/.local/bin/uv`。本阶段只新增留档并更新账本，无生产代码改动，因此没有启动仿真或运行代码测试。未推送远端。

阶段 1 结束时再次复验上述 221 个文件通过。随后按计划在 `INJECTION_REFACTOR_PLAN.md` 的实施步骤表后追加实测记录，原计划文件因此成为唯一登记的文档差异；冻结清单不重写。当前复验其余 220 个旧代码与输入文件使用：

```bash
rg -v '  INJECTION_REFACTOR_PLAN.md$' docs/validation/newtask-v2/20260917-injection-refactor/baseline.sha256 | sha256sum -c --quiet
```

## 阶段 1：候选包与全量重算

新包位于 [`scripts/injection/candidates/`](../../../../scripts/injection/candidates/)。四个核心模块先复制，保留旧入口。`specs::build_group` 使用独立上下文的观测回调，向外发送已生成的提案和结果；`ObservationCollector` 累计每条候选的真实计数，并把所有拒绝写入日志。BinFill 按物体提案计数，视频任务按整条候选提案计数，RouteStick 不适用的计数为 `null`。观测通道不消费随机数、不修改旧统计或旧规格。

`io::load_candidates` 只依赖标准库，严格检查封套字段、主键、重复/缺失、旧规格散列、采样快照身份、seed、split 和筛查计数；指定仓库根时额外验证快照内的源码指纹。`project_spec` 返回完整旧规格的深拷贝。`identity_sha256` 排除角色与派生来源等可变管理字段，包含完整旧规格，因此添加旧 `collision` 键也会改变封套身份。角色回写后旧规格字节不变。

`screen_documents` 沿用旧六项检查；可复现检查从只比散列加强为比较完整记录，并重新核算两侧旧散列。入口在冻结前校验旧配置、完整文档与统计，完成所有检查后才原子发布 `candidates.jsonl`。运行 10 只读旧输入，新增 `candidates/`；图表/报告在阶段 6 接入，当前入口只完成候选冻结与筛查，不能称为最终完整流程。交付配置解析暂用保留的旧 `delivery::load_delivery_config`，阶段 8 删除旧模块前必须迁入纯配置解析。

### 短测试

```bash
command -v uv
mkdir -p artifacts/test-tmp
timeout 280s uv run --no-sync python -m pytest \
  tests/lightweight/test_candidates_refactor.py \
  tests/lightweight/test_episode_specs.py \
  tests/lightweight/test_injection_blocks.py \
  tests/lightweight/test_scripts_do_not_import_tests.py \
  -q --basetemp artifacts/test-tmp/refactor-candidates-02
```

退出 0，`60 passed, 9 skipped`，93.41 秒；跳过的是依赖已清理历史规格的既有用例。四任务 easy 各 100 条新旧完整文档和统计相同；RouteStick/easy 两个 block 的候选生成→六项筛查→封套发布→读取→角色回写路径通过。原有生产脚本、环境源码和数据不改。

加强筛查字段校验后，另执行同测试文件的 `-k 'not observation_matches_old_random_stream'`，退出 0，`14 passed, 4 deselected`，3.16 秒；没有把未重跑的四项算入本次补测。首次尝试曾因临时目录父目录不存在出现 12 个夹具错误，补建父目录后修复；静态核验另补齐筛查模块搬迁遗漏的导入。

等待长任务时，对全部 3400 条旧规格单独核验投影与 seed，退出 0，`PROJECTION_EQUIVALENCE=PASS compared=3400 role_rewrite_mismatch=0 seed_mismatch=0`。这只验证 `project_spec`，不是阶段 2 的生成器加载器或完整环境 kwargs 对拍。复验命令如下，其中临时封套的 `split/screening` 仅为投影所需字段，不发布为正式候选，也不以它们宣称筛查通过：

```bash
command -v uv
uv run --no-sync python - <<'PY'
import copy
import json
from pathlib import Path
from scripts.injection.candidates.io import canonical_json, project_spec, seed_for
from scripts.seed_layout import get_layout
root = Path('artifacts/injection/20260912-contract-v3-10')
manifest = json.loads((root / 'manifest.json').read_text())
compared = 0
for group in manifest['groups']:
    document = json.loads((root / group['path']).read_text())
    for spec in document['episodes']:
        row = dict(record='candidate', task=spec['task'], difficulty=spec['difficulty'],
                   episode=spec['episode'], block=spec['episode'] // 100,
                   seed=seed_for(spec['task'], spec['episode']),
                   spec_sha256=spec['spec_sha256'], split='train', role='pending',
                   error_type=None, spec=copy.deepcopy(spec), screening={})
        before = canonical_json(project_spec(row))
        row['role'] = 'primary'
        assert canonical_json(project_spec(row)) == before == canonical_json(spec)
        assert row['seed'] == get_layout('train').seed(spec['task'], spec['episode'], 0)
        compared += 1
assert compared == 3400
print(f'PROJECTION_EQUIVALENCE=PASS compared={compared} role_rewrite_mismatch=0 seed_mismatch=0')
PY
```

### 全量任务

```bash
command -v uv
mkdir -p artifacts/injection/20260912-contract-v3-10/candidates/logs
tmux new-session -d -s injection-refactor-l1 -c "$PWD" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python -m scripts.injection.candidates \
  --run-id 20260912-contract-v3-10 --reconstruct-run 20260912-contract-v3-10 \
  2>&1 | tee artifacts/injection/20260912-contract-v3-10/candidates/logs/plan.log; \
  echo \"EXIT_CODE=\$?\" >> artifacts/injection/20260912-contract-v3-10/candidates/logs/plan.log"
```

实测 `EXIT_CODE=0`、`CANDIDATES=PASS rows=3400 elapsed_s=1986.59`，11 项判定全部 PASS。已冻结或已开始的编号不可覆盖重用；复验使用新的 `--run-id`，`--reconstruct-run` 保持源编号。原运行的 838 条 unused 补查、HDF5 对拍与目录迁移均不在本阶段执行。

来源口径：`plan_meta.json` 记录启动时的 HEAD，以及当时全部候选实现文件、依赖声明、依赖锁和旧输入的独立 SHA-256。本次启动时 HEAD 为阶段 0 的 `41f5fa2`，新实现尚在工作区，不能声称该提交已经包含新代码；实现版本以 `implementation_sha256` 核对。封套的 `evidence_source` 保存启动时的记录，其中 `state=running` 是采集启动状态；最终运行状态以 `logs/plan_meta.json` 及退出码、具名判定为准。

### 阶段 1 最终结果与留档

- `CANDIDATES_EQUIVALENCE=PASS compared=3400 differences=0`；`SPEC_REPRODUCIBLE` 同样 3400 条零差异，比较完整记录并复算旧散列。
- `PARITY_KEYS=PASS layer=L1 expected=3400 actual=3400 missing=0 extra=0 duplicates=0`。
- `SCREENING_EVIDENCE=PASS rows=3400 groups=14`；完整拒绝事件 11514 条、3078047 字节，与旧四类拒绝统计之和相同。
- `COLLISION_SWEEP=PASS specs=1700 rejected=0 uncertified=0 min_g_m=1.4025e-05`；其余范围、契约、配额、静态几何检查全通过。契约 6 个差异均属原有 2 项已登记 override，problems=0。
- `SOURCE_INTACT=PASS files=16`；旧清单、旧统计与 14 个规格文件字节未变。
- 候选文件 3401 行（header 加 3400 条候选），约 6 MB；train 1842、test 1558，初始角色全部 pending，筛查来源全部 reconstructed。没有提前迁入旧结果角色或执行 reset。

完整产物位于 [`candidates/`](../../../../artifacts/injection/20260912-contract-v3-10/candidates/)，其中候选文件、拒绝日志、组统计、配额报告、判定 JSON、运行元信息和完整日志入库；零字节进程锁不入库。现有忽略规则的统一调整属于阶段 8，本阶段以逐个明确文件路径强制暂存这些新增轻量证据，不放宽忽略规则。

落盘后的只读复验如下。实际执行退出 0；角色改写只发生在内存副本，3400 条旧规格和候选身份均未变。

```bash
jq -r '.implementation_sha256 | to_entries[] | "\(.value)  \(.key)"' artifacts/injection/20260912-contract-v3-10/candidates/logs/plan_meta.json | sha256sum -c --quiet
command -v uv
uv run --no-sync python - <<'PY'
import copy
from collections import Counter
from pathlib import Path
from scripts.injection.candidates.io import load_candidates, identity_sha256, validate_candidates, canonical_json
root = Path.cwd()
header, rows = load_candidates(root / 'artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl', repo_root=root)
assert len(rows) == 3400
assert Counter(r['split'] for r in rows) == {'train': 1842, 'test': 1558}
assert Counter(r['role'] for r in rows) == {'pending': 3400}
assert all(r['screening']['evidence_origin'] == 'reconstructed' for r in rows)
changed = copy.deepcopy(rows)
for row in changed:
    row['role'] = 'primary' if row['split'] == 'train' else 'spare'
assert identity_sha256(header, changed) == header['identity_sha256']
validate_candidates(header, changed, repo_root=root)
assert [canonical_json(r['spec']) for r in rows] == [canonical_json(r['spec']) for r in changed]
print('CANDIDATE_FILE=PASS candidates=3400 train=1842 test=1558 pending=3400 reconstructed=3400')
print('ROLE_REWRITE_IDENTITY=PASS rows=3400 changed_specs=0 changed_identity=0')
PY
```

阶段 0～1 已完成。阶段 2～9 尚未实施，按原计划的逐阶段批准规则保留停点；本轮没有改生成器或环境源码，没有移动、删除、重跑既有 HDF5/视频，也没有推送远端。
