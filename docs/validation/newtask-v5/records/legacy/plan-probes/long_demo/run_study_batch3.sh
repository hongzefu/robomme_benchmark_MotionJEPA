set -o pipefail
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
run() { PYTHONUNBUFFERED=1 uv run --no-sync python /tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/long_demo/pl_path_study.py "$@" 2>&1 | grep -E "RESULT|Traceback|Error"; }
run 6 6 0.08 30 33 300 &
run 6 6 0.08 31 33 300 &
run 5 6 0.1 25 28 300 &
run 7 7 0.07 32 42 300 &
run 5 5 0.1 20 24 300 dfs 1.25 &
run 5 5 0.1 20 24 300 dfs 1.35 &
run 5 5 0.1 22 25 300 dfs 1.2 &
wait
echo BATCH3_DONE
