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

V6 新值模式：xhard1～xhard4 导出的规格标 ``native-newvalue/2``，
原三档仍标 ``native-parity/1``；两类**不许互喂**（回注时 kind 与本局难度不符即拒绝）。
新值规格回注时的每条不等都要尽量归因到某个 ``decision`` 键（``value(..., decision_key=...)``），
归不了因的才算 RNG 漂移；原值规格仍要求零不等。

V7 共用布局（0928 方案第二部分 §1.2、§7.3.2）多两种模式，都只对新值族难度生效：

* **派生（derive）**：``native_episode_spec`` 传 derive 信封 ``{"envelope": "derive", "parent": 母规格,
  "layout": {"L": [...], "G": [...], "N": [...]}}``。每个取值点照常抽一次（随机流不漂移），按白名单三表分类：
  L 返回母值（``[:n]`` 模式按抽到的长度取母值前缀），N 返回由母值嵌套派生的值（:data:`NEST_RULES`），
  G 照常用抽到的值；三表都不命中即抛错（闭世界，红线 R10）。导出 ``native-layered/3`` 规格，另存
  ``layout_drawn``（L／N 点本档抽到的值）与 ``layout_paths_hit``。
* **分层回注（layered replay）**：规格类别为 ``native-layered/3``。``layout_paths_hit`` 内的点比对对象改为
  ``layout_drawn``（逐位，核随机流；不等计 ``layout_drift``），使用值仍是冻结值；其余点与原回注相同。
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

SPEC_KIND = "native-parity/1"
# V6 新值档规格版本。
SPEC_KIND_NEWVALUE = "native-newvalue/2"
# V7 派生档（xhard1～3，布局取自 xhard4 母布局）规格版本。
SPEC_KIND_LAYERED = "native-layered/3"
SPEC_KINDS = (SPEC_KIND, SPEC_KIND_NEWVALUE, SPEC_KIND_LAYERED)
LAYOUT_CLASSES = ("L", "G", "N")
PREFIX_SUFFIX = "[:n]"


def _segments_match(pattern: str, path: str) -> bool:
    """白名单模式按段匹配：``*`` 恰好匹配一段；``[:n]`` 后缀去掉后精确匹配。"""
    if pattern.endswith(PREFIX_SUFFIX):
        return pattern[: -len(PREFIX_SUFFIX)] == path
    pat, parts = pattern.split("."), path.split(".")
    return len(pat) == len(parts) and all(p == "*" or p == q for p, q in zip(pat, parts))


def classify_path(layout: dict, path: str) -> tuple[str, str]:
    """返回 ``(类别, 命中的模式)``；恰好命中一个模式才合法，否则抛 :class:`EpisodeSpecError`（R10 闭世界）。"""
    hits = [(cls, pattern) for cls in LAYOUT_CLASSES for pattern in layout.get(cls, ()) if _segments_match(pattern, path)]
    if len(hits) != 1:
        raise EpisodeSpecError(
            f"取值点 {path} 在白名单里命中 {len(hits)} 个模式 {hits}；必须恰好命中 L／G／N 之一（R10）"
        )
    return hits[0]


def _stable_int(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256("|".join(map(str, parts)).encode()).digest()[:8], "little")


def nest_binfill_targets(parent: list, drawn: list, *, seed: Any, tier: Any, **_ctx) -> list:
    """D-15：BinFill 低档逐色投入 = 母档逐色投入嵌套去掉若干块。

    本档总数取本档抽到的总数（定值 6／7／8）；从母档多重集里用独立生成器均匀去掉
    ``sum(parent) - sum(drawn)`` 块，只从多于 1 块的颜色里去（母档投入过的颜色本档至少留 1 块，
    保证「投哪几种颜色」四档一致）。不消耗环境随机流；于是 ``target_i ≤ 母 target_i ≤ 母 spawn_i`` 恒成立。
    """
    import torch

    parent = [int(v) for v in parent]
    remove = sum(parent) - sum(int(v) for v in drawn)
    if remove < 0:
        raise EpisodeSpecError(f"BinFill 嵌套派生：本档总数 {sum(drawn)} 超过母档 {sum(parent)}")
    if remove > sum(v - 1 for v in parent if v > 0):
        raise EpisodeSpecError(f"BinFill 嵌套派生：母档 {parent} 去掉 {remove} 块后会有颜色归零")
    generator = torch.Generator().manual_seed(_stable_int(seed, "binfill-nest", tier) % (2**63))
    out = list(parent)
    for _ in range(remove):
        pool = [i for i, v in enumerate(out) for _ in range(v - 1) if v > 1]
        pick = pool[int(torch.randint(0, len(pool), (1,), generator=generator).item())]
        out[pick] -= 1
    return out


OUTER_ARC_KEY = "objects.distractors.bins"


def nest_outer_arc(parent: Any, drawn: Any, *, recorder: "SpecRecorder", path: str, **_ctx) -> Any:
    """D-19（Swap 两任务外环）：低档第 i 个外环容器 = 母布局外环里被选中那段连续弧（按角度序）的第 i 个。

    弧由采样器在派生时按本档内环节奏与按钮约束选定，写进 ``recorder.nest_context[OUTER_ARC_KEY]``；
    没有上下文时退化为「按放置序取前 k 个」。母布局的位置、朝向逐字不变，只是换了挑哪 k 个。"""
    index = int(path.rsplit(".", 1)[1])
    arc = recorder.nest_context.get(OUTER_ARC_KEY) or list(range(index + 1))
    return copy.deepcopy(recorder.parent_value(f"{OUTER_ARC_KEY}.{arc[index]}"))


#: N 表模式 → 嵌套派生函数 ``(parent_value, drawn_value, *, seed, tier, recorder, path) -> value``
NEST_RULES = {"objects.target_numbers": nest_binfill_targets, f"{OUTER_ARC_KEY}.*": nest_outer_arc}


def spec_kind_for(difficulty: str | None) -> str:
    """按本局难度决定规格类别：新值族档走 V6 规格类别，其余（含不传）一律原值类别。"""
    from .difficulty import is_newvalue_difficulty

    if is_newvalue_difficulty(difficulty):
        return SPEC_KIND_NEWVALUE
    return SPEC_KIND


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

    def __init__(self, spec: dict | None, task: str, identity: dict | None = None,
                 difficulty: str | None = None):
        self.task = task
        self.identity = dict(identity or {})
        self.mismatches: list[dict] = []
        self.trace: list[dict] = []
        # 本局规格类别由难度决定（spec_kind_for）；不传 difficulty 时与 V3 行为逐字一致。
        self.spec_kind = spec_kind_for(difficulty)
        self.difficulty = difficulty
        # V7 共用布局：layered 为真时 derive／分层回注生效（§1.8 的采样器据此跳过 same_geometry 比对）
        self.layered = False
        self.layout_drawn: dict[str, Any] = {}
        self.layout_paths_hit: list[str] = []
        self.layout_overridden = 0
        self.layout_drift = 0
        # derive 模式下采样器给 N 规则的上下文（如 D-19 的外环弧）；导出时进 layout_nest_context 留痕
        self.nest_context: dict[str, Any] = {}
        if isinstance(spec, dict) and spec.get("envelope") == "derive":
            if self.spec_kind != SPEC_KIND_NEWVALUE:
                raise EpisodeSpecError(f"derive 信封只用于新值族难度（收到 {difficulty!r}）")
            parent, layout = spec.get("parent"), spec.get("layout")
            if not isinstance(parent, dict) or parent.get("spec_kind") != SPEC_KIND_NEWVALUE:
                raise EpisodeSpecError("derive 信封的母规格必须是 native-newvalue/2")
            if parent.get("task") != task:
                raise EpisodeSpecError(f"母规格属于 {parent.get('task')}，不能用于 {task}")
            if not isinstance(layout, dict) or set(layout) - set(LAYOUT_CLASSES):
                raise EpisodeSpecError(f"derive 信封的白名单只允许 {LAYOUT_CLASSES} 三表")
            self.mode = "derive"
            self.layered = True
            self.spec_kind = SPEC_KIND_LAYERED
            self._parent = copy.deepcopy(parent)
            self._layout = copy.deepcopy(layout)
            self._frozen = {}
            self._document = {"spec_kind": SPEC_KIND_LAYERED, "task": task, "identity": self.identity}
            return
        if spec is None:
            self.mode = "export"
            self._frozen: dict = {}
            self._document: dict = {
                "spec_kind": self.spec_kind,
                "task": task,
                "identity": self.identity,
            }
        else:
            # 新值族难度接受 V6 全量规格与 V7 派生规格；原值难度只接受 native-parity/1（原值与新值不许互喂）
            accepted = (SPEC_KIND_NEWVALUE, SPEC_KIND_LAYERED) if self.spec_kind == SPEC_KIND_NEWVALUE else (self.spec_kind,)
            if not isinstance(spec, dict) or spec.get("spec_kind") not in accepted:
                raise EpisodeSpecError(
                    f"native_episode_spec 需要 spec_kind∈{accepted}"
                    f"（收到 {spec.get('spec_kind') if isinstance(spec, dict) else type(spec).__name__}；"
                    "原值与新值规格不许互喂）"
                )
            if spec.get("task") != task:
                raise EpisodeSpecError(f"规格属于 {spec.get('task')}，不能用于 {task}")
            self.mode = "replay"
            if spec["spec_kind"] == SPEC_KIND_LAYERED:
                self.layered = True
                self.spec_kind = SPEC_KIND_LAYERED
                self._layered_drawn = copy.deepcopy(spec.get("layout_drawn") or {})
                self._layered_hit = set(spec.get("layout_paths_hit") or ())
                if set(self._layered_drawn) != self._layered_hit:
                    raise EpisodeSpecError("layered 规格的 layout_drawn 与 layout_paths_hit 不一致")
            self._frozen = copy.deepcopy(spec)
            self._document = copy.deepcopy(spec)

    # ------------------------------------------------------------------
    @property
    def replaying(self) -> bool:
        return self.mode == "replay"

    @property
    def newvalue(self) -> bool:
        return self.spec_kind in (SPEC_KIND_NEWVALUE, SPEC_KIND_LAYERED)

    def parent_value(self, path: str):
        """derive 模式：母规格在 ``path`` 的值（缺失返回 None）；其余模式恒为 None。"""
        if self.mode != "derive":
            return None
        try:
            return copy.deepcopy(_get_path(self._parent, path))
        except EpisodeSpecError:
            return None

    def _derive_value(self, path: str, drawn: Any, plain: Any):
        """derive 模式：抽到的值已记为 plain；按 L／G／N 返回本局使用值。"""
        cls, pattern = classify_path(self._layout, path)
        if cls == "G":
            _set_path(self._document, path, plain)
            self.trace.append({"path": path, "drawn": plain, "source": "draw"})
            return drawn
        parent = _get_path(self._parent, path)
        if cls == "L":
            if pattern.endswith(PREFIX_SUFFIX):
                if not isinstance(parent, list) or not isinstance(plain, list) or len(parent) < len(plain):
                    raise EpisodeSpecError(f"{path}：母值比本档抽到的短，不能取前缀")
                used = copy.deepcopy(parent[: len(plain)])
            else:
                used = copy.deepcopy(parent)
        else:
            rule = NEST_RULES.get(pattern)
            if rule is None:
                raise EpisodeSpecError(f"N 表模式 {pattern} 没有嵌套派生规则")
            used = rule(parent, plain, seed=self.identity.get("seed"), tier=self.difficulty, recorder=self, path=path)
        self.layout_drawn[path] = plain
        if path not in self.layout_paths_hit:
            self.layout_paths_hit.append(path)
        self.layout_overridden += int(used != plain)
        _set_path(self._document, path, used)
        self.trace.append({"path": path, "drawn": plain, "frozen": used, "source": "spec", "layout": cls})
        return used

    def value(self, path: str, drawn: Any, decision_key: str | None = None):
        """原调用点：导出模式返回抽样值并记录；回注模式返回冻结值并把抽样值记为兼容核验。

        ⚠ 回注模式**一定**返回冻结值——即便原抽样恰好抽出同样的数，也不允许用抽样值，
        否则就成了方案点名拒绝的「重抽相同却绕过规格」。

        ``decision_key``：新值模式下该取值点受哪个 ``decision`` 键控制（如 ``number_range.xhard``）；
        回注不等时记进 mismatch 供归因，原值模式忽略。
        """
        plain = _plain(drawn)
        if self.mode == "export":
            _set_path(self._document, path, plain)
            self.trace.append({"path": path, "drawn": plain, "source": "draw"})
            return drawn
        if self.mode == "derive":
            return self._derive_value(path, drawn, plain)
        frozen = _get_path(self._frozen, path)
        self.trace.append({"path": path, "drawn": plain, "frozen": frozen, "source": "spec"})
        if self.layered and path in self._layered_hit:
            # 分层回注：L／N 点核「本档抽到的值 == 派生时抽到的值」（逐位，核随机流），使用值仍是冻结值
            self.layout_overridden += int(plain != frozen)
            if plain != self._layered_drawn[path]:
                self.layout_drift += 1
                entry = self._mismatch(path, plain, self._layered_drawn[path], decision_key)
                entry["layout_drift"] = True
                self.mismatches.append(entry)
            return frozen
        if plain != frozen:
            # 兼容核验不通过只记录，不改变「用冻结值」这一事实；上层据此判 RNG 是否漂移。
            self.mismatches.append(self._mismatch(path, plain, frozen, decision_key))
        return frozen

    def _mismatch(self, path, drawn, frozen, decision_key):
        entry = {"path": path, "drawn": drawn, "frozen": frozen}
        if self.newvalue:
            # 新值模式才带归因字段；原值模式的 mismatch 形态与 V3 逐字一致。
            entry["decision_key"] = decision_key
        return entry

    def unattributed_mismatches(self) -> list[dict]:
        """归不了因的不等：原值模式下是全部 mismatch，新值模式下是没有 decision_key 的那些。"""
        if not self.newvalue:
            return list(self.mismatches)
        return [item for item in self.mismatches if not item.get("decision_key")]

    def record(self, path: str, value: Any) -> None:
        """只读记录派生量或运行观测；回注模式下同样核验。

        与 :meth:`value` 的区别只在于「不替换取值」——它同样计入 trace，因为这个路径
        确实在本局被访问过；否则 SPEC_BINDING 会把它误判成「有记录却没被消费」。
        """
        plain = _plain(value)
        self.trace.append({"path": path, "value": plain, "source": "record"})
        if self.mode in ("export", "derive"):
            # 派生局的记录点照常记本档实际值（派生量由派生运行重新导出，不取母值）
            _set_path(self._document, path, plain)
            return
        try:
            frozen = _get_path(self._frozen, path)
        except EpisodeSpecError:
            _set_path(self._document, path, plain)
            return
        if plain != frozen:
            self.mismatches.append(self._mismatch(path, plain, frozen, None))

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
        document.setdefault("spec_kind", self.spec_kind)
        document["task"] = self.task
        document["identity"] = self.identity
        document["provenance"] = {
            "mode": self.mode,
            "value_points": len([item for item in self.trace if item["source"] in ("draw", "spec")]),
            "mismatches": len(self.mismatches),
        }
        if self.newvalue:
            document["provenance"]["unattributed_mismatches"] = len(self.unattributed_mismatches())
        if self.mode == "derive":
            # 派生规格：本局实际使用值 + 本档抽到的 L／N 值（回注时核随机流）；layout_parent 由派生脚本写入
            document["layout_drawn"] = copy.deepcopy(self.layout_drawn)
            document["layout_paths_hit"] = sorted(self.layout_paths_hit)
            document["layout_nest_context"] = copy.deepcopy(self.nest_context)
        return document
