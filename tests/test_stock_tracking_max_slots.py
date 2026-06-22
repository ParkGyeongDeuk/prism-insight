import asyncio

import pytest

from stock_tracking_agent import StockTrackingAgent


def test_max_slots_uses_upstream_default_when_unset(monkeypatch):
    monkeypatch.delenv("PRISM_KR_MAX_SLOTS", raising=False)

    assert StockTrackingAgent._resolve_max_slots() == 10


def test_max_slots_accepts_local_reduction(monkeypatch):
    monkeypatch.setenv("PRISM_KR_MAX_SLOTS", "5")

    assert StockTrackingAgent._resolve_max_slots() == 5


def test_max_slots_rejects_values_outside_safe_range(monkeypatch):
    for value in ("0", "11", "not-a-number"):
        monkeypatch.setenv("PRISM_KR_MAX_SLOTS", value)

        assert StockTrackingAgent._resolve_max_slots() == 10


def test_buy_is_blocked_when_local_slot_limit_is_reached():
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.max_slots = 5

    async def not_holding(_ticker):
        return False

    async def five_slots_in_use():
        return 5

    agent._is_ticker_in_holdings = not_holding
    agent._get_current_slots_count = five_slots_in_use

    result = asyncio.run(
        agent.buy_stock(
            ticker="005930",
            company_name="삼성전자",
            current_price=70000,
            scenario={},
        )
    )

    assert result is False


def test_local_budget_reserves_cash(monkeypatch):
    monkeypatch.setenv("PRISM_KR_TOTAL_BUDGET", "2000000")
    monkeypatch.setenv("PRISM_KR_CASH_RESERVE", "400000")

    agent = StockTrackingAgent()

    assert agent.total_budget_krw == 2000000
    assert agent.cash_reserve_krw == 400000
    assert agent.investable_budget_krw == 1600000


def test_invalid_budget_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("PRISM_KR_TOTAL_BUDGET", "invalid")
    monkeypatch.setenv("PRISM_KR_CASH_RESERVE", "0")

    with pytest.raises(ValueError, match="PRISM_KR_TOTAL_BUDGET"):
        StockTrackingAgent()


def test_next_slot_is_blocked_when_investable_budget_would_be_exceeded():
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.investable_budget_krw = 1600000
    agent.active_account = {"buy_amount_krw": 320000}

    assert agent._has_budget_for_next_slot(current_slots=4) is True
    assert agent._has_budget_for_next_slot(current_slots=5) is False
