"""打包不得改变类型、shape、有符号零和原始数组字节。"""

import json
import numpy as np
import pytest

from robomme_icl.io.hdf5 import assert_identical
from robomme_icl.io.packed import pack_tree, unpack_tree


def test_packed_tree_roundtrip_is_exact_and_owns_its_arrays():
    value = {
        "pose": np.array([-0.0, 1.0], dtype=">f8"),
        "empty": np.zeros((0, 3), dtype=np.float32),
        "scalar": np.int32(5),
        "zero_dim": np.array(-0.0, dtype=np.float32),
        "tuple": (True, None, b"\x00\xff", "原版状态"),
        "list": [{"x": 1}],
    }
    restored = unpack_tree(pack_tree(value))
    assert_identical(value, restored)
    restored["pose"][0] = 3.0
    assert np.signbit(value["pose"][0])


@pytest.mark.parametrize(
    "node",
    [
        ["array", "O", [1], "AAAAAAAAAAA="],
        ["array", "<f8", [1000000], "AA=="],
        ["mapping", [["x", ["value", 1]], ["x", ["value", 2]]]],
        ["execute", "不能执行代码"],
    ],
)
def test_malformed_packed_state_is_rejected(node):
    data = np.frombuffer(json.dumps(node).encode(), dtype=np.uint8)
    with pytest.raises(ValueError):
        unpack_tree(data)
