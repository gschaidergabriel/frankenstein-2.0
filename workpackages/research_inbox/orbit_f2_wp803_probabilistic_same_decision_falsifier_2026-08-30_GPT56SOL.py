"""Research-only falsifier for a successor WP803 probabilistic evaluator layer.

This file does NOT change accepted F2-WP-803 v2 semantics. It demonstrates why the
existing hard CORRECT/INCORRECT score cannot by itself evaluate probability quality:
two predictors can make the same hard decisions and therefore receive the same hard
score while one is materially more overconfident and scores worse under proper losses.
"""
from __future__ import annotations
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Metrics:
    accuracy: float
    hard_score_mean: float
    brier: float
    log_loss: float


def evaluate(y: tuple[int, ...], p: tuple[float, ...]) -> Metrics:
    if len(y) != len(p) or not y:
        raise ValueError("aligned non-empty y/p required")
    probs = tuple(min(max(float(v), 1e-12), 1.0 - 1e-12) for v in p)
    hard = tuple(1 if v >= 0.5 else 0 for v in probs)
    correct = tuple(int(a == b) for a, b in zip(y, hard))
    return Metrics(
        accuracy=sum(correct) / len(correct),
        hard_score_mean=sum(1 if c else -1 for c in correct) / len(correct),
        brier=sum((v - t) ** 2 for t, v in zip(y, probs)) / len(y),
        log_loss=-sum(t * math.log(v) + (1-t) * math.log(1-v) for t, v in zip(y, probs)) / len(y),
    )


def main() -> None:
    # Same hard decisions by construction, but two are wrong. Greater confidence in
    # the same wrong decisions must be distinguishable by proper probabilistic scores.
    y = (1, 1, 1, 1, 0, 0, 0, 0, 1, 0)
    p_cal = (0.70, 0.68, 0.31, 0.66, 0.36, 0.29, 0.71, 0.34, 0.64, 0.38)
    p_over = tuple(0.99 if p >= 0.5 else 0.01 for p in p_cal)

    cal = evaluate(y, p_cal)
    over = evaluate(y, p_over)

    assert cal.accuracy == over.accuracy == 0.8
    assert cal.hard_score_mean == over.hard_score_mean == 0.6
    assert cal.brier < over.brier
    assert cal.log_loss < over.log_loss

    print({"calibrated": cal.__dict__, "overconfident_same_decision": over.__dict__})


if __name__ == "__main__":
    main()
