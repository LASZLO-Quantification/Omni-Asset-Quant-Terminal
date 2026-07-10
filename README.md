<div align="center">

# Omni-Asset Quant Terminal

### A runnable reference loop for systematic investment research

**Signal -> constrained execution preview -> ledger -> state rebuild -> backtest**

[![CI](https://github.com/LASZLO-Quantification/Omni-Asset-Quant-Terminal/actions/workflows/ci.yml/badge.svg)](https://github.com/LASZLO-Quantification/Omni-Asset-Quant-Terminal/actions/workflows/ci.yml)
[![Stack](https://img.shields.io/badge/Stack-Streamlit_%7C_Python-111827?style=flat-square&logo=python&logoColor=F7B73D)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-111827?style=flat-square)](LICENSE)

</div>

## Purpose

This repository is an executable reference implementation for a small,
auditable quant workflow. It demonstrates how deterministic strategy outputs,
portfolio constraints, execution costs, an append-only ledger, state rebuild,
and backtests can share explicit contracts.

It is not a broker integration and does not place market orders. Confirming an
execution writes a record to a local research ledger only.

## Reference Loop

```text
market data -> strategy signal -> execution estimate -> confirmation
                                                    -> local ledger
                                                    -> portfolio state
                                                    -> replay / backtest / export
```

| Layer | Included reference |
| --- | --- |
| Signals | Value Averaging, DCA, and rebalance calculations |
| Constraints | Cash, position, fee, and slippage limits |
| State | Local portfolio state plus deterministic ledger rebuild |
| Research | Cross-asset diagnostics, forward plan, and monthly backtest |
| Interchange | Ledger mapping, CSV export, Markdown report, ZIP snapshot |

See [Reference Architecture](docs/REFERENCE_ARCHITECTURE.md) for contracts and
extension points. See [Open-Source Boundary](docs/OPEN_SOURCE_BOUNDARY.md) for
what belongs in a public reference and what must remain private.

## Quick Start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Open `http://localhost:8501`. If the port is occupied, add
`--server.port 8502`.

### Docker

```bash
docker compose up --build
```

Docker Compose stores the local ledger and portfolio state in the named
`quant-data` volume.

## Development

```bash
python -m pip install -r requirements-dev.txt
python -m ruff check .
python -m py_compile app.py
python -m pytest -q
```

## Repository Map

| Path | Role |
| --- | --- |
| `app.py` | Streamlit UI and reference quant workflow |
| `tests/` | Deterministic strategy, constraint, replay, and backtest tests |
| `data/` | Synthetic schema example and runtime-data policy |
| `docs/REFERENCE_ARCHITECTURE.md` | Contracts and extension points |
| `docs/OPEN_SOURCE_BOUNDARY.md` | Public/private release boundary |
| `.github/workflows/ci.yml` | Python 3.11-3.13 CI |

## Runtime Data

Runtime ledger, mapping, and portfolio files are intentionally ignored by Git.
Only synthetic examples belong in the repository. See [data/README.md](data/README.md).

## Limitations

- Market data comes from `yfinance` and may be delayed, incomplete, or revised.
- The application is single-user local research software with no authentication.
- The execution model is an estimate, not an exchange or broker fill simulator.
- Local CSV/JSON persistence is not a transactional production database.
- Strategy outputs are examples for engineering study, not investment advice.

## Project Policy

- [Contributing](CONTRIBUTING.md)
- [Security](SECURITY.md)
- [MIT License](LICENSE)

Research and education only. Not financial advice.
