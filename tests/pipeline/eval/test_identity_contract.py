"""C13 身份契约：评估步数上限的取法、执行身份行的结构核对、三处 key 函数一致。

- 有效上限取 ``hard_specs.TIER_MAX_STEPS[tier]``：经真实 ``SeatRunner.run_one`` 核对 builder、环境构建、策略三处
  拿到的都是该档上限；身份行的 ``effective_max_steps`` 与之不等即运行阻塞（退出码 3）。
  xhard0 的取值不下断言（计划 Q16 待定）：本文件只参数化 xhard1～5 的档。
- 三处 key 函数（``env_client.v8_key／key_of``、``eval_manifest.v8_key``、``eval_report.key_of``）对同一身份给出同一个键，
  且键按契约手写为 ``<task>_<tier>_<seed>``；同 seed 不同档不碰撞。
"""
from __future__ import annotations

import pytest

import eval_fakes as F


def _cells_by_tier() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for task, tier in F.v9_cells_sorted():
        out.setdefault(tier, (task, tier))
    return out


TIERS = sorted(_cells_by_tier())  # V9 实际交付的档（不含 xhard0）


@pytest.mark.parametrize("tier", TIERS)
@pytest.mark.parametrize("policy", ("mme", "smvla"))
def test_effective_cap_reaches_builder_env_and_policy(tmp_path, monkeypatch, tier, policy):
    task, _ = _cells_by_tier()[tier]
    ident = F.packaged_identity(task, tier, 0)
    cap = F.hard_specs().TIER_MAX_STEPS[tier]
    assert ident["effective_max_steps"] == cap
    seen = {}
    sm = F.smvla_client()
    real = sm.run_episode

    def spy_smvla(session, identity, conn_info, recorder=None, **kw):
        seen.update(kw=kw, conn=dict(conn_info), step_cap=session.step_cap)
        return real(session, identity, conn_info, recorder, conn=F.FakeSmvlaConn(F.FakePolicyServer()), **kw)

    world = F.World()
    if policy == "mme":
        mod = F.mme_policy(monkeypatch, F.FakePolicyServer())
        orig = mod.run_episode

        def spy_mme(session, identity, conn_info, recorder):
            seen.update(kw={}, conn=dict(conn_info), step_cap=session.step_cap)
            return orig(session, identity, conn_info, recorder)

        pol = type("P", (), {"run_episode": staticmethod(spy_mme)})
    else:
        import inspect

        spy_smvla.__signature__ = inspect.signature(real)
        pol = type("P", (), {"run_episode": staticmethod(spy_smvla)})
    runner = F.make_runner(tmp_path, policy, pol, world)
    rec = runner.run_one(ident, attempt=1)
    assert rec["status"] == "success"
    assert world.builders[0].max_steps == cap  # builder 按 (task, 有效上限) 建
    assert world.make_calls[0][2] == cap  # make_env_for_episode(max_steps=有效上限)
    assert seen["step_cap"] == cap and seen["conn"]["max_steps"] == cap
    if policy == "smvla":  # smvla 签名带 max_steps／reset_retries：显式传入有效上限、reset 不重试
        assert seen["kw"] == {"max_steps": cap, "reset_retries": 0}
    else:  # mme 只读 conn_info
        assert seen["kw"] == {}


@pytest.mark.parametrize("field,delta", [("effective_max_steps", -1), ("seed", 1), ("spec_sha256", None),
                                         ("tier", None), ("candidate", 1)])
def test_identity_mismatch_blocks_run(tmp_path, monkeypatch, field, delta):
    """身份行任一项与 builder 真实解析不符（或有效上限不等于该档上限）→ RUN_BLOCKED，写 run_blocked 行，不建环境。"""
    task, tier = F.v9_cells_sorted()[0]
    ident = F.packaged_identity(task, tier, 0)
    bad = dict(ident)
    if field == "spec_sha256":
        bad[field] = "f" * 64
    elif field == "tier":
        other = next(t for t in TIERS if t != tier)
        bad["tier"] = other
        bad["effective_max_steps"] = F.hard_specs().TIER_MAX_STEPS[other]
    else:
        bad[field] = bad[field] + delta
    bad["key"] = f"{bad['task']}_{bad['tier']}_{bad['seed']}"
    world = F.World()
    runner = F.make_runner(tmp_path, "mme", F.mme_policy(monkeypatch, F.FakePolicyServer()), world)
    with pytest.raises(SystemExit) as ei:
        runner.run_one(bad, attempt=1)
    assert ei.value.code == F.env_client().EXIT_BLOCKED
    (row,) = F.read_jsonl(tmp_path / "s00" / "mme" / "results.jsonl")
    assert row["run_blocked"] is True and row["status"] == "error" and row["error"].startswith("IDENTITY_MISMATCH")
    assert world.make_calls == [] and world.envs == []


def test_validate_identity_row_structure():
    ec = F.env_client()
    task, tier = F.v9_cells_sorted()[0]
    good = F.packaged_identity(task, tier, 0)
    tm = F.hard_specs().TIER_MAX_STEPS
    assert ec.validate_v8_identity(good, tm) is None
    cases = {
        "缺字段": {k: v for k, v in good.items() if k != "spec_sha256"},
        "seed 为浮点": dict(good, seed=float(good["seed"])),
        "seed 为 bool": dict(good, seed=True),
        "candidate 为字符串": dict(good, candidate="3"),
        "source_episode 为浮点": dict(good, source_episode=1.0),
        "指纹长度不对": dict(good, spec_sha256="ab"),
        "key 与字段不符": dict(good, key=good["key"] + "x"),
        "上限与档不符": dict(good, effective_max_steps=good["effective_max_steps"] + 1),
    }
    for name, row in cases.items():
        assert ec.validate_v8_identity(row, tm), name


def test_check_identity_requires_exact_int_candidate():
    """candidate 两侧须同为 null 或同一整数；True 与 1 不算相等。"""
    ec = F.env_client()
    tm = F.hard_specs().TIER_MAX_STEPS
    task, tier = F.v9_cells_sorted()[0]
    want = F.packaged_identity(task, tier, 0)
    resolved = {"tier": tier, "seed": want["seed"], "candidate": want["candidate"], "spec_sha256": want["spec_sha256"]}
    assert ec.check_identity(resolved, want, v8=True, tier_max=tm) is None
    assert ec.check_identity(dict(resolved, candidate=None), want, v8=True, tier_max=tm)
    assert ec.check_identity(dict(resolved, candidate=1), dict(want, candidate=1), v8=True, tier_max=tm) is None
    assert ec.check_identity(dict(resolved, candidate=1), dict(want, candidate=True), v8=True, tier_max=tm)
    assert ec.check_identity(dict(resolved, candidate=None), dict(want, candidate=None), v8=True, tier_max=tm) is None
    assert ec.check_identity(resolved, dict(want, spec_sha256=None), v8=True, tier_max=tm)


def test_three_key_functions_agree():
    ec, em, er = F.env_client(), F.eval_manifest(), F.eval_report()
    rows = [F.packaged_identity(task, tier, 0) for task, tier in F.v9_cells_sorted()[:6]]
    for r in rows:
        want = f"{r['task']}_{r['tier']}_{r['seed']}"
        bare = {k: v for k, v in r.items() if k != "key"}
        assert ec.v8_key(bare) == em.v8_key(bare) == er.key_of(bare) == want
        assert ec.key_of(r) == er.key_of(r) == want  # 行内带 key 时直接用它
    # 同 seed 不同档：三处都给出不同的键
    r = rows[0]
    other = dict(r, tier=next(t for t in TIERS if t != r["tier"]))
    other.pop("key")
    assert ec.v8_key(other) != ec.v8_key({k: v for k, v in r.items() if k != "key"})
    assert em.v8_key(other) == ec.v8_key(other) == er.key_of(other)


def test_manifest_join_writes_tier_cap_and_contract_key():
    """清单第 3 步按 TIER_MAX_STEPS[tier] 写 effective_max_steps、按契约写 key；与客户端核对口径一致。"""
    em, hs = F.eval_manifest(), F.eval_manifest().load_hard_specs()
    task, tier = F.v9_cells_sorted()[0]
    ident = F.packaged_identity(task, tier, 0)
    src = [{"task": task, "episode": ident["builder_episode"], "tier": tier, "seed": ident["seed"],
            "candidate": ident["candidate"], "source_episode": None, "round": None, "shard": None}]
    delivery = {"schema": em.DELIVERY_SCHEMA, "rows": [{"task": task, "tier": tier, "seed": ident["seed"],
                                                          "candidate": ident["candidate"],
                                                          "spec_sha256": ident["spec_sha256"]}]}
    (row,) = em.join_delivery(src, delivery, hs)
    assert row == {k: ident[k] for k in em.SHARD_ROW_KEYS}
    assert F.env_client().validate_v8_identity(row, F.hard_specs().TIER_MAX_STEPS) is None
