cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
export CUDA_VISIBLE_DEVICES=0 PYTHONUNBUFFERED=1
r() { timeout 290 uv run --no-sync python /tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/long_demo/sim_oracle_eval.py "$@" 2>&1 | grep -E "RESULT|Traceback|Error" | head -3 || echo "FAILED $*"; }
r PatternLock 5500000 6 30 33 0.08
r PatternLock 5500300 6 30 33 0.08 /tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/long_demo/pl_6x6_008_seed5500300.png
r PatternLock 5500600 6 30 33 0.08
r PatternLock 5500000 5x6 25 28 0.1 /tmp/claude-114466650/-data-hongzefu-robomme-benchmark-MotionJEPANewTask/4d4f0ebe-f95a-4495-b425-f61bacbd7855/scratchpad/v5/long_demo/pl_5x6_01_seed5500000.png
r PatternLock 5500300 5x6 25 28 0.1
V5_TS=1.3 r PatternLock 5500000 5 20 24 0.1
V5_TS=1.3 r PatternLock 5500600 5 20 24 0.1
echo SIM_BATCH_DONE
