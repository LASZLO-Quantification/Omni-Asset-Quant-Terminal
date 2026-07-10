import numpy as np
import pandas as pd
import pytest

from app import (
    backtest_monthly_strategies,
    calculate_va_signal,
    compute_rsi,
    estimate_execution,
    rebuild_portfolio_state_from_ledger,
)


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


def test_estimate_execution_respects_cash_and_costs():
    estimate = estimate_execution(
        action="BUY",
        request_amount=7000,
        price=100,
        available_cash=5000,
        position_qty=0,
        fee_bps=10,
        slippage_bps=5,
    )

    assert estimate.status == "PARTIAL_CASH_LIMIT"
    assert estimate.executable_amount < 5000
    assert estimate.executable_amount + estimate.fee_amount + estimate.slippage_amount == pytest.approx(5000)


def test_rebuild_portfolio_state_replays_net_cash_and_position():
    ledger = pd.DataFrame(
        [
            {
                "timestamp": "2026-01-01T00:00:00",
                "ticker": "TEST",
                "action": "BUY",
                "amount": 1000,
                "fee_amount": 1,
                "slippage_amount": 1,
                "exec_quantity": 10,
            },
            {
                "timestamp": "2026-02-01T00:00:00",
                "ticker": "TEST",
                "action": "SELL_TO_REBALANCE",
                "amount": 550,
                "fee_amount": 0.5,
                "slippage_amount": 0.5,
                "exec_quantity": 5,
            },
        ]
    )

    state = rebuild_portfolio_state_from_ledger(5000, ledger)

    assert state["cash"] == 4548
    assert state["positions"]["TEST"] == 5
