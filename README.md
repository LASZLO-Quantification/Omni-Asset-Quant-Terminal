<div align="center">

# Omni-Asset Quant Terminal

### Multi-asset systematic investing — one closed loop.

**Signal → execution → ledger → state → backtest**

[![Organization](https://img.shields.io/badge/LASZLO--Quantification-public-FFB24D?style=for-the-badge&logo=github&logoColor=0B0D10)](https://github.com/LASZLO-Quantification)
[![Stack](https://img.shields.io/badge/Stack-Streamlit_·_Python-0B0D10?style=for-the-badge&logo=python&logoColor=FFB24D)](https://streamlit.io)
[![License](https://img.shields.io/badge/License-MIT-15181D?style=for-the-badge)](LICENSE)

<sub>A public satellite of <a href="https://github.com/LASZLO-Quantification">LASZLO Quantification</a> · Not financial advice</sub>

</div>

---

## What it is

A **production-ready Streamlit terminal** for multi-asset systematic workflows.

Discretionary DCA and value-averaging become an operator loop you can **replay, export, and defend**:

```text
signal generation → constrained execution → ledger → portfolio state → backtest / snapshot
```

**Coverage:** Value Averaging (VA) · DCA · rebalance · cross-asset macro (BTC, TSLA, QQQ, 000300.SS, GLD).

> Sister project to the private [LASZLO](https://github.com/LASZLO-Quantification) on-chain engine — same discipline, traditional-asset surface. See [public projects index](https://github.com/LASZLO-Quantification/.github/tree/main/docs/projects).

---

## Features

| Module | What you get |
|--------|----------------|
| **Execution** | VA / DCA / rebalance signals with actionable sizes; cash constraints, fees, slippage preview |
| **Stats** | SMA distance, Z-score, RSI, upside/downside, confidence, EV |
| **Macro** | Cross-asset confidence & EV — chart + table |
| **Backtest** | Monthly simulation — return, vol, max drawdown, Sharpe-like; budget injection & costs |
| **Ledger** | Local execution log, portfolio persistence, rebuild from ledger |
| **I/O** | CSV import/export, Markdown reports, ZIP snapshot packages |

---

## Quick start

```bash
python -m streamlit run app.py
```

Port busy? `python -m streamlit run app.py --server.port 8502`

**One command:**

```powershell
.\run.ps1          # Windows
./run.sh           # macOS / Linux
```

**Docker:** `docker compose up --build` → http://localhost:8501

---

## Development

```bash
pip install -r requirements-dev.txt
pytest -q
python -m py_compile app.py
```

| Doc | Link |
|-----|------|
| Contributing | [CONTRIBUTING.md](CONTRIBUTING.md) |
| Security | [SECURITY.md](SECURITY.md) |
| Issues | [GitHub Issues](../../issues) |

---

## Structure

| Path | Role |
|------|------|
| `app.py` | Main Streamlit app |
| `tests/` | Core quant logic unit tests |
| `.github/workflows/ci.yml` | CI |
| `run.ps1` / `run.sh` | Cross-platform bootstrap |

---

## Troubleshooting

**`streamlit` resolves to old Anaconda** → use `python -m streamlit run app.py`

**Port 8501 in use** → `--server.port 8502`

---

## Disclaimer

Research and education only. **Not financial advice.** Use at your own risk.

---

<div align="center">

**LASZLO Quantification** · *Measurable loops, explicit constraints*

</div>
