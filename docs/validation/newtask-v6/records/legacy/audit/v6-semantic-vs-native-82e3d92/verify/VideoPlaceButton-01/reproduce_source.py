"""独立复现 VideoPlaceButton-01：从 AUDIT_BASE 源码验证 extra_place_before 候选集恒为 after-target。
读取方式: git show 82e3d922...:src/robomme/robomme_env/VideoPlaceButton.py
"""
# targets 恒为 4 个 (config_xhard 系列 "targets":4)，xhard3/xhard4 demo_count=2。
targets = [0, 1, 2, 3]  # 索引占位
demo_count = 2
demo_before_targets_idx = [2 * k for k in range(demo_count)]   # [0, 2]
demo_after_targets_idx = [2 * k + 1 for k in range(demo_count)]  # [1, 3]
assert set(demo_before_targets_idx) | set(demo_after_targets_idx) == set(targets)

for task_flag in (True, False):
    for answer_index in range(demo_count):
        if task_flag:
            target_target_idx = demo_before_targets_idx[answer_index]
        else:
            target_target_idx = demo_after_targets_idx[answer_index]
        occupied = set(demo_before_targets_idx)  # side == "before"
        candidates = [idx for idx in targets if idx not in occupied and idx != target_target_idx]
        # 断言：候选集永远是 demo_after_targets_idx 的子集
        assert set(candidates).issubset(set(demo_after_targets_idx)), (task_flag, answer_index, candidates)
        print(f"task_flag={task_flag} answer_index={answer_index} target_target_idx={target_target_idx} "
              f"extra_before_candidates={candidates} (⊆ demo_after_targets_idx={demo_after_targets_idx})")
print("CONFIRMED: side='before' 的候选集在 targets==4, demo_count==2 时恒为 demo_after_targets 的子集（非空）")
