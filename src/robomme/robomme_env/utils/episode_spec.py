"""每局规格的只读导出与原值回注（newtaskRelease-v3 步 4）。

方案第三节／8.2 规定的两件事，本模块用同一个对象承担：

* **导出（C 路）**：在**原调用点**把每个取值点的结果只读记下来，不多抽、不少抽、
  不改变任何取值，最后封存成 ``episode_spec``。
* **回注（D 路）**：同一调用点照常执行原抽样（随机流不漂移，红线 R8），但**真正用于建场景
  的值来自冻结规格**；原抽样结果只作兼容核验。

这一点是 G4 的核心判据：方案明确拒绝「重抽出相同值却绕过规格」的实现——本模块通过
``value()`` 返回冻结值（而不是返回抽样值）来结构性地保证规格确实被消费。

与既有注入通道的关系：四个早接了 ``episode_spec`` 的环境里，那条「传了规格就跳过抽样」的
分支属于旧注入模式，按红线 R9 原样保留、不复用为 D 路；本模块只挂在原随机分支上，
由新的 ``native_episode_spec`` 开关驱动。
"""

from __future__ import annotations

import copy
from typing import Any

SPEC_KIND = "native-parity/1"


class EpisodeSpecError(ValueError):
    """规格的形态、版本或身份与本局不符。"""


def _set_path(tree: dict, path: str, value: Any) -> None:
    node = tree
    parts = path.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _get_path(tree: dict, path: str):
    node = tree
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise EpisodeSpecError(f"规格缺少取值点 {path}")
        node = node[part]
    return node


def _plain(value: Any):
    """把张量／numpy 标量转成可 JSON 化的原生对象，不改数值。"""
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    return value


class SpecRecorder:
    """一个环境实例一份；``spec=None`` 为导出模式，否则为原值回注模式。"""

    def __init__(self, spec: dict | None, task: str, identity: dict | None = None):
        self.task = task
        self.identity = dict(identity or {})
        self.mismatches: list[dict] = []
        self.trace: list[dict] = []
        if spec is None:
            self.mode = "export"
            self._frozen: dict = {}
            self._document: dict = {
                "spec_kind": SPEC_KIND,
                "task": task,
                "identity": self.identity,
            }
        else:
            if not isinstance(spec, dict) or spec.get("spec_kind") != SPEC_KIND:
                raise EpisodeSpecError(f"native_episode_spec 需要 spec_kind={SPEC_KIND}")
            if spec.get("task") != task:
                raise EpisodeSpecError(f"规格属于 {spec.get('task')}，不能用于 {task}")
            self.mode = "replay"
            self._frozen = copy.deepcopy(spec)
            self._document = copy.deepcopy(spec)

    # ------------------------------------------------------------------
    @property
    def replaying(self) -> bool:
        return self.mode == "replay"

    def value(self, path: str, drawn: Any):
        """原调用点：导出模式返回抽样值并记录；回注模式返回冻结值并把抽样值记为兼容核验。

        ⚠ 回注模式**一定**返回冻结值——即便原抽样恰好抽出同样的数，也不允许用抽样值，
        否则就成了方案点名拒绝的「重抽相同却绕过规格」。
        """
        plain = _plain(drawn)
        if self.mode == "export":
            _set_path(self._document, path, plain)
            self.trace.append({"path": path, "drawn": plain, "source": "draw"})
            return drawn
        frozen = _get_path(self._frozen, path)
        self.trace.append({"path": path, "drawn": plain, "frozen": frozen, "source": "spec"})
        if plain != frozen:
            # 兼容核验不通过只记录，不改变「用冻结值」这一事实；上层据此判 RNG 是否漂移。
            self.mismatches.append({"path": path, "drawn": plain, "frozen": frozen})
        return frozen

    def record(self, path: str, value: Any) -> None:
        """只读记录派生量或运行观测；回注模式下同样核验。"""
        plain = _plain(value)
        if self.mode == "export":
            _set_path(self._document, path, plain)
            return
        try:
            frozen = _get_path(self._frozen, path)
        except EpisodeSpecError:
            _set_path(self._document, path, plain)
            return
        if plain != frozen:
            self.mismatches.append({"path": path, "drawn": plain, "frozen": frozen})

    def leaf_paths(self) -> list[str]:
        """规格里全部取值点路径（回注模式用于算「有记录却没被消费」的 unused）。"""
        out: list[str] = []

        def walk(node, prefix):
            if isinstance(node, dict):
                for key, value in node.items():
                    walk(value, f"{prefix}.{key}" if prefix else key)
            else:
                out.append(prefix)

        for section in ("layout", "objects", "actions", "initializations"):
            if section in self._frozen:
                walk(self._frozen[section], section)
        return out

    def consumed_paths(self) -> list[str]:
        """本局真正经 ``value()``／``record()`` 消费过的取值点。"""
        return [item["path"] for item in self.trace]

    def to_dict(self) -> dict:
        document = copy.deepcopy(self._document)
        document.setdefault("spec_kind", SPEC_KIND)
        document["task"] = self.task
        document["identity"] = self.identity
        document["provenance"] = {
            "mode": self.mode,
            "value_points": len([item for item in self.trace if item["source"] in ("draw", "spec")]),
            "mismatches": len(self.mismatches),
        }
        return document
