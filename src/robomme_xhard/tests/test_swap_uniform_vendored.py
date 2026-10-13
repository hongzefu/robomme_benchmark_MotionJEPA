"""核对引入算法的字节身份与三种槽图的确定性规划。"""

import hashlib
from pathlib import Path

import pytest
import torch

from robomme_xhard.collision import swap_uniform as su


def test_source_sha256():
    assert hashlib.sha256(Path(su.__file__).read_bytes()).hexdigest() == (
        "f4a1a8c08c629e8924ff1a0d37e9acdd4c7bcfee32ba7be80cf18e6328d85821"
    )


@pytest.mark.parametrize("n,edges,expected", [
    (4, {(0, 1), (1, 2), (2, 3), (0, 3)},
     [(2, 1), (0, 3), (2, 1), (0, 3), (2, 3), (1, 0)]),
    (4, {(0, 1), (2, 3)},
     [(1, 0), (2, 3), (1, 0), (2, 3), (0, 1), (3, 2)]),
    (3, {(0, 1), (0, 2), (1, 2)},
     [(2, 0), (2, 1), (1, 0), (2, 0), (0, 1), (1, 2)]),
])
def test_graph_and_deterministic_plan(n, edges, expected):
    calls = []

    def feasible(a, b):
        calls.append((a, b))
        return (a, b) in edges

    adj = su.slot_pair_graph(n, feasible)
    assert calls == [(a, b) for a in range(n) for b in range(a + 1, n)]
    assert adj == [[a != b and (min(a, b), max(a, b)) in edges
                    for b in range(n)] for a in range(n)]
    assert su.isolated_slots(adj) == []
    for _ in range(2):
        plan = su.plan_balanced_swaps(adj, 6, torch.Generator().manual_seed(123))
        assert plan.pairs == expected
        assert plan.counts == [12 // n] * n
        assert plan.spread == 0
        assert plan.tries == 1
        problems, stats = su.verify_swap_sequence(adj, plan.pairs)
        assert problems == []
        assert stats.slot_pairs == plan.slot_pairs
    adj.append([False] * n)
    for row in adj:
        row.append(False)
    assert su.isolated_slots(adj) == [n]
