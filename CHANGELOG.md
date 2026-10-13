# Changelog

## [1.0.0] - 2026-01-01

Initial release.

- Deterministic, hash-chained decision log with tamper detection.
- Beta-Bernoulli posterior with Lentz continued fraction for `prob_above`.
- Refusal-first decider with cost-aware break-even gate.
- Continuous probing and exploration phase to prevent posterior stagnation.
- Multi-source real data fetch (Kraken, stooq, Binance) with synthetic fallback.
- Walk-forward framework comparing frozen and online posterior adaptation.
- Multi-seed aggregation.
- Full paper: `docs/paper.tex`.