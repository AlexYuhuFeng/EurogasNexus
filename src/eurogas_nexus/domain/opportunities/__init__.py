"""Opportunities: claims for human review, each with its arithmetic (design basis 2, B and J.2).

An opportunity says what the firm could do with its book and proves the figure: ordered legs
that sum to the headline, the assumptions used, what would make it untrue, its sensitivity,
its checks and the class of its weakest input. It is never an order, a nomination or an
instruction; the only next steps are to open it as a decision case, to follow it or to
dismiss it.

- :mod:`.model`: the object, typed figures, legs, checks, the reconciliation rule.
- :mod:`.claims`: claim sentences rendered from fields, never free text.
- :mod:`.controls`: false-positive controls (thresholds, staleness, input classes, checks).
- :mod:`.lifecycle`: persistence, hysteresis, material change, expiry.
- :mod:`.ranking`: the two lanes, the score and the ranking reason.
- :mod:`.evaluator`: the evaluator contract, registration and context.
- :mod:`.hedge_gap`: the reference evaluator (type G, hedge gap against policy).
- :mod:`.testing`: the harness evaluator authors test with.
"""
