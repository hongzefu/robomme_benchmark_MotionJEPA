set -o pipefail
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
P=artifacts/newtask-v6/plan-probes/path-place-tasks
run() { PYTHONUNBUFFERED=1 uv run --no-sync python $P/vp_layout_mc_cfg.py "$@" 2>&1 | grep -E "RESULT|Traceback|Error"; }
for e in VideoPlaceButton VideoPlaceOrder; do
  run $e 400 0 0.2 3 4,5 &
  run $e 400 0 0.2 3 6 &
  run $e 400 0 0.2 3 7,8 &
  run $e 400 0 0.2 4 4,5 &
  run $e 400 0 0.2 4 6 &
  run $e 400 1 0.25 3 4,5 &
  run $e 400 1 0.25 3 6 &
  run $e 400 0 0.25 3 6,8 &
done
wait
echo BATCH_DONE
