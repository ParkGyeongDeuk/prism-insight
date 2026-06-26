import logging
import sqlite3
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import trading.domestic_stock_trading as domestic_trading
from stock_tracking_enhanced_agent import EnhancedStockTrackingAgent
from stock_tracking_agent import StockTrackingAgent


class _FakeAsyncTradingContext:
    def __init__(self, account_name=None, **kwargs):
        self.account_name = account_name

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def async_buy_stock(self, stock_code, limit_price=None):
        return {
            "success": True,
            "message": f"bought for {self.account_name}",
            "partial_success": self.account_name == "kr-primary",
            "successful_accounts": ["kr-primary"],
            "failed_accounts": ["kr-secondary"],
        }

    async def async_sell_stock(self, stock_code, limit_price=None, quantity=None):
        return {
            "success": True,
            "message": f"sold for {self.account_name}",
        }


class _FailingAsyncTradingContext(_FakeAsyncTradingContext):
    async def async_buy_stock(self, stock_code, limit_price=None):
        return {
            "success": False,
            "message": "broker rejected order",
        }


class _FailingSellAsyncTradingContext(_FakeAsyncTradingContext):
    async def async_sell_stock(self, stock_code, limit_price=None, quantity=None):
        return {
            "success": False,
            "message": "broker rejected sell",
        }


class _FilledBuyAsyncTradingContext(_FakeAsyncTradingContext):
    async def async_buy_stock(self, stock_code, limit_price=None):
        return {
            "success": True,
            "message": "Buy completed",
            "current_price": 169100,
            "avg_price": 168450,
            "stock_name": "원익IPS",
            "quantity": 1,
            "total_amount": 168450,
        }


def _install_signal_modules(monkeypatch, redis_calls, gcp_calls):
    redis_module = types.ModuleType("messaging.redis_signal_publisher")
    gcp_module = types.ModuleType("messaging.gcp_pubsub_signal_publisher")

    async def publish_buy_signal(**kwargs):
        redis_calls.append(kwargs)

    async def publish_sell_signal(**kwargs):
        redis_calls.append(kwargs)

    async def gcp_publish_buy_signal(**kwargs):
        gcp_calls.append(kwargs)

    async def gcp_publish_sell_signal(**kwargs):
        gcp_calls.append(kwargs)

    redis_module.publish_buy_signal = publish_buy_signal
    redis_module.publish_sell_signal = publish_sell_signal
    gcp_module.publish_buy_signal = gcp_publish_buy_signal
    gcp_module.publish_sell_signal = gcp_publish_sell_signal

    monkeypatch.setitem(sys.modules, "messaging.redis_signal_publisher", redis_module)
    monkeypatch.setitem(sys.modules, "messaging.gcp_pubsub_signal_publisher", gcp_module)


def _install_corporate_status_stub(monkeypatch):
    corporate_module = types.ModuleType("cores.corporate_status")

    async def fetch_status_codes(tickers, account_name=None):
        return {}

    corporate_module.fetch_status_codes = fetch_status_codes
    monkeypatch.setitem(sys.modules, "cores.corporate_status", corporate_module)


@pytest.mark.asyncio
async def test_process_reports_analyzes_once_and_dedupes_signals(monkeypatch, caplog):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.account_configs = [
        {"name": "kr-primary", "account_key": "vps:kr-primary:01"},
        {"name": "kr-secondary", "account_key": "vps:kr-secondary:01"},
    ]
    agent.active_account = None
    agent.max_slots = 10

    core_calls = []
    holdings_checks = []
    slot_checks = []
    sector_checks = []
    buy_calls = []
    redis_calls = []
    gcp_calls = []

    async def fake_core(report_path):
        core_calls.append(report_path)
        return {
            "success": True,
            "ticker": "005930",
            "company_name": "Samsung Electronics",
            "current_price": 70000,
            "scenario": {"buy_score": 8, "min_score": 7, "sector": "Technology"},
            "decision": "Enter",
            "sector": "Technology",
            "rank_change_msg": "Up",
            "rank_change_percentage": 12.0,
        }

    async def fake_update_holdings():
        return []

    async def fake_is_ticker_in_holdings(ticker):
        holdings_checks.append((agent.active_account["name"], ticker))
        return False

    async def fake_get_current_slots_count():
        slot_checks.append(agent.active_account["name"])
        return 0

    async def fake_check_sector_diversity(sector):
        sector_checks.append((agent.active_account["name"], sector))
        return True

    async def fake_buy_stock(
        ticker, company_name, current_price, scenario, rank_change_msg, persist=True
    ):
        buy_calls.append((agent.active_account["name"], ticker, persist))
        return True

    async def fake_broker_tracking_state_matches(account):
        return True

    agent._analyze_report_core = fake_core
    agent.update_holdings = fake_update_holdings
    agent._is_ticker_in_holdings = fake_is_ticker_in_holdings
    agent._get_current_slots_count = fake_get_current_slots_count
    agent._check_sector_diversity = fake_check_sector_diversity
    agent.buy_stock = fake_buy_stock
    agent._broker_tracking_state_matches = fake_broker_tracking_state_matches

    monkeypatch.setattr(domestic_trading, "AsyncTradingContext", _FakeAsyncTradingContext)
    _install_signal_modules(monkeypatch, redis_calls, gcp_calls)

    caplog.set_level(logging.WARNING)

    buy_count, sell_count = await StockTrackingAgent.process_reports(agent, ["report-a.pdf"])

    assert buy_count == 2
    assert sell_count == 0
    assert core_calls == ["report-a.pdf"]
    assert holdings_checks == [("kr-primary", "005930"), ("kr-secondary", "005930")]
    assert slot_checks == ["kr-primary", "kr-secondary"]
    assert sector_checks == [("kr-primary", "Technology"), ("kr-secondary", "Technology")]
    assert buy_calls == [
        ("kr-primary", "005930", False),
        ("kr-primary", "005930", True),
        ("kr-secondary", "005930", False),
        ("kr-secondary", "005930", True),
    ]
    assert len(redis_calls) == 1
    assert len(gcp_calls) == 1
    assert "partial success" in caplog.text.lower()


@pytest.mark.asyncio
async def test_process_reports_does_not_persist_when_broker_buy_fails(monkeypatch):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.account_configs = [
        {"name": "kr-primary", "account_key": "vps:kr-primary:01"},
    ]
    agent.active_account = None
    agent.max_slots = 5
    persist_calls = []
    watchlist_calls = []

    async def fake_core(_report_path):
        return {
            "success": True,
            "ticker": "005930",
            "company_name": "Samsung Electronics",
            "current_price": 70000,
            "scenario": {"buy_score": 8, "min_score": 7, "sector": "Technology"},
            "decision": "Enter",
            "sector": "Technology",
            "rank_change_msg": "Up",
        }

    async def fake_true(*_args, **_kwargs):
        return True

    async def fake_zero_slots():
        return 0

    async def fake_no_sales():
        return []

    async def fake_buy_stock(
        ticker, company_name, current_price, scenario, rank_change_msg, persist=True
    ):
        persist_calls.append(persist)
        return True

    async def fake_save_watchlist_item(**kwargs):
        watchlist_calls.append(kwargs)
        return True

    agent._analyze_report_core = fake_core
    agent._broker_tracking_state_matches = fake_true
    agent.update_holdings = fake_no_sales

    async def fake_not_holding(_ticker):
        return False

    agent._is_ticker_in_holdings = fake_not_holding
    agent._get_current_slots_count = fake_zero_slots
    agent._check_sector_diversity = fake_true
    agent.buy_stock = fake_buy_stock
    agent._save_watchlist_item = fake_save_watchlist_item

    monkeypatch.setattr(domestic_trading, "AsyncTradingContext", _FailingAsyncTradingContext)

    buy_count, sell_count = await StockTrackingAgent.process_reports(agent, ["report.pdf"])

    assert (buy_count, sell_count) == (0, 0)
    assert persist_calls == [False]
    assert len(watchlist_calls) == 1
    assert watchlist_calls[0]["was_traded"] is False


@pytest.mark.asyncio
async def test_enhanced_process_does_not_persist_when_broker_buy_fails(monkeypatch):
    agent = EnhancedStockTrackingAgent.__new__(EnhancedStockTrackingAgent)
    agent.active_account = {
        "name": "kr-primary",
        "account_key": "vps:kr-primary:01",
    }
    persist_calls = []

    async def fake_true(*_args, **_kwargs):
        return True

    async def fake_no_sales():
        return []

    async def fake_analysis(_report_path):
        return {
            "success": True,
            "ticker": "005930",
            "company_name": "Samsung Electronics",
            "current_price": 70000,
            "scenario": {
                "buy_score": 8,
                "min_score": 7,
                "sector": "Technology",
                "rationale": "test",
            },
            "decision": "Enter",
            "sector": "Technology",
            "sector_diverse": True,
            "rank_change_msg": "Up",
        }

    async def fake_buy_stock(
        ticker,
        company_name,
        current_price,
        scenario,
        rank_change_msg,
        is_add=False,
        persist=True,
    ):
        persist_calls.append(persist)
        return True

    agent._broker_tracking_state_matches = fake_true
    agent.update_holdings = fake_no_sales
    agent.analyze_report = fake_analysis
    agent.buy_stock = fake_buy_stock

    monkeypatch.setattr(domestic_trading, "AsyncTradingContext", _FailingAsyncTradingContext)

    buy_count, sell_count = await EnhancedStockTrackingAgent.process_reports(
        agent, ["report.pdf"]
    )

    assert (buy_count, sell_count) == (0, 0)
    assert persist_calls == [False]


@pytest.mark.asyncio
async def test_enhanced_process_persists_broker_fill_price_and_name(monkeypatch):
    agent = EnhancedStockTrackingAgent.__new__(EnhancedStockTrackingAgent)
    agent.active_account = {
        "name": "kr-primary",
        "account_key": "vps:kr-primary:01",
    }
    buy_calls = []
    redis_calls = []
    gcp_calls = []

    async def fake_true(*_args, **_kwargs):
        return True

    async def fake_no_sales():
        return []

    async def fake_analysis(_report_path):
        return {
            "success": True,
            "ticker": "240810",
            "company_name": "Stock",
            "current_price": 159400,
            "scenario": {
                "buy_score": 7,
                "min_score": 4,
                "sector": "기계·장비",
                "rationale": "test",
            },
            "decision": "Enter",
            "sector": "기계·장비",
            "sector_diverse": True,
            "rank_change_msg": "Up",
        }

    async def fake_buy_stock(
        ticker,
        company_name,
        current_price,
        scenario,
        rank_change_msg,
        is_add=False,
        persist=True,
    ):
        buy_calls.append(
            {
                "ticker": ticker,
                "company_name": company_name,
                "current_price": current_price,
                "persist": persist,
            }
        )
        return True

    agent._broker_tracking_state_matches = fake_true
    agent.update_holdings = fake_no_sales
    agent.analyze_report = fake_analysis
    agent.buy_stock = fake_buy_stock

    monkeypatch.setattr(domestic_trading, "AsyncTradingContext", _FilledBuyAsyncTradingContext)
    _install_signal_modules(monkeypatch, redis_calls, gcp_calls)

    buy_count, sell_count = await EnhancedStockTrackingAgent.process_reports(
        agent, ["report.md"]
    )

    assert (buy_count, sell_count) == (1, 0)
    assert buy_calls == [
        {
            "ticker": "240810",
            "company_name": "Stock",
            "current_price": 159400,
            "persist": False,
        },
        {
            "ticker": "240810",
            "company_name": "원익IPS",
            "current_price": 168450,
            "persist": True,
        },
    ]
    assert redis_calls[0]["company_name"] == "원익IPS"
    assert redis_calls[0]["price"] == 168450
    assert gcp_calls[0]["company_name"] == "원익IPS"
    assert gcp_calls[0]["price"] == 168450


@pytest.mark.asyncio
async def test_process_reports_returns_zero_for_empty_accounts(caplog):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.account_configs = []
    agent.active_account = None
    agent.max_slots = 10

    caplog.set_level(logging.WARNING)

    buy_count, sell_count = await StockTrackingAgent.process_reports(agent, ["report-a.pdf"])

    assert (buy_count, sell_count) == (0, 0)
    assert "no accounts configured" in caplog.text.lower()


@pytest.mark.asyncio
async def test_analyze_report_core_fails_on_llm_analysis_error(tmp_path):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    report_path = tmp_path / "005930_Samsung_20260625_morning_gpt5.md"
    report_path.write_text("# report", encoding="utf-8")

    async def fake_extract_ticker_info(_report_path):
        return "005930", "Samsung"

    async def fake_get_current_stock_price(_ticker):
        return 70000

    async def fake_rank(_ticker):
        return 0, "Flat"

    async def fake_scenario(*args, **kwargs):
        return {
            "decision": "No Entry",
            "_analysis_error": "trading_scenario_llm_failed",
        }

    agent._extract_ticker_info = fake_extract_ticker_info
    agent._get_current_stock_price = fake_get_current_stock_price
    agent._get_trading_value_rank_change = fake_rank
    agent._extract_trading_scenario = fake_scenario
    agent.trigger_info_map = {}

    result = await StockTrackingAgent._analyze_report_core(agent, str(report_path))

    assert result["success"] is False
    assert result["error"] == "trading_scenario_llm_failed"


@pytest.mark.asyncio
async def test_process_reports_does_not_save_watchlist_when_analysis_fails(monkeypatch):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.account_configs = [
        {"name": "kr-primary", "account_key": "vps:kr-primary:01"},
    ]
    agent.active_account = None
    agent.max_slots = 10
    watchlist_calls = []

    async def fake_core(_report_path):
        return {
            "success": False,
            "error": "trading_scenario_llm_failed",
            "ticker": "005930",
            "company_name": "Samsung",
        }

    async def fake_update_holdings():
        return []

    async def fake_save_watchlist_item(**kwargs):
        watchlist_calls.append(kwargs)
        return True

    async def fake_broker_tracking_state_matches(account):
        return True

    agent._analyze_report_core = fake_core
    agent.update_holdings = fake_update_holdings
    agent._save_watchlist_item = fake_save_watchlist_item
    agent._broker_tracking_state_matches = fake_broker_tracking_state_matches

    buy_count, sell_count = await StockTrackingAgent.process_reports(agent, ["report-a.pdf"])

    assert (buy_count, sell_count) == (0, 0)
    assert watchlist_calls == []


@pytest.mark.asyncio
async def test_process_reports_saves_watchlist_once_when_not_traded(monkeypatch):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.account_configs = [
        {"name": "kr-primary", "account_key": "vps:kr-primary:01"},
        {"name": "kr-secondary", "account_key": "vps:kr-secondary:01"},
    ]
    agent.active_account = None
    agent.max_slots = 10

    watchlist_calls = []

    async def fake_core(report_path):
        return {
            "success": True,
            "ticker": "005930",
            "company_name": "Samsung Electronics",
            "current_price": 70000,
            "scenario": {"buy_score": 6, "min_score": 7, "sector": "Technology"},
            "decision": "Skip",
            "sector": "Technology",
            "rank_change_msg": "Flat",
        }

    async def fake_update_holdings():
        return []

    async def fake_is_ticker_in_holdings(ticker):
        return False

    async def fake_get_current_slots_count():
        return 0

    async def fake_check_sector_diversity(sector):
        return True

    async def fake_buy_stock(*args, **kwargs):
        raise AssertionError("buy_stock should not be called for non-entry decisions")

    async def fake_save_watchlist_item(**kwargs):
        watchlist_calls.append(kwargs)
        return True

    async def fake_broker_tracking_state_matches(account):
        return True

    agent._analyze_report_core = fake_core
    agent.update_holdings = fake_update_holdings
    agent._is_ticker_in_holdings = fake_is_ticker_in_holdings
    agent._get_current_slots_count = fake_get_current_slots_count
    agent._check_sector_diversity = fake_check_sector_diversity
    agent.buy_stock = fake_buy_stock
    agent._save_watchlist_item = fake_save_watchlist_item
    agent._broker_tracking_state_matches = fake_broker_tracking_state_matches

    buy_count, sell_count = await StockTrackingAgent.process_reports(agent, ["report-a.pdf"])

    assert (buy_count, sell_count) == (0, 0)
    assert len(watchlist_calls) == 1
    assert watchlist_calls[0]["ticker"] == "005930"
    assert watchlist_calls[0]["decision"] == "Skip"


@pytest.mark.asyncio
async def test_update_holdings_masks_sold_account_payload(monkeypatch):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.conn = sqlite3.connect(":memory:")
    agent.conn.row_factory = sqlite3.Row
    agent.cursor = agent.conn.cursor()
    agent.cursor.execute(
        """
        CREATE TABLE stock_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            company_name TEXT,
            buy_price REAL,
            buy_date TEXT,
            current_price REAL,
            scenario TEXT,
            target_price REAL,
            stop_loss REAL,
            last_updated TEXT,
            trigger_type TEXT,
            trigger_mode TEXT,
            account_key TEXT,
            account_name TEXT,
            sector TEXT
        )
        """
    )
    agent.cursor.execute(
        """
        INSERT INTO stock_holdings
        (ticker, company_name, buy_price, buy_date, current_price, scenario, target_price,
         stop_loss, last_updated, trigger_type, trigger_mode, account_key, account_name, sector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "005930",
            "Samsung Electronics",
            70000,
            "2026-03-01 09:00:00",
            71000,
            "{}",
            None,
            None,
            "2026-03-01 09:00:00",
            "AI Analysis",
            "morning",
            "vps:12345678:01",
            "kr-primary",
            "Technology",
        ),
    )
    agent.conn.commit()
    agent.active_account = {"name": "kr-primary", "account_key": "vps:12345678:01"}
    agent.message_queue = []
    agent._msg_types = []
    agent._get_live_regime_safe = lambda: None

    async def fake_get_current_stock_price(ticker):
        return 72000

    async def fake_analyze_sell_decision(stock):
        return True, "Take profit"

    async def fake_sell_stock(stock, reason):
        return True

    agent._get_current_stock_price = fake_get_current_stock_price
    agent._analyze_sell_decision = fake_analyze_sell_decision
    agent.sell_stock = fake_sell_stock

    redis_calls = []
    gcp_calls = []
    monkeypatch.setattr(domestic_trading, "AsyncTradingContext", _FakeAsyncTradingContext)
    _install_corporate_status_stub(monkeypatch)
    _install_signal_modules(monkeypatch, redis_calls, gcp_calls)

    sold = await StockTrackingAgent.update_holdings(agent)

    assert len(sold) == 1
    assert sold[0]["account_label"] == "kr-primary (vps:12****78:01)"
    assert "account_key" not in sold[0]


@pytest.mark.asyncio
async def test_update_holdings_keeps_tracking_row_when_broker_sell_fails(monkeypatch):
    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    agent.conn = sqlite3.connect(":memory:")
    agent.conn.row_factory = sqlite3.Row
    agent.cursor = agent.conn.cursor()
    agent.cursor.execute(
        """
        CREATE TABLE stock_holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            company_name TEXT,
            buy_price REAL,
            buy_date TEXT,
            current_price REAL,
            scenario TEXT,
            target_price REAL,
            stop_loss REAL,
            last_updated TEXT,
            trigger_type TEXT,
            trigger_mode TEXT,
            account_key TEXT,
            account_name TEXT,
            sector TEXT
        )
        """
    )
    agent.cursor.execute(
        """
        CREATE TABLE trading_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_key TEXT,
            account_name TEXT,
            ticker TEXT,
            company_name TEXT,
            buy_price REAL,
            buy_date TEXT,
            sell_price REAL,
            sell_date TEXT,
            profit_rate REAL,
            holding_days INTEGER,
            scenario TEXT,
            trigger_type TEXT,
            trigger_mode TEXT,
            sector TEXT
        )
        """
    )
    agent.cursor.execute(
        """
        INSERT INTO stock_holdings
        (ticker, company_name, buy_price, buy_date, current_price, scenario, target_price,
         stop_loss, last_updated, trigger_type, trigger_mode, account_key, account_name, sector)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "006340",
            "Daewon Cable",
            10580,
            "2026-06-23 16:14:47",
            10220,
            "{}",
            None,
            10000,
            "2026-06-25 12:00:00",
            "AI Analysis",
            "morning",
            "vps:12345678:01",
            "kr-primary",
            "Electrical",
        ),
    )
    agent.conn.commit()
    agent.active_account = {"name": "kr-primary", "account_key": "vps:12345678:01"}
    agent.message_queue = []
    agent._msg_types = []
    agent._get_live_regime_safe = lambda: None
    sell_stock_called = False

    async def fake_get_current_stock_price(ticker):
        return 9900

    async def fake_analyze_sell_decision(stock):
        return True, "Stop loss"

    async def fake_sell_stock(stock, reason):
        nonlocal sell_stock_called
        sell_stock_called = True
        return True

    agent._get_current_stock_price = fake_get_current_stock_price
    agent._analyze_sell_decision = fake_analyze_sell_decision
    agent.sell_stock = fake_sell_stock

    monkeypatch.setattr(domestic_trading, "AsyncTradingContext", _FailingSellAsyncTradingContext)
    _install_corporate_status_stub(monkeypatch)

    sold = await StockTrackingAgent.update_holdings(agent)

    holdings = agent.cursor.execute("SELECT ticker, current_price FROM stock_holdings").fetchall()
    history = agent.cursor.execute("SELECT ticker FROM trading_history").fetchall()

    assert sold == []
    assert sell_stock_called is False
    assert [dict(row) for row in holdings] == [{"ticker": "006340", "current_price": 9900.0}]
    assert history == []


def test_safe_account_log_label_masks_account_key():
    label = StockTrackingAgent._safe_account_log_label(
        {"name": "kr-primary", "account_key": "vps:12345678:01"}
    )

    assert label == "kr-primary (vps:12****78:01)"
