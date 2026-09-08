"""VideoRepick 只覆盖重复次数、方块数和交换数及布局。"""

from ..native.imports import NativeVideoRepick
from ..native.parameters import NativePlacements, initialize_parameters, runtime_options


class ICLVideoRepick(NativeVideoRepick):
    def __init__(self, *, episode_spec, render_gpu=0):
        parameters = initialize_parameters(self, episode_spec)
        self.configs[self.episode_spec.difficulty] = {
            "cube": parameters.spawn_count,
            "swap_min": parameters.swap_count,
            "swap_max": parameters.swap_count,
        }
        super().__init__(**runtime_options(self.episode_spec, render_gpu))

    def _load_scene(self, options):
        self.num_repeats = self.parameters.repeat_count
        self._build_scene(options, NativePlacements(self.episode_spec))
