# Monte Carlo Pricing Engine

[![CI](https://github.com/SohamMessi10/Monte-Carlo-Pricing-Engine/actions/workflows/ci.yml/badge.svg)](https://github.com/SohamMessi10/Monte-Carlo-Pricing-Engine/actions/workflows/ci.yml)

A C++20 Monte Carlo option-pricing engine with Python bindings (`mcpricer`).

> Work in progress — see [PROGRESS.md](PROGRESS.md). Every number in this README is measured;
> hardware, compiler and flags are recorded next to it.

## Features (planned)

- European options under GBM (exact simulation), validated against Black–Scholes
- Multithreaded with `std::thread`; results bit-identical for any thread count
- Variance reduction: antithetic variates, control variates
- Path-dependent products: arithmetic Asian (geometric control variate), discrete up-and-out barrier
- Quasi-Monte Carlo: Sobol (Joe–Kuo) + Brownian bridge, randomized for error bars
- Heston model (full-truncation Euler) against a semi-analytic reference

## Install (development)

Requires a C++20 compiler and Python ≥ 3.11.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --group dev
python -m pip install --no-build-isolation -ve .
python -m pytest
```

## Usage

_TODO (milestone 1)._

## Results

_TODO (milestone 7)._

## Architecture, testing, limitations

_TODO (milestone 8)._
