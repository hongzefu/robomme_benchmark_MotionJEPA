set -o pipefail
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
run() { PYTHONUNBUFFERED=1 uv run --no-sync python /tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/long_demo/pl_path_study.py "$@" 2>&1 | grep RESULT; }
run 5 5 0.1 20 24 300 &
run 5 5 0.1 23 25 300 &
run 6 6 0.08 27 33 300 &
run 6 6 0.08 28 34 300 &
run 6 6 0.08 29 36 300 &
run 5 6 0.1 24 30 300 &
wait
echo BATCH1_DONE
