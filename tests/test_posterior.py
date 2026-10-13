from vesper.posterior import BetaPosterior


def test_prior_mean():
    p = BetaPosterior()
    assert p.mean == 0.5
    assert p.n == 0


def test_update_win():
    p = BetaPosterior()
    for _ in range(9):
        p.update(True)
    p.update(False)
    assert p.n == 10
    # Prior (1, 1) + 9 wins + 1 loss = alpha=10, beta=2, mean = 10/12
    assert abs(p.mean - 10.0 / 12.0) < 1e-9


def test_prob_above_symmetric():
    p = BetaPosterior(5.0, 5.0)
    assert abs(p.prob_above(0.5) - 0.5) < 0.02


def test_prob_above_high():
    p = BetaPosterior(20.0, 5.0)
    assert p.prob_above(0.5) > 0.99


def test_prob_above_low():
    p = BetaPosterior(5.0, 20.0)
    assert p.prob_above(0.5) < 0.01


def test_clone_preserves_state():
    p = BetaPosterior(7.0, 3.0)
    c = p.clone()
    assert c.alpha == 7.0
    assert c.beta == 3.0
    c.update(True)
    assert p.alpha == 7.0