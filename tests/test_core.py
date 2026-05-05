import numpy as np
import pandas as pd

from app import backtest_monthly_strategies, calculate_va_signal, compute_rsi


def test_calculate_va_signal_buy():
    sig = calculate_va_signal(
        initial_capital=10000,
        monthly_target_growth=500,
        execution_month=2,
        current_asset_value=9000,
    )
    assert sig.action == "BUY"
    assert sig.amount == 2000


def test_calculate_va_signal_sell():
    sig = calculate_va_signal(
        initial_capital=10000,
        monthly_target_growth=500,
        execution_month=2,
        current_asset_value=13000,
    )
    assert sig.action == "SELL_TO_LOCK_PROFIT"
    assert sig.amount == 2000


def test_compute_rsi_range():
    s = pd.Series(np.linspace(100, 120, 60))
    rsi = compute_rsi(s)
    assert len(rsi) == len(s)
    assert (rsi >= 0).all() and (rsi <= 100).all()


def test_backtest_monthly_strategies_output():
    idx = pd.date_range("2024-01-01", periods=365, freq="D")
    close = pd.Series(np.linspace(100, 160, len(idx)), index=idx)
    history = pd.DataFrame({"Close": close})

    out = backtest_monthly_strategies(
        history=history,
        initial_capital=10000,
        monthly_target_growth=300,
        dca_amount=500,
        target_weight=0.5,
        monthly_budget=500,
        fee_bps=10,
        slippage_bps=5,
    )
    assert not out.empty
    assert set(out.columns) == {"VA", "DCA", "REBALANCE"}
