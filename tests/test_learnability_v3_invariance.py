"""D61 blocker D — mechanical invariance tests required by
PREREGISTRATION_LEARNABILITY_V3.md, committed BEFORE the v3 run:
the rotation permutation is an exact bijection (multiset, count,
feature-side group sizes), respects the displacement bounds, and is
deterministically reproducible; the CI bootstrap is a TRUE circular
moving-block scheme (overlapping starts) with exact boundary count.
"""
import numpy as np

from lab.tools.learnability_v3 import (D28_MS,
                                       circular_moving_block_sequences,
                                       draw_rotations,
                                       eligible_rotation_boundaries,
                                       rotate_labels)

DAY = 86_400_000


def make_data(n_boundaries=120, seed=7):
    rng = np.random.default_rng(seed)
    ts, y = [], []
    t0 = 1_600_000_000_000
    for u in range(n_boundaries):
        t = t0 + u * DAY                       # daily boundaries
        for _ in range(int(rng.integers(1, 6))):   # UNEQUAL group sizes
            ts.append(t)
            y.append(float(rng.normal()))
    return np.array(ts, np.int64), np.array(y)


def test_rotation_exact_multiset_and_count():
    ts, y = make_data()
    ub = np.unique(ts)
    for j in eligible_rotation_boundaries(ub)[:20]:
        yp = rotate_labels(y, ts, int(j))
        assert len(yp) == len(y)                       # count
        assert sorted(yp.tolist()) == sorted(y.tolist())   # exact multiset
        # bijection, not value-copying: rotation by s positions
        counts = np.unique(ts, return_counts=True)[1]
        s = int(np.cumsum(counts)[int(j) - 1])
        assert np.array_equal(yp, np.concatenate([y[s:], y[:s]]))


def test_rotation_feature_side_group_sizes_unchanged():
    ts, y = make_data()
    # slots (feature side) are untouched by construction: the permutation
    # returns ONLY a rearranged label vector; ts is never modified
    before = np.unique(ts, return_counts=True)
    _ = rotate_labels(y, ts, int(eligible_rotation_boundaries(
        np.unique(ts))[0]))
    after = np.unique(ts, return_counts=True)
    assert np.array_equal(before[0], after[0])
    assert np.array_equal(before[1], after[1])


def test_rotation_displacement_bounds():
    ts, _y = make_data()
    ub = np.unique(ts)
    span = int(ub[-1]) - int(ub[0])
    for j in eligible_rotation_boundaries(ub):
        d = int(ub[j]) - int(ub[0])
        assert d >= D28_MS and d <= span - D28_MS


def test_rotation_deterministic_reproduction():
    ts, _y = make_data()
    assert draw_rotations(ts, 50, seed=123) == draw_rotations(ts, 50,
                                                              seed=123)
    assert draw_rotations(ts, 50, seed=123) != draw_rotations(ts, 50,
                                                              seed=124)


def test_bootstrap_is_true_circular_moving_block():
    u, L = 50, 7
    seqs = circular_moving_block_sequences(u, L, 400, seed=9)
    # exact boundary count per resample
    assert all(len(s) == u for s in seqs)
    # blocks are L consecutive indices with circular wrap
    starts = set()
    for s in seqs:
        for k in range(0, u, L):
            blk = s[k:k + L]
            if len(blk) < 2:
                continue
            assert all((blk[i + 1] - blk[i]) % u == 1
                       for i in range(len(blk) - 1))
            starts.add(int(blk[0]))
    # MOVING blocks: starts cover (nearly) every position, not a fixed
    # tiling — overlapping starts must appear
    assert len(starts) > u // L + 5
    # deterministic
    s1 = circular_moving_block_sequences(u, L, 5, seed=42)
    s2 = circular_moving_block_sequences(u, L, 5, seed=42)
    assert all(np.array_equal(a, b) for a, b in zip(s1, s2))
