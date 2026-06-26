import sys
import types
from pathlib import Path

import pandas as pd
import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from stock_analysis_orchestrator import StockAnalysisOrchestrator


@pytest.mark.asyncio
async def test_run_trigger_batch_uses_stock_name_column(monkeypatch, tmp_path):
    fake_trigger_batch = types.ModuleType("trigger_batch")

    def fake_run_batch(mode, log_level, output_file, macro_context=None):
        return {
            "갭 상승 모멘텀 상위주": pd.DataFrame(
                {
                    "stock_name": ["원익IPS"],
                    "손익비": [3.0],
                },
                index=["240810"],
            )
        }

    fake_trigger_batch.run_batch = fake_run_batch
    monkeypatch.setitem(sys.modules, "trigger_batch", fake_trigger_batch)
    monkeypatch.chdir(tmp_path)

    orchestrator = StockAnalysisOrchestrator.__new__(StockAnalysisOrchestrator)
    orchestrator.selected_tickers = {}

    result = await StockAnalysisOrchestrator.run_trigger_batch(orchestrator, "morning")

    assert result == [
        {
            "code": "240810",
            "name": "원익IPS",
            "trigger_type": "갭 상승 모멘텀 상위주",
            "trigger_mode": "morning",
            "risk_reward_ratio": 3.0,
        }
    ]
