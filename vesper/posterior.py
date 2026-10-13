"""Beta-Bernoulli posterior over win probability."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class BetaPosterior:
    alpha: float = 1.0
    beta: float = 1.0

    def update(self, win: bool) -> None:
        if win:
            self.alpha += 1.0
        else:
            self.beta += 1.0

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def n(self) -> float:
        return self.alpha + self.beta - 2.0

    def clone(self) -> "BetaPosterior":
        return BetaPosterior(self.alpha, self.beta)

    def prob_above(self, p0: float) -> float:
        """P(p > p0) for p ~ Beta(alpha, beta). Regularized incomplete beta."""
        if self.n < 1:
            return 0.0
        a, b = self.alpha, self.beta

        def betacf(a: float, b: float, x: float) -> float:
            MAXIT, EPS, FPMIN = 200, 3.0e-12, 1.0e-300
            qab, qap, qam = a + b, a + 1.0, a - 1.0
            c, d = 1.0, 1.0 - qab * x / qap
            if abs(d) < FPMIN:
                d = FPMIN
            d = 1.0 / d
            h = d
            for m in range(1, MAXIT + 1):
                m2 = 2 * m
                aa = m * (b - m) * x / ((qam + m2) * (a + m2))
                d = 1.0 + aa * d
                if abs(d) < FPMIN:
                    d = FPMIN
                c = 1.0 + aa / c
                if abs(c) < FPMIN:
                    c = FPMIN
                d = 1.0 / d
                h *= d * c
                aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
                d = 1.0 + aa * d
                if abs(d) < FPMIN:
                    d = FPMIN
                c = 1.0 + aa / c
                if abs(c) < FPMIN:
                    c = FPMIN
                d = 1.0 / d
                delta = d * c
                h *= delta
                if abs(delta - 1.0) < EPS:
                    break
            return h

        def betai(a: float, b: float, x: float) -> float:
            if x <= 0.0:
                return 0.0
            if x >= 1.0:
                return 1.0
            lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
            front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
            if x < (a + 1.0) / (a + b + 2.0):
                return front * betacf(a, b, x) / a
            return 1.0 - front * betacf(b, a, 1.0 - x) / b

        return 1.0 - betai(a, b, p0)