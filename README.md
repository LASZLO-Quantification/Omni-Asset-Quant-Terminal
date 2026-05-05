# Multi-Asset VA & Macro Alpha Terminal

A production-ready Streamlit terminal for multi-asset systematic investing workflows.

This project turns discretionary DCA/VA decisions into a reproducible closed loop:
**signal generation -> constrained execution -> ledger recording -> portfolio state update -> backtest/report/snapshot export**.

Core coverage:
- Value Averaging (VA), DCA, and Rebalance execution
- Statistical confidence and expected value (EV)
- Cross-asset macro benchmarking (BTC, TSLA, QQQ, 000300.SS, GLD)
- Monthly strategy backtest with realistic assumptions

## Community & Governance

- Contributing Guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Security Policy: [`SECURITY.md`](SECURITY.md)
- Bug Reports: [GitHub Issues](../../issues)
- Pull Requests: [GitHub Pull Requests](../../pulls)

## Features

- **Execution Engine**: VA, DCA, Rebalance signals with actionable buy/sell amounts.
- **Execution Controls**: cash-constrained execution, fee/slippage estimation, fill quantity preview.
- **Stat Engine**: 50/200 SMA distance, Z-score, RSI, upside/downside estimation, confidence score, EV.
- **Macro Panel**: cross-asset comparison for confidence and EV with chart + table.
- **Backtest Panel**: monthly simulation and metrics (return, vol, max drawdown, Sharpe-like).
- **Backtest Realism**: monthly budget injection and transaction cost assumptions.
- **Ledger & State Loop**: local execution ledger, portfolio cash/position persistence, rebuild state from ledger.
- **Import/Export Workflow**: drag-drop ledger import, mapping templates, CSV export, Markdown report export, ZIP snapshot package.
- **Resilient Data Fetching**: retry + backoff for temporary market data failures.

## Quick Start (Recommended)

Use Python module invocation to avoid PATH conflicts:

```bash
python -m streamlit run app.py
```

If port `8501` is busy:

```bash
python -m streamlit run app.py --server.port 8502
```

## One-Command Startup Scripts

- Windows PowerShell:
  ```powershell
  .\run.ps1
  ```
- macOS/Linux:
  ```bash
  chmod +x run.sh
  ./run.sh
  ```

Both scripts:
- create `.venv` if needed
- install dependencies
- run `python -m streamlit run app.py`

## Manual Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```

## Development

```bash
pip install -r requirements-dev.txt
pytest -q
python -m py_compile app.py
```

## Docker

```bash
docker compose up --build
```

Then open `http://localhost:8501`.

## Project Structure

- `app.py` - main Streamlit app
- `requirements.txt` - runtime dependencies
- `requirements-dev.txt` - test/lint dependencies
- `tests/` - unit tests for core quant logic
- `.github/workflows/ci.yml` - CI pipeline
- `run.ps1` / `run.sh` - cross-platform startup scripts
- `Dockerfile` / `docker-compose.yml` - containerized run

## Troubleshooting

- **`streamlit run app.py` points to old Anaconda path**  
  Use:
  ```bash
  python -m streamlit run app.py
  ```
- **Port in use (`8501`)**
  ```bash
  python -m streamlit run app.py --server.port 8502
  ```

## Disclaimer

This project is for research and educational use only.  
Not financial advice. Use at your own risk.
