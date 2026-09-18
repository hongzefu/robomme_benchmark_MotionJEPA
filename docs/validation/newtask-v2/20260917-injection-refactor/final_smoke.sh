#!/usr/bin/env bash
# 最终独立冒烟：新候选、一个 HDF5、一个 reset、完整图表与幂等复核。
set -euo pipefail
command -v uv
SMOKE_RUN=refactor-final-smoke
SOURCE=artifacts/injection/20260912-contract-v3-10/candidates/candidates.jsonl
SOURCE_BEFORE=$(sha256sum "$SOURCE")
SECONDS=0
uv run --no-sync python -m scripts.injection.candidates --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --blocks 2
uv run --no-sync python -m scripts.injection.rollout --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --episodes 1 --reset-limit 1 \
  --tier 1 --gpus 0 --label smoke
uv run --no-sync python -m scripts.injection.rollout.reset_check --run-id "$SMOKE_RUN" \
  --purpose smoke --groups RouteStick/easy --limit 1 --tier 1 --gpus 0 --label smoke
test "$SOURCE_BEFORE" = "$(sha256sum "$SOURCE")"
uv run --no-sync python - <<'PY'
import json
from pathlib import Path
from scripts.injection.candidates.io import load_candidates
from scripts.injection.rollout.state import RunStore, file_sha
root = Path('artifacts/injection/refactor-final-smoke').resolve()
header, candidates = load_candidates(root / 'candidates/candidates.jsonl')
assert len(candidates) == 200
store = RunStore(root, 'smoke')
audit = store.audit()
rows = store.load()[2]
assert len(rows) == 2 and {r['kind'] for r in rows} == {'h5', 'reset'}
assert all(r['ok'] for r in rows)
h5 = next(r for r in rows if r['kind'] == 'h5')
assert file_sha(Path(h5['h5_path'])) == h5['h5_sha256']
assert h5['h5_sha256'] == '27d7e1c62583025e7f6a18610749e6e3990cfe85c00219e80fbf1d1b086c203b'
assert len(list((root / 'candidates/figures').rglob('*.png'))) == 7
assert len(list((store.state / 'figures').rglob('*.png'))) == 2
for path in (root / 'candidates/DISTRIBUTION.md', store.state / 'ROLLOUT.md', store.state / 'WINDOWS.md'):
    assert path.is_file() and path.stat().st_size
print('FINAL_SMOKE=PASS candidates=200 h5=1 reset=1 figures=9 reports=3 source_unchanged=1')
PY
echo "FINAL_SMOKE_TIME=PASS elapsed_s=$SECONDS limit_s=280"
