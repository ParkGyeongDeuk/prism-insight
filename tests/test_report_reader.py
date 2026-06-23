from pathlib import Path

import pytest

from cores.report_reader import read_report_text_for_llm, sanitize_report_markdown


def test_sanitize_report_markdown_removes_base64_images_and_keeps_text_tables():
    raw = """# Report

| 항목 | 값 |
| --- | --- |
| 매출 | 100 |

<img src="data:image/jpeg;base64,AAA111==" alt="chart">

![price](data:image/png;base64,BBB222==)

![keep](charts/price.png)

[link](https://example.com)
"""

    sanitized = sanitize_report_markdown(raw)

    assert "data:image" not in sanitized
    assert "<img" not in sanitized
    assert "| 매출 | 100 |" in sanitized
    assert "![keep](charts/price.png)" in sanitized
    assert "[link](https://example.com)" in sanitized


def test_read_report_text_for_llm_reads_markdown_without_pdf_extraction(tmp_path, monkeypatch):
    report_path = tmp_path / "005930_삼성전자_20260623_morning_gpt5.md"
    report_path.write_text(
        "# 삼성전자\n\n본문\n\n<img src=\"data:image/jpeg;base64,AAA=\">",
        encoding="utf-8",
    )

    def fail_pdf_extraction(_path):
        raise AssertionError("PDF extraction should not be used for markdown input")

    monkeypatch.setattr("pdf_converter.pdf_to_markdown_text", fail_pdf_extraction)

    content = read_report_text_for_llm(report_path)

    assert "본문" in content
    assert "data:image" not in content


def test_read_report_text_for_llm_uses_pdf_fallback(monkeypatch):
    calls = []

    def fake_pdf_to_markdown_text(path):
        calls.append(Path(path).name)
        return "pdf text"

    monkeypatch.setattr("pdf_converter.pdf_to_markdown_text", fake_pdf_to_markdown_text)

    assert read_report_text_for_llm("005930_삼성전자.pdf") == "pdf text"
    assert calls == ["005930_삼성전자.pdf"]


@pytest.mark.asyncio
async def test_stock_tracking_analyze_report_core_uses_sanitized_markdown(tmp_path, monkeypatch):
    from stock_tracking_agent import StockTrackingAgent

    report_path = tmp_path / "005930_삼성전자_20260623_morning_gpt5.md"
    report_path.write_text(
        "# 삼성전자\n\n투자 의견 본문\n\n![chart](data:image/png;base64,AAA=)",
        encoding="utf-8",
    )

    def fail_pdf_extraction(_path):
        raise AssertionError("PDF extraction should not be used for markdown input")

    monkeypatch.setattr("pdf_converter.pdf_to_markdown_text", fail_pdf_extraction)

    agent = StockTrackingAgent.__new__(StockTrackingAgent)
    captured = {}

    async def fake_price(_ticker):
        return 70000

    async def fake_rank(_ticker):
        return 0.0, "flat"

    async def fake_scenario(report_content, rank_change_msg, **kwargs):
        captured["report_content"] = report_content
        captured["rank_change_msg"] = rank_change_msg
        captured["kwargs"] = kwargs
        return {
            "decision": "No entry",
            "sector": "Technology",
            "buy_score": 6,
            "min_score": 7,
        }

    agent._get_current_stock_price = fake_price
    agent._get_trading_value_rank_change = fake_rank
    agent._extract_trading_scenario = fake_scenario
    agent.trigger_info_map = {}

    result = await StockTrackingAgent._analyze_report_core(agent, str(report_path))

    assert result["success"] is True
    assert result["ticker"] == "005930"
    assert "투자 의견 본문" in captured["report_content"]
    assert "data:image" not in captured["report_content"]


@pytest.mark.asyncio
async def test_telegram_summary_process_report_uses_sanitized_markdown(tmp_path, monkeypatch):
    from telegram_summary_agent import TelegramSummaryGenerator

    report_path = tmp_path / "005930_삼성전자_20260623_morning_gpt5.md"
    report_path.write_text(
        "# 삼성전자\n\n요약 대상 본문\n\n<img src=\"data:image/jpeg;base64,AAA=\">",
        encoding="utf-8",
    )

    def fail_pdf_extraction(_path):
        raise AssertionError("PDF extraction should not be used for markdown input")

    monkeypatch.setattr("pdf_converter.pdf_to_markdown_text", fail_pdf_extraction)

    generator = TelegramSummaryGenerator()
    captured = {}

    def fake_trigger(_ticker, _date):
        return "AI Analysis", "morning"

    async def fake_generate(report_content, metadata, trigger_type, from_lang, to_lang):
        captured["report_content"] = report_content
        captured["metadata"] = metadata
        captured["trigger_type"] = trigger_type
        return "telegram message"

    generator.determine_trigger_type = fake_trigger
    generator.generate_telegram_message = fake_generate

    message = await generator.process_report(str(report_path), str(tmp_path))

    assert message == "telegram message"
    assert "요약 대상 본문" in captured["report_content"]
    assert "data:image" not in captured["report_content"]
    assert captured["metadata"]["stock_code"] == "005930"
