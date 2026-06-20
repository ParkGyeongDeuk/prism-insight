from cores.chatgpt_proxy.constants import _resolve_callback_host


def test_callback_host_defaults_to_loopback(monkeypatch):
    monkeypatch.delenv("PRISM_OAUTH_CALLBACK_HOST", raising=False)

    assert _resolve_callback_host() == "127.0.0.1"


def test_callback_host_can_bind_for_docker(monkeypatch):
    monkeypatch.setenv("PRISM_OAUTH_CALLBACK_HOST", "0.0.0.0")

    assert _resolve_callback_host() == "0.0.0.0"


def test_callback_host_ignores_blank_override(monkeypatch):
    monkeypatch.setenv("PRISM_OAUTH_CALLBACK_HOST", "   ")

    assert _resolve_callback_host() == "127.0.0.1"
