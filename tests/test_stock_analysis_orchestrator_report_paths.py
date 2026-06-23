import sys
import types

import pytest

import stock_analysis_orchestrator as orchestrator_module
from stock_analysis_orchestrator import StockAnalysisOrchestrator


@pytest.mark.asyncio
async def test_generate_telegram_messages_uses_markdown_report_paths(tmp_path, monkeypatch):
    report_path = tmp_path / "005930_삼성전자_20260623_morning_gpt5.md"
    report_path.write_text("# 삼성전자\n\n본문", encoding="utf-8")

    captured = []

    class FakeTelegramSummaryGenerator:
        async def process_report(self, report_path_arg, output_dir, to_lang="ko"):
            captured.append((report_path_arg, output_dir, to_lang))
            (tmp_path / "005930_삼성전자_telegram.txt").write_text(
                "telegram message",
                encoding="utf-8",
            )

    fake_module = types.ModuleType("telegram_summary_agent")
    fake_module.TelegramSummaryGenerator = FakeTelegramSummaryGenerator
    monkeypatch.setitem(sys.modules, "telegram_summary_agent", fake_module)
    monkeypatch.setattr(orchestrator_module, "TELEGRAM_MSGS_DIR", tmp_path)

    orchestrator = StockAnalysisOrchestrator.__new__(StockAnalysisOrchestrator)

    message_paths = await orchestrator.generate_telegram_messages([str(report_path)], "ko")

    assert captured == [(str(report_path), str(tmp_path), "ko")]
    assert message_paths == [tmp_path / "005930_삼성전자_telegram.txt"]
