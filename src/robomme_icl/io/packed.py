"""安全的类型化JSON二进制封装，减少状态树的小HDF5节点，不执行反序列化代码。"""

import base64
import json
import math

import numpy as np


def _encode(value):
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject or value.dtype.kind not in "biufc":
            raise TypeError("状态数组只支持数值dtype")
        return [
            "array",
            value.dtype.str,
            list(value.shape),
            base64.b64encode(np.ascontiguousarray(value).tobytes()).decode("ascii"),
        ]
    if isinstance(value, np.generic):
        return ["numpy_scalar", _encode(np.asarray(value))]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("状态字典只接受字符串键")
        return ["mapping", [[key, _encode(value[key])] for key in sorted(value)]]
    if isinstance(value, (list, tuple)):
        return [
            "tuple" if isinstance(value, tuple) else "list",
            [_encode(child) for child in value],
        ]
    if isinstance(value, bytes):
        return ["bytes", base64.b64encode(value).decode("ascii")]
    if value is None or type(value) in (str, bool, int, float):
        return ["value", value]
    raise TypeError(f"不支持打包类型：{type(value).__name__}")


def _decode(node):
    if not isinstance(node, list) or not node:
        raise ValueError("状态封装节点非法")
    tag = node[0]
    if tag == "array" and len(node) == 4:
        dtype = np.dtype(node[1])
        shape = node[2]
        if dtype.hasobject or dtype.kind not in "biufc":
            raise ValueError("拒绝对象或非数值dtype")
        if not isinstance(shape, list) or any(
            type(size) is not int or size < 0 for size in shape
        ):
            raise ValueError("数组shape非法")
        data = base64.b64decode(node[3], validate=True)
        if len(data) != math.prod(shape) * dtype.itemsize:
            raise ValueError("数组字节数与shape不符")
        return np.frombuffer(data, dtype=dtype).reshape(shape).copy()
    if len(node) != 2:
        raise ValueError("状态封装节点长度非法")
    value = node[1]
    if tag == "numpy_scalar":
        array = _decode(value)
        if not isinstance(array, np.ndarray) or array.shape != ():
            raise ValueError("NumPy标量必须为零维数组")
        return array[()]
    if tag == "mapping":
        result = {}
        for key, child in value:
            if not isinstance(key, str) or key in result:
                raise ValueError("状态字典键非法或重复")
            result[key] = _decode(child)
        return result
    if tag in ("list", "tuple"):
        result = [_decode(child) for child in value]
        return tuple(result) if tag == "tuple" else result
    if tag == "bytes":
        return base64.b64decode(value, validate=True)
    if tag == "value" and (value is None or type(value) in (str, bool, int, float)):
        return value
    raise ValueError(f"未知状态封装标签：{tag}")


def pack_tree(value):
    payload = json.dumps(
        _encode(value), ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return np.frombuffer(payload, dtype=np.uint8)


def unpack_tree(payload):
    return _decode(json.loads(np.asarray(payload, dtype=np.uint8).tobytes()))
