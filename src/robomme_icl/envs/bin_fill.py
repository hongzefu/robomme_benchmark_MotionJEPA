"""BinFill 只覆盖数量、动态模式和布局，其余继承原版。"""

from ..native.imports import NativeBinFill
from ..native.parameters import NativePlacements, initialize_parameters, runtime_options


class ICLBinFill(NativeBinFill):
    def __init__(self, *, episode_spec, render_gpu=0):
        parameters = initialize_parameters(self, episode_spec)
        self.configs[self.episode_spec.difficulty] = {
            "color": parameters.scene_color_count,
            "spawn_cubes": [parameters.spawn_count] * 2,
            "put_in_color": [parameters.target_color_count] * 2,
            "put_in_numbers": [parameters.pick_count] * 2,
        }
        super().__init__(**runtime_options(self.episode_spec, render_gpu))

    def _load_scene(self, options):
        self.dynamic = self.parameters.dynamic
        self._build_scene(options, NativePlacements(self.episode_spec))
