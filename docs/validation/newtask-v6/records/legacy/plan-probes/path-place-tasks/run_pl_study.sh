set -o pipefail
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
P=artifacts/newtask-v6/plan-probes/path-place-tasks
run() { PYTHONUNBUFFERED=1 timeout 1500 uv run --no-sync python $P/pl_path_study_v6.py "$@" 2>&1 | grep -E "RESULT|Traceback|Error"; }
run 6 6 0.08 33 35 120 &
run 7 7 0.07 38 40 120 &
run 7 7 0.07 42 44 120 &
run 7 7 0.07 45 46 120 &
run 5 5 0.1 30 34 120 walk &
run 5 5 0.1 36 40 120 walk &
wait
echo BATCH_DONE
