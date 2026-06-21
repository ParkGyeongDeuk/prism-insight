import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cores.agents.market_index_agents import create_market_index_analysis_agent
from cores.agents.mcp_availability import is_mcp_api_key_configured
from cores.agents.news_strategy_agents import create_news_analysis_agent


def _write_config(path: Path, value: str) -> None:
    path.write_text(
        "mcp:\n"
        "  servers:\n"
        "    perplexity:\n"
        "      env:\n"
        f"        PERPLEXITY_API_KEY: {value!r}\n",
        encoding="utf-8",
    )


class OptionalPerplexityTests(unittest.TestCase):
    def test_key_detection_rejects_blank_and_placeholder(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {},
            clear=False,
        ):
            os.environ.pop("PERPLEXITY_API_KEY", None)
            config_path = Path(temp_dir) / "mcp_agent.config.yaml"

            _write_config(config_path, "")
            self.assertFalse(
                is_mcp_api_key_configured("perplexity", "PERPLEXITY_API_KEY", config_path)
            )

            _write_config(config_path, "example key")
            self.assertFalse(
                is_mcp_api_key_configured("perplexity", "PERPLEXITY_API_KEY", config_path)
            )

    def test_key_detection_accepts_yaml_or_environment(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "mcp_agent.config.yaml"
            _write_config(config_path, "pplx-configured")
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("PERPLEXITY_API_KEY", None)
                self.assertTrue(
                    is_mcp_api_key_configured("perplexity", "PERPLEXITY_API_KEY", config_path)
                )

            _write_config(config_path, "")
            with patch.dict(
                os.environ,
                {"PERPLEXITY_API_KEY": "pplx-from-environment"},
                clear=False,
            ):
                self.assertTrue(
                    is_mcp_api_key_configured("perplexity", "PERPLEXITY_API_KEY", config_path)
                )

    def test_news_agent_uses_firecrawl_only_without_perplexity(self):
        agent = create_news_analysis_agent(
            "삼성전자",
            "005930",
            "20260621",
            use_perplexity=False,
        )

        self.assertEqual(agent.server_names, ["firecrawl"])
        self.assertIn("Perplexity가 설정되지 않았으므로", agent.instruction)

    def test_market_agent_uses_prefetched_data_without_mcp_server(self):
        agent = create_market_index_analysis_agent(
            "20260621",
            "20250621",
            1,
            prefetched_kospi="KOSPI data",
            prefetched_kosdaq="KOSDAQ data",
            use_perplexity=False,
        )

        self.assertEqual(agent.server_names, [])
        self.assertIn("Perplexity가 설정되지 않았으므로", agent.instruction)

    def test_configured_perplexity_preserves_existing_server_lists(self):
        news_agent = create_news_analysis_agent(
            "Samsung Electronics",
            "005930",
            "20260621",
            language="en",
            use_perplexity=True,
        )
        market_agent = create_market_index_analysis_agent(
            "20260621",
            "20250621",
            1,
            language="en",
            prefetched_kospi="KOSPI data",
            prefetched_kosdaq="KOSDAQ data",
            use_perplexity=True,
        )

        self.assertEqual(news_agent.server_names, ["perplexity", "firecrawl"])
        self.assertEqual(market_agent.server_names, ["perplexity"])


if __name__ == "__main__":
    unittest.main()
