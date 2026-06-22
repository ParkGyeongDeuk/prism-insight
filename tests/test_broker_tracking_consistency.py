import sqlite3

import pytest

import stock_tracking_agent as tracking_module
import trading.domestic_stock_trading as domestic_trading
from stock_tracking_agent import StockTrackingAgent


class _BrokerContext:
    portfolio = []
    open_orders = []
    portfolio_ok = True
    open_orders_ok = True

    def __init__(self, **_kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def get_portfolio(self):
        self._last_portfolio_query_ok = self.portfolio_ok
        return list(self.portfolio)

    def get_revisable_orders(self):
        self._last_revisable_orders_query_ok = self.open_orders_ok
        return list(self.open_orders)


def _make_agent(db_tickers=()):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.conn = sqlite3.connect(":memory:")
    agent.cursor = agent.conn.cursor()
    agent.cursor.execute(
        "CREATE TABLE stock_holdings (account_key TEXT, ticker TEXT)"
    )
    agent.cursor.executemany(
        "INSERT INTO stock_holdings (account_key, ticker) VALUES (?, ?)",
        [("vps:test:01", ticker) for ticker in db_tickers],
    )
    agent.conn.commit()
    agent.active_account = {
        "name": "paper-main",
        "account_key": "vps:test:01",
    }
    return agent


@pytest.fixture(autouse=True)
def _fast_broker_checks(monkeypatch):
    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(tracking_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(domestic_trading, "AsyncTradingContext", _BrokerContext)
    _BrokerContext.portfolio = []
    _BrokerContext.open_orders = []
    _BrokerContext.portfolio_ok = True
    _BrokerContext.open_orders_ok = True


@pytest.mark.asyncio
async def test_broker_and_tracking_tickers_match():
    agent = _make_agent(["005930"])
    _BrokerContext.portfolio = [{"stock_code": "005930", "quantity": 2}]

    assert await agent._broker_tracking_state_matches() is True


@pytest.mark.asyncio
async def test_pending_buy_counts_as_broker_tracking_state():
    agent = _make_agent(["035720"])
    _BrokerContext.open_orders = [
        {
            "stock_code": "035720",
            "sll_buy_dvsn_cd": "02",
            "psbl_qty": 1,
        }
    ]

    assert await agent._broker_tracking_state_matches() is True


@pytest.mark.asyncio
async def test_broker_tracking_mismatch_blocks_processing():
    agent = _make_agent()
    _BrokerContext.portfolio = [{"stock_code": "035720", "quantity": 2}]

    assert await agent._broker_tracking_state_matches() is False


@pytest.mark.asyncio
async def test_failed_broker_query_blocks_processing():
    agent = _make_agent()
    _BrokerContext.portfolio_ok = False

    assert await agent._broker_tracking_state_matches() is False
