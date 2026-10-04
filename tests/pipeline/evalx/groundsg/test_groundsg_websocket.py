"""GroundSG 两侧经真实 websocket 客户端连回环假服务（slow；1003 评估计划 1.3，子任务 S3）。

新侧走生产默认的 ``mme_client.make_recording_client``（``MMEVLAWebsocketClientPolicy`` 子类），原侧走生产默认的
TCP 探测 + 真实 ``MMEVLAWebsocketClientPolicy``；假服务经 msgpack 收发，其余同 ``test_groundsg_official_adapter``。
"""
from __future__ import annotations

import pytest

import groundsg_fakes as F


@pytest.mark.slow
@pytest.mark.parametrize("variant", F.VARIANTS)
def test_real_websocket_clients_match(tmp_path, variant):
    total = {"payload": 0, "exec": 0, "terminal": 0}
    for name, (plan, max_steps) in {"success": (F.Plan(success_at=37), 60), "timeout": (F.Plan(), 40)}.items():
        fs_new, fs_orig = F.FakeServer(), F.FakeServer()
        lb_new, lb_orig = F.LoopbackServer(fs_new), F.LoopbackServer(fs_orig)
        try:
            wn, wo = F.World(default=plan), F.World(default=plan)
            new = F.NewSide(variant, max_steps, tmp_path / name / "new", wn, port=lb_new.port, real_client=True)
            orig = F.OrigSide(variant, max_steps, tmp_path / name / "orig", wo, port=lb_orig.port, real_client=True)
            new.server, orig.server = fs_new, fs_orig
            rn, ro = new.run(F.identity()), orig.run(F.identity())
        finally:
            lb_new.close()
            lb_orig.close()
        assert len(fs_new.log) > 3 and rn["status"] == ro["status"]
        # 新侧录制客户端的逐消息计时已按 mme_client 口径汇总
        assert rn["timing"]["infer"]["n"] == rn["decisions"]
        d = F.diffs((new, wn, rn), (orig, wo, ro))
        for k in total:
            total[k] += d[k]
    assert total == {"payload": 0, "exec": 0, "terminal": 0}, total
    print(f"OFFICIAL_ADAPTER_WS=PASS variant={variant} payload_diff=0 exec_diff=0 terminal_diff=0")
