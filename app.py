import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple
import json
import io
import zipfile

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf


TRADING_DAYS_YEAR = 252
DEFAULT_ASSETS = ["BTC-USD", "TSLA", "QQQ", "000300.SS", "GLD"]
HISTORY_DIR = Path("data")
HISTORY_FILE = HISTORY_DIR / "trade_history.csv"
MAPPING_TEMPLATE_FILE = HISTORY_DIR / "mapping_templates.json"
PORTFOLIO_STATE_FILE = HISTORY_DIR / "portfolio_state.json"
LEDGER_COLUMNS = [
    "timestamp",
    "ticker",
    "strategy",
    "action",
    "amount",
    "exec_price",
    "exec_quantity",
    "fee_amount",
    "slippage_amount",
    "available_cash",
    "portfolio_cash_after",
    "portfolio_position_after",
    "order_status",
    "confidence_level_pct",
    "expected_value_pct",
    "note",
]
LEDGER_ALIASES = {
    "timestamp": ["timestamp", "time", "date", "datetime", "created_at"],
    "ticker": ["ticker", "symbol", "asset", "code"],
    "strategy": ["strategy", "model", "plan"],
    "action": ["action", "side", "order_side", "trade_action"],
    "amount": ["amount", "value", "order_value", "size", "notional"],
    "exec_price": ["exec_price", "price", "fill_price", "execution_price"],
    "exec_quantity": ["exec_quantity", "quantity", "qty", "filled_qty"],
    "fee_amount": ["fee_amount", "fee", "commission"],
    "slippage_amount": ["slippage_amount", "slippage"],
    "available_cash": ["available_cash", "cash", "cash_balance"],
    "portfolio_cash_after": ["portfolio_cash_after", "cash_after"],
    "portfolio_position_after": ["portfolio_position_after", "position_after", "qty_after"],
    "order_status": ["order_status", "status", "execution_status"],
    "confidence_level_pct": ["confidence_level_pct", "confidence", "confidence_pct"],
    "expected_value_pct": ["expected_value_pct", "ev", "ev_pct", "expected_value"],
    "note": ["note", "remark", "memo", "comment"],
}


@dataclass
class VASignal:
    action: str
    amount: float
    target_value: float
    current_value: float


@dataclass
class StrategySignal:
    strategy: str
    action: str
    amount: float
    note: str


@dataclass
class ExecutionEstimate:
    executable_amount: float
    estimated_quantity: float
    fee_amount: float
    slippage_amount: float
    status: str


def ensure_history_store() -> None:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        pd.DataFrame(columns=LEDGER_COLUMNS).to_csv(HISTORY_FILE, index=False)
    if not MAPPING_TEMPLATE_FILE.exists():
        MAPPING_TEMPLATE_FILE.write_text("{}", encoding="utf-8")
    if not PORTFOLIO_STATE_FILE.exists():
        PORTFOLIO_STATE_FILE.write_text(
            json.dumps({"cash": 5000.0, "positions": {}, "rebuild_initial_cash": 10000.0}, indent=2),
            encoding="utf-8",
        )


def append_trade_history(record: Dict[str, object]) -> None:
    ensure_history_store()
    current = pd.read_csv(HISTORY_FILE)
    updated = pd.concat([current, pd.DataFrame([record])], ignore_index=True)
    updated.to_csv(HISTORY_FILE, index=False)


def load_trade_history() -> pd.DataFrame:
    ensure_history_store()
    return pd.read_csv(HISTORY_FILE)


def save_trade_history(df: pd.DataFrame) -> None:
    ensure_history_store()
    normalized = normalize_ledger_dataframe(df)
    normalized.to_csv(HISTORY_FILE, index=False)


def normalize_ledger_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    normalized = df.copy()
    for col in LEDGER_COLUMNS:
        if col not in normalized.columns:
            normalized[col] = np.nan
    normalized = normalized[LEDGER_COLUMNS]
    return normalized


def auto_detect_mapping(columns: list[str]) -> Dict[str, Optional[str]]:
    lower_map = {c.lower().strip(): c for c in columns}
    mapping: Dict[str, Optional[str]] = {}
    for target_col in LEDGER_COLUMNS:
        detected = None
        for alias in LEDGER_ALIASES[target_col]:
            if alias in lower_map:
                detected = lower_map[alias]
                break
        mapping[target_col] = detected
    return mapping


def apply_column_mapping(
    source_df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
) -> pd.DataFrame:
    mapped = pd.DataFrame()
    for target_col in LEDGER_COLUMNS:
        source_col = mapping.get(target_col)
        mapped[target_col] = source_df[source_col] if source_col else np.nan
    return mapped


def load_mapping_templates() -> Dict[str, Dict[str, Optional[str]]]:
    ensure_history_store()
    try:
        raw = MAPPING_TEMPLATE_FILE.read_text(encoding="utf-8")
        templates = json.loads(raw) if raw.strip() else {}
        return templates if isinstance(templates, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def save_mapping_templates(templates: Dict[str, Dict[str, Optional[str]]]) -> None:
    ensure_history_store()
    MAPPING_TEMPLATE_FILE.write_text(
        json.dumps(templates, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )


def load_portfolio_state() -> Dict[str, object]:
    ensure_history_store()
    try:
        raw = PORTFOLIO_STATE_FILE.read_text(encoding="utf-8")
        state = json.loads(raw) if raw.strip() else {}
    except Exception:  # noqa: BLE001
        state = {}
    cash = float(state.get("cash", 5000.0))
    positions = state.get("positions", {})
    if not isinstance(positions, dict):
        positions = {}
    rebuild_initial_cash = float(state.get("rebuild_initial_cash", 10000.0))
    return {"cash": cash, "positions": positions, "rebuild_initial_cash": rebuild_initial_cash}


def save_portfolio_state(state: Dict[str, object]) -> None:
    ensure_history_store()
    PORTFOLIO_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def rebuild_portfolio_state_from_ledger(initial_cash: float, ledger_df: pd.DataFrame) -> Dict[str, object]:
    cash = float(initial_cash)
    positions: Dict[str, float] = {}
    if ledger_df.empty:
        return {"cash": cash, "positions": positions}

    ordered = ledger_df.copy()
    if "timestamp" in ordered.columns:
        ordered = ordered.sort_values("timestamp", ascending=True)

    for _, row in ordered.iterrows():
        ticker = str(row.get("ticker", "")).strip()
        if not ticker:
            continue
        action = str(row.get("action", "")).strip()
        amount = float(row.get("amount", 0.0) or 0.0)
        fee = float(row.get("fee_amount", 0.0) or 0.0)
        slip = float(row.get("slippage_amount", 0.0) or 0.0)
        qty = float(row.get("exec_quantity", 0.0) or 0.0)
        pos = float(positions.get(ticker, 0.0))

        if action in {"BUY", "DCA_BUY"}:
            cash -= amount + fee + slip
            pos += qty
        elif action in {"SELL_TO_LOCK_PROFIT", "SELL_TO_REBALANCE"}:
            cash += amount
            pos -= qty
        positions[ticker] = max(pos, 0.0)

    return {"cash": float(cash), "positions": positions}


def apply_terminal_theme() -> None:
    st.markdown(
        """
        <style>
            .stApp {
                background: #f3f5f6;
                color: #1f2937;
            }
            .block-container {
                max-width: 1480px;
                padding-top: 1rem;
                padding-bottom: 2rem;
            }
            [data-testid="stSidebar"] {
                background: #e9edef;
                border-right: 1px solid #d6dce0;
            }
            [data-testid="stMetric"] {
                background: #ffffff;
                border: 1px solid #d9dfe3;
                border-radius: 6px;
                padding: 12px 14px;
                box-shadow: none;
            }
            [data-testid="stMetricValue"] {
                color: #111827;
                font-weight: 700;
            }
            [data-testid="stMetricLabel"] {
                color: #6b7280;
            }
            .stDataFrame, .stTable, .stAlert {
                border: 1px solid #d9dfe3;
                border-radius: 6px;
                background: #ffffff;
            }
            h1, h2, h3 {
                color: #111827;
                letter-spacing: 0;
            }
            h1 {
                font-size: 2rem !important;
                line-height: 1.15 !important;
                margin-bottom: 0.25rem !important;
            }
            [data-testid="stSidebar"] [data-testid="stExpander"] {
                border: 1px solid #d6dce0;
                border-radius: 6px;
                background: rgba(255, 255, 255, 0.44);
            }
            .stButton > button, .stDownloadButton > button {
                border-radius: 6px;
            }
            .stButton > button[kind="primary"] {
                border-color: #111827;
                background: #111827;
                color: #ffffff;
            }
            .stButton > button[kind="primary"]:hover {
                border-color: #d89a24;
                background: #f7b73d;
                color: #111827;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_product_header() -> None:
    st.title("Omni-Asset Quant Terminal")
    st.caption("RESEARCH MODE / LOCAL LEDGER / NO BROKER CONNECTION")


def fetch_price_history_with_retry(
    ticker: str,
    period: str = "1y",
    interval: str = "1d",
    retries: int = 3,
    sleep_seconds: float = 1.2,
) -> pd.DataFrame:
    for attempt in range(1, retries + 1):
        try:
            data = yf.download(
                ticker,
                period=period,
                interval=interval,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if data is None or data.empty:
                raise ValueError(f"Empty data for {ticker}")
            if isinstance(data.columns, pd.MultiIndex):
                if ("Close", ticker) in data.columns:
                    data = data[[("Close", ticker)]].copy()
                    data.columns = ["Close"]
                elif "Close" in data.columns.get_level_values(0):
                    close_col = [c for c in data.columns if c[0] == "Close"][0]
                    data = data[[close_col]].copy()
                    data.columns = ["Close"]
            return data
        except Exception as exc:  # noqa: BLE001
            if attempt == retries:
                raise RuntimeError(
                    f"Failed to fetch {ticker} after {retries} attempts: {exc}"
                ) from exc
            time.sleep(sleep_seconds * attempt)
    raise RuntimeError(f"Unexpected failure while fetching {ticker}")


@st.cache_data(ttl=900, show_spinner=False)
def get_price_history(ticker: str) -> pd.DataFrame:
    return fetch_price_history_with_retry(ticker=ticker)


def compute_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(window=window).mean()
    loss = (-delta.clip(upper=0)).rolling(window=window).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)


def calculate_va_signal(
    initial_capital: float,
    monthly_target_growth: float,
    execution_month: int,
    current_asset_value: float,
) -> VASignal:
    target = initial_capital + (execution_month * monthly_target_growth)
    gap = target - current_asset_value

    if gap > 0:
        action = "BUY"
        amount = gap
    elif gap < 0:
        action = "SELL_TO_LOCK_PROFIT"
        amount = abs(gap)
    else:
        action = "HOLD"
        amount = 0.0

    return VASignal(
        action=action,
        amount=round(amount, 2),
        target_value=round(target, 2),
        current_value=round(current_asset_value, 2),
    )


def calculate_dca_signal(monthly_amount: float) -> StrategySignal:
    return StrategySignal(
        strategy="DCA",
        action="BUY",
        amount=round(monthly_amount, 2),
        note="Fixed periodic buy regardless of current valuation.",
    )


def calculate_rebalance_signal(
    total_portfolio_value: float,
    target_asset_weight: float,
    current_asset_value: float,
) -> StrategySignal:
    target_asset_value = total_portfolio_value * target_asset_weight
    diff = target_asset_value - current_asset_value
    if diff > 0:
        action = "BUY"
    elif diff < 0:
        action = "SELL_TO_REBALANCE"
    else:
        action = "HOLD"
    return StrategySignal(
        strategy="REBALANCE",
        action=action,
        amount=round(abs(diff), 2),
        note=f"Target asset value: ${target_asset_value:,.2f}",
    )


def estimate_execution(
    action: str,
    request_amount: float,
    price: float,
    available_cash: float,
    position_qty: float,
    fee_bps: float,
    slippage_bps: float,
) -> ExecutionEstimate:
    gross = max(request_amount, 0.0)
    if gross <= 0 or not np.isfinite(price) or price <= 0:
        return ExecutionEstimate(0.0, 0.0, 0.0, 0.0, "SKIPPED")

    fee_rate = max(fee_bps, 0.0) / 10000.0
    slip_rate = max(slippage_bps, 0.0) / 10000.0
    total_cost_rate = 1 + fee_rate + slip_rate

    if action in {"BUY", "DCA_BUY"}:
        max_affordable = max(available_cash, 0.0) / total_cost_rate
        executable = min(gross, max_affordable)
        if executable <= 0:
            return ExecutionEstimate(0.0, 0.0, 0.0, 0.0, "REJECTED_NO_CASH")
        status = "FILLED" if executable >= gross else "PARTIAL_CASH_LIMIT"
        fee = executable * fee_rate
        slip = executable * slip_rate
        qty = executable / price
        return ExecutionEstimate(executable, qty, fee, slip, status)

    if action in {"SELL_TO_LOCK_PROFIT", "SELL_TO_REBALANCE"}:
        max_sell_notional = max(position_qty, 0.0) * price if price > 0 else 0.0
        executable = min(gross, max_sell_notional)
        if executable <= 0:
            return ExecutionEstimate(0.0, 0.0, 0.0, 0.0, "REJECTED_NO_POSITION")
        status = "FILLED" if executable >= gross else "PARTIAL_POSITION_LIMIT"
        fee = executable * fee_rate
        slip = executable * slip_rate
        net_sell = max(executable - fee - slip, 0.0)
        qty = executable / price if price > 0 else 0.0
        return ExecutionEstimate(net_sell, qty, fee, slip, status)

    return ExecutionEstimate(0.0, 0.0, 0.0, 0.0, "SKIPPED")


def execution_is_actionable(estimate: ExecutionEstimate) -> bool:
    return (
        estimate.status in {"FILLED", "PARTIAL_CASH_LIMIT", "PARTIAL_POSITION_LIMIT"}
        and estimate.executable_amount > 0
        and estimate.estimated_quantity > 0
    )


def apply_execution_to_portfolio(
    state: Dict[str, object],
    ticker: str,
    action: str,
    exec_estimate: ExecutionEstimate,
    price: float,
) -> Dict[str, object]:
    cash = float(state.get("cash", 0.0))
    positions = dict(state.get("positions", {}))
    qty = float(positions.get(ticker, 0.0))

    if action in {"BUY", "DCA_BUY"} and exec_estimate.executable_amount > 0 and price > 0:
        gross_spend = (
            exec_estimate.executable_amount + exec_estimate.fee_amount + exec_estimate.slippage_amount
        )
        cash = max(cash - gross_spend, 0.0)
        qty += exec_estimate.estimated_quantity
    elif action in {"SELL_TO_LOCK_PROFIT", "SELL_TO_REBALANCE"} and exec_estimate.estimated_quantity > 0:
        sell_qty = min(exec_estimate.estimated_quantity, qty)
        qty -= sell_qty
        cash += exec_estimate.executable_amount

    positions[ticker] = float(max(qty, 0.0))
    return {"cash": float(cash), "positions": positions}


def max_drawdown(close: pd.Series) -> float:
    rolling_max = close.cummax()
    drawdown = close / rolling_max - 1
    return float(drawdown.min())


def compute_stat_features(history: pd.DataFrame) -> Dict[str, float]:
    close_obj = history["Close"]
    if isinstance(close_obj, pd.DataFrame):
        close = close_obj.iloc[:, 0].dropna()
    else:
        close = close_obj.dropna()
    if len(close) < 210:
        raise ValueError("Not enough daily bars to compute long-horizon statistics.")

    sma_50 = close.rolling(50).mean()
    sma_200 = close.rolling(200).mean()
    std_50 = close.rolling(50).std()

    last_close = float(close.iloc[-1])
    last_sma50 = float(sma_50.iloc[-1])
    last_sma200 = float(sma_200.iloc[-1])
    last_std50 = float(std_50.iloc[-1]) if not np.isnan(std_50.iloc[-1]) else 1e-9

    distance_to_sma50_pct = (last_close / last_sma50 - 1) * 100 if last_sma50 != 0 else 0.0
    distance_to_sma200_pct = (
        (last_close / last_sma200 - 1) * 100 if last_sma200 != 0 else 0.0
    )
    zscore_50 = (last_close - last_sma50) / (last_std50 if last_std50 != 0 else 1e-9)

    rsi_series = compute_rsi(close)
    rsi_now = float(rsi_series.iloc[-1])

    rolling_std = close.rolling(20).std()
    bollinger_upper = close.rolling(20).mean() + 2 * rolling_std
    upper_ref = float(bollinger_upper.iloc[-1]) if not np.isnan(bollinger_upper.iloc[-1]) else last_close

    resistance_60d = float(close.tail(60).max())
    upside_ref = max(upper_ref, resistance_60d)
    upside_potential_pct = max((upside_ref / last_close - 1) * 100, 0.0)

    downside_ref = float(close.tail(60).min())
    downside_risk_pct = max((last_close / downside_ref - 1) * 100, 0.0)

    returns = close.pct_change().dropna()
    vol_annual = float(returns.std() * np.sqrt(TRADING_DAYS_YEAR) * 100)
    roi_30d = (
        float((close.iloc[-1] / close.iloc[-30] - 1) * 100)
        if len(close) >= 30
        else float("nan")
    )
    mdd = max_drawdown(close) * 100

    # Confidence math:
    # 1) Price deeply below 200SMA increases rebound probability.
    # 2) RSI < 30 indicates oversold momentum exhaustion.
    # 3) Extra weight when price is below 50SMA (short-term mean reversion signal).
    confidence = 50.0
    confidence += np.clip(-distance_to_sma200_pct * 0.8, 0, 25)
    confidence += np.clip((30 - rsi_now) * 1.5, 0, 20)
    confidence += np.clip(-distance_to_sma50_pct * 0.5, 0, 10)
    confidence -= np.clip((rsi_now - 70) * 1.0, 0, 20)
    confidence = float(np.clip(confidence, 0, 100))

    p_up = confidence / 100.0
    p_down = 1 - p_up
    ev_pct = p_up * upside_potential_pct - p_down * downside_risk_pct

    return {
        "close": last_close,
        "sma50": last_sma50,
        "sma200": last_sma200,
        "zscore_50": float(zscore_50),
        "distance_to_sma50_pct": float(distance_to_sma50_pct),
        "distance_to_sma200_pct": float(distance_to_sma200_pct),
        "rsi": rsi_now,
        "upside_potential_pct": float(upside_potential_pct),
        "downside_risk_pct": float(downside_risk_pct),
        "confidence_level_pct": confidence,
        "expected_value_pct": float(ev_pct),
        "roi_30d_pct": roi_30d,
        "vol_annual_pct": vol_annual,
        "max_drawdown_pct": float(mdd),
    }


def asset_snapshot(ticker: str) -> Tuple[Optional[Dict[str, float]], Optional[str]]:
    try:
        hist = get_price_history(ticker)
        stats = compute_stat_features(hist)
        return stats, None
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def backtest_monthly_strategies(
    history: pd.DataFrame,
    initial_capital: float,
    monthly_target_growth: float,
    dca_amount: float,
    target_weight: float,
    monthly_budget: float,
    fee_bps: float,
    slippage_bps: float,
) -> pd.DataFrame:
    monthly_close = history["Close"].resample("ME").last().dropna()
    if len(monthly_close) < 8:
        raise ValueError("Backtest needs at least 8 monthly data points.")

    records = []

    va_units = 0.0
    va_cash = initial_capital
    dca_units = 0.0
    dca_cash = initial_capital
    rb_units = 0.0
    rb_cash = initial_capital

    for i, (_, price) in enumerate(monthly_close.items(), start=1):
        va_cash += max(monthly_budget, 0.0)
        dca_cash += max(monthly_budget, 0.0)
        rb_cash += max(monthly_budget, 0.0)

        va_port = va_cash + va_units * price
        va_signal = calculate_va_signal(
            initial_capital=initial_capital,
            monthly_target_growth=monthly_target_growth,
            execution_month=i,
            current_asset_value=va_port,
        )
        if va_signal.action == "BUY":
            va_exec = estimate_execution(
                action="BUY",
                request_amount=va_signal.amount,
                price=price,
                available_cash=va_cash,
                position_qty=va_units,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
            )
            gross_spend = va_exec.executable_amount + va_exec.fee_amount + va_exec.slippage_amount
            va_cash -= gross_spend
            va_units += va_exec.estimated_quantity
        elif va_signal.action == "SELL_TO_LOCK_PROFIT":
            va_exec = estimate_execution(
                action="SELL_TO_LOCK_PROFIT",
                request_amount=va_signal.amount,
                price=price,
                available_cash=va_cash,
                position_qty=va_units,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
            )
            va_units -= min(va_exec.estimated_quantity, va_units)
            va_cash += max(va_exec.executable_amount, 0.0)
        else:
            pass
        va_port = va_cash + va_units * price

        dca_exec = estimate_execution(
            action="BUY",
            request_amount=max(dca_amount, 0.0),
            price=price,
            available_cash=dca_cash,
            position_qty=dca_units,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
        dca_gross_spend = dca_exec.executable_amount + dca_exec.fee_amount + dca_exec.slippage_amount
        dca_cash -= dca_gross_spend
        dca_units += dca_exec.estimated_quantity
        dca_port = dca_cash + dca_units * price

        rb_port = rb_cash + rb_units * price
        rb_signal = calculate_rebalance_signal(
            total_portfolio_value=rb_port,
            target_asset_weight=target_weight,
            current_asset_value=rb_units * price,
        )
        if rb_signal.action == "BUY":
            rb_exec = estimate_execution(
                action="BUY",
                request_amount=rb_signal.amount,
                price=price,
                available_cash=rb_cash,
                position_qty=rb_units,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
            )
            rb_spend = rb_exec.executable_amount + rb_exec.fee_amount + rb_exec.slippage_amount
            rb_cash -= rb_spend
            rb_units += rb_exec.estimated_quantity
        elif rb_signal.action == "SELL_TO_REBALANCE":
            rb_exec = estimate_execution(
                action="SELL_TO_REBALANCE",
                request_amount=rb_signal.amount,
                price=price,
                available_cash=rb_cash,
                position_qty=rb_units,
                fee_bps=fee_bps,
                slippage_bps=slippage_bps,
            )
            rb_units -= min(rb_exec.estimated_quantity, rb_units)
            rb_cash += max(rb_exec.executable_amount, 0.0)
        rb_port = rb_cash + rb_units * price

        records.append(
            {
                "Date": monthly_close.index[i - 1],
                "VA": va_port,
                "DCA": dca_port,
                "REBALANCE": rb_port,
            }
        )

    return pd.DataFrame(records).set_index("Date")


def backtest_metrics(equity_curve: pd.Series) -> Dict[str, float]:
    r = equity_curve.pct_change().dropna()
    total_return = (equity_curve.iloc[-1] / equity_curve.iloc[0] - 1) * 100
    ann_return = ((1 + total_return / 100) ** (12 / max(len(equity_curve), 1)) - 1) * 100
    ann_vol = r.std() * np.sqrt(12) * 100 if not r.empty else 0.0
    sharpe = (ann_return / ann_vol) if ann_vol > 0 else np.nan
    mdd = (equity_curve / equity_curve.cummax() - 1).min() * 100
    return {
        "final_value": float(equity_curve.iloc[-1]),
        "total_return_pct": float(total_return),
        "annualized_return_pct": float(ann_return),
        "annualized_vol_pct": float(ann_vol),
        "sharpe_like": float(sharpe) if not np.isnan(sharpe) else np.nan,
        "max_drawdown_pct": float(mdd),
    }


def build_backtest_markdown_report(
    ticker: str,
    strategy_mode: str,
    assumptions: Dict[str, float],
    metrics_df: pd.DataFrame,
) -> str:
    lines = [
        "# Backtest Report",
        "",
        f"- Generated At: {datetime.now().isoformat(timespec='seconds')}",
        f"- Ticker: {ticker}",
        f"- Active Strategy View: {strategy_mode}",
        "",
        "## Assumptions",
        f"- Initial Capital: ${assumptions['initial_capital']:,.2f}",
        f"- Monthly Budget Injection: ${assumptions['monthly_budget']:,.2f}",
        f"- Monthly Target Growth: ${assumptions['monthly_target_growth']:,.2f}",
        f"- DCA Amount: ${assumptions['dca_amount']:,.2f}",
        f"- Target Weight: {assumptions['target_weight']:.2%}",
        f"- Fee: {assumptions['fee_bps']:.2f} bps",
        f"- Slippage: {assumptions['slippage_bps']:.2f} bps",
        "",
        "## Strategy Metrics",
        "",
        "| Strategy | Final Value ($) | Total Return (%) | Annualized Return (%) | Annualized Vol (%) | Sharpe-Like | Max Drawdown (%) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, row in metrics_df.iterrows():
        lines.append(
            "| "
            f"{row['Strategy']} | "
            f"{row['Final Value ($)']:.2f} | "
            f"{row['Total Return (%)']:.2f} | "
            f"{row['Annualized Return (%)']:.2f} | "
            f"{row['Annualized Vol (%)']:.2f} | "
            f"{row['Sharpe-Like']:.2f} | "
            f"{row['Max Drawdown (%)']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "- This report includes cash constraints and fee/slippage assumptions.",
            "- Results are for research only, not financial advice.",
        ]
    )
    return "\n".join(lines)


def build_snapshot_zip(
    ticker: str,
    assumptions: Dict[str, float],
    ledger_df: pd.DataFrame,
    metrics_df: pd.DataFrame,
    forward_plan_df: pd.DataFrame,
    report_md: str,
) -> bytes:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{ticker}_assumptions_{timestamp}.json", json.dumps(assumptions, indent=2))
        zf.writestr(f"{ticker}_ledger_{timestamp}.csv", ledger_df.to_csv(index=False))
        zf.writestr(f"{ticker}_metrics_{timestamp}.csv", metrics_df.to_csv(index=False))
        zf.writestr(f"{ticker}_forward_plan_{timestamp}.csv", forward_plan_df.to_csv(index=False))
        zf.writestr(f"{ticker}_backtest_report_{timestamp}.md", report_md)
    return buf.getvalue()


def generate_forward_plan(
    strategy_mode: str,
    execution_month: int,
    horizon_months: int,
    monthly_target: float,
    initial_capital: float,
    dca_amount: float,
    target_weight: float,
    monthly_budget: float,
) -> pd.DataFrame:
    rows = []
    for step in range(1, horizon_months + 1):
        month_t = execution_month + step
        if strategy_mode == "VA":
            target_value = initial_capital + month_t * monthly_target
            action = "BUY" if monthly_target > 0 else "HOLD"
            amount = max(monthly_target, 0.0)
            note = f"Target portfolio value: ${target_value:,.2f}"
        elif strategy_mode == "DCA":
            action = "BUY"
            amount = max(dca_amount, 0.0)
            note = "Fixed periodic buy."
        else:
            action = "REBALANCE_CHECK"
            amount = 0.0
            note = f"Rebalance asset weight to {target_weight:.0%} at month-end."

        rows.append(
            {
                "Month(T)": month_t,
                "Planned Action": action,
                "Planned Amount ($)": amount,
                "Budget Injection ($)": max(monthly_budget, 0.0),
                "Note": note,
            }
        )
    return pd.DataFrame(rows)


def build_macro_table(tickers: list[str]) -> pd.DataFrame:
    rows = []
    for tk in tickers:
        stats, err = asset_snapshot(tk)
        if err:
            rows.append(
                {
                    "Ticker": tk,
                    "Error": err,
                    "Confidence Level (%)": np.nan,
                    "Expected Value (%)": np.nan,
                    "30D ROI (%)": np.nan,
                    "Ann. Volatility (%)": np.nan,
                    "RSI": np.nan,
                }
            )
            continue

        rows.append(
            {
                "Ticker": tk,
                "Error": "",
                "Confidence Level (%)": stats["confidence_level_pct"],
                "Expected Value (%)": stats["expected_value_pct"],
                "30D ROI (%)": stats["roi_30d_pct"],
                "Ann. Volatility (%)": stats["vol_annual_pct"],
                "RSI": stats["rsi"],
            }
        )
    return pd.DataFrame(rows)


def render_macro_chart(macro_df: pd.DataFrame) -> None:
    chart_df = macro_df.dropna(subset=["Confidence Level (%)", "Expected Value (%)"]).copy()
    if chart_df.empty:
        st.warning("No valid cross-asset data available for charting.")
        return

    melted = chart_df.melt(
        id_vars="Ticker",
        value_vars=["Confidence Level (%)", "Expected Value (%)"],
        var_name="Metric",
        value_name="Value",
    )
    fig = px.bar(
        melted,
        x="Ticker",
        y="Value",
        color="Metric",
        barmode="group",
        template="plotly_white",
        title="Cross-Asset Macro Benchmarking",
    )
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font_color="#111827",
        legend_title_text="",
    )
    st.plotly_chart(fig, width="stretch")


def render_backtest_chart(backtest_df: pd.DataFrame) -> None:
    chart_df = (
        backtest_df.rename_axis("Date")
        .reset_index()
        .melt(id_vars="Date", var_name="Strategy", value_name="Portfolio Value ($)")
    )
    fig = px.line(
        chart_df,
        x="Date",
        y="Portfolio Value ($)",
        color="Strategy",
        color_discrete_map={
            "VA": "#2563eb",
            "DCA": "#16a34a",
            "REBALANCE": "#d97706",
        },
    )
    fig.update_traces(line_width=2.5)
    fig.update_layout(
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font_color="#111827",
        hovermode="x unified",
        legend_title_text="",
        legend={"orientation": "h", "x": 0, "y": 1.02, "yanchor": "bottom"},
        margin={"l": 12, "r": 12, "t": 48, "b": 12},
        xaxis_title="",
    )
    fig.update_yaxes(tickprefix="$", separatethousands=True)
    st.plotly_chart(fig, width="stretch")


def main() -> None:
    st.set_page_config(
        page_title="Omni-Asset Quant Terminal",
        page_icon=":chart_with_upwards_trend:",
        layout="wide",
    )
    apply_terminal_theme()
    render_product_header()
    if "show_exec_dialog" not in st.session_state:
        st.session_state.show_exec_dialog = False
    if "imported_ledger_df" not in st.session_state:
        st.session_state.imported_ledger_df = None
    if "raw_import_df" not in st.session_state:
        st.session_state.raw_import_df = None
    if "mapping_selection" not in st.session_state:
        st.session_state.mapping_selection = {}
    if "portfolio_state" not in st.session_state:
        st.session_state.portfolio_state = load_portfolio_state()
    portfolio_state = st.session_state.portfolio_state
    portfolio_positions = portfolio_state.get("positions", {})
    current_position_qty = float(portfolio_positions.get("BTC-USD", 0.0))
    rebuild_initial_cash = float(portfolio_state.get("rebuild_initial_cash", 10000.0))

    with st.sidebar:
        st.subheader("Research Setup")
        ticker = st.text_input("Target Ticker", value="BTC-USD").strip().upper()
        current_position_qty = float(portfolio_positions.get(ticker, 0.0))
        strategy_mode = st.selectbox("Execution Strategy", ["VA", "DCA", "REBALANCE"])
        with st.expander("Portfolio State", expanded=True):
            available_cash = st.number_input(
                "Available Cash ($)",
                min_value=0.0,
                value=float(portfolio_state.get("cash", 5000.0)),
                step=100.0,
            )
            manual_position_qty = st.number_input(
                f"Current Position Qty ({ticker})",
                min_value=0.0,
                value=current_position_qty,
                step=0.001,
                format="%.6f",
            )
            sync_col1, sync_col2 = st.columns(2)
            if sync_col1.button("Sync State", width="stretch"):
                new_positions = dict(portfolio_positions)
                new_positions[ticker] = float(manual_position_qty)
                st.session_state.portfolio_state = {
                    "cash": float(available_cash),
                    "positions": new_positions,
                    "rebuild_initial_cash": float(rebuild_initial_cash),
                }
                save_portfolio_state(st.session_state.portfolio_state)
                st.success("Portfolio state synced to local store.")
                st.rerun()
            if sync_col2.button("Rebuild Ledger", width="stretch"):
                ledger_for_rebuild = load_trade_history()
                rebuilt = rebuild_portfolio_state_from_ledger(
                    initial_cash=float(rebuild_initial_cash),
                    ledger_df=ledger_for_rebuild,
                )
                rebuilt["rebuild_initial_cash"] = float(rebuild_initial_cash)
                st.session_state.portfolio_state = rebuilt
                save_portfolio_state(rebuilt)
                st.success("Portfolio state rebuilt from local ledger.")
                st.rerun()
            st.caption(f"Rebuild cash baseline: ${rebuild_initial_cash:,.2f}")

        with st.expander("Strategy Parameters", expanded=True):
            initial_capital = st.number_input(
                "Initial Capital ($)", min_value=0.0, value=10000.0, step=100.0
            )
            monthly_target = st.number_input(
                "Monthly Target Growth ($)", min_value=0.0, value=500.0, step=10.0
            )
            execution_month = st.number_input("Execution Month (T)", min_value=1, value=12, step=1)
            dca_amount = st.number_input(
                "DCA Monthly Amount ($)", min_value=0.0, value=500.0, step=10.0
            )
            total_portfolio_value = st.number_input(
                "Portfolio Total Value ($)", min_value=0.0, value=20000.0, step=100.0
            )
            target_weight = st.slider(
                "Target Asset Weight", min_value=0.0, max_value=1.0, value=0.5, step=0.05
            )
            current_asset_value = st.number_input(
                "Current Asset Value ($)", min_value=0.0, value=9000.0, step=100.0
            )

        with st.expander("Execution Assumptions", expanded=False):
            monthly_budget = st.number_input(
                "Monthly Budget Injection ($)", min_value=0.0, value=500.0, step=10.0
            )
            fee_bps = st.number_input("Fee (bps)", min_value=0.0, value=10.0, step=1.0)
            slippage_bps = st.number_input(
                "Slippage (bps)", min_value=0.0, value=5.0, step=1.0
            )
        st.caption("Universe: BTC / TSLA / QQQ / CSI300 / GLD")

    working_positions = dict(portfolio_positions)
    working_positions[ticker] = float(manual_position_qty)
    working_portfolio_state = {
        "cash": float(available_cash),
        "positions": working_positions,
        "rebuild_initial_cash": float(rebuild_initial_cash),
    }

    va = calculate_va_signal(
        initial_capital=initial_capital,
        monthly_target_growth=monthly_target,
        execution_month=int(execution_month),
        current_asset_value=current_asset_value,
    )
    dca_signal = calculate_dca_signal(dca_amount)
    rb_signal = calculate_rebalance_signal(total_portfolio_value, target_weight, current_asset_value)

    if strategy_mode == "VA":
        selected_action = va.action
        selected_amount = va.amount
        selected_note = f"VA Target Value: ${va.target_value:,.2f}"
    elif strategy_mode == "DCA":
        selected_action = "DCA_BUY"
        selected_amount = dca_signal.amount
        selected_note = dca_signal.note
    else:
        selected_action = rb_signal.action
        selected_amount = rb_signal.amount
        selected_note = rb_signal.note

    target_stats, target_err = asset_snapshot(ticker)
    if target_err:
        st.error(f"Failed to compute target asset stats for {ticker}: {target_err}")
        target_stats = {
            "confidence_level_pct": np.nan,
            "expected_value_pct": np.nan,
            "distance_to_sma50_pct": np.nan,
            "distance_to_sma200_pct": np.nan,
            "zscore_50": np.nan,
            "max_drawdown_pct": np.nan,
        }
        mark_price = np.nan
    else:
        mark_price = float(target_stats.get("close", np.nan))

    exec_estimate = estimate_execution(
        action=selected_action,
        request_amount=selected_amount,
        price=mark_price if not np.isnan(mark_price) else 0.0,
        available_cash=float(working_portfolio_state.get("cash", 0.0)),
        position_qty=float(working_portfolio_state.get("positions", {}).get(ticker, 0.0)),
        fee_bps=fee_bps,
        slippage_bps=slippage_bps,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric(
        "Required Action Amount ($)",
        f"{selected_amount:,.2f}",
        delta=f"{strategy_mode}: {selected_action} [{exec_estimate.status}]",
    )
    c2.metric("Asset Confidence Level (%)", f"{target_stats['confidence_level_pct']:.2f}")
    c3.metric("Expected Value (%)", f"{target_stats['expected_value_pct']:.2f}")
    st.caption(
        f"{selected_note} | Executable: ${exec_estimate.executable_amount:,.2f} | "
        f"Fee+Slippage: ${(exec_estimate.fee_amount + exec_estimate.slippage_amount):,.2f}"
    )

    allow_execute = execution_is_actionable(exec_estimate)
    exec_col1, exec_col2 = st.columns([1, 3])
    if exec_col1.button(
        "Confirm Execution",
        type="primary",
        width="stretch",
        disabled=not allow_execute,
    ):
        st.session_state.show_exec_dialog = True

    if st.session_state.show_exec_dialog:
        @st.dialog("Trade Execution Confirmation")
        def confirm_execution_dialog() -> None:
            st.write(f"Ticker: `{ticker}`")
            st.write(f"Strategy: `{strategy_mode}`")
            st.write(f"Action: `{selected_action}`")
            st.write(f"Amount: `${selected_amount:,.2f}`")
            st.write(f"Estimated Fill Quantity: `{exec_estimate.estimated_quantity:,.6f}`")
            st.write(
                f"Estimated Costs (fee+slippage): `${(exec_estimate.fee_amount + exec_estimate.slippage_amount):,.2f}`"
            )
            st.write(f"Execution Status: `{exec_estimate.status}`")
            st.write("Mark this order as executed?")
            yes_col, no_col = st.columns(2)
            if not allow_execute:
                st.warning("Current order cannot be executed under portfolio constraints.")
            if yes_col.button("Yes, Executed", width="stretch", disabled=not allow_execute):
                updated_portfolio = apply_execution_to_portfolio(
                    state=working_portfolio_state,
                    ticker=ticker,
                    action=selected_action,
                    exec_estimate=exec_estimate,
                    price=mark_price if not np.isnan(mark_price) else 0.0,
                )
                st.session_state.portfolio_state = updated_portfolio
                save_portfolio_state(updated_portfolio)
                append_trade_history(
                    {
                        "timestamp": datetime.now().isoformat(timespec="seconds"),
                        "ticker": ticker,
                        "strategy": strategy_mode,
                        "action": selected_action,
                        "amount": round(exec_estimate.executable_amount, 2),
                        "exec_price": mark_price if not np.isnan(mark_price) else np.nan,
                        "exec_quantity": round(exec_estimate.estimated_quantity, 8),
                        "fee_amount": round(exec_estimate.fee_amount, 4),
                        "slippage_amount": round(exec_estimate.slippage_amount, 4),
                        "available_cash": round(float(working_portfolio_state.get("cash", 0.0)), 2),
                        "portfolio_cash_after": round(float(updated_portfolio.get("cash", 0.0)), 2),
                        "portfolio_position_after": round(
                            float(updated_portfolio.get("positions", {}).get(ticker, 0.0)),
                            8,
                        ),
                        "order_status": exec_estimate.status,
                        "confidence_level_pct": (
                            float(target_stats["confidence_level_pct"])
                            if not np.isnan(target_stats["confidence_level_pct"])
                            else np.nan
                        ),
                        "expected_value_pct": (
                            float(target_stats["expected_value_pct"])
                            if not np.isnan(target_stats["expected_value_pct"])
                            else np.nan
                        ),
                        "note": selected_note,
                    }
                )
                st.session_state.show_exec_dialog = False
                st.success("Execution logged to local history table.")
                st.rerun()
            if no_col.button("No", width="stretch"):
                st.session_state.show_exec_dialog = False
                st.rerun()

        confirm_execution_dialog()

    st.markdown("---")
    st.subheader("Cross-Asset Comparison")
    macro_df = build_macro_table(DEFAULT_ASSETS)
    render_macro_chart(macro_df)

    st.markdown("---")
    st.subheader("Raw Diagnostics Table")
    diagnostics = macro_df.copy()
    if not np.isnan(target_stats["distance_to_sma50_pct"]):
        detail_row = pd.DataFrame(
            [
                {
                    "Ticker": f"{ticker} (Target Detail)",
                    "Error": "",
                    "Confidence Level (%)": target_stats["confidence_level_pct"],
                    "Expected Value (%)": target_stats["expected_value_pct"],
                    "30D ROI (%)": np.nan,
                    "Ann. Volatility (%)": np.nan,
                    "RSI": np.nan,
                }
            ]
        )
        diagnostics = pd.concat([diagnostics, detail_row], ignore_index=True)

    st.dataframe(
        diagnostics.style.format(
            {
                "Confidence Level (%)": "{:.2f}",
                "Expected Value (%)": "{:.2f}",
                "30D ROI (%)": "{:.2f}",
                "Ann. Volatility (%)": "{:.2f}",
                "RSI": "{:.2f}",
            }
        ),
        width="stretch",
    )

    raw_target_df = pd.DataFrame(
        [
            {
                "Ticker": ticker,
                "Distance to 50SMA (%)": target_stats["distance_to_sma50_pct"],
                "Distance to 200SMA (%)": target_stats["distance_to_sma200_pct"],
                "Z-Score vs 50SMA": target_stats["zscore_50"],
                "Max Drawdown (%)": target_stats["max_drawdown_pct"],
            }
        ]
    )
    st.dataframe(
        raw_target_df.style.format(
            {
                "Distance to 50SMA (%)": "{:.2f}",
                "Distance to 200SMA (%)": "{:.2f}",
                "Z-Score vs 50SMA": "{:.2f}",
                "Max Drawdown (%)": "{:.2f}",
            }
        ),
        width="stretch",
    )

    st.markdown("---")
    st.subheader("Execution History (Local Ledger)")
    st.caption("Import ledger by drag-and-drop or click upload. Export local or imported ledger.")
    uploaded_file = st.file_uploader(
        "Import Ledger File (CSV/XLSX)",
        type=["csv", "xlsx"],
        accept_multiple_files=False,
    )
    if uploaded_file is not None:
        try:
            if uploaded_file.name.lower().endswith(".csv"):
                imported_df = pd.read_csv(uploaded_file)
            else:
                imported_df = pd.read_excel(uploaded_file)
            st.session_state.raw_import_df = imported_df
            st.success(f"Loaded {len(imported_df)} rows from `{uploaded_file.name}`.")
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to import ledger: {exc}")

    raw_import_df = st.session_state.raw_import_df
    if raw_import_df is not None:
        st.markdown("**Import Mapping Wizard**")
        st.caption("Map source columns to ledger fields. Auto-detection is pre-selected.")
        suggested = auto_detect_mapping(list(raw_import_df.columns))
        options = ["<EMPTY>"] + list(raw_import_df.columns)
        templates = load_mapping_templates()

        tpl_col1, tpl_col2 = st.columns(2)
        template_names = ["<NONE>"] + sorted(list(templates.keys()))
        selected_template = tpl_col1.selectbox(
            "Load Mapping Template",
            options=template_names,
            index=0,
        )
        if tpl_col1.button("Apply Template", width="stretch"):
            if selected_template != "<NONE>":
                st.session_state.mapping_selection = templates[selected_template]
                for target_col in LEDGER_COLUMNS:
                    selected_col = templates[selected_template].get(target_col)
                    st.session_state[f"map_{target_col}"] = selected_col if selected_col else "<EMPTY>"
                st.success(f"Template `{selected_template}` loaded.")
                st.rerun()
            else:
                st.info("Please select a saved template first.")
        template_save_name = tpl_col2.text_input("Save Current Mapping As", value="")

        mapping_result: Dict[str, Optional[str]] = {}
        map_cols = st.columns(2)
        for idx, target_col in enumerate(LEDGER_COLUMNS):
            col_ui = map_cols[idx % 2]
            prior_map = st.session_state.mapping_selection.get(target_col)
            default_option = prior_map or suggested.get(target_col) or "<EMPTY>"
            default_idx = options.index(default_option) if default_option in options else 0
            selected = col_ui.selectbox(
                f"{target_col} <-",
                options=options,
                index=default_idx,
                key=f"map_{target_col}",
            )
            mapping_result[target_col] = None if selected == "<EMPTY>" else selected

        action_col1, action_col2 = st.columns(2)
        if action_col1.button("Apply Mapping to Imported Data", width="stretch"):
            mapped_df = apply_column_mapping(raw_import_df, mapping_result)
            mapped_df = normalize_ledger_dataframe(mapped_df)
            st.session_state.imported_ledger_df = mapped_df
            st.session_state.mapping_selection = mapping_result
            st.success("Column mapping applied. Imported ledger is ready.")
            st.rerun()
        if action_col2.button("Save Mapping Template", width="stretch"):
            clean_name = template_save_name.strip()
            if not clean_name:
                st.warning("Please input a template name.")
            else:
                templates[clean_name] = mapping_result
                save_mapping_templates(templates)
                st.session_state.mapping_selection = mapping_result
                st.success(f"Template `{clean_name}` saved.")

    imported_ledger_df = st.session_state.imported_ledger_df
    if imported_ledger_df is not None:
        st.markdown("**Imported Ledger Preview**")
        st.dataframe(imported_ledger_df, width="stretch")
        imp_col1, imp_col2, imp_col3 = st.columns(3)
        if imp_col1.button("Replace Local Ledger with Imported", width="stretch"):
            save_trade_history(imported_ledger_df)
            st.success("Local ledger replaced by imported data.")
            st.rerun()
        if imp_col2.button("Append Imported to Local Ledger", width="stretch"):
            local_df = load_trade_history()
            merged_df = pd.concat([local_df, imported_ledger_df], ignore_index=True)
            save_trade_history(merged_df)
            st.success("Imported rows appended to local ledger.")
            st.rerun()
        if imp_col3.button("Clear Imported Table", width="stretch"):
            st.session_state.imported_ledger_df = None
            st.session_state.raw_import_df = None
            st.success("Imported table cleared.")
            st.rerun()

    history_df = load_trade_history()
    if history_df.empty:
        st.info("No executed orders yet. Use 'Confirm Execution' to create records.")
    else:
        st.dataframe(
            history_df.sort_values("timestamp", ascending=False).style.format(
                {
                    "amount": "{:,.2f}",
                    "confidence_level_pct": "{:.2f}",
                    "expected_value_pct": "{:.2f}",
                }
            ),
            width="stretch",
        )

    st.markdown("**Export Ledger**")
    export_source = st.selectbox(
        "Select export source",
        ["Local Ledger Records", "Current Imported Table"],
        index=0,
    )
    export_df = (
        history_df
        if export_source == "Local Ledger Records" or imported_ledger_df is None
        else imported_ledger_df
    )
    export_name = (
        "local_ledger_export.csv"
        if export_source == "Local Ledger Records"
        else "imported_ledger_export.csv"
    )
    st.download_button(
        label="Export Selected Ledger as CSV",
        data=export_df.to_csv(index=False).encode("utf-8"),
        file_name=export_name,
        mime="text/csv",
        width="stretch",
    )

    st.markdown("---")
    st.subheader("Next Months Operation Plan")
    plan_horizon = st.slider("Plan Horizon (months)", min_value=1, max_value=12, value=6, step=1)
    forward_plan_df = generate_forward_plan(
        strategy_mode=strategy_mode,
        execution_month=int(execution_month),
        horizon_months=int(plan_horizon),
        monthly_target=monthly_target,
        initial_capital=initial_capital,
        dca_amount=dca_amount,
        target_weight=target_weight,
        monthly_budget=monthly_budget,
    )
    st.dataframe(
        forward_plan_df.style.format(
            {"Planned Amount ($)": "{:,.2f}", "Budget Injection ($)": "{:,.2f}"}
        ),
        width="stretch",
    )

    st.markdown("---")
    st.subheader("Strategy Backtest (Monthly Simulation)")
    try:
        target_hist = get_price_history(ticker)
        bt_df = backtest_monthly_strategies(
            history=target_hist,
            initial_capital=initial_capital,
            monthly_target_growth=monthly_target,
            dca_amount=dca_amount,
            target_weight=target_weight,
            monthly_budget=monthly_budget,
            fee_bps=fee_bps,
            slippage_bps=slippage_bps,
        )
        render_backtest_chart(bt_df)

        metric_rows = []
        for col in bt_df.columns:
            m = backtest_metrics(bt_df[col])
            metric_rows.append(
                {
                    "Strategy": col,
                    "Final Value ($)": m["final_value"],
                    "Total Return (%)": m["total_return_pct"],
                    "Annualized Return (%)": m["annualized_return_pct"],
                    "Annualized Vol (%)": m["annualized_vol_pct"],
                    "Sharpe-Like": m["sharpe_like"],
                    "Max Drawdown (%)": m["max_drawdown_pct"],
                }
            )
        bt_metrics_df = pd.DataFrame(metric_rows)
        st.dataframe(
            bt_metrics_df.style.format(
                {
                    "Final Value ($)": "{:,.2f}",
                    "Total Return (%)": "{:.2f}",
                    "Annualized Return (%)": "{:.2f}",
                    "Annualized Vol (%)": "{:.2f}",
                    "Sharpe-Like": "{:.2f}",
                    "Max Drawdown (%)": "{:.2f}",
                }
            ),
            width="stretch",
        )

        assumptions = {
            "initial_capital": float(initial_capital),
            "monthly_budget": float(monthly_budget),
            "monthly_target_growth": float(monthly_target),
            "dca_amount": float(dca_amount),
            "target_weight": float(target_weight),
            "fee_bps": float(fee_bps),
            "slippage_bps": float(slippage_bps),
        }
        report_md = build_backtest_markdown_report(
            ticker=ticker,
            strategy_mode=strategy_mode,
            assumptions=assumptions,
            metrics_df=bt_metrics_df,
        )
        export_col1, export_col2 = st.columns(2)
        export_col1.download_button(
            label="Export Backtest Metrics (CSV)",
            data=bt_metrics_df.to_csv(index=False).encode("utf-8"),
            file_name=f"{ticker}_backtest_metrics.csv",
            mime="text/csv",
            width="stretch",
        )
        export_col2.download_button(
            label="Export Backtest Report (Markdown)",
            data=report_md.encode("utf-8"),
            file_name=f"{ticker}_backtest_report.md",
            mime="text/markdown",
            width="stretch",
        )

        snapshot_zip = build_snapshot_zip(
            ticker=ticker,
            assumptions=assumptions,
            ledger_df=history_df,
            metrics_df=bt_metrics_df,
            forward_plan_df=forward_plan_df,
            report_md=report_md,
        )
        st.download_button(
            label="Export Full Snapshot Package (ZIP)",
            data=snapshot_zip,
            file_name=f"{ticker}_snapshot_package.zip",
            mime="application/zip",
            width="stretch",
        )
    except Exception as exc:  # noqa: BLE001
        st.warning(f"Backtest unavailable for {ticker}: {exc}")


if __name__ == "__main__":
    main()
