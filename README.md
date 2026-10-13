# Vesper

A deterministic, refusal-first trading agent with hash-chained audit and cost-aware Bayesian gating.

**Author:** Raell, Sciencedelic Metatech

## What Vesper is

Vesper is a research artifact and reference implementation of a refusal-first decision architecture. It refuses to trade unless a Beta-Bernoulli posterior proves that edge exceeds a cost-adjusted break-even probability. Every decision, including every refusal, is appended to a hash-chained log so the entire decision history is reproducible bit-for-bit and tamper-evident.

## What Vesper is not

Vesper is **not** a live model trading system. It has no broker integration, no position sizing, no enforced stop losses, no live data feed, and no execution (slippage, partial fills, latency). See `docs/paper.tex` Section 9 for the full limitations list.

## Install

```bash
git clone https://github.com/sciencedelicmetatech/vesper
cd vesper
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"