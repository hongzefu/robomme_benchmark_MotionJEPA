"""结果归并与候选角色：运行级单写者、单文件原子发布、可重放终态日志。"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import tempfile
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from ..candidates.io import canonical_json, candidate_key, load_candidates, write_candidates

ROOT = Path(__file__).resolve().parents[3]


class StateError(ValueError):
    """输入重复、身份冲突、状态不一致或迁移未完成。"""


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".publish-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_json(path, value):
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def read_rows(path, *, incomplete_tail=False):
    path = Path(path)
    if not path.exists():
        return []
    raw = path.read_bytes()
    lines = raw.splitlines(keepends=True)
    rows = []
    for index, line in enumerate(lines):
        if not line.endswith(b"\n") and incomplete_tail and index == len(lines) - 1:
            write_json(path.with_suffix(path.suffix + ".interrupted.json"),
                       {"offset": sum(len(v) for v in lines[:index]), "ignored_bytes": len(line), "reason": "末尾未完成行，未当作终态"})
            break
        if not line.strip():
            raise StateError(f"结果日志出现空行：{path}/{index + 1}")
        rows.append(json.loads(line))
    return rows


def result_key(row):
    return row["kind"], row["task"], row["difficulty"], row["episode"]


def unique_rows(rows):
    result = {}
    for row in rows:
        key = result_key(row)
        if key in result:
            raise StateError(f"唯一结果表重复键：{key}")
        result[key] = row
    return result


def run_root(run_id):
    if not run_id or run_id.startswith(".") or "/" in run_id or "\\" in run_id:
        raise StateError(f"运行编号非法：{run_id}")
    root = ROOT / "artifacts/injection" / run_id
    if root.is_symlink() or root.resolve().parent != (ROOT / "artifacts/injection").resolve():
        raise StateError("运行目录不能使用符号链接或越界")
    return root


def assert_not_migrating(root):
    if (root / "rollout/logs/archive.json").exists():
        raise StateError("该诊断运行已归档，不能复用已清理的成品；复验请使用新编号")
    status = root / "rollout/logs/migration/state.json"
    if status.exists() and json.loads(status.read_text())["state"] != "complete":
        raise StateError("产物迁移未完成，须先恢复迁移，禁止启动普通消费入口")


def import_candidates(source, target, run_id):
    source, target = Path(source).resolve(), Path(target)
    source_run = source.parent.parent
    assert_not_migrating(source_run)
    source_sha = file_sha(source)
    header, rows = load_candidates(source, repo_root=ROOT)
    if target.exists():
        existing, _ = load_candidates(target, repo_root=ROOT)
        if existing["identity_sha256"] != header["identity_sha256"]:
            raise StateError("已导入副本身份与请求来源不一致")
        return existing
    header = copy.deepcopy(header)
    header.update(parent_run_id=header["run_id"], parent_candidates_sha256=source_sha, run_id=run_id)
    header.pop("roles", None)
    for row in rows:
        row["role"], row["error_type"] = "pending", None
    write_candidates(target, header, rows)
    if source_sha != file_sha(source):
        raise StateError("导入候选时源文件发生变化")
    return header


def assign_roles(header, candidates, results, completed_reset_groups=()):
    """结果决定角色；局部 scope 未执行的候选保持 pending，足额 test 的后续才标 unused。"""
    index = {candidate_key(row): row for row in candidates}
    records = unique_rows(results)
    if len(index) != len(candidates):
        raise StateError("候选重复")
    config = {(g["task"], g["difficulty"]): g for g in header["delivery_config_snapshot"]["groups"]}
    succeeded = Counter()
    result_by_candidate = {}
    for key in sorted(records):
        row = records[key]
        ck = candidate_key(row)
        candidate = index.get(ck)
        if candidate is None or ck in result_by_candidate:
            raise StateError(f"额外结果或同候选跨 kind 重复：{key}")
        expected_kind = "h5" if candidate["split"] == "train" else "reset"
        if row["kind"] != expected_kind or row["spec_sha256"] != candidate["spec_sha256"] or row["seed"] != candidate["seed"]:
            raise StateError(f"结果与候选身份不符：{key}")
        if type(row.get("ok")) is not bool:
            raise StateError(f"结果缺少布尔 ok：{key}")
        if row["kind"] == "reset" and row["ok"] != (row["outcome"] == "通过"):
            raise StateError(f"reset 的 ok 与 outcome 冲突：{key}")
        row["split"] = candidate["split"]
        group = (row["task"], row["difficulty"])
        bucket = (row["kind"], *group)
        if row["kind"] == "reset":
            row["counted"] = succeeded[bucket] < header["delivery_config_snapshot"]["extra_candidates"]
        if row["ok"]:
            if row.get("error_type") is not None:
                raise StateError(f"成功结果与异常类型冲突：{key}")
            if row["kind"] == "h5" and (not row.get("h5_sha256") or not row.get("h5_path") or not row.get("h5_bytes")):
                raise StateError(f"成功 h5 缺少成品路径或散列：{key}")
            succeeded[bucket] += 1
            target = config[group]["target_h5"] if row["kind"] == "h5" else header["delivery_config_snapshot"]["extra_candidates"]
            row["role"] = "primary" if succeeded[bucket] <= target else "spare"
            row["error_type"] = None
        else:
            row["role"] = "failed"
            row.setdefault("error_type", None)
        if row["kind"] == "reset":
            row["delivered"] = row["role"] == "primary"
        result_by_candidate[ck] = row
    completed = set(completed_reset_groups)
    extra = header["delivery_config_snapshot"]["extra_candidates"]
    for candidate in candidates:
        row = result_by_candidate.get(candidate_key(candidate))
        if row is not None:
            candidate["role"], candidate["error_type"] = row["role"], row["error_type"]
        else:
            group = (candidate["task"], candidate["difficulty"])
            unused = candidate["split"] == "test" and "/".join(group) in completed and succeeded[("reset", *group)] >= extra
            candidate["role"], candidate["error_type"] = ("unused" if unused else "pending"), None
    header["roles"] = dict(Counter(f"{r['split']}/{r['role']}" for r in candidates))
    return [records[key] for key in sorted(records)]


class RunStore:
    """结果文件先发布，再派生候选角色；恢复重放完整终态，不声称两文件整体原子。"""

    def __init__(self, root, label=None):
        self.root = Path(root)
        if label is not None and (not label or "/" in label or "\\" in label or label.startswith(".")):
            raise StateError("label 非法")
        self.state = self.root / "rollout" if label is None else self.root / "rollout/logs/smoke" / label
        self.candidates = self.root / "candidates/candidates.jsonl" if label is None else self.state / "candidates.jsonl"
        self.results_path = self.state / "results.jsonl"
        self.logs = self.state / "logs"
        self.label = label

    @contextmanager
    def locked(self):
        assert_not_migrating(self.root)
        self.logs.mkdir(parents=True, exist_ok=True)
        with (self.root / "rollout/logs/writer.lock").open("a+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            assert_not_migrating(self.root)
            if self.label and not self.candidates.exists():
                import_candidates(self.root / "candidates/candidates.jsonl", self.candidates, self.root.name + "-" + self.label)
            yield self

    def load(self):
        header, candidates = load_candidates(self.candidates, repo_root=ROOT)
        results = read_rows(self.results_path)
        unique_rows(results)
        return header, candidates, results

    def completed_groups(self):
        path = self.logs / "reset_completed.json"
        return json.loads(path.read_text()) if path.exists() else []

    def publish(self, results, *, completed_groups=None, interrupt_after_results=False):
        header, candidates, _ = self.load()
        completed = self.completed_groups() if completed_groups is None else list(completed_groups)
        rows = assign_roles(header, candidates, copy.deepcopy(results), completed)
        # 检查身份与字段后才写入；两文件之间中断由下一次恢复重新派生角色。
        from ..candidates.io import validate_candidates
        validate_candidates(header, candidates, repo_root=ROOT)
        atomic_text(self.results_path, "".join(canonical_json(row) + "\n" for row in rows))
        write_json(self.logs / "reset_completed.json", completed)
        if interrupt_after_results:
            raise InterruptedError("测试中断点：结果已发布，候选尚未回写")
        write_candidates(self.candidates, header, candidates, replace=True)
        return rows

    def normalize(self, raw, kind, *, candidate_index=None):
        if candidate_index is None:
            _, candidates, _ = self.load()
            candidate_index = {candidate_key(r): r for r in candidates}
        candidate = candidate_index.get(candidate_key(raw))
        if candidate is None:
            raise StateError("终态记录不属于当前候选")
        row = copy.deepcopy(raw)
        if row.get("spec_sha256", candidate["spec_sha256"]) != candidate["spec_sha256"]:
            raise StateError("终态规格散列冲突")
        if row.get("split", candidate["split"]) != candidate["split"] or row["seed"] != candidate["seed"]:
            raise StateError("终态划分或 seed 冲突")
        row.update(kind=kind, spec_sha256=candidate["spec_sha256"], split=candidate["split"])
        row.setdefault("error_type", None)
        if kind == "reset":
            if "ok" not in row:
                row["ok"] = row["outcome"] == "通过"
            row.update(h5_path=None, h5_sha256=None, h5_bytes=None)
        elif not row.get("ok"):
            row.update(h5_path=None, h5_sha256=None, h5_bytes=None)
        return row

    def merge(self, incoming):
        _, _, old = self.load()
        index = unique_rows(old)
        seen = set()
        for row in incoming:
            key = result_key(row)
            if key in seen:
                raise StateError(f"输入批次重复终态：{key}")
            seen.add(key)
            if key in index:
                left, right = copy.deepcopy(index[key]), copy.deepcopy(row)
                for record in (left, right):
                    record.pop("role", None)
                if row["kind"] == "reset":
                    for field in ("counted", "delivered"):
                        if field not in right:
                            right[field] = left[field]
                if canonical_json(left) != canonical_json(right):
                    raise StateError(f"同键终态冲突，拒绝猜测新旧：{key}")
            else:
                index[key] = row
        return self.publish(list(index.values()))

    def audit(self):
        header, candidates, results = self.load()
        expected_header, expected_candidates = copy.deepcopy(header), copy.deepcopy(candidates)
        expected_results = assign_roles(expected_header, expected_candidates, copy.deepcopy(results), self.completed_groups())
        if expected_candidates != candidates or expected_header != header or expected_results != results:
            raise StateError("候选与结果角色不一致，必须先恢复")
        counts = Counter(r["role"] for r in candidates)
        return {"rows": len(candidates), "results": len(results), "mismatch": 0, "duplicates": 0,
                "pending": counts["pending"], "unused": counts["unused"], "roles": header["roles"]}
