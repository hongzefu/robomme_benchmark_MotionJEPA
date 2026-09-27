#!/bin/bash
# 只读审计：逐个符号在 src/ scripts/ tests/ 下 grep 命中文件数与首个命中文件
cd /data/hongzefu/robomme_benchmark_MotionJEPANewTask
for s in VALID_DIFFICULTIES XHARD_KEY _strip_xhard _xhard_shape assert_native_decision spec_kind_for _unmask_pick_count validate_demo_plan 'decision\["xhard"\]' spawn_random_cube spawn_random_target '\bDIFFICULTY\b' SEED_RULE RELEASE_NOTES NATIVE_SAMPLING NATIVE_SPEC_GOLDEN NATIVE_AST_GOLDEN _spawn_cubes_xhard _plan_swap_partners_xhard _xhard_planned_partner plan_distractor_swaps evaluate_outer_candidate predict_inner_windows prejudge_inner_windows joint_sweep_from_actual check_swap_sweep_prefiltered swap_initiator_indices swap_initiator_third demo_return_policy return_to_origin 'visit_selection' count_sampler path_search_max_attempts segment_count_range demo_layout execution_layout swap_speed_multiplier distractor_swap corner_bias hsv_floor_color HSV_FLOOR_COLOR exact_obb min_center_gap min_center_dist_m random_yaw distractor_count cube_count_range '"cube_range"' _compute_dynamic_swap_candidates _select_swap_pair_from_positions _resolve_sampling_config DIFFICULTY_ORDER is_newvalue_difficulty newvalue_tier NEWVALUE_DIFFICULTIES _load_cubes_xhard partner_policy inner_swap_policy visit_count_max; do
  files=$(grep -rlE --include='*.py' --include='*.json' "$s" src scripts tests 2>/dev/null | grep -v __pycache__)
  n=$(echo -n "$files" | grep -c . )
  echo "$s|$n|$(echo "$files" | head -4 | tr '\n' ' ')"
done
