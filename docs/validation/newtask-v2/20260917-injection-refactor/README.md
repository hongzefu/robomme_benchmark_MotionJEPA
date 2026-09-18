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

阶段 1 结束时再次复验上述 221 个文件通过。随后按计划在 `INJECTION_REFACTOR_PLAN.md` 的实施步骤表后追加实测记录，原计划文件因此成为阶段 1 唯一登记的文档差异；冻结清单不重写。阶段 1 提交时复验其余 220 个旧代码与输入文件使用下列命令；阶段 2 已按授权修改生成器，当前允许差异见本文末尾阶段 2 的复验命令：

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

## 阶段 2：生成器接入与单条成品对拍

用户对上一轮明确提问「是否批准阶段 2：接入生成器、完成加载器对拍及单条 HDF5 冒烟？」答复原话「同意」。实施从 `c336390`（11.10）开始，工作区干净；只改计划 R2 的五处生成器锚点，未改候选包和环境源码，未执行阶段 3～9。

### 实现与输入约束

[`scripts/generate_dataset_newseed.py`](../../../../scripts/generate_dataset_newseed.py) 的 `load_sampling_config` 提取 `validate_sampling_config`，使旧文件与 header 完整采样对象经过同一套结构、动作参数和来源指纹校验。旧文件异常口径及返回的独立任务配置副本不变。

`load_episode_specs` 对 `.jsonl` 文件使用 `candidates.io::load_candidates/project_spec`，先验证整个候选文件，再选择任务、难度和 episode 范围。默认读取可覆盖全部 3400 条；实际生成入口指定 `candidate_split="train"`，只启动 train 与范围的交集。没有匹配条目直接报错，不能退回无规格随机生成。输出按 `<输出根>/<任务>/<难度>` 分组，即使只选一组也如此。

`generate_dataset_newseed` 通过独立 header 输出参数显式辨认 JSONL 来源，不根据投影后相同的 spec 猜来源。JSONL 的配置只取内嵌快照；若另外传 `--sampling-config`，完整对象必须相同。布局和固定 kwargs 必须与 header 一致，所有 seed 须等于现行 train 公式；要求 `--max-attempts 1`，防止冻结候选被换 seed 重试。旧 JSON 和无规格路径不受这些新增限制，原重试调度代码没有修改。原 worker 按 episode 派生的恢复参数也保持原样，已纳入全量参数对拍。

`EpisodeJob.emit_h5_digest` 默认 False，仅 JSONL 入口设置 True。`_worker` 在 `close()`、可选 BinFill 转换及最终 `_raw_summary` 之后以 8 MiB 分块只读散列，增加 `h5_sha256/h5_bytes` 和 `phases.h5_digest_s`。读文件失败或读取期间大小改变则记录代码失败，不交付成功；旧路径不增加散列字段和文件读取。录像器没有修改或覆盖。

### 加载器与短测试

```bash
command -v uv
mkdir -p artifacts/test-tmp
timeout 240s uv run --no-sync python -m pytest \
  tests/lightweight/test_candidate_loader.py \
  tests/lightweight/test_episode_specs.py \
  tests/lightweight/test_native_sampling_config.py \
  tests/lightweight/test_episode_timeout.py \
  tests/lightweight/test_binfill_demo_duplicate.py \
  -q -s --basetemp artifacts/test-tmp/refactor-stage2-01
```

实测退出 0，73 passed / 4 skipped，19.46 秒。4 项是 `test_episode_specs.py` 对已缺失历史规格的既有跳过，未增加 skip。[`test_candidate_loader.py`](../../../../tests/lightweight/test_candidate_loader.py) 从 `git show c336390:scripts/generate_dataset_newseed.py` 加载旧入口；完整 kwargs 由新旧 `_worker` 的实际 AST 语句执行得到，包含恢复参数，不另手抄一张期望参数表。3400 条、角色改写后再次读取均完全一致：

```text
LOADER_PARITY=PASS compared=3400 kwargs_mismatch=0 role_rewrite_mismatch=0
```

同时覆盖实际生成函数的 job 构造与显式散列开关、旧 JSON/无规格回归、快照冲突、错误 seed/layout、换 seed 重试、误选 test 条目时建池前拒绝，以及最终字节散列和文件读取失败。

收尾复核发现默认 pytest 的临时目录在仓库外，会与真实生成器的输出守卫冲突。仅修改本测试文件的夹具，使它无论是否传 `--basetemp` 都使用仓库内 `artifacts/test-tmp/candidate-loader-*`，生产代码未再变。随后实际执行默认临时目录调用：

```bash
command -v uv
set -o pipefail
timeout 120s uv run --no-sync python -m pytest tests/lightweight/test_candidate_loader.py -q -s \
  2>&1 | tee artifacts/injection/refactor-stage2-smoke/rollout/logs/loader-test.log
```

退出 0，11 passed，10.28 秒，完整日志已入库。源码、配置和源候选均未被测试改写，角色改写只作用于测试副本。

### 单任务、单 episode、单 worker 实跑

实际命令如下。复验时改成新的仓库内输出目录，不复用已经留档的路径。本次不传外部 `--sampling-config`，证明环境配置来自候选 header；180 秒单条超时是冒烟保护上限，原参考运行的上限为 600 秒，两次都未触发。其余 worker/GPU/亲和性/进程回收参数沿用旧单条 smoke；`--binfill-demo` 沿用旧调用，但 RouteStick 不进入 BinFill 转换。

```bash
command -v uv
mkdir -p artifacts/injection/refactor-stage2-smoke/rollout/logs
set -o pipefail
PYTHONUNBUFFERED=1 timeout 240s uv run --no-sync python scripts/generate_dataset_newseed.py \
  --episode-specs artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl \
  --env RouteStick --difficulty 100 --episodes 1 --episode-start 0 \
  --workers 1 --gpus 0 --layout train --max-attempts 1 \
  --max-tasks-per-child 8 --affinity per-gpu --episode-timeout 180 --binfill-demo \
  --output-dir artifacts/injection/refactor-stage2-smoke/rollout \
  2>&1 | tee artifacts/injection/refactor-stage2-smoke/rollout/logs/smoke.log
smoke_status=$?
echo "EXIT_CODE=$smoke_status" >> artifacts/injection/refactor-stage2-smoke/rollout/logs/smoke.log
exit "$smoke_status"
```

实测退出 0，成功 1、失败 0，整体 18.2 秒，worker 14.034 秒，散列读取 0.121 秒。结果文件为 [`episode_results.jsonl`](../../../../artifacts/injection/refactor-stage2-smoke/rollout/episode_results.jsonl)。新旧 HDF5 均为 300 帧、200071952 字节，SHA-256 为 `27d7e1c62583025e7f6a18610749e6e3990cfe85c00219e80fbf1d1b086c203b`。

基线核实：旧 `delivery_manifest.json::groups.RouteStick/easy.primary[0]` 指向 `feasibility/P0x1` 的 smoke 文件，实测它与 `feasibility/P01x20` 的同条文件散列相同。因此本条基线不存在内容歧义；不据此推断其他组或其他 episode 的重复文件也相同。

```bash
command -v uv
uv run --no-sync python - <<'PY'
import hashlib
import json
from pathlib import Path
root = Path.cwd()
source = root / 'artifacts/injection/20260912-contract-v3-10'
out = root / 'artifacts/injection/refactor-stage2-smoke/rollout'
rows = [json.loads(line) for line in (out / 'episode_results.jsonl').read_text().splitlines()]
assert len(rows) == 1 and rows[0]['ok'] is True
row = rows[0]
assert (row['task'], row['difficulty'], row['episode'], row['seed']) == ('RouteStick', 'easy', 0, 16000)
old = json.loads((source / 'delivery_manifest.json').read_text())['groups']['RouteStick/easy']['primary'][0]
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
left, right = root / old['h5_path'], Path(row['h5_path'])
assert digest(left) == old['sha256'] == digest(right) == row['h5_sha256']
assert left.stat().st_size == right.stat().st_size == old['bytes'] == row['h5_bytes']
assert row['timestep_count'] == old['timestep_count'] == 300
print('SMOKE_H5_PARITY=PASS compared=1 sha_mismatch=0')
PY
```

实测 `SMOKE_H5_PARITY=PASS compared=1 sha_mismatch=0`，详情见 [`smoke_parity.json`](../../../../artifacts/injection/refactor-stage2-smoke/rollout/logs/smoke_parity.json)。视频状态 complete 只表示本次完整性，不宣称跨次视频内容相同。本阶段只实跑 RouteStick/easy/ep0；BinFill 等其余任务的真实 HDF5 对拍仍属阶段 5。

### 阶段 2 留档与当前停点

本次启动的基础 HEAD 为 `c336390`，实测工作区生成器、依赖锁、源候选和录像器的字节指纹保存在 [`source.sha256`](../../../../artifacts/injection/refactor-stage2-smoke/rollout/logs/source.sha256)，实跑后复验一致。源候选散列仍为 `f578ca6e7d0c475d577943e08473874631515a835983eedc98ee7d345469ba02`。

```bash
sha256sum -c artifacts/injection/refactor-stage2-smoke/rollout/logs/source.sha256 --quiet
rg -v '  (INJECTION_REFACTOR_PLAN.md|scripts/generate_dataset_newseed.py)$' docs/validation/newtask-v2/20260917-injection-refactor/baseline.sha256 | sha256sum -c --quiet
git diff --quiet c336390 -- src/robomme
```

当前阶段 0 原清单的登记差异只有计划追加记录和生成器这两项；其余 219 个旧文件保持原字节。九个轻量产物（参数、摘要、实际使用的配置、逐条结果、metadata、指纹、测试日志、冒烟日志和对拍结果）逐个入库，HDF5/mp4 留在本地、不入库。未改忽略规则，未修改或覆盖任何 `src/robomme/` 行为，未推送。

阶段 2 已完成；阶段 3 待单独批准，将使用旧工具冻结运行 10 的图表和数轴完整基线。没有提前执行 210 条 HDF5 对拍、838 条 reset 补查或现有目录迁移。

## 阶段 3：旧图表基线

用户后续原话「一口气全做完 不要再来问我了」，一次授权剩余阶段。阶段 3 从 `e53173d` 起，旧图表模块与输入不改，使用[独立采集入口](capture_baseline.py) 调用旧算法，图表及原始数据层落在运行 10 的 [`rollout/logs/baseline/`](../../../../artifacts/injection/20260912-contract-v3-10/rollout/logs/baseline/)。

```bash
command -v uv
uv run --no-sync python -m pytest tests/lightweight/test_window_timeline.py -q
mkdir -p artifacts/injection/20260912-contract-v3-10/rollout/logs
tmux new-session -d -s injection-baseline -c "$PWD" \
  "set -o pipefail; PYTHONUNBUFFERED=1 uv run --no-sync python docs/validation/newtask-v2/20260917-injection-refactor/capture_baseline.py \
  2>&1 | tee artifacts/injection/20260912-contract-v3-10/rollout/logs/baseline.log; \
  echo \"EXIT_CODE=\$?\" >> artifacts/injection/20260912-contract-v3-10/rollout/logs/baseline.log"
```

短测 34 passed，2.79 秒。采集退出 0，977.79 秒：`BASELINE_CAPTURED=PASS png=113 tables=14 before=1796 kept=1795 excluded=1 skipped=0`。98 张跑前图、15 张数轴图、14 组 156 行事件表已冻结；旧规则只剔除 1 条慢条。全部输入与输出散列记入 `manifest.json`，旧 timeline 和窗口表原样保留。复验采集须在旧源码仍在的基线提交上使用新的输出目录，不覆盖现有基线；阶段 8 删除旧入口后，本采集脚本属于历史复现材料。

实施调整：发现冻结的 `hf_release.py` 仍导入旧 delivery 的判定行格式化函数，故最终仅保留该公共纯函数；旧配置加载、交付清单生成与 CLI 流程仍按计划删除或迁入新包。这样保持发布脚本不变且模块导入闭包成立。

## 阶段 4：唯一结果、角色归并与恢复

`scripts/injection/_migrate_run10.py prepare` 把旧 1842 条实跑和 720 条 reset 归并成唯一结果表，保存原始对照和 L4 范围到 `rollout/logs/migration/`。原正式/备用/失败与 unused 数均保持不变，候选身份散列不变，只回写管理状态。`path_map.json` 冻结 3820 个文件的一对一迁移目标及经实际散列验证的同条 HDF5 别名；只冻结映射，数据尚未移动。

```bash
command -v uv
uv run --no-sync python -m scripts.injection._migrate_run10 prepare
uv run --no-sync python -m pytest tests/lightweight/test_rollout_state.py tests/lightweight/test_reset_pipeline.py tests/lightweight/test_candidate_loader.py -q -s
```

归并命令退出 0，重复执行只核验，不覆盖。`RESULTS_EQUIVALENCE=PASS h5_rows=1842 primary=1600 spare=196 failed=46 reset_rows=720 reset_primary=700`；`ROLES_CONSISTENT=PASS rows=3400 mismatch=0 duplicates=0 pending=0 unused=838`。短测 17 passed，31.18 秒；`RESET_BATCH_PARITY=PASS keys=720 resume_rerun=0 unused_checked=838`，混合失败不能让 unused 提前停在 50 条。

新包 `rollout/state.py` 实现运行级独占锁、严格唯一键和两文件恢复；`run.py` 保存调用范围，复用生成器的真实 `_run_jobs`，只把范围/配置从候选快照转成作业，不反投影成旧规格文件启动环境；生成器实际文件须匹配仓库绝对路径。`reset_check.py` 复制旧调度与环境核验，改为 header 配置对象，新增缓存终态、完整 unused 范围和 CLI。完整终态即刻落日志，半行保留并标中断；恢复后才派缺失项，不重复运行已经成功或失败的条目。`report.py` 区分完整交付与局部用途，局部结果不冒充 1600/700 配额完成。

真实新入口冒烟与幂等核验（相同命令执行两次，第二次复用终态）：

```bash
command -v uv
uv run --no-sync python -m scripts.injection.rollout \
  --run-id refactor-rollout-smoke \
  --candidates artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl \
  --purpose smoke --groups RouteStick/easy --episodes 1 --reset-limit 1 \
  --tier 1 --gpus 0 --no-figures --label smoke
```

第一次 `RUN=PASS ... h5_executed=1 reset_executed=1`，第二次 `RESET_IDEMPOTENT=PASS rerun=0 duplicates=0`、`RUN=PASS ... h5_executed=0 reset_executed=0`。源候选前后字节不变；影子状态目录为 `rollout/logs/smoke/smoke/`，结果恰为 2 条，HDF5 与旧 RouteStick/easy/ep0 同散列。核对摘要见运行十 `rollout/logs/migration/stage4_checks.json`。

归并后源候选的角色和错误字段确实改变，因此阶段二的角色改写测试同时清空测试副本的 error_type，仍然验证完整 spec 和身份不变；不放宽生产校验。阶段零/一/二的字节散列记录是各自时间点的历史证据，不能用管理状态合法更新后的候选去冒充当时字节。旧环境源码、规格、HDF5 和视频没有改动。

## 阶段 5：方案 B、reset 全量对拍和 unused 补查

独立主调用使用 `20260912-contract-v3-10-parity`，候选副本重置管理状态，完整旧规格与身份保持不变。14 组各 ep0～14 共 210 条；同一主调用随后执行一次正常 reset 配额，恰为原 720 个键。`tmux injection-parity` 的主调用与 `injection-parity-check` 的比较均退出 0。

```bash
command -v uv
uv run --no-sync python -m scripts.injection.rollout \
  --run-id 20260912-contract-v3-10-parity \
  --candidates artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl \
  --purpose parity --tier 20 --gpus 0,1 --episodes 15 --no-figures
uv run --no-sync python -m scripts.injection.rollout.parity \
  --left 20260912-contract-v3-10 --right 20260912-contract-v3-10-parity --scheme B --video-budget-s 120
```

本次已完成并归档，以上是实跑参数，复验须使用新运行编号。具名硬判定：

```text
H5_PARITY=PASS compared=210 success=205 failures=5 sha_mismatch=0 failure_mismatch=0
RESET_PARITY=PASS compared=720 outcome_mismatch=0 stop_episode_mismatch=0 role_mismatch=0
PARITY_SOURCE_INTACT=PASS
```

L3/L4 两侧完整键的 missing/extra/duplicates 均为 0。实际读取两侧 HDF5 散列，没有把只比较记录里的散列冒充文件核验。视频诊断 221 对通过，2 条超时样本没有可比较视频，整体 `VIDEO_DIAGNOSTIC=NOT_RUN`，不伪称全视频一致。真实 BinFill/medium ep1 与 ep16 都为 1388 帧，完整解码后识别 DIFFERENT；首差帧及两份视频原件保留。诊断反例短测 2 passed；连同归并守卫回归 7 passed，20.36 秒。

对拍硬闸完成后执行 `parity --left … --right … --archive`：先逐文件复制和核对证据，再核对临时媒体清单及散列，最后逐项清理。38 份证据保存在正式运行 [`rollout/logs/parity/20260912-contract-v3-10-parity/`](../../../../artifacts/injection/20260912-contract-v3-10/rollout/logs/parity/20260912-contract-v3-10-parity/)，其中 `logs/parity/result.json` 是完整比较结果，`archive_index.json` 和 `cleanup_manifest.json` 记录留存/清理边界；反例视频与差异帧留在本地，不入库。清理临时媒体 426 个、101712029329 字节，原运行媒体零删除。临时运行已标记 archived，普通入口拒绝复用其已清理成品。

随后在 `tmux injection-unused` 中对原运行执行：

```bash
command -v uv
uv run --no-sync python -m scripts.injection.rollout.reset_check \
  --run-id 20260912-contract-v3-10 --only-unused --tier 20 --gpus 0,1
```

退出 0，`UNUSED_RESET=PASS checked=838 passed=838 failed=0 unused_left=0 primary_changed=0`。原 700 个 test primary 与全部 train 角色不变；现在 test spare=858、test failed=0、test unused=0，唯一结果总数 3400。完整范围与原 primary 在 `unused_scope.json` 冻结，重复调用不缩小分母。该例外仅对原运行十开放，普通新运行仍在每组足额 50 条后停下并保留 unused。

## 阶段 6～7：图表等价与实际迁移

阶段六流水线 `figure-pipeline-retry.log` 退出 0：113 张 PNG 字节相同、14 组事件表零漂移；1796 条数轴含 1795 条保留、1 条完整剔除记录全部相同。正式报告核对 1796 个 HDF5 实际散列后通过。首轮展示字典顺序与交换规格投影问题已修复，原失败日志保留；37 项短测通过，5.30 秒。候选输入快照已进入 Git，并放行新运行的同名输入。

阶段七在 detached tmux `injection-migration` 执行：

```bash
command -v uv
uv run --no-sync python -m scripts.injection._migrate_run10 move
```

迁移前后实际读取所有 3820 个文件计算 SHA-256，`H5_INTACT=PASS count=1796 sha_mismatch=0 missing=0`、`ARTIFACTS_INTACT=PASS count=3820 missing=0 extra=0 sha_mismatch=0`、`ACTIVE_PATHS=PASS missing=0 old_prefix=0`、`MIGRATION_METADATA=PASS unexpected_field_changes=0`，退出 0。仅按冻结映射 rename，HDF5/视频不删除、不改写；活动结果、timeline、表与范围仅更新允许路径，原始旧日志不重写。

完整证据在运行十 `rollout/logs/migration/` 的 `inventory.json`、`journal.jsonl`、`active_files.json`、`verification.json`，并保留活动小文件 backups/versions。迁移状态 complete；中断后用同入口 `resume` 续跑，同目标存在或散列变化直接拒绝。5 项恢复反例通过，0.89 秒。

## 阶段 8：清理、Git 边界与回归

已按计划清理 62 个旧跟踪文件（旧生产模块、图表目录、六份文档及六个轻量包），旧图目录剩余 42 个生成文件/缓存一并清理。运行十媒体不删。v1/v2 契约经 cmp 确认字节不变后迁入 tests/fixtures/injection_legacy；测试用纯构建器没有写文件或 CLI。旧校准数学断言与独立采样基线从固定提交 e53173d 加载，仅限测试；新范围、唯一键、角色、报告、reset 和数轴均断言新实现。

`audit_final.py` 核验 25 模块导入闭包、26 个 Git 忽略探针、4 份候选输入及 4 个消费代码文件跟踪、正式 3400 条角色和 114 个文档链接。环境源码与 hf_release.py 相对 2bcd9cc 无差异。代码拓扑的 AST 测试继续禁止生产 import tests。

验证命令：

```bash
command -v uv
uv run --no-sync python -m pytest tests/lightweight/ tests/dataset/ --collect-only -q
timeout 280s uv run --no-sync python -m pytest tests/lightweight/ -m 'not gpu and not slow' -q -ra
uv run --no-sync python docs/validation/newtask-v2/20260917-injection-refactor/audit_final.py
```

623 项收集成功，0 导入错误。最终核心回归见 stage8-final-tests.log：490 passed、4 failed、22 skipped、74 deselected，146.83 秒。4 失败为 TaskGoal 两项与 step_error_handling 两项，独立复现见 existing-failures.log；相关测试与实现相对重构前均无改动，未擅改冻结源码。22 跳过全部来自原已缺失的 04/05/09 规格，无新增 skip/xfail。原全量含 GPU 的轻量运行 280 秒退出 124，见 stage8-tests.log，不把未完成部分写成通过。

首轮核心回归另有 2 个旧夹具仍引用迁前路径的失败（stage8-cpu-tests.log），已按冻结映射修复；加载器补测 11 passed，10.41 秒。窗口报告补齐图链接与图例后，37 项图表/数轴测试通过，5.43 秒；对应表与图片算法未变。数据集对拍离线缺参守卫 1 passed，0.01 秒。

## 阶段 9：最终独立端到端冒烟

`timeout 280s bash docs/validation/newtask-v2/20260917-injection-refactor/final_smoke.sh` 退出 0，总耗时 60 秒。完整 stdout/stderr 在 [final-smoke.log](final-smoke.log)，可复制脚本为 [final_smoke.sh](final_smoke.sh)；再次完整执行须换未使用的运行编号。

```text
FINAL_SMOKE=PASS candidates=200 h5=1 reset=1 figures=9 reports=3 source_unchanged=1
FINAL_SMOKE_TIME=PASS elapsed_s=60 limit_s=280
RESET_IDEMPOTENT=PASS rerun=0 duplicates=0
```

运行编号 refactor-final-smoke。候选生成 4.61 秒；GPU 0、单 worker，RouteStick/easy/ep0 的 HDF5 worker 37.082 秒，test ep115 reset 3.418 秒。HDF5 300 帧、200071952 字节，SHA-256 `27d7e1c62583025e7f6a18610749e6e3990cfe85c00219e80fbf1d1b086c203b` 与原成品相同；视频 complete、300 帧。影子状态在该运行 rollout/logs/smoke/smoke，两条唯一结果均成功，剩余 198 pending 是局部运行的预期状态，不作为完整交付。原运行候选字节不变。

清理后再次执行 `uv run --no-sync python -m scripts.injection.rollout.figure_parity --run-id 20260912-contract-v3-10`：113 PNG 字节、事件表、1796 条数轴（1795 保留、1 完整剔除）仍零差异。最终只读核验见 [final-audit.log](final-audit.log)：6 份候选原件/影子快照和 4 个读取/执行文件全部 Git 跟踪，25 个模块导入成功，26 个忽略边界探针及 114 个现行文档链接通过，正式 3400 条角色相符，环境与发布源码未改。

阶段 0～9 已全部实施。保留既有测试失败和预算未跑范围，不把视频缺失诊断写成通过；原始测试日志含 pytest 输出尾部空白，按证据原样保存。所有实现与轻量证据已逐阶段提交，未推送。
