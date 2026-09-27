"""审计：重跑 PickHighlight N=7/8/9/10 与 BinFill N=12 reset 成功率（原 run_mc.sweep，种子由 N 决定、固定），
以及 binfill_color.run(12,5,7)（xhard 杂乱布局 + 同色团口径）。不写回原目录。"""
import sys, inspect
sys.path.insert(0, "/data/hongzefu/robomme_benchmark_MotionJEPANewTask/artifacts/newtask-v6/plan-probes/count-tasks")
import run_mc, binfill_color
run_mc.sweep("PickHighlight", [7, 8, 9, 10], "现值 0.2 gap=0.04")
run_mc.sweep("BinFill", [12], "现值框 0.4x0.5")
binfill_color.run(12, 5, 7, (0.2, 0.25))
