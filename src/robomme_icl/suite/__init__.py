"""不导入仿真库的新版配置与冻结清单 API。"""

from .compiler import candidate_for_slot, distribution_summary, load_configs, plan_slots, validate_configs
from .spec import COMPILER_VERSION, DIFFICULTIES, TASKS, EpisodeSpec, canonical_json, content_hash
from .storage import find_spec, load_suite, save_suite

__all__ = [
    "COMPILER_VERSION", "DIFFICULTIES", "TASKS", "EpisodeSpec", "canonical_json", "content_hash",
    "candidate_for_slot", "distribution_summary", "find_spec", "load_configs", "load_suite",
    "plan_slots", "save_suite", "validate_configs",
]
