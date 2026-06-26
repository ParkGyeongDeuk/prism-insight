import sys
import types
from types import SimpleNamespace

import pytest

from stock_analysis_orchestrator import StockAnalysisOrchestrator


class FakeTelegramBotAgent:
    instances = []

    def __init__(self):
        self.processed = []
        self.documents = []
        FakeTelegramBotAgent.instances.append(self)

    async def process_messages_directory(self, messages_dir, chat_id, sent_dir, msg_type="analysis"):
        self.processed.append((messages_dir, chat_id, sent_dir, msg_type))

    async def send_document(self, chat_id, document_path, msg_type="pdf"):
        self.documents.append((chat_id, document_path, msg_type))
        return True


def _install_fake_telegram_bot(monkeypatch):
    FakeTelegramBotAgent.instances = []
    fake_module = types.ModuleType("telegram_bot_agent")
    fake_module.TelegramBotAgent = FakeTelegramBotAgent
    monkeypatch.setitem(sys.modules, "telegram_bot_agent", fake_module)


def _orchestrator(broadcast_languages=None):
    orchestrator = StockAnalysisOrchestrator.__new__(StockAnalysisOrchestrator)
    orchestrator.telegram_config = SimpleNamespace(
        use_telegram=True,
        channel_id="telegram-channel",
        broadcast_languages=broadcast_languages or [],
    )
    orchestrator._broadcast_tasks = []
    return orchestrator


@pytest.mark.asyncio
async def test_convert_to_pdf_skips_converter_when_generation_disabled(monkeypatch):
    monkeypatch.setenv("PRISM_GENERATE_PDF_REPORTS", "false")
    monkeypatch.setitem(sys.modules, "pdf_converter", None)

    pdf_paths = await _orchestrator().convert_to_pdf(["reports/005930_삼성전자.md"])

    assert pdf_paths == []


@pytest.mark.asyncio
async def test_send_telegram_messages_skips_pdf_documents_when_disabled(monkeypatch):
    _install_fake_telegram_bot(monkeypatch)
    monkeypatch.setenv("PRISM_SEND_PDF_REPORTS", "false")

    await _orchestrator().send_telegram_messages(
        message_paths=["telegram_messages/005930_삼성전자_telegram.txt"],
        pdf_paths=["pdf_reports/005930_삼성전자.pdf"],
        report_paths=["reports/005930_삼성전자.md"],
    )

    bot_agent = FakeTelegramBotAgent.instances[0]

    assert len(bot_agent.processed) == 1
    assert bot_agent.documents == []


@pytest.mark.asyncio
async def test_send_telegram_messages_does_not_schedule_translated_pdfs_without_generation(monkeypatch):
    _install_fake_telegram_bot(monkeypatch)
    monkeypatch.setenv("PRISM_GENERATE_PDF_REPORTS", "false")
    monkeypatch.setenv("PRISM_SEND_PDF_REPORTS", "true")

    orchestrator = _orchestrator(broadcast_languages=["en"])

    await orchestrator.send_telegram_messages(
        message_paths=["telegram_messages/005930_삼성전자_telegram.txt"],
        pdf_paths=[],
        report_paths=["reports/005930_삼성전자.md"],
    )

    assert orchestrator._broadcast_tasks == []


@pytest.mark.asyncio
async def test_send_telegram_messages_sends_pdf_documents_by_default(monkeypatch):
    _install_fake_telegram_bot(monkeypatch)
    monkeypatch.delenv("PRISM_SEND_PDF_REPORTS", raising=False)

    await _orchestrator().send_telegram_messages(
        message_paths=["telegram_messages/005930_삼성전자_telegram.txt"],
        pdf_paths=["pdf_reports/005930_삼성전자.pdf"],
        report_paths=["reports/005930_삼성전자.md"],
    )

    bot_agent = FakeTelegramBotAgent.instances[0]

    assert len(bot_agent.processed) == 1
    assert bot_agent.documents == [
        ("telegram-channel", "pdf_reports/005930_삼성전자.pdf", "pdf")
    ]
