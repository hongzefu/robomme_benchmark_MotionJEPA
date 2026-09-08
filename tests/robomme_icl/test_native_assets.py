"""素材检查器必须检测组件缺失、材质和几何差异。"""

import copy

import numpy as np
import pytest

from robomme_icl.io.hdf5 import ReproducibilityError
from robomme_icl.validation.assets import compare_assets


@pytest.mark.parametrize("mutation", ["missing_component", "color", "geometry"])
def test_asset_comparator_detects_mutation(mutation):
    reference = {
        "board": [
            {
                "visuals": [
                    {
                        "half_size": np.array([0.05, 0.005, 0.025]),
                        "color": np.array([0.8, 0.6, 0.4, 1.0]),
                    },
                    {
                        "half_size": np.array([0.04, 0.04, 0.0125]),
                        "color": np.array([0.0, 0.0, 0.0, 1.0]),
                    },
                ]
            }
        ]
    }
    actual = copy.deepcopy(reference)
    compare_assets(reference, actual)
    if mutation == "missing_component":
        actual["board"][0]["visuals"].pop()
    elif mutation == "color":
        actual["board"][0]["visuals"][0]["color"][0] = 0.75
    else:
        actual["board"][0]["visuals"][0]["half_size"][0] += 0.001
    with pytest.raises(ReproducibilityError):
        compare_assets(reference, actual)
