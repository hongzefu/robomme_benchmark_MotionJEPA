"""VideoUnmaskSwap 保留原版映射、最近邻交换和抓放任务。"""

from ..native.imports import NativeVideoUnmaskSwap
from ..native.parameters import NativePlacements, initialize_parameters, runtime_options


class ICLVideoUnmaskSwap(NativeVideoUnmaskSwap):
    def __init__(self, *, episode_spec, render_gpu=0):
        parameters = initialize_parameters(self, episode_spec)
        self.configs[self.episode_spec.difficulty] = {
            "bin": parameters.container_count,
            "pick_min": parameters.pick_count,
            "pick_max": parameters.pick_count,
            "swap_min": parameters.swap_count,
            "swap_max": parameters.swap_count,
        }
        super().__init__(**runtime_options(self.episode_spec, render_gpu))

    def _load_scene(self, options):
        self._build_scene(options, NativePlacements(self.episode_spec))
