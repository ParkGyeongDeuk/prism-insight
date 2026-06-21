"""Helpers for optional MCP server credentials."""

from __future__ import annotations

import os
from pathlib import Path

import yaml


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PLACEHOLDERS = {
    "",
    "example key",
    "your-api-key",
    "your_api_key",
    "your perplexity api key",
}


def is_mcp_api_key_configured(
    server_name: str,
    env_name: str,
    config_path: str | Path | None = None,
) -> bool:
    """Return whether an optional MCP API key has a non-placeholder value."""
    env_value = os.getenv(env_name, "").strip()
    if env_value and env_value.lower() not in _PLACEHOLDERS:
        return True

    path = Path(config_path) if config_path else _PROJECT_ROOT / "mcp_agent.config.yaml"
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        value = (
            config.get("mcp", {})
            .get("servers", {})
            .get(server_name, {})
            .get("env", {})
            .get(env_name, "")
        )
    except (OSError, AttributeError, TypeError, yaml.YAMLError):
        return False

    normalized = str(value or "").strip().lower()
    return bool(normalized and normalized not in _PLACEHOLDERS)
