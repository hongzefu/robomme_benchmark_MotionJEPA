"""RouteStick 只覆盖路径长度、折返选项及整排位置角度。"""

from ..native.imports import NativeRouteStick
from ..native.parameters import NativePlacements, initialize_parameters, runtime_options


class ICLRouteStick(NativeRouteStick):
    def __init__(self, *, episode_spec, render_gpu=0):
        parameters = initialize_parameters(self, episode_spec)
        self.configs[self.episode_spec.difficulty] = {
            "length": [parameters.walk_steps] * 2,
            "backtrack": parameters.allow_backtracking,
        }
        super().__init__(**runtime_options(self.episode_spec, render_gpu))

    def _load_scene(self, options):
        self._build_scene(options, NativePlacements(self.episode_spec))
